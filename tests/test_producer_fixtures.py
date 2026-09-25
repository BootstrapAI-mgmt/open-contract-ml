"""Pinned producer packages must keep passing the checker.

``tests/fixtures/producer_packages/`` holds contract packages copied from the
producers that emit them (its README lists, per package, what the copy changed
and the digest of each file in the copy). They pin what producers actually
ship, so a change to ``opencontractml.verify`` that would reject real producer
output fails here -- and in the CI ``package`` job, which checks the same
directories with the installed wheel -- instead of failing a producer.

Every one of these packages is conformant and every one reports
``overall: FAIL``. Both halves are asserted: a checker that stopped accepting an
honest FAIL, and a copy whose blocking check had quietly been promoted to PASS,
are the two ways this fixture set could stop meaning anything.
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


def _report(pkg: Path) -> dict:
    return json.loads((pkg / "validation_report.json").read_text(encoding="utf-8"))


def test_the_pinned_set_is_complete():
    """Deleting a fixture must fail loudly, not quietly shrink the gate."""
    assert tuple(p.name for p in PACKAGES) == EXPECTED


@pytest.mark.parametrize("pkg", PACKAGES, ids=lambda p: p.name)
def test_each_pinned_producer_package_passes_the_checker(pkg: Path):
    pytest.importorskip("yaml", reason="the fixture packages ship manifest.yaml")
    findings = vs.check_package(pkg)
    assert findings == [], "%s is no longer conformant: %r" % (pkg.name, findings)


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
