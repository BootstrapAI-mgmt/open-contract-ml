"""The single chokepoint through which every serialized artifact is read.

Nothing else in this package may call ``torch.load``, ``pickle.load`` or
``numpy.load(allow_pickle=True)``.  All three are arbitrary-code-execution
surfaces, because the pickle format underneath them is a little stack language
whose ``REDUCE`` opcode calls whatever callable the byte stream names.  Reading
a model from an untrusted ``.pt`` is therefore not distinguishable from running
it, and "load someone else's checkpoint" is a remote code execution primitive.

Policy -- safe artifact format
------------------------------

=============================  ===========================================
format                         how this module reads it
=============================  ===========================================
``.safetensors``               ``safetensors`` -- a length-prefixed tensor
                               blob plus a ``str -> str`` metadata map.
                               The format has no opcodes, so it has no
                               code path to hijack.
``.npz``                       ``numpy.load(allow_pickle=False)``
``.pt`` / ``.pth`` / ``.ckpt`` ``torch.load(weights_only=True)``
anything else                  refused
=============================  ===========================================

``weights_only=True`` is not a courtesy flag.  It replaces the stock unpickler
with one that resolves only an allow-list of globals, so a stream naming
``os.system`` fails to *resolve* rather than succeeding in calling it.

Checkpoints that store their ``kind``/``config``/``norm``/``extra`` as plain
scalars, lists and dicts need exactly one addition to that allow-list, and it
is worth saying why rather than hiding it.  A trainer that records its package
versions records ``torch.__version__``, and that is not a ``str``: it is a
``torch.torch_version.TorchVersion``, a ``str`` *subclass*, so it lands in the
stream as a custom global.  Disassembling the pickle streams of 17 real
checkpoints gives this complete set of globals::

    collections OrderedDict                torch FloatStorage
    torch._utils _rebuild_tensor_v2        torch.torch_version TorchVersion

The first three are in torch's defaults; ``TorchVersion`` is added by
:func:`_extra_safe_globals` below.  Reconstructing a ``TorchVersion`` can only
produce a string -- the class defines no ``__reduce__`` and no ``__setstate__``
of its own -- so allow-listing it adds no execution path.  The allow-list is
applied through the ``safe_globals`` *context manager*, scoped to the one call,
rather than ``add_safe_globals``, which would mutate torch's global state for
the rest of the process.

The escape hatch, and why it is shaped like this
-----------------------------------------------

A legacy artifact the restricted reader cannot parse may still be read
unrestricted, but only by naming its exact content digest at the call site::

    payload = safeload.load_checkpoint(p, trust_sha256="3f2a...")   # 64 hex

The pin is deliberately not a boolean and deliberately not an environment
variable.  ``trusted=True`` and ``ALLOW_PICKLE=1`` are both
write-once/trust-forever: whoever sets one stops thinking about it, and every
later file arriving at that path inherits the exemption.  A digest pin expires
the moment the bytes change, so an artifact swapped underneath a pinned call
site fails closed instead of executing.  **There is no environment-variable
bypass, and adding one would defeat the purpose.**

Migrating an artifact off pickle entirely: once its provenance is verified,
read it a single time under a digest pin with :func:`load_checkpoint` and write
the payload back with :func:`save_checkpoint`, which stores tensors as
safetensors and everything else as JSON metadata.

Its companion (``opencontractml.safe_artifact``) is the *pickle-bundle* loader.
The two are siblings, not copies: this one loads tensor checkpoints, that one
restricts ``pickle`` unpickling.  They share only ``sha256_file`` and the two
exception types.
"""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

SAFETENSORS_SUFFIX = ".safetensors"
TORCH_SUFFIXES = (".pt", ".pth", ".ckpt")

#: the keys under which checkpoints store their tensors: ``state_dict`` or
#: ``state``.
STATE_KEYS = ("state_dict", "state")

_METADATA_KEY = "__opencontractml__"
_FORMAT = "opencontractml-safetensors-1"


def _extra_safe_globals() -> list:
    """The one global first-party checkpoints need beyond torch's defaults.

    See the module docstring for the survey that establishes this list is
    complete and for why the entry cannot execute anything.
    """
    from torch.torch_version import TorchVersion

    return [TorchVersion]


def _blocked_global(exc: BaseException) -> str:
    """Pull the useful sentence out of torch's multi-paragraph refusal.

    torch buries the name of the rejected global six lines into a message that
    otherwise just explains how to disable the check, so a refusal that only
    quotes the first line tells an operator nothing about what was wrong.
    """
    lines = [ln.strip() for ln in str(exc).splitlines()]
    for i, line in enumerate(lines):
        if "Unsupported global" in line or "WeightsUnpickler error" in line:
            # torch sometimes leaves this line a bare "WeightsUnpickler error:" and
            # puts the detail on the next non-empty one, so returning it alone says
            # nothing -- which defeats the point of extracting it at all
            if line.endswith(":"):
                tail = next((x for x in lines[i + 1:] if x), "")
                return ("%s %s" % (line, tail)).strip()
            return line
    return next((x for x in lines if x), repr(exc))


class UntrustedArtifactError(RuntimeError):
    """An artifact was refused by the safe-load policy.

    Raised instead of deserializing, which is the whole point: the refusal has
    to happen before any opcode from the file is interpreted.
    """


class UnsafePickleWarning(UserWarning):
    """Emitted when the digest-pinned escape hatch actually opens."""


# --------------------------------------------------------------------------- digests

def is_safetensors(path: "str | Path") -> bool:
    """True when *path* names a safetensors artifact, by suffix.

    The suffix table lives here rather than in each caller
    so there is exactly one place that decides what a format is called.
    """
    return Path(str(path)).suffix.lower() == SAFETENSORS_SUFFIX


def sha256_file(path: "str | Path") -> str:
    """Streaming SHA-256 of a file, as 64 lowercase hex characters."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_pin(pin: Any) -> str:
    s = str(pin).strip().lower()
    if len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        raise UntrustedArtifactError(
            "trust_sha256 must be 64 hex characters (a SHA-256 digest); got %r. "
            "Compute it with opencontractml.safeload.sha256_file(path)." % (pin,)
        )
    return s


def _pin_opens(path: Path, trust_sha256: Optional[str]) -> bool:
    """Decide whether the escape hatch opens for *path*.

    Returns False when no pin was supplied.  Raises when a pin was supplied but
    is malformed or does not match the bytes on disk -- a stale pin is a louder
    signal than a missing one, so it must never silently degrade to a refusal
    message that looks like "unsupported format".
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
            "The file changed since the pin was written, or this is not the file you think "
            "it is. Refusing to unpickle it." % (path, pin, actual)
        )
    message = (
        "UNRESTRICTED PICKLE LOAD: %s (sha256 %s...%s) is being deserialized with "
        "torch.load(weights_only=False) because the caller pinned its digest. Arbitrary "
        "code in this file will execute. Migrate it to safetensors with "
        "opencontractml.safeload.save_checkpoint and drop the pin." % (path, pin[:12], pin[-6:])
    )
    warnings.warn(message, UnsafePickleWarning, stacklevel=3)
    print("opencontractml.safeload: " + message, file=sys.stderr)
    return True


# --------------------------------------------------------------------------- safetensors

def split_payload(payload: Dict[str, Any], state_key: Optional[str] = None) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """Split a checkpoint payload into (state_key, tensors, json-able remainder)."""
    if state_key is None:
        found = [k for k in STATE_KEYS if k in payload]
        if len(found) != 1:
            raise ValueError(
                "cannot tell which key holds the tensors: expected exactly one of %r in the "
                "payload, found %r" % (list(STATE_KEYS), found)
            )
        state_key = found[0]
    tensors = dict(payload[state_key])
    rest = {k: v for k, v in payload.items() if k != state_key}
    return state_key, tensors, rest


def save_checkpoint(path: "str | Path", payload: Dict[str, Any], state_key: Optional[str] = None) -> Path:
    """Write a checkpoint payload as safetensors + a JSON metadata header.

    The tensors become the safetensors tensor map; everything else -- ``kind``,
    ``config``, ``norm`` and any ``extra`` -- is JSON-encoded into the metadata
    map, which safetensors types as ``str -> str``.  Nothing in the result can
    carry code.
    """
    from safetensors.torch import save_file

    path = Path(path)
    key, tensors, rest = split_payload(payload, state_key)
    try:
        header = json.dumps({"format": _FORMAT, "state_key": key, "payload": rest})
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "the non-tensor part of this checkpoint is not JSON-serializable (%s). safetensors "
            "metadata is str->str, so the payload must be plain scalars/lists/dicts." % exc
        ) from None
    # contiguous(): safetensors rejects non-contiguous and storage-sharing tensors
    flat = {k: v.detach().cpu().contiguous() for k, v in tensors.items()}
    save_file(flat, str(path), metadata={_METADATA_KEY: header})
    return path


def _load_safetensors(path: Path, device: str) -> Dict[str, Any]:
    from safetensors import safe_open

    with safe_open(str(path), framework="pt", device=device) as f:
        meta = (f.metadata() or {}).get(_METADATA_KEY)
        tensors = {k: f.get_tensor(k) for k in f.keys()}
    if meta is None:
        # a bare safetensors file written by something else: still safe to read,
        # we just have no config/norm to go with it
        return {"state_dict": tensors}
    header = json.loads(meta)
    if header.get("format") != _FORMAT:
        raise UntrustedArtifactError(
            "unknown safetensors metadata format %r in %s" % (header.get("format"), path)
        )
    payload = dict(header["payload"])
    payload[header["state_key"]] = tensors
    return payload


# --------------------------------------------------------------------------- the entry point

def load_checkpoint(path: "str | Path", device: str = "cpu", trust_sha256: Optional[str] = None) -> Dict[str, Any]:
    """Read a checkpoint payload under the safe-load policy.

    ``.safetensors`` is read natively.  ``.pt``/``.pth``/``.ckpt`` is read with
    ``torch.load(weights_only=True)``.  Any other suffix, and any torch file the
    restricted unpickler rejects, raises :class:`UntrustedArtifactError` unless
    ``trust_sha256`` pins the exact bytes on disk.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    suffix = path.suffix.lower()

    if suffix == SAFETENSORS_SUFFIX:
        return _load_safetensors(path, device)

    if suffix not in TORCH_SUFFIXES:
        raise UntrustedArtifactError(
            "refusing to load %s: suffix %r is not a recognised artifact format. Supported: %s, %s."
            % (path, suffix, SAFETENSORS_SUFFIX, ", ".join(TORCH_SUFFIXES))
        )

    import torch

    if _pin_opens(path, trust_sha256):
        return torch.load(str(path), map_location=device, weights_only=False)

    try:
        with torch.serialization.safe_globals(_extra_safe_globals()):
            return torch.load(str(path), map_location=device, weights_only=True)
    except Exception as exc:
        # torch raises UnpicklingError for a blocked global and for a malformed
        # archive alike; either way we have not executed anything from the file.
        raise UntrustedArtifactError(
            "refusing to load %s.\n"
            "torch's restricted unpickler (weights_only=True) rejected it: %s: %s\n"
            "\n"
            "This means the file asks to reconstruct objects outside the allow-list. A "
            "checkpoint of tensors and plain metadata never does, so treat this file as "
            "untrusted until you know where it came from.\n"
            "\n"
            "If you have verified its provenance, migrate it off pickle: read it once with\n"
            "    opencontractml.safeload.load_checkpoint('%s', trust_sha256='%s')\n"
            "and write the payload back with opencontractml.safeload.save_checkpoint().\n"
            % (path, type(exc).__name__, _blocked_global(exc), path, sha256_file(path))
        ) from None


def open_npz(path: "str | Path"):
    """``numpy.load`` with ``allow_pickle=False`` made explicit and non-overridable.

    numpy has defaulted to ``allow_pickle=False`` since 1.16.3, so the npz
    surfaces were never the hole that the torch ones were; routing them here
    keeps the default from being flipped back by a future edit and gives the
    audit one place to look.
    """
    import numpy as np

    return np.load(str(path), allow_pickle=False)


__all__ = [
    "UntrustedArtifactError", "UnsafePickleWarning", "SAFETENSORS_SUFFIX", "TORCH_SUFFIXES",
    "is_safetensors", "sha256_file", "split_payload", "save_checkpoint", "load_checkpoint", "open_npz",
]
