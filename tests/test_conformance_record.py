"""The conformance record ``open-contract-ml check --json`` writes.

A record must let a reader tell a rule that was evaluated and passed from one that
never ran. So every rule of the checker appears with a state -- ``evaluated``,
``fired`` (with how many findings) or ``not_evaluated`` (with the reason) -- beside
the checker's version, the digests of the documents it read and when it ran. The
record's JSON Schema ships in the package and lists every rule id as required;
these tests hold records of very different packages to it, plant defects in a
record to show the schema rejects them, and pin the states the checker reports
where a rule cannot apply.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
import shutil
from importlib import resources
from pathlib import Path

import pytest

from opencontractml import verify as vs

REPO = Path(__file__).resolve().parents[1]
REFERENCE_PACKAGE = REPO / "examples" / "reference-package"
PRODUCER_PACKAGES = REPO / "tests" / "fixtures" / "producer_packages"
SCHEMA_PATH = Path(str(resources.files("opencontractml") / "schemas" / "contract-v1"
                       / "conformance-record.schema.json"))


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _errors(document) -> list:
    jsonschema = pytest.importorskip("jsonschema", reason="the record is validated with the jsonschema package")
    return sorted(e.message for e in jsonschema.Draft202012Validator(_schema()).iter_errors(document))


def _states(record: dict) -> dict:
    out: dict = {}
    for rule, state in record["rules"].items():
        out.setdefault(state["state"], set()).add(rule)
    return out


def _several_defects(root: Path) -> Path:
    import yaml
    pkg = root / "defective"
    shutil.copytree(REFERENCE_PACKAGE, pkg)
    manifest = yaml.safe_load((pkg / "manifest.yaml").read_text(encoding="utf-8"))
    manifest["modality"] = "anything_goes"
    manifest["provenance"]["artifacts"][0]["bytes"] = "not-a-number"
    (pkg / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8", newline="\n")
    (pkg / "model_card.md").unlink()
    return pkg


# --------------------------------------------------------------------------- #
# The schema and the rule table.
# --------------------------------------------------------------------------- #
def test_the_record_schema_is_a_valid_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator.check_schema(_schema())


def test_the_record_schema_requires_exactly_the_rules_this_checker_has():
    required = _schema()["$defs"]["record"]["properties"]["rules"]["required"]
    assert required == [r.id for r in vs.RULES], (
        "conformance-record.schema.json and verify.RULES disagree; a rule added to the checker is a rule its "
        "record must report")


# --------------------------------------------------------------------------- #
# Records of different packages, each valid and each internally consistent.
# --------------------------------------------------------------------------- #
def _records(tmp_path: Path) -> dict:
    no_manifest = tmp_path / "no-manifest"
    no_manifest.mkdir()
    return {
        "reference": vs.conformance_record(REFERENCE_PACKAGE),
        "reference --smoke": vs.conformance_record(REFERENCE_PACKAGE, smoke=True),
        "several defects": vs.conformance_record(_several_defects(tmp_path)),
        "not a directory": vs.conformance_record(tmp_path / "does-not-exist"),
        "no manifest": vs.conformance_record(no_manifest),
        **{pkg.name: vs.conformance_record(pkg) for pkg in sorted(PRODUCER_PACKAGES.iterdir()) if pkg.is_dir()},
    }


def test_every_record_is_valid_and_names_every_rule_with_a_state(tmp_path: Path):
    for name, record in _records(tmp_path).items():
        assert _errors(record) == [], name
        assert set(record["rules"]) == {r.id for r in vs.RULES}, name
        for rule, state in record["rules"].items():
            assert state["state"] in vs.RULE_STATES, (name, rule)
            assert state["severity"] == vs.RULES_BY_ID[rule].severity, (name, rule)
            if state["state"] == "not_evaluated":
                assert state["reason"].strip() and state["reason"] != "not reached", (name, rule, state)


def test_a_record_agrees_with_its_own_findings(tmp_path: Path):
    for name, record in _records(tmp_path).items():
        fired = {f["rule"] for f in record["findings"]}
        assert _states(record).get("fired", set()) == fired, name
        assert record["rules_failed"] == sorted(fired), name
        for rule in fired:
            assert record["rules"][rule]["findings"] == sum(1 for f in record["findings"] if f["rule"] == rule)
        assert record["n_error"] == sum(1 for f in record["findings"] if f["severity"] == "ERROR"), name
        assert record["conformant"] == (record["n_error"] == 0), name


#: Rules the scalar reference package gives nothing to read: it has no field output.
NOTHING_TO_READ = {"M019": "no output is of type field or declares a field block"}


def test_the_reference_package_evaluates_every_rule_but_the_smoke_ones():
    record = vs.conformance_record(REFERENCE_PACKAGE)
    states = _states(record)
    assert states.get("fired", set()) == set()
    assert states["not_evaluated"] == set(vs.SMOKE_RULES) | set(NOTHING_TO_READ)
    assert all("--smoke was not requested" in record["rules"][r]["reason"] for r in vs.SMOKE_RULES)
    assert {r: record["rules"][r]["reason"] for r in NOTHING_TO_READ} == NOTHING_TO_READ
    smoked = _states(vs.conformance_record(REFERENCE_PACKAGE, smoke=True))
    assert smoked == {"evaluated": {r.id for r in vs.RULES} - set(NOTHING_TO_READ),
                      "not_evaluated": set(NOTHING_TO_READ)}


def test_the_record_says_which_checker_read_which_documents_and_when():
    stamp = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    record = vs.conformance_record(REFERENCE_PACKAGE, now=stamp)
    assert record["checked_at"] == "2026-01-02T03:04:05Z"
    assert record["checker"] == {"name": "open-contract-ml", "version": vs.checker_version()}
    assert record["checker"]["version"] not in ("", "unknown")
    assert record["record_version"] == vs.RECORD_VERSION
    assert record["contract_version"] == vs.CONTRACT_VERSION
    for kind, name in (("manifest", "manifest.yaml"), ("model_card", "model_card.md"),
                       ("validation_report", "validation_report.json")):
        body = (REFERENCE_PACKAGE / name).read_bytes()
        assert record["documents"][kind] == {"path": name, "sha256": hashlib.sha256(body).hexdigest(),
                                             "bytes": len(body)}


def test_a_document_that_was_not_read_is_null_and_its_rules_say_why(tmp_path: Path):
    record = vs.conformance_record(_several_defects(tmp_path))
    assert record["documents"]["model_card"] is None
    assert record["documents"]["manifest"] is not None and record["documents"]["validation_report"] is not None
    for rule in ("C001", "C002", "C003", "C004", "C005", "C006"):
        assert record["rules"][rule] == {"severity": vs.RULES_BY_ID[rule].severity, "state": "not_evaluated",
                                         "reason": "the model card was not read"}


def test_rules_that_cannot_apply_to_an_untrained_package_say_so():
    """An honest NOT_RUN on A3 and A5 leaves V010 and V011 nothing to read; the record says that, not 'passed'."""
    record = vs.conformance_record(PRODUCER_PACKAGES / "brake_disc_link1_thermal_fno")
    assert record["rules"]["V010"]["state"] == "not_evaluated"
    assert "no measurement to read" in record["rules"]["V010"]["reason"]
    assert record["rules"]["V011"]["state"] == "not_evaluated"
    assert record["rules"]["V006"]["state"] == "evaluated"          # its C3 check reports PASS
    assert record["rules"]["M018"]["state"] == "fired"
    assert record["spec_version"] == "1.0"


# --------------------------------------------------------------------------- #
# The schema can fail: planted defects in an otherwise valid record.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("plant", [
    lambda r: r["rules"].pop("V008"),
    lambda r: r["rules"]["M013"].__setitem__("state", "skipped"),
    lambda r: r["rules"]["S001"].pop("reason"),
    lambda r: r["rules"]["M001"].update(state="fired"),
    lambda r: r.pop("checker"),
    lambda r: r.__setitem__("checked_at", "2026-01-02 03:04:05"),
    lambda r: r["documents"]["manifest"].__setitem__("sha256", "not-a-digest"),
    lambda r: r.__setitem__("record_version", "0.9"),
], ids=["a rule missing", "an unknown state", "not_evaluated without a reason", "fired without a count",
        "no checker", "a local timestamp", "a malformed digest", "another record version"])
def test_the_record_schema_rejects_a_planted_defect(plant):
    record = vs.conformance_record(REFERENCE_PACKAGE)
    assert _errors(record) == []
    broken = copy.deepcopy(record)
    plant(broken)
    assert _errors(broken) != []


# --------------------------------------------------------------------------- #
# The command line: one record for one package, an array for several.
# --------------------------------------------------------------------------- #
def test_check_json_writes_one_record_for_one_package(tmp_path: Path):
    out = tmp_path / "record.json"
    assert vs.main(["check", str(REFERENCE_PACKAGE), "--json", str(out)]) == 0
    record = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(record, dict) and _errors(record) == []
    assert record["package"] == str(REFERENCE_PACKAGE)


def test_check_json_writes_every_package_when_several_are_checked(tmp_path: Path):
    """Each package's record is kept, in argument order; one package's no longer overwrites another's."""
    out = tmp_path / "records.json"
    packages = [REFERENCE_PACKAGE, PRODUCER_PACKAGES / "plate_heat_fno",
                PRODUCER_PACKAGES / "brake_disc_link3_fatigue_gbm_gp"]
    assert vs.main(["check", *map(str, packages), "--json", str(out)]) == 1
    records = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(records, list) and _errors(records) == []
    assert [r["package"] for r in records] == [str(p) for p in packages]
    assert [r["conformant"] for r in records] == [True, True, False]


def test_the_ok_line_names_the_version_a_package_declares_when_it_is_not_the_checkers(capsys):
    """A 1.0 package checked by a 1.1 checker must not read as a 1.1 package."""
    assert vs.main(["check", str(REFERENCE_PACKAGE)]) == 0
    assert "(contract %s, 0 warning(s))" % vs.CONTRACT_VERSION in capsys.readouterr().out
    assert vs.main(["check", str(PRODUCER_PACKAGES / "plate_heat_fno")]) == 0
    assert "(contract %s, package declares 1.0, 0 warning(s))" % vs.CONTRACT_VERSION in capsys.readouterr().out
