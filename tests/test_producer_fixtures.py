"""Pinned producer packages must pass the checker, or fail exactly as recorded.

``tests/fixtures/producer_packages/`` holds contract packages copied from the
producers that emit them (its README lists, per package, what the copy changed
and the digest of each file in the copy). They pin what producers actually
ship, so a change to ``opencontractml.verify`` that would reject real producer
output fails here -- and in the CI ``package`` job, which checks the same
directories with the installed wheel -- instead of failing a producer.

A copy the checker rejects for a reason that is the producer's to fix is not
edited to pass. Its findings are recorded in ``known-findings.json`` instead, and
the copy must produce exactly those: a recorded finding that stops firing fails
here until its entry is deleted, and an unrecorded one fails at once, so the
record can only shrink. A package with no entry must be conformant.

Every one of these packages reports ``overall: FAIL``, and that is asserted too:
a checker that stopped accepting an honest FAIL, and a copy whose blocking check
had quietly been promoted to PASS, are the two ways this fixture set could stop
meaning anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opencontractml import verify as vs

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "producer_packages"
EXPECTED = (
    "brake_disc_link1_thermal_fno",
    "brake_disc_link2_thermo_mech_rom",
    "brake_disc_link3_fatigue_gbm_gp",
    "plate_heat_fno",
)
PACKAGES = sorted(p for p in FIXTURES.iterdir() if p.is_dir())
KNOWN_FINDINGS = json.loads((FIXTURES / "known-findings.json").read_text(encoding="utf-8"))["packages"]


def _report(pkg: Path) -> dict:
    return json.loads((pkg / "validation_report.json").read_text(encoding="utf-8"))


def test_the_pinned_set_is_complete():
    """Deleting a fixture must fail loudly, not quietly shrink the gate."""
    assert tuple(p.name for p in PACKAGES) == EXPECTED


@pytest.mark.parametrize("pkg", PACKAGES, ids=lambda p: p.name)
def test_each_pinned_producer_package_passes_or_fails_exactly_as_recorded(pkg: Path):
    pytest.importorskip("yaml", reason="the fixture packages ship manifest.yaml")
    found = sorted((f.rule, f.where, f.message) for f in vs.check_package(pkg))
    recorded = sorted((f["rule"], f["where"], f["message"])
                      for f in KNOWN_FINDINGS.get(pkg.name, {}).get("findings", []))
    assert found == recorded, (
        "%s: the checker's findings differ from known-findings.json\n  only found: %s\n  only recorded: %s"
        % (pkg.name, sorted(set(found) - set(recorded)), sorted(set(recorded) - set(found))))


def test_the_known_findings_record_names_only_pinned_packages_and_says_why():
    """An entry for a package that is not here, or one without a reason, is a stale record."""
    assert set(KNOWN_FINDINGS) <= set(EXPECTED)
    for name, entry in KNOWN_FINDINGS.items():
        assert str(entry.get("why", "")).strip(), name
        assert entry.get("findings"), "%s: an entry with no findings belongs deleted" % name


@pytest.mark.parametrize("pkg", PACKAGES, ids=lambda p: p.name)
def test_each_directory_is_named_by_its_package_id(pkg: Path):
    yaml = pytest.importorskip("yaml")
    manifest = yaml.safe_load((pkg / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["id"] == pkg.name == _report(pkg)["model_id"]


@pytest.mark.parametrize("pkg", PACKAGES, ids=lambda p: p.name)
def test_each_fixture_keeps_its_honest_fail(pkg: Path):
    """Conformant is not validated: a copy must never promote a blocking check."""
    report = _report(pkg)
    assert report["overall"] == "FAIL"
    assert set(report["checks"]) == set(vs.LADDER)
    blocking = [key for key, check in report["checks"].items() if check["status"] in vs.BLOCKING_STATUSES]
    assert blocking, "%s: nothing blocks, so its FAIL would be a lie" % pkg.name


@pytest.mark.parametrize("pkg", [p for p in PACKAGES if p.name.startswith("brake_disc_")], ids=lambda p: p.name)
def test_the_untrained_packages_still_report_tier_a_as_not_run(pkg: Path):
    """These are the packages V010 / V011 were narrowed for: an honest NOT_RUN on A3 and A5."""
    checks = _report(pkg)["checks"]
    assert {key: checks[key]["status"] for key in vs.TIER_A} == {key: "NOT_RUN" for key in vs.TIER_A}


# --------------------------------------------------------------------------- #
# Under check --smoke. None of these copies can answer its examples here, each
# for a stated reason, and the checker must say which rather than pass them.
# --------------------------------------------------------------------------- #
def _smoke_findings(pkg: Path) -> list:
    return [f for f in vs.check_package(pkg, smoke=True) if f.rule in vs.SMOKE_RULES]


@pytest.mark.parametrize("pkg", [p for p in PACKAGES if p.name.startswith("brake_disc_")], ids=lambda p: p.name)
def test_the_untrained_packages_declare_no_examples_so_the_smoke_test_cannot_run(pkg: Path):
    pytest.importorskip("yaml", reason="the fixture packages ship manifest.yaml")
    assert [(f.rule, f.message) for f in _smoke_findings(pkg)] == [
        ("S002", "the smoke test could not run: the manifest declares no examples[] to run")]


def test_the_plate_copy_cannot_answer_its_examples_because_its_weights_are_a_stub():
    """The copy's weights file is a text stub (see its README), so its entrypoint reports an internal error.

    It declares batch support, so the smoke test sends its two examples one at a
    time and then together, and each of the three requests ends in that error.
    Where numpy is not installed the entrypoint cannot even start, and the smoke
    test reports that it could not run instead.
    """
    import importlib.util
    pytest.importorskip("yaml", reason="the fixture packages ship manifest.yaml")
    found = _smoke_findings(FIXTURES / "plate_heat_fno")
    if importlib.util.find_spec("numpy") is None:
        assert [f.rule for f in found] == ["S002"] and "'numpy'" in found[0].message
    else:
        assert [(f.rule, f.where) for f in found] == [
            ("S001", "manifest.yaml examples[0]"), ("S001", "manifest.yaml examples[1]"),
            ("S001", "manifest.yaml examples, as one batch")]
        assert all("cannot load the packaged weights" in f.message for f in found), found
