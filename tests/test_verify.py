"""Tests for the Contract v1 conformance checker.

The shape of this suite is the point. Every ERROR rule gets a *negative* test: a
one-line mutation of a known-good package that must make that rule fire (a defect
that breaks the manifest schema too also fires M018 beside it).
``test_every_error_rule_has_a_negative_test`` then asserts that the mutation
table covers the rule table, so adding a rule without proving it can fail breaks
the build.

This is "a gate must be able to fail" applied to the checker itself. The thing
a real scalar ladder got wrong -- V2.3 conservation "passes" when a free-text
field is a non-empty string, and a test enshrined the pass -- is the failure
mode these tests exist to prevent in the contract.
"""

from __future__ import annotations

import json
import sys
from importlib import resources
from pathlib import Path

import pytest

from opencontractml import verify as vs

LF = chr(10)


# --------------------------------------------------------------------------- #
# A known-good package, built in a tmp dir, in dependency-free JSON form.
# --------------------------------------------------------------------------- #
ENTRYPOINT_SRC = (
    '"""Minimal stdio_json entrypoint for the test fixture."""' + LF
    + "import json, sys" + LF
    + "req = json.loads(sys.stdin.read())" + LF
    + 'json.dump({"outputs": {"life_cycles": 1.0}}, sys.stdout)' + LF
)
WEIGHTS_SRC = json.dumps({"intercept": 1.0}, indent=2) + LF


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def base_manifest() -> dict:
    return {
        "spec_version": "1.1",
        "id": "fixture_model_v1",
        "name": "Fixture Model",
        "version": "1.0.0",
        "owner": {"team": "contract tests", "contact": "tests@example.invalid"},
        "domain": "thermomechanical_fatigue",
        "modality": "scalar_in_scalar_out",
        "purpose": "A known-good package the negative tests mutate.",
        "inputs": [
            {"name": "peak_temp_K", "type": "float", "units": "K", "range": [400.0, 1200.0], "required": True},
            {"name": "material", "type": "categorical", "choices": ["GG20", "GG25"], "required": True},
        ],
        "outputs": [{"name": "life_cycles", "type": "float", "units": "cycles", "viewer": "scalar_with_uq"}],
        "uncertainty": {
            "form": "predictive_interval",
            "per_output": {"life_cycles": {"lower_field": "life_cycles_lower",
                                           "upper_field": "life_cycles_upper", "level": 0.9}},
        },
        "invocation": {"executable": "./predict.py", "protocol": "stdio_json", "timeout_s": 60},
        "lineage": {"training_data_version": "fixture-1.0", "training_date": "2026-09-12",
                    "metrics": {"r2": 0.99}},
        "provenance": {
            "artifacts": [
                {"path": "./predict.py", "role": "entrypoint",
                 "sha256": _sha(ENTRYPOINT_SRC), "bytes": len(ENTRYPOINT_SRC.encode("utf-8"))},
                {"path": "./model_weights.json", "role": "weights",
                 "sha256": _sha(WEIGHTS_SRC), "bytes": len(WEIGHTS_SRC.encode("utf-8"))},
            ],
            "dataset": {"sha256": "a" * 64, "n_samples": 600, "generator_version": "fixture-1.0"},
            "code": {"repo": "example-org/fixture-model", "commit": "0123456789abcdef"},
            "environment": {"python": "3.13.3"},
        },
        "validation": {"report": "./validation_report.json", "overall": "PASS"},
        "model_card": "./model_card.md",
        "licence": {
            "model": {"spdx": "Apache-2.0", "url": "http://www.apache.org/licenses/LICENSE-2.0"},
            "weights": {"spdx": "Apache-2.0", "url": "http://www.apache.org/licenses/LICENSE-2.0"},
            "training_data": {"spdx": "NOASSERTION", "note": "a constant function has no training data"},
        },
    }


def _compare(*triples) -> list:
    return [{"metric": metric, "op": op, "bar": bar} for metric, op, bar in triples]


def base_report() -> dict:
    def passing(**extra):
        base = {"status": "PASS", "metrics": {"value": 1.0, "n": 10}, "thresholds": {"limit": 2.0},
                "comparators": _compare(("value", "<=", "limit"))}
        base.update(extra)
        return base

    return {
        "spec_version": "1.1",
        "produced_by": "contract test fixture",
        "model_id": "fixture_model_v1",
        "model_version": "1.0.0",
        "dataset_sha256": "a" * 64,
        "checks": {
            "A1_accuracy": passing(),
            "A2_extrapolation": passing(),
            "A3_uq_calibration": passing(
                method="split conformal",
                metrics={"nominal": 0.9, "empirical_coverage": 0.91, "n": 108},
                thresholds={"coverage_band_lo": 0.85, "coverage_band_hi": 0.96},
                comparators=_compare(("empirical_coverage", ">=", "coverage_band_lo"),
                                     ("empirical_coverage", "<=", "coverage_band_hi"))),
            "A4_baseline_beat": passing(),
            "A5_reproducibility": passing(determinism_class="bitwise", metrics={"delta": 0.0},
                                          thresholds={"tolerance": 0.0},
                                          comparators=_compare(("delta", "<=", "tolerance"))),
            "B1_monotonicity": passing(),
            "B2_bounds": passing(),
            "B3_residual": {"status": "NOT_APPLICABLE", "reason": "scalar model, no field to take a residual of"},
            "B4_conservation": {
                "status": "PASS", "applicable": True, "quantity": "energy",
                "control_volume": "the whole plate, all six faces",
                "scope": "control_volume",
                "metrics": {"relative_imbalance": 0.012, "n": 64},
                "thresholds": {"imbalance_max": 0.05},
                "comparators": _compare(("relative_imbalance", "<=", "imbalance_max")),
            },
            "B5_invariance": {"status": "NOT_APPLICABLE", "reason": "no mesh or sampling to be invariant to"},
            "B6_integrated_quantities": {"status": "NOT_APPLICABLE", "reason": "no field to re-derive from"},
            "C1_ood_guard": passing(),
            "C2_serve_parity": passing(),
            "C3_provenance_integrity": passing(),
            "C4_deployment_readiness": passing(),
        },
        "overall": "PASS",
    }


CARD_SECTION_TEXT = {
    "TL;DR": "A fixture model that exists so the conformance checker has something known-good to grade.",
    "Intended use": "Exercising verify.py. It has no other use and predicts nothing meaningful.",
    "Out of scope": "Every engineering decision. The fixture returns a constant and claims nothing.",
    "Training data": "None. The fixture is a constant function; the dataset hash is a placeholder of the right shape.",
    "Architecture": "A constant function returning 1.0, wrapped in the stdio_json protocol. There is no model.",
    "Training configuration": "No training occurs. There is no optimiser, no schedule and no seed to record.",
    "Performance": "Not measured, because a constant function has no meaningful accuracy to report here.",
    "Uncertainty quantification": "A split conformal interval at a nominal level of 0.90 with coverage 0.91.",
    "Known failure modes": "It is a constant. It is wrong for every input that is not exactly its constant.",
    "Provenance": "The entrypoint and the weights file are pinned by sha256 in the manifest beside this card.",
    "Version history": "1.0.0 (2026-09-12) first issue as the conformance checker's known-good test fixture.",
}


def base_card() -> str:
    lines = ["---", "model_id: fixture_model_v1", "version: 1.0.0", 'spec_version: "1.1"', "---", "",
             "# Fixture Model", ""]
    for name in vs.CARD_SECTIONS:
        lines += ["## " + name, "", CARD_SECTION_TEXT[name], ""]
    return LF.join(lines)


def write_package(root: Path, manifest=None, report=None, card=None,
                  entrypoint=ENTRYPOINT_SRC, weights=WEIGHTS_SRC) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "predict.py").write_text(entrypoint, encoding="utf-8", newline=LF)
    (root / "model_weights.json").write_text(weights, encoding="utf-8", newline=LF)
    (root / "model_card.md").write_text(base_card() if card is None else card, encoding="utf-8", newline=LF)
    (root / "validation_report.json").write_text(
        json.dumps(base_report() if report is None else report, indent=2), encoding="utf-8", newline=LF)
    (root / "manifest.json").write_text(
        json.dumps(base_manifest() if manifest is None else manifest, indent=2), encoding="utf-8", newline=LF)
    return root


@pytest.fixture()
def good(tmp_path: Path) -> Path:
    return write_package(tmp_path / "pkg")


def rules_fired(findings) -> set:
    return {f.rule for f in findings}


# --------------------------------------------------------------------------- #
# Positive cases.
# --------------------------------------------------------------------------- #
def test_synthetic_base_package_is_conformant(good: Path):
    findings = vs.check_package(good)
    assert findings == [], "known-good fixture must be clean, got: %r" % (findings,)


def test_committed_reference_package_is_conformant():
    """The shipped examples/reference-package must validate as authored."""
    pytest.importorskip("yaml", reason="the reference package ships manifest.yaml")
    pkg = Path(__file__).resolve().parents[1] / "examples" / "reference-package"
    assert pkg.is_dir(), "reference package is missing from the tree"
    findings = vs.check_package(pkg)
    assert findings == [], "reference package must be conformant, got: %r" % (findings,)


def test_reference_package_entrypoint_really_runs():
    """A pinned entrypoint that cannot execute is a contract fixture in name only."""
    import subprocess
    pkg = Path(__file__).resolve().parents[1] / "examples" / "reference-package"
    request = {"inputs": {"peak_temp_K": 773.15, "cycle_count": 5000, "material": "GG25"}}
    out = subprocess.run([sys.executable, str(pkg / "predict.py")], input=json.dumps(request),
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert set(payload["outputs"]) == {"life_cycles", "life_cycles_lower", "life_cycles_upper"}
    assert payload["outputs"]["life_cycles_lower"] < payload["outputs"]["life_cycles"] \
        < payload["outputs"]["life_cycles_upper"]


def test_fg7_collision_is_resolved_by_lane():
    """FG7 names two different physical claims; the contract must not flatten them."""
    assert vs.legacy_key("grid", "FG7") == "B4_conservation"
    assert vs.legacy_key("mesh", "FG7") == "B4_conservation"
    assert vs.legacy_key("cloud", "FG7") == "B6_integrated_quantities"
    assert "FG7" not in vs.LEGACY_ALIASES, "FG7 must not have a lane-independent alias"
    assert vs.legacy_key("scalar", "V2.3") == "B4_conservation"
    assert vs.legacy_key("grid", "FG3") == vs.legacy_key("scalar", "V1.3") == "A3_uq_calibration"


def test_fg11_is_the_cloud_integrated_quantities_check_and_cloud_fg7_is_retired():
    """The cloud ladder renamed its integrated-quantities check from FG7 to FG11.

    FG11 must resolve on its own, and the retired FG7 must still resolve to the
    same key, because reports written before the rename carry the old id.
    """
    assert vs.legacy_key("cloud", "FG11") == "B6_integrated_quantities"
    assert vs.LEGACY_ALIASES["FG11"] == "B6_integrated_quantities"
    assert vs.RETIRED_ALIASES == {"FG7": {"cloud": "FG11"}}
    for old, replaced in vs.RETIRED_ALIASES.items():
        for ladder, new in replaced.items():
            assert vs.legacy_key(ladder, old) == vs.legacy_key(ladder, new) is not None, (old, ladder, new)
    # nothing changes where FG7 was never renamed: it is still conservation there
    assert vs.legacy_key("grid", "FG7") == vs.legacy_key("mesh", "FG7") == "B4_conservation"
    vocab = vs.vocabulary()
    assert vocab["legacy_aliases"]["FG11"] == "B6_integrated_quantities"
    assert vocab["legacy_aliases_retired"] == {"FG7": {"cloud": "FG11"}}


def test_card_section_set_keeps_the_nine_package_v1_sections_in_order():
    """A card written to the nine package-v1 sections conforms after two insertions, no re-ordering."""
    package_v1_nine = ["TL;DR", "Intended use", "Out of scope", "Training data", "Architecture",
                       "Performance", "Uncertainty quantification", "Known failure modes", "Version history"]
    kept = [s for s in vs.CARD_SECTIONS if s in package_v1_nine]
    assert kept == package_v1_nine
    assert set(vs.CARD_SECTIONS) - set(package_v1_nine) == {"Training configuration", "Provenance"}


def test_headings_inside_code_fences_are_ignored():
    body = LF.join(["## Real", "text", "```", "## Not a heading", "```", "## Also real"])
    assert vs.h2_headings(body) == ["Real", "Also real"]


# --------------------------------------------------------------------------- #
# Negative cases: one mutation per ERROR rule.
# --------------------------------------------------------------------------- #
def _mutate_manifest(fn):
    def apply(root: Path):
        man = base_manifest()
        fn(man)
        (root / "manifest.json").write_text(json.dumps(man, indent=2), encoding="utf-8", newline=LF)
    return apply


def _mutate_report(fn):
    def apply(root: Path):
        rep = base_report()
        fn(rep)
        (root / "validation_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8", newline=LF)
    return apply


def _mutate_card(fn):
    def apply(root: Path):
        (root / "model_card.md").write_text(fn(base_card()), encoding="utf-8", newline=LF)
    return apply


def _no_manifest(root: Path):
    (root / "manifest.json").unlink()


def _corrupt_entrypoint(root: Path):
    (root / "predict.py").write_text(ENTRYPOINT_SRC + "# edited after packaging" + LF,
                                     encoding="utf-8", newline=LF)


def _missing_card_file(root: Path):
    (root / "model_card.md").unlink()


# Mutations of the committed reference package. Each replaces the synthetic
# package in the test's directory with a copy of examples/reference-package and
# changes one thing in it, so the defect sits in a package that is otherwise
# exactly what this repository ships. Its manifest is YAML, rewritten through
# PyYAML, which is a dependency of this package.
REFERENCE_PACKAGE = Path(__file__).resolve().parents[1] / "examples" / "reference-package"


def _reference_package(change):
    def apply(root: Path):
        import shutil
        shutil.rmtree(root)
        shutil.copytree(REFERENCE_PACKAGE, root)
        change(root)
    return apply


def _rewrite_yaml_manifest(root: Path, fn) -> None:
    import yaml
    path = root / "manifest.yaml"
    man = yaml.safe_load(path.read_text(encoding="utf-8"))
    fn(man)
    path.write_text(yaml.safe_dump(man, sort_keys=False), encoding="utf-8", newline=LF)


def _rewrite_json_report(root: Path, fn) -> None:
    path = root / "validation_report.json"
    rep = json.loads(path.read_text(encoding="utf-8"))
    fn(rep)
    path.write_text(json.dumps(rep, indent=2) + LF, encoding="utf-8", newline=LF)


def _reference_manifest(fn):
    return _reference_package(lambda root: _rewrite_yaml_manifest(root, fn))


def _reference_report(fn):
    return _reference_package(lambda root: _rewrite_json_report(root, fn))


def _move_entrypoint_outside(root: Path):
    """The entrypoint moved next to the package rather than into it, its hash still right."""
    outside = root.parent / "outside"
    outside.mkdir()
    (root / "predict.py").rename(outside / "predict.py")

    def point_outside(m):
        m["provenance"]["artifacts"][0]["path"] = "../outside/predict.py"
        m["invocation"]["executable"] = "../outside/predict.py"
    _rewrite_yaml_manifest(root, point_outside)


def _weights_beside_the_package(root: Path):
    (root.parent / "model_weights.json").write_text(WEIGHTS_SRC, encoding="utf-8", newline=LF)
    _mutate_manifest(lambda m: m["provenance"]["artifacts"][1].__setitem__("path", "../model_weights.json"))(root)


def _weights_by_absolute_path(root: Path):
    absolute = str((root / "model_weights.json").resolve())
    _mutate_manifest(lambda m: m["provenance"]["artifacts"][1].__setitem__("path", absolute))(root)


def _card_beside_the_package(root: Path):
    (root.parent / "model_card.md").write_text(base_card(), encoding="utf-8", newline=LF)
    _mutate_manifest(lambda m: m.__setitem__("model_card", "../model_card.md"))(root)


def _report_beside_the_package(root: Path):
    (root.parent / "validation_report.json").write_text(json.dumps(base_report(), indent=2), encoding="utf-8",
                                                        newline=LF)
    _mutate_manifest(lambda m: m["validation"].__setitem__("report", "../validation_report.json"))(root)


def _reference_entrypoint(source: str, manifest_fn=None):
    """The reference package with its entrypoint replaced and re-pinned, so only its behaviour differs."""
    def change(root: Path):
        import hashlib
        body = source.encode("utf-8")
        (root / "predict.py").write_bytes(body)

        def repin(m):
            m["provenance"]["artifacts"][0]["sha256"] = hashlib.sha256(body).hexdigest()
            m["provenance"]["artifacts"][0]["bytes"] = len(body)
            if manifest_fn is not None:
                manifest_fn(m)
        _rewrite_yaml_manifest(root, repin)
    return _reference_package(change)


def _a1_misses_its_bars(r) -> None:
    r["checks"]["A1_accuracy"]["metrics"]["r2"] = 0.10        # its threshold r2_min is 0.9
    r["checks"]["A1_accuracy"]["metrics"]["mae"] = 9.0        # its threshold mae_max is 0.2


def _b4_passes_over_its_bar(comparators: bool):
    def plant(r) -> None:
        check = {"status": "PASS", "applicable": True, "quantity": "energy", "control_volume": "disc",
                 "scope": "control_volume", "metrics": {"relative_imbalance": 0.90, "n": 10},
                 "thresholds": {"imbalance_max": 0.05}}
        if comparators:
            check["comparators"] = _compare(("relative_imbalance", "<=", "imbalance_max"))
        r["checks"]["B4_conservation"] = check
    return plant


def _fail_whose_comparators_hold(r) -> None:
    """The other direction: a FAIL that its own numbers call a PASS."""
    r["checks"]["A1_accuracy"]["status"] = "FAIL"
    r["overall"] = "FAIL"


def _a5_bitwise_at(tolerance: float):
    def plant(r) -> None:
        a5 = r["checks"]["A5_reproducibility"]
        a5["determinism_class"] = "bitwise"
        a5["thresholds"]["tolerance"] = tolerance
    return plant


#: B4 as a check that applies and was not run: the honest encoding contract 1.1 accepts.
B4_NOT_RUN = {"status": "NOT_RUN", "applicable": True,
              "reason": "the model conserves energy, and the balance has not been measured yet"}

#: What a point predictor's card says where another card names a method and a number.
POINT_PREDICTOR_UQ = ("A point predictor: the model reports no uncertainty, and its answers carry no bands, "
                      "so there is no interval to calibrate.")


def _point_predictor_package(spec_version: str = "1.1", calibration: bool = False, card_says_so: bool = True):
    """The synthetic package declaring uncertainty.form none, consistently in all three documents."""
    def apply(root: Path) -> None:
        man = base_manifest()
        man["spec_version"] = spec_version
        man["uncertainty"] = {"form": "none", "per_output": {}}
        if calibration:
            man["uncertainty"]["calibration"] = {"holdout_size": 10, "empirical_coverage": 0.9, "method": "none"}
        rep = base_report()
        rep["spec_version"] = spec_version
        rep["checks"]["A3_uq_calibration"] = {"status": "NOT_APPLICABLE",
                                              "reason": "the model reports no uncertainty, so there is no band"}
        card = base_card().replace('spec_version: "1.1"', 'spec_version: "%s"' % spec_version)
        if card_says_so:
            card = card.replace(CARD_SECTION_TEXT["Uncertainty quantification"], POINT_PREDICTOR_UQ)
        write_package(root, manifest=man, report=rep, card=card)
    return apply


#: A complete field block (contract 1.1): what a type: field output declares before any run.
FIELD_BLOCK = {"kind": "scalar", "units": "K", "support": "node", "media_type": "application/vnd.vtk.vtp+xml",
               "shape": [17, 17], "coordinate_ref": "nodes of a regular grid on the plate, row-major, axis order (y, x)"}

#: The block a grid producer emits today: shape, coordinate reference and units alone.
GRID_PRODUCER_BLOCK = {"shape": [64, 64],
                       "coordinate_ref": "regular_grid_cell_centred; axis order (y, x), row-major; "
                                         "y in [0, 0.1] m, x in [0, 0.1] m",
                       "units": "K"}


def _add_field_output(block=None, **extra):
    """Add a type: field output, with its uncertainty block, to the synthetic manifest."""
    def change(m) -> None:
        out = {"name": "surface_temp", "type": "field", "units": "K", "viewer": "field_contour",
               "description": "the temperature over the plate's surface"}
        out.update(extra)
        if block is not None:
            out["field"] = dict(block) if isinstance(block, dict) else block
        m["outputs"].append(out)
        m["uncertainty"]["per_output"]["surface_temp"] = {"lower_artifact": "surface_temp_lower",
                                                          "upper_artifact": "surface_temp_upper", "level": 0.9}
    return change


def _strip_units(m) -> None:
    for field in m["inputs"] + m["outputs"]:
        field.pop("units", None)
        field.pop("canonical_units", None)


def _rename_reference_id(new_id: str):
    """Rename the package everywhere its id appears, so only the id's form is wrong."""
    def change(root: Path):
        card = root / "model_card.md"
        card.write_text(card.read_text(encoding="utf-8").replace(
            "model_id: contract_reference_tmf_v1", "model_id: " + new_id), encoding="utf-8", newline=LF)
        _rewrite_json_report(root, lambda r: r.__setitem__("model_id", new_id))
        _rewrite_yaml_manifest(root, lambda m: m.__setitem__("id", new_id))
    return _reference_package(change)


MUTATIONS = [
    ("M001", _no_manifest),
    ("M002", _mutate_manifest(lambda m: m.__setitem__("spec_version", "9.0"))),
    ("M003", _mutate_manifest(lambda m: m.pop("domain"))),
    ("M004", _mutate_manifest(lambda m: m["inputs"][0].__setitem__("type", "bogus"))),
    ("M005", _mutate_manifest(lambda m: m["outputs"][0].pop("viewer"))),
    ("M006", _mutate_manifest(lambda m: m["inputs"].append(dict(m["inputs"][0])))),
    ("M007", _mutate_manifest(lambda m: m["uncertainty"]["per_output"].clear())),
    ("M008", _mutate_manifest(lambda m: m["invocation"].__setitem__("protocol", "http"))),
    ("M009", _missing_card_file),
    ("M010", _mutate_manifest(lambda m: m["validation"].pop("report"))),
    ("M011", _mutate_manifest(lambda m: m.pop("provenance"))),
    ("M012", _mutate_manifest(lambda m: m["provenance"]["artifacts"][1].__setitem__("role", "junk"))),
    # M012 and M013 each guard several independent branches; one mutation per branch,
    # because a branch with no negative test is an unproven branch.
    ("M012", _mutate_manifest(lambda m: m["provenance"]["artifacts"][0].__setitem__("sha256", "CAFE"))),
    ("M012", _mutate_manifest(lambda m: m["provenance"]["artifacts"][1].__setitem__("role", "entrypoint"))),
    ("M012", _mutate_manifest(lambda m: m["provenance"]["artifacts"][0].pop("bytes"))),
    ("M013", _corrupt_entrypoint),
    ("M013", _mutate_manifest(lambda m: m["provenance"]["artifacts"][1].__setitem__(
        "path", "./weights_that_were_never_shipped.json"))),
    ("M014", _mutate_manifest(lambda m: m["provenance"]["dataset"].__setitem__("sha256", "not-a-hash"))),
    ("M015", _mutate_manifest(lambda m: m["provenance"]["code"].__setitem__("commit", "zzz"))),
    ("M016", _mutate_manifest(lambda m: m["provenance"]["environment"].pop("python"))),
    ("C001", _mutate_card(lambda c: c.split("---" + LF, 2)[-1])),
    ("C002", _mutate_card(lambda c: c.replace("model_id: fixture_model_v1", "model_id: some_other_model"))),
    ("C003", _mutate_card(lambda c: c.replace("## Performance", "## Results"))),
    ("C004", _mutate_card(lambda c: c.replace(CARD_SECTION_TEXT["Provenance"], "TBD"))),
    ("C005", _mutate_card(lambda c: c.replace(CARD_SECTION_TEXT["Uncertainty quantification"],
                                              "We are quite confident in the numbers this model produces."))),
    ("C006", _mutate_card(lambda c: c + LF + "## Appendix Q" + LF + LF + "Extra." + LF)),
    ("V001", _mutate_report(lambda r: r.pop("produced_by"))),
    ("V002", _mutate_report(lambda r: r.__setitem__("model_id", "a_different_model"))),
    ("V003", _mutate_report(lambda r: r.__setitem__("dataset_sha256", "b" * 64))),
    ("V004", _mutate_report(lambda r: r["checks"].pop("C1_ood_guard"))),
    ("V005", _mutate_report(lambda r: r["checks"]["A1_accuracy"].__setitem__("status", "PROBABLY"))),
    # V006 has two independent halves -- no measurement, and nothing to measure
    # against. Mutating both at once would let either half carry the test.
    ("V006", _mutate_report(lambda r: r["checks"]["A4_baseline_beat"].__setitem__(
        "metrics", {"note": "looks fine to me"}))),
    ("V006", _mutate_report(lambda r: r["checks"]["A4_baseline_beat"].__setitem__(
        "thresholds", {"note": "no bar was set"}))),
    ("V007", _mutate_report(lambda r: r["checks"]["B5_invariance"].pop("reason"))),
    ("V008", _mutate_report(lambda r: r.__setitem__("overall", "FAIL"))),
    ("V009", _mutate_report(lambda r: r["checks"].__setitem__(
        "B4_conservation", "applicable_not_implemented_v0 (queued)"))),
    ("V010", _mutate_report(lambda r: r["checks"]["A3_uq_calibration"]["metrics"].__setitem__(
        "empirical_coverage", 1.5))),
    ("V011", _mutate_report(lambda r: r["checks"]["A5_reproducibility"].pop("determinism_class"))),
    # NOT_RUN on A3 / A5 is exempt from V010 / V011, never from the rollup: a
    # NOT_RUN key under a declared overall PASS must still fire V008.
    ("V008", _mutate_report(lambda r: r["checks"]["A3_uq_calibration"].__setitem__("status", "NOT_RUN"))),
    ("V008", _mutate_report(lambda r: r["checks"]["A5_reproducibility"].__setitem__("status", "NOT_RUN"))),
    # FAIL is a measured verdict, so its instrument is graded exactly like a PASS's.
    ("V010", _mutate_report(lambda r: r["checks"]["A3_uq_calibration"].update(status="FAIL", metrics={}))),
    ("V011", _mutate_report(lambda r: r["checks"]["A5_reproducibility"].update(status="FAIL", thresholds={}))),
    # M018 holds the manifest to the contract-v1 schema. One mutation of the
    # synthetic package, then six manifests the checker accepted before it applied
    # the schema, each planted in a copy of the reference package: a missing
    # required block, an id that breaks the id pattern, a timeout of zero, and an
    # uncertainty form, a file kind and a modality outside their enumerations.
    ("M018", _mutate_manifest(lambda m: m.__setitem__("modality", "not_a_modality"))),
    ("M018", _reference_manifest(lambda m: m.pop("lineage"))),
    ("M018", _rename_reference_id("Bad-ID")),
    ("M018", _reference_manifest(lambda m: m["invocation"].__setitem__("timeout_s", 0))),
    ("M018", _reference_manifest(lambda m: m["uncertainty"].__setitem__("form", "vibes"))),
    ("M018", _reference_manifest(lambda m: m["inputs"].append(
        {"name": "geom", "type": "file", "file_kind": "exe", "required": False}))),
    ("M018", _reference_manifest(lambda m: m.__setitem__("modality", "anything_goes"))),
    # Every file the manifest names is inside the package, and a byte count is a
    # non-negative integer. The first two are defects the checker accepted before:
    # the entrypoint moved to ../outside/ with its hash still right, and a byte
    # count of 'not-a-number', which skipped the size comparison altogether.
    ("M012", _reference_package(_move_entrypoint_outside)),
    ("M012", _reference_manifest(lambda m: m["provenance"]["artifacts"][0].__setitem__("bytes", "not-a-number"))),
    ("M012", _weights_beside_the_package),
    ("M012", _weights_by_absolute_path),
    ("M012", _mutate_manifest(lambda m: m["provenance"]["artifacts"][1].__setitem__("bytes", -1))),
    ("M009", _card_beside_the_package),
    ("M010", _report_beside_the_package),
    # A float input or output states its units, and a declared range runs from a
    # smaller to a larger bound. The first two are defects the checker accepted
    # before, planted in the reference package: an inverted input range, and every
    # input and output stripped of its units.
    ("M004", _reference_manifest(lambda m: m["inputs"][0].__setitem__("range", [1123.15, 473.15]))),
    ("M004", _reference_manifest(_strip_units)),
    ("M005", _reference_manifest(_strip_units)),
    ("M004", _mutate_manifest(lambda m: m["inputs"][0].pop("units"))),
    ("M004", _mutate_manifest(lambda m: m["inputs"][0].__setitem__("range", [500.0, 500.0]))),
    ("M005", _mutate_manifest(lambda m: m["outputs"][0].__setitem__("units", " "))),
    # check --smoke runs the entrypoint on the manifest's examples. The first is a
    # defect the checker accepted before: an entrypoint that cannot run, re-pinned
    # so its hash is right. The others answer wrongly in each way S001 names.
    ("S001", _reference_entrypoint('import sys' + LF + 'sys.exit("this model does not run")' + LF)),
    ("S001", _reference_entrypoint('print("not a JSON object")' + LF)),
    ("S001", _reference_entrypoint('import json' + LF + 'print(json.dumps({"status": "error", "error": '
                                   '{"code": "OUT_OF_RANGE", "message": "refused"}}))' + LF)),
    ("S001", _reference_entrypoint('import json' + LF + 'print(json.dumps({"outputs": {"life_cycles": 1.0}}))' + LF)),
    ("S001", _reference_entrypoint('import time' + LF + 'time.sleep(30)' + LF,
                                   lambda m: m["invocation"].__setitem__("timeout_s", 1))),
    ("S001", _reference_manifest(lambda m: m["examples"][0].pop("inputs"))),
    # S002 is a warning: the smoke test could not run, and says why instead of passing.
    ("S002", _reference_manifest(lambda m: m.pop("examples"))),
    # A measured check's status follows from its comparators (V013), which must be
    # well formed and, in a contract 1.1 package, present (V012). The first five are
    # defects the checker accepted before, planted in the reference package: a PASS
    # whose r2 and mae miss their bars, a PASS whose only metric is a sample count,
    # a coverage of 0.50 under a band of [0.85, 0.96], and a conservation PASS with
    # an imbalance of 0.90 over a bar of 0.05 -- reported without comparators, and
    # with one.
    ("V013", _reference_report(_a1_misses_its_bars)),
    ("V012", _reference_report(lambda r: r["checks"]["A4_baseline_beat"].__setitem__("metrics", {"n": 5}))),
    ("V013", _reference_report(lambda r: r["checks"]["A3_uq_calibration"]["metrics"].__setitem__(
        "empirical_coverage", 0.50))),
    ("V012", _reference_report(_b4_passes_over_its_bar(comparators=False))),
    ("V013", _reference_report(_b4_passes_over_its_bar(comparators=True))),
    ("V012", _mutate_report(lambda r: r["checks"]["A1_accuracy"].pop("comparators"))),
    ("V012", _mutate_report(lambda r: r["checks"]["A1_accuracy"].__setitem__("comparators", []))),
    ("V012", _mutate_report(lambda r: r["checks"]["A1_accuracy"]["comparators"][0].__setitem__("op", "<<"))),
    ("V012", _mutate_report(lambda r: r["checks"]["A1_accuracy"]["comparators"][0].__setitem__("bar", "no_such"))),
    ("V013", _mutate_report(lambda r: r["checks"]["A1_accuracy"]["metrics"].__setitem__("value", 9.0))),
    ("V013", _mutate_report(_fail_whose_comparators_hold)),
    ("V009", _mutate_report(lambda r: r["checks"]["B4_conservation"].__setitem__(
        "comparators", _compare(("n", ">=", "imbalance_max"))))),
    # From contract 1.1, bitwise reproducibility means a tolerance of 0. The first is
    # the defect the checker accepted before, planted in the reference package.
    ("V011", _reference_report(_a5_bitwise_at(0.02))),
    ("V011", _mutate_report(_a5_bitwise_at(1e-6))),
    # The report declares the contract version its manifest declares.
    ("V002", _mutate_report(lambda r: r.__setitem__("spec_version", "1.0"))),
    # Honest statuses (contract 1.1). B4 may report NOT_RUN with applicable: true -- the
    # check applies and was not run -- which blocks the rollup like every NOT_RUN, and a
    # NOT_RUN B4 still declares that it applies.
    ("V008", _mutate_report(lambda r: r["checks"].__setitem__("B4_conservation", dict(B4_NOT_RUN)))),
    ("V009", _mutate_report(lambda r: r["checks"].__setitem__("B4_conservation",
                                                              dict(B4_NOT_RUN, applicable=False)))),
    ("V009", _mutate_report(lambda r: r["checks"].__setitem__(
        "B4_conservation", {k: v for k, v in B4_NOT_RUN.items() if k != "applicable"}))),
    # uncertainty.form none declares a point predictor: no per_output block, no
    # calibration, from contract 1.1, and a card that says the model reports no
    # uncertainty. The first keeps the synthetic package's bands under form none.
    ("M007", _mutate_manifest(lambda m: m["uncertainty"].__setitem__("form", "none"))),
    ("M007", _point_predictor_package(calibration=True)),
    ("M007", _point_predictor_package(spec_version="1.0")),
    ("C005", _point_predictor_package(card_says_so=False)),
    # A type: field output states what it holds (contract 1.1). The first is the field
    # output the checker accepted before, declared with nothing but a description; the
    # second is the block a grid producer emits today, which the schema accepts and
    # which lacks kind, support and media_type.
    ("M019", _mutate_manifest(_add_field_output())),
    ("M019", _mutate_manifest(_add_field_output(GRID_PRODUCER_BLOCK))),
    ("M019", _mutate_manifest(lambda m: m["outputs"][0].__setitem__("field", dict(FIELD_BLOCK)))),
    ("M019", _mutate_manifest(_add_field_output(dict(FIELD_BLOCK, units="degC")))),
    ("M019", _mutate_manifest(_add_field_output("a VTK file"))),
    ("M018", _mutate_manifest(_add_field_output(dict(FIELD_BLOCK, media_type="VTK PolyData")))),
    ("M018", _mutate_manifest(_add_field_output(dict(FIELD_BLOCK, kind="tensor")))),
    # A declared licence block names three licences, each an SPDX expression with its
    # text or URL, or NOASSERTION with a note (M020); a 1.1 package without one is
    # warned (M021). The first two are defects the checker accepted before.
    ("M020", _mutate_manifest(lambda m: m["licence"]["model"].__setitem__("spdx", "Apache 2.0"))),
    ("M020", _mutate_manifest(lambda m: m["licence"].pop("weights"))),
    ("M020", _mutate_manifest(lambda m: m["licence"]["model"].__setitem__("spdx", "mit or apache-2.0"))),
    ("M020", _mutate_manifest(lambda m: m["licence"]["training_data"].pop("note"))),
    ("M020", _mutate_manifest(lambda m: m["licence"]["weights"].pop("url"))),
    ("M020", _mutate_manifest(lambda m: m["licence"]["weights"].update(text="../LICENSE"))),
    ("M020", _mutate_manifest(lambda m: m["licence"]["weights"].update(text="./LICENSE.txt"))),
    ("M020", _mutate_manifest(lambda m: m.__setitem__("licence", "Apache-2.0"))),
    ("M021", _mutate_manifest(lambda m: m.pop("licence"))),
    ("M018", _mutate_manifest(lambda m: m["licence"]["model"].__setitem__("url", "ftp://example.invalid/licence"))),
]


@pytest.mark.parametrize("rule,mutate", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_each_rule_can_fail(tmp_path: Path, rule: str, mutate):
    pkg = write_package(tmp_path / "pkg")
    assert vs.check_package(pkg) == [], "fixture must start clean"
    mutate(pkg)
    findings = vs.check_package(pkg, smoke=rule in vs.SMOKE_RULES)
    assert rule in rules_fired(findings), (
        "mutation for %s did not fire it; fired=%s" % (rule, sorted(rules_fired(findings))))


def test_every_error_rule_has_a_negative_test():
    """A rule with no demonstrated failure is an unproven rule."""
    covered = {rule for rule, _ in MUTATIONS}
    # E001, E002 and E003 are environment rules with their own dedicated tests below.
    environment_rules = {"E001", "E002", "E003"}
    declared = {r.id for r in vs.RULES}
    uncovered = declared - covered - environment_rules
    assert uncovered == set(), "rules with no negative test: %s" % sorted(uncovered)


def test_e001_non_directory_is_an_error(tmp_path: Path):
    findings = vs.check_package(tmp_path / "does_not_exist")
    assert "E001" in rules_fired(findings)


def test_e002_missing_yaml_parser_is_an_error_not_a_skip(tmp_path: Path, monkeypatch):
    """A package the checker cannot parse must FAIL, never silently pass."""
    pkg = write_package(tmp_path / "pkg")
    (pkg / "manifest.json").rename(pkg / "manifest.yaml")
    monkeypatch.setitem(sys.modules, "yaml", None)   # makes `import yaml` raise ImportError
    findings = vs.check_package(pkg)
    assert "E002" in rules_fired(findings)
    assert not vs.summarize(findings)["conformant"]


def test_e003_a_missing_manifest_schema_is_an_error_not_a_skip(good: Path, monkeypatch):
    """A checker that cannot read the schema it applies must say so, never pass the manifest."""
    monkeypatch.setattr(vs, "MANIFEST_SCHEMA_PATH", ("schemas", "contract-v1", "no-such-schema.json"))
    findings = vs.check_package(good)
    assert rules_fired(findings) == {"E003"}
    assert not vs.summarize(findings)["conformant"]


def test_e003_a_schema_keyword_the_checker_cannot_apply_is_an_error(good: Path, monkeypatch):
    schema, problem = vs.load_manifest_schema()
    assert problem is None
    schema["properties"]["modality"]["oneOf"] = [{"const": "scalar_in_scalar_out"}]
    monkeypatch.setattr(vs, "_manifest_schema_text", lambda: json.dumps(schema))
    findings = vs.check_package(good)
    assert rules_fired(findings) == {"E003"}
    assert any("oneOf" in f.message for f in findings if f.rule == "E003")


# --------------------------------------------------------------------------- #
# The two rules real validation ladders actually got wrong. Worth their own tests.
# --------------------------------------------------------------------------- #
def test_a_declaration_string_is_not_a_conservation_measurement(tmp_path: Path):
    """The exact shape the scalar ladder green-stamps today must fail here.

    The scalar gate engine (`opencontractml.gate`) grades V2.3 by
    `v not in ("not declared", None, "")`, so the string below is a PASS there.
    """
    pkg = write_package(tmp_path / "pkg")
    rep = base_report()
    rep["checks"]["B4_conservation"] = (
        "applicable_not_implemented_v0 (displacement proportional to load at fixed geometry -- queued)")
    (pkg / "validation_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8", newline=LF)
    fired = rules_fired(vs.check_package(pkg))
    assert "V009" in fired and "V005" in fired


def test_asserting_applicability_without_a_number_fails(tmp_path: Path):
    """applicable: true obliges a measured relative imbalance."""
    pkg = write_package(tmp_path / "pkg")
    rep = base_report()
    rep["checks"]["B4_conservation"] = {
        "status": "PASS", "applicable": True, "quantity": "energy",
        "control_volume": "whole part", "scope": "control_volume",
        "metrics": {"note": "implementation queued"}, "thresholds": {"imbalance_max": 0.05},
    }
    (pkg / "validation_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8", newline=LF)
    findings = vs.check_package(pkg)
    assert "V009" in rules_fired(findings)
    assert any("relative_imbalance" in f.message for f in findings if f.rule == "V009")


def test_not_applicable_conservation_needs_a_reason_and_the_right_status(tmp_path: Path):
    pkg = write_package(tmp_path / "pkg")
    rep = base_report()
    rep["checks"]["B4_conservation"] = {"status": "PASS", "applicable": False}
    (pkg / "validation_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8", newline=LF)
    messages = [f.message for f in vs.check_package(pkg) if f.rule == "V009"]
    assert any("must state why" in m for m in messages)
    assert any("NOT_APPLICABLE" in m for m in messages)


def test_not_run_blocks_the_rollup(tmp_path: Path):
    """NOT_RUN is never a silent pass -- the recomputed overall must go FAIL."""
    pkg = write_package(tmp_path / "pkg")
    rep = base_report()
    rep["checks"]["C2_serve_parity"] = {"status": "NOT_RUN", "reason": "no export built"}
    (pkg / "validation_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8", newline=LF)
    findings = vs.check_package(pkg)
    assert "V008" in rules_fired(findings)
    assert any("recomputing from the checks gives FAIL" in f.message for f in findings)


def test_not_applicable_with_a_reason_does_not_block(tmp_path: Path):
    """The counterpart: a stated inapplicability is allowed to keep a package green."""
    pkg = write_package(tmp_path / "pkg")
    rep = base_report()
    rep["checks"]["C2_serve_parity"] = {"status": "NOT_APPLICABLE",
                                        "reason": "no torch-free export exists for this estimator"}
    (pkg / "validation_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8", newline=LF)
    assert vs.check_package(pkg) == []


# --------------------------------------------------------------------------- #
# NOT_RUN on A3 and A5: an honest status, graded by the rollup (V008) rather
# than by the legibility rules V010 and V011, which read only a check that ran.
# --------------------------------------------------------------------------- #
NOT_RUN_REASON = "no model has been trained, so nothing was measured"


def _copy_reference_package(root: Path) -> Path:
    """A scratch copy of the committed reference package, safe to mutate."""
    import shutil
    pytest.importorskip("yaml", reason="the reference package ships manifest.yaml")
    pkg = root / "reference-copy"
    shutil.copytree(REFERENCE_PACKAGE, pkg)
    return pkg


def _rewrite_report(pkg: Path, fn) -> None:
    rep = json.loads((pkg / "validation_report.json").read_text(encoding="utf-8"))
    fn(rep)
    (pkg / "validation_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8", newline=LF)


def test_an_honest_a3_not_run_is_conformant(tmp_path: Path):
    """A3 reported NOT_RUN under an overall FAIL is a truthful report, and it passes.

    Before NOT_RUN was split out of V010 this report was rejected for four
    missing measurements, while the dishonest alternative -- NOT_APPLICABLE with
    any reason at all -- was accepted.
    """
    pkg = _copy_reference_package(tmp_path)

    def a3_not_run(rep):
        rep["checks"]["A3_uq_calibration"] = {"status": "NOT_RUN", "reason": "no calibration split yet"}
        rep["overall"] = "FAIL"

    _rewrite_report(pkg, a3_not_run)
    assert vs.check_package(pkg) == []


def test_an_untrained_package_with_every_tier_a_key_not_run_is_conformant(tmp_path: Path):
    """The report an untrained contract package ships: Tier A all NOT_RUN, overall FAIL.

    Before the split this exact report drew four V010 findings and two V011
    findings, so a producer that told the truth about an untrained model could
    not ship a conformant package.
    """
    pkg = _copy_reference_package(tmp_path)

    def untrained(rep):
        for key in vs.TIER_A:
            rep["checks"][key] = {"status": "NOT_RUN", "reason": NOT_RUN_REASON}
        rep["overall"] = "FAIL"

    _rewrite_report(pkg, untrained)
    assert vs.check_package(pkg) == []


@pytest.mark.parametrize("key", ["A3_uq_calibration", "A5_reproducibility"])
def test_not_run_still_blocks_the_rollup(tmp_path: Path, key: str):
    """The split narrows V010 / V011; it never lets NOT_RUN through the rollup."""
    pkg = _copy_reference_package(tmp_path)
    _rewrite_report(pkg, lambda rep: rep["checks"].__setitem__(key, {"status": "NOT_RUN", "reason": NOT_RUN_REASON}))
    fired = rules_fired(vs.check_package(pkg))
    assert fired == {"V008"}, "overall PASS over a NOT_RUN key must fail V008 and nothing else; fired=%s" % sorted(fired)


@pytest.mark.parametrize("key,rule", [("A3_uq_calibration", "V010"), ("A5_reproducibility", "V011")])
def test_a_measured_fail_is_still_graded_for_legibility(tmp_path: Path, key: str, rule: str):
    """FAIL is a measured verdict, so its instrument must be as legible as a PASS's."""
    pkg = _copy_reference_package(tmp_path)

    def fail_without_its_instrument(rep):
        rep["checks"][key] = {"status": "FAIL", "metrics": {"value": 0.5}, "thresholds": {"limit": 0.9},
                              "comparators": _compare(("value", ">=", "limit"))}
        rep["overall"] = "FAIL"

    _rewrite_report(pkg, fail_without_its_instrument)
    assert rules_fired(vs.check_package(pkg)) == {rule}


def test_b4_not_run_with_applicable_true_is_an_honest_blocking_status(tmp_path: Path):
    """The conservation check applies and was not run: conformant under an overall FAIL, never under a PASS.

    Before contract 1.1, V009 demanded a measurement from this check, so a
    producer whose model conserves a quantity it had not measured could only call
    the check NOT_APPLICABLE, which is false.
    """
    pkg = _copy_reference_package(tmp_path)
    _rewrite_report(pkg, lambda rep: (rep["checks"].__setitem__("B4_conservation", dict(B4_NOT_RUN)),
                                      rep.__setitem__("overall", "FAIL")))
    assert vs.check_package(pkg) == []
    _rewrite_report(pkg, lambda rep: rep.__setitem__("overall", "PASS"))
    findings = vs.check_package(pkg)
    assert rules_fired(findings) == {"V008"}
    assert "recomputing from the checks gives FAIL (1 blocking)" in findings[0].message


def test_a_not_run_check_is_read_for_no_measurement_on_any_key(tmp_path: Path):
    """No rule reads a measurement from NOT_RUN, whatever the key; every NOT_RUN key blocks the rollup."""
    pkg = _copy_reference_package(tmp_path)

    def every_key_not_run(rep):
        for key in vs.LADDER:
            rep["checks"][key] = {"status": "NOT_RUN", "reason": NOT_RUN_REASON}
        rep["checks"]["B4_conservation"]["applicable"] = True
        rep["overall"] = "FAIL"

    _rewrite_report(pkg, every_key_not_run)
    assert vs.check_package(pkg) == []


def test_a_point_predictor_with_no_bands_is_conformant(tmp_path: Path):
    """uncertainty.form none, an empty per_output, no calibration, and a card that says so."""
    root = tmp_path / "pkg"
    write_package(root)
    _point_predictor_package()(root)
    assert vs.check_package(root) == []


def test_form_none_names_each_band_it_still_declares(tmp_path: Path):
    root = write_package(tmp_path / "pkg")
    _mutate_manifest(lambda m: m["uncertainty"].__setitem__("form", "none"))(root)
    messages = [f.message for f in vs.check_package(root) if f.rule == "M007"]
    assert messages == ["uncertainty.form is 'none', so no output carries a band, but uncertainty.per_output "
                        "declares a block for 'life_cycles'"]


def test_a_complete_field_block_is_conformant(tmp_path: Path):
    root = write_package(tmp_path / "pkg")
    _mutate_manifest(_add_field_output(FIELD_BLOCK))(root)
    assert vs.check_package(root) == []


def test_a_bare_field_output_keeps_conforming_in_a_contract_1_0_package(tmp_path: Path):
    """The 1.0 shape -- a field output with no block -- conforms in a package that declares 1.0."""
    man = base_manifest()
    _add_field_output()(man)
    man["spec_version"] = "1.0"
    rep = base_report()
    rep["spec_version"] = "1.0"
    card = base_card().replace('spec_version: "1.1"', 'spec_version: "1.0"')
    assert vs.check_package(write_package(tmp_path / "pkg", manifest=man, report=rep, card=card)) == []


def test_the_grid_producers_block_passes_the_schema_and_lacks_three_keys(tmp_path: Path):
    """What a grid producer emits today is structurally valid and, under 1.1, incomplete -- and says which keys."""
    root = write_package(tmp_path / "pkg")
    _mutate_manifest(_add_field_output(GRID_PRODUCER_BLOCK))(root)
    findings = vs.check_package(root)
    assert [(f.rule, f.where) for f in findings] == [("M019", "manifest.json outputs[1]")]
    assert "lacks kind, support, media_type" in findings[0].message


@pytest.mark.parametrize("expression", [
    "MIT", "Apache-2.0", "GPL-2.0+", "GPL-2.0-only WITH Classpath-exception-2.0",
    "(MIT OR Apache-2.0) AND BSD-3-Clause", "MIT OR Apache-2.0 AND BSD-3-Clause", "LicenseRef-proprietary",
    "DocumentRef-spdx-tool-1.2:LicenseRef-MIT-Style-2", "  MIT  ",
])
def test_an_spdx_expression_is_accepted(expression: str):
    assert vs.spdx_expression_problem(expression) is None


@pytest.mark.parametrize("expression,why", [
    ("", "not a non-empty string"),
    (None, "not a non-empty string"),
    ("Apache 2.0", "'2.0' follows a complete expression without an operator"),
    ("MIT/Apache-2.0", "is not a licence identifier"),
    ("MIT, Apache-2.0", "is not a licence identifier"),
    ("mit or apache-2.0", "in upper case"),
    ("MIT and Apache-2.0", "in upper case"),
    ("(MIT OR Apache-2.0", "is not closed"),
    ("MIT)", "follows a complete expression"),
    ("MIT AND", "ends where a licence identifier is expected"),
    ("AND MIT", "stands where a licence identifier is expected"),
    ("GPL-2.0 WITH", "ends where an exception identifier is expected"),
    ("MIT WITH (X)", "stands where an exception identifier is expected"),
    ("GPL-2.0 WITH Classpath-exception-2.0+", "is not an exception identifier"),
    ("NOASSERTION AND MIT", "is not a licence"),
    ("NONE", "is not a licence"),
])
def test_a_malformed_spdx_expression_is_named(expression, why):
    problem = vs.spdx_expression_problem(expression)
    assert problem is not None and why in problem, problem


def test_the_reference_package_declares_its_licences():
    import yaml
    man = yaml.safe_load((REFERENCE_PACKAGE / "manifest.yaml").read_text(encoding="utf-8"))
    assert set(man["licence"]) == set(vs.LICENCE_MEMBERS)
    assert vs.check_package(REFERENCE_PACKAGE) == []


def test_a_1_1_package_without_a_licence_block_earns_the_warning_only(tmp_path: Path):
    """No licence block is a warning, never an error: the package stays conformant and says what it lacks."""
    pkg = _copy_reference_package(tmp_path)
    _rewrite_yaml_manifest(pkg, lambda m: m.pop("licence"))
    findings = vs.check_package(pkg)
    assert [(f.rule, f.severity) for f in findings] == [("M021", "WARN")]
    assert vs.summarize(findings)["conformant"]


def test_the_warning_names_a_license_key_the_contract_does_not_read(tmp_path: Path):
    pkg = _copy_reference_package(tmp_path)
    _rewrite_yaml_manifest(pkg, lambda m: m.__setitem__("license", m.pop("licence")))
    [finding] = vs.check_package(pkg)
    assert finding.rule == "M021" and "'license' key" in finding.message


def test_only_the_two_unmeasured_statuses_are_exempt():
    """Pins the split: exempting FAIL or PASS would make a measured verdict unreadable."""
    assert set(vs._UNMEASURED_STATUSES) == {"NOT_RUN", "NOT_APPLICABLE"}
    assert set(vs._UNMEASURED_STATUSES) == set(vs.STATUSES) - {"PASS", "FAIL"}


# --------------------------------------------------------------------------- #
# The comparator convention: required from contract 1.1, optional before, and
# read only where a check carries a measurement.
# --------------------------------------------------------------------------- #
def _as_contract_1_0(root: Path, report=None) -> Path:
    man = base_manifest()
    man["spec_version"] = "1.0"
    rep = base_report() if report is None else report
    rep["spec_version"] = "1.0"
    card = base_card().replace('spec_version: "1.1"', 'spec_version: "1.0"')
    return write_package(root, manifest=man, report=rep, card=card)


def test_a_contract_1_0_package_needs_no_comparators(tmp_path: Path):
    rep = base_report()
    for check in rep["checks"].values():
        check.pop("comparators", None)
    assert vs.check_package(_as_contract_1_0(tmp_path / "pkg", rep)) == []


def test_a_contract_1_0_package_is_held_to_the_comparators_it_declares(tmp_path: Path):
    rep = base_report()
    rep["checks"]["A1_accuracy"]["metrics"]["value"] = 9.0      # value <= limit (2.0) no longer holds
    assert rules_fired(vs.check_package(_as_contract_1_0(tmp_path / "pkg", rep))) == {"V013"}


def test_bitwise_at_a_small_tolerance_is_still_accepted_in_a_contract_1_0_package(tmp_path: Path):
    """Contract 1.0 called the scalar ladder's 1e-6 'effectively bitwise'; 1.1 changes that only for 1.1."""
    rep = base_report()
    _a5_bitwise_at(1e-6)(rep)
    assert vs.check_package(_as_contract_1_0(tmp_path / "pkg", rep)) == []


def test_comparators_on_an_unmeasured_check_are_not_read(tmp_path: Path):
    rep = base_report()
    rep["checks"]["C2_serve_parity"] = {"status": "NOT_APPLICABLE", "reason": "no export exists for this estimator",
                                        "comparators": "not even a list"}
    assert vs.check_package(write_package(tmp_path / "pkg", report=rep)) == []


def test_v013_names_the_comparison_that_does_not_hold(tmp_path: Path):
    rep = base_report()
    rep["checks"]["A1_accuracy"]["metrics"]["value"] = 9.0
    findings = vs.check_package(write_package(tmp_path / "pkg", report=rep))
    [finding] = [f for f in findings if f.rule == "V013"]
    assert "value = 9.0 <= limit = 2.0 does not hold" in finding.message
    assert finding.where.endswith("validation_report.json checks.A1_accuracy")


def test_unhashed_entrypoint_is_rejected(tmp_path: Path):
    """The dispatched executable must be one of the hashed artifacts."""
    pkg = write_package(tmp_path / "pkg")
    man = base_manifest()
    man["invocation"]["executable"] = "./some_other_script.py"
    (pkg / "manifest.json").write_text(json.dumps(man, indent=2), encoding="utf-8", newline=LF)
    findings = vs.check_package(pkg)
    assert "M013" in rules_fired(findings)
    assert any("unverifiable" in f.message for f in findings)


def test_a_symbolic_link_out_of_the_package_is_outside_it(tmp_path: Path):
    """A link inside the directory that resolves outside it names a file the package does not carry."""
    pkg = write_package(tmp_path / "pkg")
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(WEIGHTS_SRC, encoding="utf-8", newline=LF)
    (pkg / "model_weights.json").unlink()
    try:
        (pkg / "model_weights.json").symlink_to(elsewhere)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("this host cannot create a symbolic link here: %s" % exc)
    findings = vs.check_package(pkg)
    assert any(f.rule == "M012" and "outside the package" in f.message for f in findings), findings


@pytest.mark.parametrize("rel,reason", [
    ("model.bin", None),
    ("./sub/model.bin", None),
    ("sub/../model.bin", None),
    ("../model.bin", "resolves outside the package directory"),
    ("sub/../../model.bin", "resolves outside the package directory"),
    ("/etc/hosts", "is absolute"),
    ("\\model.bin", "is absolute"),
    ("\\\\server\\share\\model.bin", "is absolute"),
    ("C:/models/model.bin", "is absolute"),
    ("C:model.bin", "is absolute"),
    ("   ", "is empty"),
])
def test_outside_package_names_what_is_wrong(tmp_path: Path, rel: str, reason):
    assert vs.outside_package(tmp_path, rel) == reason


# --------------------------------------------------------------------------- #
# check --smoke: what it runs, what it never runs, and what it reports when it
# cannot run.
# --------------------------------------------------------------------------- #
def _no_processes(monkeypatch):
    import subprocess

    def refuse(*args, **kwargs):
        raise AssertionError("the checker started a process: %r" % (args,))
    monkeypatch.setattr(subprocess, "Popen", refuse)


def test_the_default_check_executes_nothing(tmp_path: Path, monkeypatch):
    """Without --smoke the check reads files and runs nothing, the entrypoint included."""
    import shutil
    pkg = tmp_path / "pkg"
    shutil.copytree(REFERENCE_PACKAGE, pkg)
    _no_processes(monkeypatch)
    assert vs.check_package(pkg) == []
    assert vs.main(["check", str(pkg)]) == 0


def test_smoke_passes_the_reference_package():
    assert vs.check_package(REFERENCE_PACKAGE, smoke=True) == []


def test_smoke_runs_from_a_relative_package_path(monkeypatch):
    """The entrypoint is launched by absolute path, because it runs in the package directory."""
    monkeypatch.chdir(REFERENCE_PACKAGE.parents[1])
    assert vs.main(["check", "--smoke", "examples/reference-package"]) == 0


def test_smoke_without_examples_is_a_warning_with_its_reason(good: Path):
    findings = vs.check_package(good, smoke=True)
    assert [(f.rule, f.severity) for f in findings] == [("S002", "WARN")]
    assert "declares no examples" in findings[0].message
    assert vs.summarize(findings)["conformant"]


def test_smoke_never_runs_an_entrypoint_the_static_check_did_not_verify(tmp_path: Path, monkeypatch):
    import shutil
    pkg = tmp_path / "pkg"
    shutil.copytree(REFERENCE_PACKAGE, pkg)
    with open(pkg / "predict.py", "a", encoding="utf-8", newline=LF) as fh:
        fh.write("# edited after packaging" + LF)
    _no_processes(monkeypatch)
    findings = vs.check_package(pkg, smoke=True)
    assert rules_fired(findings) == {"M013", "S002"}
    assert any("did not verify the entrypoint" in f.message for f in findings if f.rule == "S002")


def test_smoke_reports_a_module_missing_here_as_not_run_rather_than_failed(tmp_path: Path):
    """An environment without a model's dependency cannot judge the model; it says so instead."""
    root = tmp_path / "pkg"
    write_package(root)
    _reference_entrypoint("import zz_a_module_no_environment_has" + LF)(root)
    findings = vs.check_package(root, smoke=True)
    assert rules_fired(findings) == {"S002"}
    assert "zz_a_module_no_environment_has" in findings[0].message


def test_numeric_leaves_ignores_booleans():
    """`passed: true` must not count as the measurement that justifies a PASS."""
    assert vs.numeric_leaves({"passed": True, "ok": False}) == []
    assert vs.numeric_leaves({"passed": True, "rmse": 0.5}) == [0.5]


def test_front_matter_must_be_flat(tmp_path: Path):
    front, _body, error = vs.split_front_matter("---" + LF + "model_id: x" + LF + "nested:" + LF
                                                + "  a: 1" + LF + "---" + LF + "body")
    assert front is None and error is not None and "flat" in error


# --------------------------------------------------------------------------- #
# The shipped schema artifacts must not drift from the checker (a schema and the
# code that mirrors it can diverge silently).
# --------------------------------------------------------------------------- #
# Resolved out of the *installed* package, not out of the source tree, so this
# guard measures what a consumer actually gets. Under an editable install that
# is still `src/opencontractml/schemas/`; from a wheel it is site-packages.
SCHEMA_DIR = Path(str(resources.files("opencontractml") / "schemas" / "contract-v1"))


def test_committed_vocabulary_matches_the_module():
    committed = json.loads((SCHEMA_DIR / "contract-vocabulary.json").read_text(encoding="utf-8"))
    assert committed == vs.vocabulary(), (
        "schemas/contract-v1/contract-vocabulary.json is stale; regenerate with "
        "`python -m opencontractml.verify vocabulary --out schemas/contract-v1/contract-vocabulary.json`")


def test_manifest_schema_required_keys_match_the_checker():
    """The JSON Schema and verify must demand the same top-level keys."""
    schema = json.loads((SCHEMA_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    required = set(schema["required"])
    checker_requires = set(vs._IDENTITY) | {
        "owner", "inputs", "outputs", "uncertainty", "invocation", "model_card",
        "provenance", "validation", "spec_version", "lineage",
    }
    assert required == checker_requires, (
        "schema requires %s; checker requires %s"
        % (sorted(required - checker_requires), sorted(checker_requires - required)))


def test_manifest_schema_enums_match_the_checker():
    schema = json.loads((SCHEMA_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    props = schema["properties"]
    assert set(props["inputs"]["items"]["properties"]["type"]["enum"]) == vs._INPUT_TYPES
    assert set(props["outputs"]["items"]["properties"]["type"]["enum"]) == vs._OUTPUT_TYPES
    assert {props["invocation"]["properties"]["protocol"]["const"]} == vs._PROTOCOLS
    roles = props["provenance"]["properties"]["artifacts"]["items"]["properties"]["role"]["enum"]
    assert set(roles) == vs._ARTIFACT_ROLES


def test_reference_manifest_validates_against_the_json_schema():
    """The schema is only worth shipping if the reference package satisfies it."""
    jsonschema = pytest.importorskip("jsonschema")
    yaml = pytest.importorskip("yaml")
    schema = json.loads((SCHEMA_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    pkg = Path(__file__).resolve().parents[1] / "examples" / "reference-package"
    data = yaml.safe_load((pkg / "manifest.yaml").read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(data),
                    key=lambda e: e.json_path)
    assert errors == [], [f"{e.json_path}: {e.message}" for e in errors]


def test_json_schema_rejects_a_bad_hash():
    """The schema's own hash pattern must be able to fail."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((SCHEMA_DIR / "manifest.schema.json").read_text(encoding="utf-8"))
    man = base_manifest()
    man["provenance"]["artifacts"][0]["sha256"] = "NOTAHASH"
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(man))
    assert any("sha256" in e.json_path for e in errors), [e.json_path for e in errors]


def test_checker_emits_lf_only(tmp_path: Path):
    """Everything the checker writes must be LF.

    A CRLF artifact in an `eol=lf` repo has a different hash on disk than in the
    blob, so a package that was conformant when built fails M013 after the next
    checkout. The reference package tripped exactly this when it was first built.
    """
    pkg = write_package(tmp_path / "pkg")
    out_json = tmp_path / "report.json"
    vocab = tmp_path / "vocab.json"
    assert vs.main(["check", str(pkg), "--json", str(out_json)]) == 0
    assert vs.main(["vocabulary", "--out", str(vocab)]) == 0
    for path in (out_json, vocab):
        assert b"\r\n" not in path.read_bytes(), "%s was written with CRLF" % path.name
