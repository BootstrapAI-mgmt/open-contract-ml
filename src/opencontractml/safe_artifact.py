"""The single chokepoint through which this pipeline reads a model bundle.

The model gate used to call ``pickle.load`` on ``model_bundle.pkl`` directly.
Pickle is not a data format -- it is a little stack language, and its ``REDUCE``
opcode calls whatever callable the byte stream names.  So "validate someone
else's model bundle" was a remote code execution primitive: a bundle whose
``__reduce__`` names ``os.system`` runs a shell the moment the gate opens it,
before a single check has been evaluated.

Policy -- safe artifact format
------------------------------

The policy: serving runs on numpy/ONNX, sklearn estimators go to ``skops``, and an
untrusted pickle is never loaded.  This module implements the third clause today
and clears the path to the second.  There are three tiers, and only the first is
reachable by default:

1. **restricted** (default) -- the bundle is unpickled through
   :class:`_RestrictedUnpickler`, which resolves only globals in a closed
   allow-list.  ``os.system``, ``subprocess.Popen``, ``builtins.eval`` and
   every other execution primitive is outside it, so a hostile stream fails to
   *resolve* its payload rather than succeeding in calling it.
2. **digest-pinned** -- an unrestricted ``pickle.load`` for a bundle whose exact
   bytes the caller names via ``trust_sha256``.  Loud on stderr and on the
   warnings channel.
3. **refused** -- everything else.

What tier 1 is and is not
-------------------------

Restricted unpickling is a **hardening layer, not a proof**.  It reliably kills
the standard payload class, which needs to name a callable that the allow-list
does not contain.  It cannot prove that no reachable gadget exists *inside*
numpy/scipy/sklearn.  The only airtight answer is to stop putting estimators in
pickles at all -- ``skops`` for the sklearn objects, ``.npz``/ONNX for anything
that is really just arrays.  This module is what makes the existing corpus of
``.pkl`` bundles safe enough to keep working while that migration happens; it is
not a reason to skip the migration.

:func:`inspect_globals` is the audit primitive behind that claim: it reports
every global a pickle *names* using ``pickletools``, which only parses opcodes
and never executes them.  That is how the gate can describe a bundle it has
refused.
"""

from __future__ import annotations

import hashlib
import io
import pickle
import pickletools
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PICKLE_SUFFIXES = (".pkl", ".pickle")


class UntrustedArtifactError(RuntimeError):
    """A bundle was refused, or named a global outside the allow-list.

    Raised *instead of* completing the deserialization, which is the point: the
    refusal has to land before the offending opcode is interpreted.
    """


class UnsafePickleWarning(UserWarning):
    """Emitted when the digest-pinned escape hatch actually opens."""


# --------------------------------------------------------------------------- the allow-list
#
# A legitimate bundle from train_b1.py holds numpy arrays, plain containers, and
# five kinds of fitted sklearn estimator (HistGradientBoostingRegressor x the
# ensemble seeds, and Pipelines wrapping StandardScaler / Ridge /
# PolynomialFeatures / GaussianProcessRegressor / DummyRegressor).  Between them
# those drag in dozens of private sklearn and numpy reconstruction helpers, which
# is why this is a *module-prefix* allow-list rather than a class list: a class
# list would break on every sklearn point release, and a gate that breaks on
# upgrade gets switched off.
#
# The security property comes from the list being CLOSED.  Nothing in the
# standard library is reachable, so os/nt/posix/subprocess/importlib/ctypes/
# operator/functools -- every documented pickle RCE gadget -- cannot be named at
# all.  `builtins` is the one exception, and it is an exact-name subset with no
# callable that can run code.

_ALLOWED_MODULE_PREFIXES: Tuple[str, ...] = ("numpy", "scipy", "sklearn", "pandas")

#: sklearn's Cython loss extension module. Cython registers it under the
#: unqualified name ``_loss``, not ``sklearn._loss._loss``, so a fitted
#: HistGradientBoostingRegressor pickles a global whose module is bare ``_loss``
#: (confirmed by instrumenting find_class on a real bundle: it asks for
#: ``_loss.CyHalfSquaredError``).  An unqualified name is a hazard in its own
#: right -- ``find_class`` would import whatever ``_loss`` resolves to, so a
#: stray ``_loss.py`` on sys.path could impersonate it -- which is why
#: :func:`_is_sklearns_cython_loss` insists the module is already imported and
#: comes from inside sklearn rather than letting the import fire.
_CYTHON_LOSS_MODULE = "_loss"


def _is_sklearns_cython_loss(module: str) -> bool:
    if module != _CYTHON_LOSS_MODULE:
        return False
    mod = sys.modules.get(_CYTHON_LOSS_MODULE)
    if mod is None:
        return False                      # not already imported: do not trigger an import
    return "sklearn" in str(getattr(mod, "__file__", "")).replace("\\", "/")

#: denied even though their parent prefix is allowed: these wrap exec/subprocess
#: or arbitrary file IO, which is exactly the shape of a gadget.
_DENIED_MODULE_PREFIXES: Tuple[str, ...] = (
    "numpy.testing", "numpy.f2py", "numpy.distutils", "numpy.ctypeslib",
    "scipy.io", "scipy.weave",
    "sklearn.externals",
    "pandas.io", "pandas.compat",
)

#: data constructors only. Deliberately absent: eval, exec, compile, open,
#: __import__, getattr, setattr, globals, locals, input, breakpoint, memoryview,
#: staticmethod, classmethod, super, vars, dir, help, exit, quit.
_ALLOWED_BUILTINS: Set[str] = {
    "bool", "bytearray", "bytes", "complex", "dict", "float", "frozenset", "int",
    "list", "object", "set", "slice", "str", "tuple",
}

_ALLOWED_EXACT: Set[Tuple[str, str]] = {
    ("collections", "OrderedDict"),
    ("collections", "defaultdict"),
    ("copyreg", "_reconstructor"),      # the protocol-2 rebuild helper; constructs, never calls
    ("__builtin__", "object"),          # python 2-era streams name builtins this way
}


def _is_allowed(module: str, name: str) -> bool:
    if (module, name) in _ALLOWED_EXACT:
        return True
    if module in ("builtins", "__builtin__"):
        return name in _ALLOWED_BUILTINS
    if any(module == d or module.startswith(d + ".") for d in _DENIED_MODULE_PREFIXES):
        return False
    if _is_sklearns_cython_loss(module):
        return True
    return any(module == a or module.startswith(a + ".") for a in _ALLOWED_MODULE_PREFIXES)


class _RestrictedUnpickler(pickle.Unpickler):
    """An unpickler that resolves only allow-listed globals.

    ``find_class`` is the single funnel every ``GLOBAL``/``STACK_GLOBAL`` opcode
    passes through before ``REDUCE`` can call anything, so refusing here refuses
    before execution -- not after.
    """

    def find_class(self, module: str, name: str) -> Any:       # noqa: D102
        if not _is_allowed(module, name):
            raise UntrustedArtifactError(
                "refusing to reconstruct %s.%s while unpickling: it is not in the safe-load "
                "allow-list.\n"
                "A bundle written by train_b1.py names only numpy/scipy/sklearn reconstruction "
                "helpers and plain containers. A bundle that wants %s.%s is either built by "
                "something else or hostile -- pickle calls what it names, so this is refused "
                "before it runs.\n"
                "Audit what it asks for with safe_artifact.inspect_globals(path) (that only "
                "parses opcodes, it never executes them)." % (module, name, module, name)
            )
        return super().find_class(module, name)


# --------------------------------------------------------------------------- audit

def sha256_file(path: "str | Path") -> str:
    """Streaming SHA-256 of a file, as 64 lowercase hex characters."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_globals(path: "str | Path") -> List[Tuple[str, str]]:
    """Every ``(module, name)`` the pickle at *path* names, without executing it.

    ``pickletools.genops`` is a pure opcode parser -- it walks the stream and
    yields instructions.  Nothing is constructed and nothing is called, so this
    is safe to run on a bundle you do not trust, which is what makes it usable
    for reporting on one you have already refused.
    """
    raw = Path(path).read_bytes()
    found: Set[Tuple[str, str]] = set()
    recent: List[str] = []            # adjacency buffer: the strings STACK_GLOBAL will consume
    memo: Dict[Any, str] = {}
    memo_count = 0
    last: Optional[str] = None

    # Getting this right took two wrong versions, both worth recording because both
    # failure modes are traps:
    #
    #  1. tracking only "the last two string pushes" without clearing the buffer on
    #     other opcodes reported globals like `k1.Product` -- `k1` is a kernel
    #     *attribute* name that happened to be two slots down. Over-reporting.
    #  2. clearing correctly but ignoring the memo found 18 of 29 globals, because a
    #     module string like `sklearn.gaussian_process.kernels` is written once,
    #     memoized, and every later STACK_GLOBAL refers to it by memo index rather
    #     than pushing it again. UNDER-reporting, which for an audit tool is the
    #     dangerous direction -- it would have let `unsafe_globals()` answer "none"
    #     for a bundle that names something it should not.
    #
    # So memo gets have to be resolved. Verified against find_class on a real
    # bundle: the two sets are now identical (see tests/test_safe_artifact.py).
    for op, arg, _pos in pickletools.genops(raw):
        nm = op.name
        if nm in ("GLOBAL", "INST"):
            mod, _, gname = str(arg).partition(" ")
            found.add((mod, gname))
            recent.clear()
            last = None
        elif nm in ("SHORT_BINUNICODE", "BINUNICODE", "BINUNICODE8", "UNICODE",
                    "SHORT_BINSTRING", "BINSTRING", "STRING"):
            last = str(arg)
            recent.append(last)
        elif nm == "MEMOIZE":
            if last is not None:
                memo[memo_count] = last
            memo_count += 1
        elif nm in ("BINPUT", "LONG_BINPUT", "PUT"):
            if last is not None:
                memo[arg] = last
        elif nm in ("BINGET", "LONG_BINGET", "GET"):
            v = memo.get(arg)
            if isinstance(v, str):
                last = v
                recent.append(v)
            else:
                recent.clear()
                last = None
        elif nm == "STACK_GLOBAL":
            if len(recent) >= 2:
                found.add((recent[-2], recent[-1]))
            recent.clear()
            last = None
        elif nm == "FRAME":
            pass                      # framing directive: pushes nothing
        else:
            recent.clear()
            last = None
    return sorted(found)


def unsafe_globals(path: "str | Path") -> List[Tuple[str, str]]:
    """The subset of :func:`inspect_globals` that the allow-list would refuse."""
    return [(m, n) for m, n in inspect_globals(path) if not _is_allowed(m, n)]


# --------------------------------------------------------------------------- the escape hatch

def _normalize_pin(pin: Any) -> str:
    s = str(pin).strip().lower()
    if len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        raise UntrustedArtifactError(
            "trust_sha256 must be 64 hex characters (a SHA-256 digest); got %r. "
            "Compute it with safe_artifact.sha256_file(path)." % (pin,)
        )
    return s


def _pin_opens(path: Path, trust_sha256: Optional[str]) -> bool:
    """Whether the unrestricted-read hatch opens for *path*.

    The pin is deliberately not a boolean and not an environment variable.
    ``trusted=True`` and ``ALLOW_PICKLE=1`` are both write-once/trust-forever:
    whoever sets one stops thinking about it, and every later file arriving at
    that path inherits the exemption.  A digest pin expires the moment the bytes
    change, so a bundle swapped underneath a pinned call site fails closed.
    """
    if trust_sha256 is None:
        return False
    pin = _normalize_pin(trust_sha256)
    actual = sha256_file(path)
    if actual != pin:
        raise UntrustedArtifactError(
            "digest pin does not match: %s\n"
            "  pinned by caller : %s\n"
            "  actual on disk   : %s\n"
            "The file changed since the pin was written, or it is not the file you think it "
            "is. Refusing to unpickle it." % (path, pin, actual)
        )
    message = (
        "UNRESTRICTED PICKLE LOAD: %s (sha256 %s...%s) is being deserialized with the stock "
        "unpickler because the caller pinned its digest. Arbitrary code in this file will "
        "execute." % (path, pin[:12], pin[-6:])
    )
    warnings.warn(message, UnsafePickleWarning, stacklevel=3)
    print("safe_artifact: " + message, file=sys.stderr)
    return True


# --------------------------------------------------------------------------- the entry point

def load_bundle(path: "str | Path", trust_sha256: Optional[str] = None) -> Any:
    """Read a model bundle under the safe-load policy.

    ``.pkl``/``.pickle`` is read through the restricted unpickler.  Any other
    suffix is refused.  ``trust_sha256``, and only ``trust_sha256``, buys an
    unrestricted read of exactly the pinned bytes.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() not in PICKLE_SUFFIXES:
        raise UntrustedArtifactError(
            "refusing to load %s: suffix %r is not a recognised bundle format (expected one of %s)."
            % (path, path.suffix, ", ".join(PICKLE_SUFFIXES))
        )

    raw = path.read_bytes()
    if _pin_opens(path, trust_sha256):
        return pickle.loads(raw)                     # documented, digest-pinned, warned
    return _RestrictedUnpickler(io.BytesIO(raw)).load()


def describe(path: "str | Path") -> Dict[str, Any]:
    """A non-executing summary of a bundle, for the gate's report."""
    path = Path(path)
    bad = unsafe_globals(path)
    return {
        "path": str(path), "sha256": sha256_file(path), "size_bytes": path.stat().st_size,
        "globals_named": ["%s.%s" % g for g in inspect_globals(path)],
        "globals_refused": ["%s.%s" % g for g in bad],
        "loadable_under_policy": not bad,
    }


__all__ = [
    "UntrustedArtifactError", "UnsafePickleWarning", "PICKLE_SUFFIXES",
    "sha256_file", "inspect_globals", "unsafe_globals", "load_bundle", "describe",
]
