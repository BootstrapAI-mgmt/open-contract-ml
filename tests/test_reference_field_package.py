"""The reference field package, examples/reference-field-package/, and the three clauses it answers.

It is the worked instance of a Contract 1.1 field output: a ``type: field`` output with
its field block, answered by artifact reference, with its band in two more references
and a scalar in the frame. Contract 1.1 serves field models only if three things hold
together, and one test below holds each:

1. ``check``, ``check --smoke`` and ``check --json`` each accept the field package,
   with no finding of any severity;
2. each 1.0 package in ``tests/fixtures/producer_packages/``, and the scalar
   reference package, gets exactly the findings ``known-findings.json`` records for it
   (none, for a package without an entry): 1.1 rejects nothing that conformed before;
3. the field package, once it declares ``spec_version: "2.0"``, is refused by ``M002``
   and by nothing else.

Beside them: the builder reproduces every generated file byte for byte and says so when
one differs; a copy whose entrypoint misdescribes a payload, or whose weights were
edited, is red; and a payload holds the nodes, the values and the layout the manifest
and the frame declare.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from opencontractml import verify as vs

REPO = Path(__file__).resolve().parents[1]
FIELD_PACKAGE = REPO / "examples" / "reference-field-package"
REFERENCE_PACKAGE = REPO / "examples" / "reference-package"
BUILDER = REPO / "examples" / "build_reference_field_package.py"
FIXTURES = REPO / "tests" / "fixtures" / "producer_packages"
KNOWN_FINDINGS = json.loads((FIXTURES / "known-findings.json").read_text(encoding="utf-8"))["packages"]

yaml = pytest.importorskip("yaml", reason="the field package ships manifest.yaml")


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "reference-field-package"
    shutil.copytree(FIELD_PACKAGE, target)
    return target


def _replace(path: Path, old: str, new: str) -> None:
    text = path.read_bytes().decode("utf-8")
    assert text.count(old) == 1, "%s: expected one %r" % (path.name, old)
    path.write_bytes(text.replace(old, new).encode("utf-8"))


def _repin(pkg: Path, rel: str) -> None:
    """Point the copy's manifest at the bytes now in ``rel``, so the static check passes again."""
    manifest = (pkg / "manifest.yaml").read_text(encoding="utf-8")
    block = re.search(r"- path: \./%s\n      role: \w+\n      sha256: ([0-9a-f]{64})\n      bytes: (\d+)\n"
                      % re.escape(rel), manifest)
    data = (pkg / rel).read_bytes()
    pinned = block.group(0).replace(block.group(1), hashlib.sha256(data).hexdigest()).replace(
        "bytes: %s" % block.group(2), "bytes: %d" % len(data))
    _replace(pkg / "manifest.yaml", block.group(0), pinned)


def _dispatch(pkg: Path, request: dict, run_dir: Path) -> list:
    run_dir.mkdir()
    proc = subprocess.run([sys.executable, str(pkg / "predict.py")], input=json.dumps(request), capture_output=True,
                          text=True, encoding="utf-8", cwd=str(run_dir), timeout=60)
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Clause 1: check, check --smoke and check --json accept the field package.
# --------------------------------------------------------------------------- #
def test_clause_1_check_accepts_the_field_package():
    assert vs.check_package(FIELD_PACKAGE) == []


def test_clause_1_check_smoke_accepts_the_field_package():
    assert vs.check_package(FIELD_PACKAGE, smoke=True) == []


def test_clause_1_check_json_records_no_finding_and_the_smoke_verifies_references(tmp_path: Path):
    for smoke, name in ((False, "record.json"), (True, "record-smoke.json")):
        argv = ["check", str(FIELD_PACKAGE), "--json", str(tmp_path / name)] + (["--smoke"] if smoke else [])
        assert vs.main(argv) == 0
        record = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert record["conformant"] is True and record["findings"] == [], record["findings"]
        assert (record["n_error"], record["n_warn"], record["spec_version"]) == (0, 0, "1.1")
        for rule in ("M019", "M020", "M021", "V009", "V012", "V013"):
            assert record["rules"][rule]["state"] == "evaluated", rule
    # the smoke run really verified artifact references against the files the entrypoint wrote
    assert record["smoke"] is True and record["rules"]["S003"]["state"] == "evaluated"


# --------------------------------------------------------------------------- #
# Clause 2: the 1.0 packages and the scalar reference package, exactly as recorded.
# --------------------------------------------------------------------------- #
def test_clause_2_the_1_0_packages_and_the_scalar_reference_get_exactly_the_recorded_findings():
    packages = sorted(p for p in FIXTURES.iterdir() if p.is_dir()) + [REFERENCE_PACKAGE]
    assert len(packages) == 5
    for pkg in packages[:-1]:
        assert re.search(r'^spec_version: "1\.0"$', (pkg / "manifest.yaml").read_text(encoding="utf-8"), re.M), pkg
    for pkg in packages:
        found = sorted((f.rule, f.where, f.message) for f in vs.check_package(pkg))
        recorded = sorted((f["rule"], f["where"], f["message"])
                          for f in KNOWN_FINDINGS.get(pkg.name, {}).get("findings", []))
        assert found == recorded, "%s: only found %s; only recorded %s" % (
            pkg.name, sorted(set(found) - set(recorded)), sorted(set(recorded) - set(found)))
    assert REFERENCE_PACKAGE.name not in KNOWN_FINDINGS


# --------------------------------------------------------------------------- #
# Clause 3: declaring 2.0 is refused.
# --------------------------------------------------------------------------- #
def test_clause_3_declaring_spec_version_2_0_is_refused_by_m002_alone(tmp_path: Path):
    pkg = _copy(tmp_path)
    _replace(pkg / "manifest.yaml", 'spec_version: "1.1"', 'spec_version: "2.0"')
    _replace(pkg / "model_card.md", 'spec_version: "1.1"', 'spec_version: "2.0"')
    _replace(pkg / "validation_report.json", '"spec_version": "1.1"', '"spec_version": "2.0"')
    findings = vs.check_package(pkg)
    assert [(f.rule, f.severity) for f in findings] == [("M002", "ERROR")], findings
    assert "supports major <= 1" in findings[0].message
    assert vs.main(["check", str(pkg)]) == 1


# --------------------------------------------------------------------------- #
# The builder, and planted defects.
# --------------------------------------------------------------------------- #
def _builder(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(BUILDER), *args], capture_output=True, text=True, timeout=300)


def test_the_builder_reproduces_every_generated_file():
    out = _builder("--check")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "4 of 4 generated files reproduce" in out.stdout


def test_the_builder_check_names_a_file_that_does_not_reproduce(tmp_path: Path):
    pkg = _copy(tmp_path)
    _replace(pkg / "validation_report.json", '"overall": "PASS"', '"overall": "PASS" ')
    out = _builder("--check", "--package", str(pkg))
    assert out.returncode == 1, out.stdout + out.stderr
    assert [line for line in out.stdout.splitlines() if line.startswith("differs from a rebuild:")] == [
        "differs from a rebuild: %s" % (pkg.resolve() / "validation_report.json")]
    assert "3 of 4 generated files reproduce" in out.stdout


def test_a_copy_whose_entrypoint_misstates_a_payload_size_fails_s003(tmp_path: Path):
    pkg = _copy(tmp_path)
    _replace(pkg / "predict.py", '"bytes": len(written),', '"bytes": len(written) + 1,')
    _repin(pkg, "predict.py")
    assert vs.check_package(pkg) == []                     # the static check cannot see it
    findings = vs.check_package(pkg, smoke=True)
    assert findings and {f.rule for f in findings} == {"S003"}, findings
    assert any("bytes, not the declared" in f.message for f in findings)


def test_a_copy_with_edited_weights_fails_m013(tmp_path: Path):
    pkg = _copy(tmp_path)
    _replace(pkg / "model_weights.json", '"amplitude": ', '"amplitude":  ')
    findings = vs.check_package(pkg)
    assert {f.rule for f in findings} == {"M013"}, findings


# --------------------------------------------------------------------------- #
# The payload is what the manifest and the frame say it is.
# --------------------------------------------------------------------------- #
def test_a_payload_holds_the_declared_nodes_values_and_layout(tmp_path: Path):
    manifest = yaml.safe_load((FIELD_PACKAGE / "manifest.yaml").read_text(encoding="utf-8"))
    output = manifest["outputs"][0]
    inputs = manifest["examples"][1]["inputs"]
    (frame,) = _dispatch(FIELD_PACKAGE, {"run_id": "layout", "mode": "single", "inputs": inputs}, tmp_path / "run")
    ref = frame["outputs"]["temperature_rise"]
    assert vs.reference_problems(ref, tmp_path / "run", output["field"]["media_type"], output["field"]["units"]) == []
    piece = ET.parse(tmp_path / "run" / ref["path"]).getroot().find("PolyData/Piece")
    values = [float(v) for v in piece.find("PointData/DataArray[@Name='temperature_rise']").text.split()]
    points = [float(v) for v in piece.find("Points/DataArray").text.split()]
    rows, cols = output["field"]["shape"]
    assert int(piece.get("NumberOfPoints")) == len(values) == rows * cols == ref["field"]["n_nodes"]
    assert [min(values), max(values)] == ref["field"]["range"]
    # the declared layout: entry j * cols + i sits at x = i L / (cols - 1), y = j W / (rows - 1)
    for j in (0, rows // 2, rows - 1):
        for i in (0, cols // 2, cols - 1):
            x, y, z = points[3 * (j * cols + i):3 * (j * cols + i) + 3]
            want = (i * inputs["length_m"] / (cols - 1), j * inputs["width_m"] / (rows - 1), 0.0)
            assert (x, y, z) == pytest.approx(want)
    assert values[(rows // 2) * cols + cols // 2] == frame["outputs"]["peak_rise"] == max(values)
    assert values[0] == 0.0                               # every edge is held at zero rise
