"""Fail-demos for the safe-load policy.

This file builds *hostile* model bundles -- pickles whose deserialization
executes an attacker's callable -- and proves:

1. the hostile bundle is genuinely live: under the pre-policy call,
   ``pickle.load``, its payload really does run
   (:func:`test_hostile_bundle_is_live_under_plain_pickle_load`);
2. ``safe_artifact.load_bundle`` refuses it and the payload does not run;
3. the refusal is specific, not an accident of a corrupt file -- a legitimate
   bundle of real fitted sklearn estimators still loads, and the same hostile
   bytes do load once their digest is pinned.

(1) is the part that keeps this suite honest.  A "gate" whose hostile input was
never dangerous proves nothing: it passes whether or not the guard works.  The
marker file is the witness here: if a refactor ever makes the hostile bundle
inert, test (1) goes red instead of the suite silently passing for the wrong
reason.

Nothing here needs thermal-mesh-calculators or a corpus; the estimators in the
legitimate bundle come from the ``[gate]`` extra, which ``[dev]`` installs.
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest

from opencontractml.safe_artifact import (UntrustedArtifactError, UnsafePickleWarning, describe,
                           inspect_globals, load_bundle, sha256_file, unsafe_globals)


# --------------------------------------------------------------------------- hostile artifacts

def _payload_marker(path: str) -> str:
    """Stand-in for a real payload. Writes a witness file so we can see it ran."""
    Path(path).write_text("pwned", encoding="utf-8")
    return path


class _HostileBundle:
    """Runs code when deserialized. `__reduce__` names a callable; pickle calls it."""

    def __init__(self, marker: Path):
        self.marker = str(marker)

    def __reduce__(self):
        return (_payload_marker, (self.marker,))


class _ShellBundle:
    """The same trick naming `os.system` -- a real RCE primitive."""

    def __init__(self, marker: Path):
        self.marker = str(marker)

    def __reduce__(self):
        # creates the file under both cmd.exe and sh, so the marker's absence is
        # meaningful evidence that this never ran
        return (os.system, ("echo pwned > %s" % self.marker,))


class _EvalBundle:
    """`builtins.eval` -- the other canonical primitive."""

    def __init__(self, marker: Path):
        self.marker = str(marker)

    def __reduce__(self):
        return (eval, ("open(%r,'w').write('pwned')" % self.marker,))


class _SubprocessBundle:
    def __init__(self, marker: Path):
        self.marker = str(marker)

    def __reduce__(self):
        return (subprocess.call, (["cmd", "/c", "echo pwned > %s" % self.marker],))


HOSTILE = {"reduce_to_function": _HostileBundle, "os.system": _ShellBundle,
           "builtins.eval": _EvalBundle, "subprocess.call": _SubprocessBundle}


@pytest.fixture()
def hostile(tmp_path):
    marker = tmp_path / "PWNED.txt"
    path = tmp_path / "model_bundle.pkl"
    path.write_bytes(pickle.dumps(_HostileBundle(marker)))
    assert not marker.exists()
    return path, marker


@pytest.fixture(scope="module")
def real_bundle_bytes():
    """A bundle of genuinely fitted sklearn estimators, shaped like train_b1's.

    Built directly with train_b1.fit_models rather than through the corpus
    pipeline, so it needs no thermal-mesh-calculators and no parquet.
    """
    from opencontractml.train_b1 import fit_models

    rng = np.random.RandomState(0)
    X = rng.rand(60, 4)
    y = X[:, 0] * 2.0 + X[:, 1] ** 2 + rng.rand(60) * 0.01
    model = fit_models(X[:40], y[:40], X[40:], y[40:], 0.90)
    bundle = {"heat_shield/T_max_K": {
        "model": model, "feature_columns": list("abcd"), "features": list("abcd"),
        "component": "heat_shield", "target": "T_max_K", "row_case_ids": [1, 2],
        "splits": {"fit": [0], "calibration": [1], "random_test": [2], "corner": [3],
                   "corner_axis": "a", "corner_threshold": 0.5},
        "transform": {"features": {}, "target": None}}}
    return pickle.dumps(bundle), X, model


# --------------------------------------------------------------------------- 1. the demos are live

@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_hostile_bundle_is_live_under_plain_pickle_load(tmp_path, name):
    """The anti-vacuity guard: each payload really executes under `pickle.load`.

    This is the call the model gate used to make, twice, before the safe-load policy.
    If this test fails, the corresponding "is refused" test below is worthless.
    """
    marker = tmp_path / ("PWNED_%s.txt" % name.replace(".", "_"))
    path = tmp_path / "b.pkl"
    path.write_bytes(pickle.dumps(HOSTILE[name](marker)))
    assert not marker.exists()
    with open(path, "rb") as fh:
        pickle.load(fh)                      # the surface the safe-load policy removes
    assert marker.exists(), "payload %r did not execute -- this fail-demo is vacuous" % name


# --------------------------------------------------------------------------- 2. all of them refused

@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_hostile_bundle_refused_by_load_bundle(tmp_path, name):
    marker = tmp_path / ("PWNED_%s.txt" % name.replace(".", "_"))
    path = tmp_path / "b.pkl"
    path.write_bytes(pickle.dumps(HOSTILE[name](marker)))
    with pytest.raises(UntrustedArtifactError, match="not in the safe-load allow-list"):
        load_bundle(path)
    assert not marker.exists(), "payload %r executed despite the refusal" % name


def test_model_gate_run_gate_refuses_a_hostile_bundle(tmp_path, hostile):
    """The routing end-to-end: the gate itself refuses, not just the policy module.

    run_gate reads the corpus before it reads the bundle, so this needs a real
    corpus to get as far as the bundle. load_corpus accepts CSV, so one row of one
    column is enough -- nothing between the read and the bundle load touches more.
    """
    from opencontractml.gate import run_gate

    path, marker = hostile
    model_dir = path.parent
    corpus = tmp_path / "training_corpus.csv"
    corpus.write_text("case_id,component_name,T_max_K\n1,heat_shield,300.0\n", encoding="utf-8")

    with pytest.raises(UntrustedArtifactError, match="not in the safe-load allow-list"):
        run_gate(corpus, {"admissible_index": [0]}, {}, model_dir)
    assert not marker.exists(), "the gate executed the hostile bundle"


def test_unknown_suffix_is_refused(tmp_path):
    p = tmp_path / "bundle.bin"
    p.write_bytes(pickle.dumps({"a": 1}))
    with pytest.raises(UntrustedArtifactError, match="not a recognised bundle format"):
        load_bundle(p)


@pytest.mark.parametrize("mod,name", [("os", "system"), ("nt", "system"), ("posix", "system"),
                                      ("subprocess", "Popen"), ("builtins", "eval"),
                                      ("builtins", "exec"), ("builtins", "__import__"),
                                      ("builtins", "getattr"), ("builtins", "open"),
                                      ("operator", "attrgetter"), ("functools", "partial"),
                                      ("importlib", "import_module"), ("ctypes", "CDLL"),
                                      ("pickle", "loads"), ("numpy.testing", "assert_"),
                                      ("pandas.io.pickle", "read_pickle")])
def test_known_gadget_modules_are_outside_the_allow_list(mod, name):
    """Spot-check the allow-list is closed over the documented RCE primitives."""
    from opencontractml import safe_artifact

    assert not safe_artifact._is_allowed(mod, name), "%s.%s is reachable" % (mod, name)


@pytest.mark.parametrize("mod,name", [("numpy", "ndarray"), ("numpy._core.multiarray", "_reconstruct"),
                                      ("sklearn.pipeline", "Pipeline"), ("builtins", "dict"),
                                      ("collections", "OrderedDict"), ("copyreg", "_reconstructor")])
def test_legitimate_reconstruction_helpers_are_inside_the_allow_list(mod, name):
    from opencontractml import safe_artifact

    assert safe_artifact._is_allowed(mod, name)


def test_unqualified_cython_loss_module_needs_sklearn_to_own_it(monkeypatch):
    """`_loss` is allowed only because sklearn already imported it.

    An unqualified module name is a path-injection hazard: find_class would import
    whatever `_loss` resolves to. The guard requires the module to be present and
    to live inside sklearn, so a stray _loss.py cannot impersonate it.
    """
    from opencontractml import safe_artifact

    import sklearn.ensemble  # noqa: F401  (ensures the Cython loss module is imported)
    assert safe_artifact._is_allowed("_loss", "CyHalfSquaredError")

    monkeypatch.delitem(sys.modules, "_loss", raising=False)
    assert not safe_artifact._is_allowed("_loss", "CyHalfSquaredError")

    class Fake:
        __file__ = "/tmp/evil/_loss.py"
    monkeypatch.setitem(sys.modules, "_loss", Fake())
    assert not safe_artifact._is_allowed("_loss", "CyHalfSquaredError")


# --------------------------------------------------------------------------- 3. specific, not blanket

def test_a_real_sklearn_bundle_still_loads(tmp_path, real_bundle_bytes):
    """The guard must not brick the bundles train_b1.py actually writes."""
    raw, X, model = real_bundle_bytes
    p = tmp_path / "model_bundle.pkl"
    p.write_bytes(raw)
    assert unsafe_globals(p) == [], "a legitimate bundle was flagged: %r" % unsafe_globals(p)
    back = load_bundle(p)
    entry = back["heat_shield/T_max_K"]
    assert entry["model"]["champion"] in ("ensemble", "linear", "poly2", "gp", "mean")
    for which in ("linear", "poly2", "gp", "mean"):
        assert np.allclose(entry["model"][which].predict(X[:5]), model[which].predict(X[:5])), which
    assert len(entry["model"]["ensemble"]) == len(model["ensemble"])


def test_digest_pin_opens_the_hatch_and_is_loud(hostile):
    """The documented escape hatch really is a hole -- which is why it warns.

    Asserting the payload fires is the honest characterization. A test that
    pretended the hatch was safe would be the vacuous kind.
    """
    path, marker = hostile
    pin = sha256_file(path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_bundle(path, trust_sha256=pin)
    assert marker.exists(), "the pinned load did not behave as documented"
    assert any(isinstance(w.message, UnsafePickleWarning) for w in caught), "the hatch opened silently"
    assert any("UNRESTRICTED PICKLE LOAD" in str(w.message) for w in caught)


def test_stale_digest_pin_refuses(hostile):
    path, marker = hostile
    pin = sha256_file(path)
    path.write_bytes(path.read_bytes() + b"\x00")
    with pytest.raises(UntrustedArtifactError, match="digest pin does not match"):
        load_bundle(path, trust_sha256=pin)
    assert not marker.exists()


@pytest.mark.parametrize("bad", ["", "deadbeef", "not-a-digest", "z" * 64, True])
def test_malformed_digest_pin_refuses(hostile, bad):
    path, marker = hostile
    with pytest.raises(UntrustedArtifactError):
        load_bundle(path, trust_sha256=bad)
    assert not marker.exists()


def test_no_environment_variable_can_open_the_hatch(hostile, monkeypatch):
    path, marker = hostile
    for name in ("ALLOW_PICKLE", "CC_ALLOW_PICKLE", "CC_TRUST_ARTIFACTS", "SAFE_ARTIFACT_UNSAFE"):
        monkeypatch.setenv(name, "1")
    with pytest.raises(UntrustedArtifactError):
        load_bundle(path)
    assert not marker.exists()


# --------------------------------------------------------------------------- 4. the audit primitive

def test_inspect_globals_sees_the_payload_without_running_it(tmp_path):
    marker = tmp_path / "PWNED.txt"
    p = tmp_path / "b.pkl"
    p.write_bytes(pickle.dumps(_ShellBundle(marker)))
    named = inspect_globals(p)
    assert not marker.exists(), "inspect_globals executed the bundle"
    # os.system is `nt.system` on Windows and `posix.system` on POSIX
    assert any(n == "system" for _m, n in named), named
    assert unsafe_globals(p) == named
    d = describe(p)
    assert d["loadable_under_policy"] is False and d["sha256"] == sha256_file(p)
    assert not marker.exists()


def test_inspect_globals_agrees_with_find_class_on_a_real_bundle(tmp_path, real_bundle_bytes):
    """The static parser must not under-report -- that is the dangerous direction.

    A version of inspect_globals that ignored the pickle memo found 18 of the 29
    globals in this bundle, because a module string is written once, memoized, and
    referenced by index afterwards. This pins the two views together.
    """
    import io

    raw, _X, _model = real_bundle_bytes
    p = tmp_path / "model_bundle.pkl"
    p.write_bytes(raw)

    seen = set()

    class Recording(pickle.Unpickler):
        def find_class(self, module, name):
            seen.add((module, name))
            return super().find_class(module, name)

    Recording(io.BytesIO(raw)).load()
    static = set(inspect_globals(p))
    assert static == seen, ("static parse disagrees with find_class:\n  only static: %r\n  only dynamic: %r"
                            % (sorted(static - seen), sorted(seen - static)))
    assert len(seen) > 20, "expected a rich bundle, got %d globals" % len(seen)


# --------------------------------------------------------------------------- 5. keep the class dead

def test_no_raw_pickle_load_remains_in_the_corpus_consumer():
    """Regression net: `pickle.load` must not come back into this pipeline.

    Walks the AST rather than grepping, so prose in a docstring that mentions
    ``pickle.load(`` is not mistaken for a call. ``safe_artifact.py`` is the one
    file allowed to make the call, and this test file is allowed to demonstrate
    the danger it guards against.
    """
    import ast

    root = Path(__file__).resolve().parents[1]
    allowed = {"safe_artifact.py", "test_safe_artifact.py"}
    offenders = []
    checked = 0
    for py in sorted(root.rglob("*.py")):
        if py.name in allowed:
            continue
        checked += 1
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                if (f.value.id, f.attr) in {("pickle", "load"), ("pickle", "loads"),
                                            ("joblib", "load"), ("dill", "load")}:
                    offenders.append("%s:%d %s.%s(...)" % (py.relative_to(root), node.lineno, f.value.id, f.attr))
            for kw in node.keywords:
                if kw.arg == "allow_pickle" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    offenders.append("%s:%d allow_pickle=True" % (py.relative_to(root), node.lineno))
    assert checked >= 5, "the scan found almost nothing -- it is not looking where it thinks it is"
    assert not offenders, "raw pickle reads reappeared:\n  " + "\n  ".join(offenders)
