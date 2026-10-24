"""The pinned copy of the cell vocabulary, ``schemas/contract-v1/taxonomy-cells.json``.

The checker holds a manifest's ``taxonomy_cell`` to this copy, so the copy must say
exactly what it is and hold together: the vocabulary's name and version, the content
digests and counts a producer's pin carries, the grammar of a cell id, the live ids,
sorted, and the retired ids -- and nothing else, because the copy carries ids and
counts only. A copy that does not hold together is refused whole by the reader,
never applied in part.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path

import pytest

from opencontractml import verify as vs

#: Resolved out of the installed package, as the checker reads it.
COPY = Path(str(resources.files("opencontractml") / "schemas" / "contract-v1" / "taxonomy-cells.json"))

#: Every key of the copy, in its order: the note, the pin's six keys and the read date,
#: the grammar, and the two lists of ids.
KEYS = ("about", "registry", "version", "sha256", "document_sha256", "bytes", "cells", "read",
        "id_pattern", "ids", "retired")


def _copy() -> dict:
    return json.loads(COPY.read_text(encoding="utf-8"))


def test_the_copy_carries_ids_and_counts_only():
    doc = _copy()
    assert tuple(doc) == KEYS
    assert set(vs.TAXONOMY_PIN_REQUIRED) < set(doc)
    assert isinstance(doc["about"], str) and "ids and counts only" in doc["about"].lower()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["read"])
    # every entry of both lists is a bare id in the copy's own grammar: no name, target or label rides along
    grammar = re.compile(doc["id_pattern"])
    assert all(isinstance(i, str) and grammar.fullmatch(i) for i in doc["ids"] + doc["retired"])


def test_the_copy_holds_together():
    doc = _copy()
    vocabulary, problem = vs.load_taxonomy_cells()
    assert problem is None and vocabulary is not None, problem
    assert doc["ids"] == sorted(doc["ids"]) and len(set(doc["ids"])) == len(doc["ids"])
    assert doc["cells"] == len(doc["ids"]) == len(vocabulary["ids"])
    assert doc["retired"] == sorted(doc["retired"]) and not set(doc["ids"]) & set(doc["retired"])
    for key in vs.TAXONOMY_PIN_REQUIRED:
        assert vs.taxonomy_pin_value_problem(key, doc[key]) is None, key
        assert vocabulary[key] == doc[key], key
    assert vocabulary["id_pattern"] == doc["id_pattern"]
    assert vocabulary["retired"] == frozenset(doc["retired"])


def test_the_copy_is_lf_and_ascii():
    raw = COPY.read_bytes()
    assert b"\r" not in raw and raw.endswith(b"\n")
    assert raw.isascii()


def _with(**changes) -> str:
    doc = _copy()
    for key, value in changes.items():
        if value is KeyError:
            doc.pop(key)
        else:
            doc[key] = value
    return json.dumps(doc)


@pytest.mark.parametrize("text,why", [
    ("{not json", "not valid JSON"),
    ("[]", "it is not a JSON object"),
    (_with(registry=""), "registry must be a non-empty string"),
    (_with(version=1), "version must be a non-empty string"),
    (_with(sha256="CAFE"), "sha256 must be 64 lowercase hex characters"),
    (_with(document_sha256=KeyError), "document_sha256 must be 64 lowercase hex characters"),
    (_with(bytes=True), "bytes must be a positive integer"),
    (_with(cells=0), "cells must be a positive integer"),
    (_with(id_pattern="^A\\.[0-9"), "does not compile"),
    (_with(ids=_copy()["ids"][0]), "ids must be a list of cell ids"),
    (_with(ids=_copy()["ids"] + ["not-a-cell"], cells=len(_copy()["ids"]) + 1), "which is not a cell id"),
    (_with(ids=_copy()["ids"] + [_copy()["ids"][0]], cells=len(_copy()["ids"]) + 1), "ids holds a duplicate id"),
    (_with(cells=len(_copy()["ids"]) + 1), "but ids holds"),
    (_with(retired=[_copy()["ids"][0]]), "is both live and retired"),
], ids=["not JSON", "not an object", "an empty name", "a numeric version", "a short digest", "a digest missing",
        "a boolean byte count", "no cells", "a grammar that does not compile", "ids not a list",
        "an id outside the grammar", "a duplicate id", "a count that is not the ids'", "an id live and retired"])
def test_a_copy_that_does_not_hold_together_is_refused(monkeypatch, text, why):
    monkeypatch.setattr(vs, "_taxonomy_cells_text", lambda: text)
    vocabulary, problem = vs.load_taxonomy_cells()
    assert vocabulary is None and problem is not None and why in problem, problem


def test_a_missing_copy_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(vs, "TAXONOMY_CELLS_PATH", ("schemas", "contract-v1", "no-such-copy.json"))
    vocabulary, problem = vs.load_taxonomy_cells()
    assert vocabulary is None and problem.startswith("cannot read the pinned cell vocabulary"), problem
