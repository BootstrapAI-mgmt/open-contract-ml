"""The scalar gate engine's V3 declarations, under their current and their former names.

V3 is the gate's deployment-readiness step. A rules file's ``v3`` block makes three
declarations -- the independent evidence the model is to be validated against
(``validation_anchor``), what it is meant to run on (``inference_target``) and whether
that evidence is available yet (``validation_anchor_status``) -- and a model does not
pass while any of them is missing. Two of the three had other names before 0.1.1. A
rules file that still uses a former name must keep working for one release, with a
warning, and a reader of the model card must keep finding the former key; both stop
at ``gate.V3_FORMER_NAMES_REMOVED_IN``.
"""

from __future__ import annotations

import warnings

import pytest

import opencontractml
from opencontractml import gate

CURRENT = {
    "validation_anchor": "thermocouple measurements from a bench test",
    "inference_target": "workstation CPU, one call per design",
    "validation_anchor_status": "not_available",
}
FORMER = {
    "rung4_anchor": CURRENT["validation_anchor"],
    "inference_target": CURRENT["inference_target"],
    "stage8_status": CURRENT["validation_anchor_status"],
}


def _read_without_warnings(v3: dict) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("error")          # any warning fails the test
        return gate.v3_declarations(v3)


def test_the_current_names_are_read_without_a_warning():
    assert _read_without_warnings(CURRENT) == CURRENT


def test_the_former_names_are_still_read_with_a_deprecation_warning():
    with pytest.warns(DeprecationWarning) as record:
        fields = gate.v3_declarations(FORMER)
    assert fields == CURRENT
    messages = [str(w.message) for w in record]
    assert len(messages) == 2, messages
    for former, current in (("rung4_anchor", "validation_anchor"), ("stage8_status", "validation_anchor_status")):
        said = [m for m in messages if "v3.%s " % former in m]
        assert said, "no warning names %s" % former
        assert "v3.%s" % current in said[0] and gate.V3_FORMER_NAMES_REMOVED_IN in said[0], said[0]


def test_the_current_name_wins_when_both_are_given():
    v3 = {**CURRENT, "rung4_anchor": "an older anchor"}
    with pytest.warns(DeprecationWarning, match="ignored"):
        fields = gate.v3_declarations(v3)
    assert fields["validation_anchor"] == CURRENT["validation_anchor"]


def test_the_card_block_carries_both_names_until_the_former_ones_go():
    block = gate.v3_card_block(CURRENT)
    for name in gate.V3_FIELDS:
        assert block[name] == CURRENT[name]
    assert block["rung4_anchor"] == CURRENT["validation_anchor"]
    assert block["stage8_status"] == CURRENT["validation_anchor_status"]
    assert block["fields_present"] is True


@pytest.mark.parametrize("missing", gate.V3_FIELDS)
def test_a_missing_declaration_fails_v3(missing):
    """The step must be able to fail: dropping any one declaration fails it."""
    v3 = {k: v for k, v in CURRENT.items() if k != missing}
    block = gate.v3_card_block(_read_without_warnings(v3))
    assert block["fields_present"] is False
    assert block[missing] is None


def test_an_empty_declaration_is_not_a_declaration():
    block = gate.v3_card_block(_read_without_warnings({**CURRENT, "validation_anchor": ""}))
    assert block["fields_present"] is False


def test_the_former_names_are_dropped_by_the_announced_release():
    """A deprecation that outlives its announced release is a promise broken silently.

    Fails once the package version reaches the release the former names were to be
    removed in, so removing them cannot be forgotten.
    """
    def parts(version: str) -> tuple:
        return tuple(int(p) for p in version.split(".")[:3])

    assert parts(opencontractml.__version__) < parts(gate.V3_FORMER_NAMES_REMOVED_IN), (
        "version %s has reached %s: remove gate.V3_FORMER_NAMES and this test"
        % (opencontractml.__version__, gate.V3_FORMER_NAMES_REMOVED_IN))
