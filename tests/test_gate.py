"""The scalar gate engine's V3 declarations.

V3 is the gate's deployment-readiness step. A rules file's ``v3`` block makes three
declarations -- the independent evidence the model is to be validated against
(``validation_anchor``), what it is meant to run on (``inference_target``) and whether
that evidence is available yet (``validation_anchor_status``) -- and a model does not
pass while any of them is missing. Only those names are read: a declaration made under
any other name does not count.
"""

from __future__ import annotations

import warnings

import pytest

from opencontractml import gate

CURRENT = {
    "validation_anchor": "thermocouple measurements from a bench test",
    "inference_target": "workstation CPU, one call per design",
    "validation_anchor_status": "not_available",
}


def _read_without_warnings(v3: dict) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("error")          # any warning fails the test
        return gate.v3_declarations(v3)


def test_the_declarations_are_read_without_a_warning():
    assert _read_without_warnings(CURRENT) == CURRENT


def test_the_card_block_carries_the_declarations_and_nothing_else():
    block = gate.v3_card_block(CURRENT)
    assert {name: block[name] for name in gate.V3_FIELDS} == CURRENT
    assert block["fields_present"] is True
    assert set(block) == set(gate.V3_FIELDS) | {"fields_present"}


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


def test_a_declaration_under_another_name_is_not_read():
    """A rules file that names the anchor and its status differently has not declared them."""
    v3 = {"anchor": CURRENT["validation_anchor"], "inference_target": CURRENT["inference_target"],
          "anchor_status": CURRENT["validation_anchor_status"]}
    block = gate.v3_card_block(_read_without_warnings(v3))
    assert block["fields_present"] is False
    assert block["validation_anchor"] is None and block["validation_anchor_status"] is None
