"""The checker's schema walker and the published contract-v1 manifest schema must agree.

``opencontractml.verify`` applies ``schemas/contract-v1/manifest.schema.json``
itself (rule ``M018``), with a small standard-library walker, rather than through
a JSON Schema library. A second implementation of a published schema is only
worth having if it can be shown to say what the schema says, so these tests hold
the walker to the file in three ways:

* **coverage** -- every keyword the schema uses is one the walker applies, so no
  constraint is ignored without notice (the checker reports ``E003`` otherwise);
* **agreement** -- for every constraint the schema states (each enumeration,
  constant, pattern, type, required key, length, count and bound) a manifest that
  breaks it is rejected by the walker at exactly the places an independent
  validator, the ``jsonschema`` package, rejects it; and over whole manifests --
  the reference package, every producer fixture and the planted defects -- the
  two report the same set of places;
* **falsifiability** -- a schema carrying a constraint the walker cannot apply is
  refused, so planting one in the shipped schema file turns this module red.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest
import yaml

from opencontractml import verify as vs

REPO = Path(__file__).resolve().parents[1]
REFERENCE_PACKAGE = REPO / "examples" / "reference-package"
PRODUCER_PACKAGES = REPO / "tests" / "fixtures" / "producer_packages"

#: Keywords that hold sub-schemas rather than constraining a value themselves.
STRUCTURAL = ("properties", "items", "additionalProperties")
#: The key a planted value uses where the schema says "any other key".
EXTRA_KEY = "zz_unlisted_key"
#: What _breaking_value returns for a keyword it has no way to break.
UNKNOWN = object()


def _published_schema() -> dict:
    schema, problem = vs.load_manifest_schema()
    assert schema is not None, problem
    return schema


def _shipped_schema_as_written() -> dict:
    """The shipped file parsed as JSON, without the walker's refusal of what it cannot apply.

    The planted cases are enumerated from this, so a keyword the walker does not
    know still yields a case -- one that fails by name -- instead of stopping
    collection.
    """
    return json.loads(vs._manifest_schema_text())


def _reference_manifest() -> dict:
    return yaml.safe_load((REFERENCE_PACKAGE / "manifest.yaml").read_text(encoding="utf-8"))


def _walker_places(instance, schema) -> set:
    return {location for location, _ in vs.schema_errors(instance, schema)}


def _oracle_places(instance, schema) -> set:
    jsonschema = pytest.importorskip("jsonschema", reason="the independent validator the walker is compared with")
    places = set()
    for error in jsonschema.Draft202012Validator(schema).iter_errors(instance):
        location = ""
        for step in error.absolute_path:
            location = "%s[%d]" % (location, step) if isinstance(step, int) else vs._child(location, step)
        places.add(location)
    return places


# --------------------------------------------------------------------------- #
# Every constraint the schema states, and a value that breaks it.
# --------------------------------------------------------------------------- #
def _constraints(schema: dict, steps: tuple = ()):
    """Yield ``(steps, keyword, value)`` for every constraint in ``schema``.

    ``steps`` addresses the sub-schema: ``("prop", name)``, ``("items",)`` or
    ``("extra",)`` for ``additionalProperties``.
    """
    for keyword, value in schema.items():
        if keyword in vs.SCHEMA_ASSERTIONS and keyword not in STRUCTURAL:
            yield steps, keyword, value
        elif keyword not in vs.SCHEMA_ASSERTIONS and keyword not in vs.SCHEMA_ANNOTATIONS:
            yield steps, keyword, value          # an unknown keyword; the test below names it
    for name, sub in schema.get("properties", {}).items():
        yield from _constraints(sub, steps + (("prop", name),))
    if isinstance(schema.get("items"), dict):
        yield from _constraints(schema["items"], steps + (("items",),))
    if isinstance(schema.get("additionalProperties"), dict):
        yield from _constraints(schema["additionalProperties"], steps + (("extra",),))


def _container_for(step) -> object:
    return [] if step[0] == "items" else {}


def _locate(instance, steps):
    """The parent container and key or index ``steps`` address, creating what is missing."""
    node, location, key = instance, "", None
    for i, step in enumerate(steps):
        if key is not None:
            if isinstance(node, dict) and not isinstance(node.get(key), (dict, list)):
                node[key] = _container_for(step)
            elif isinstance(node, list) and not isinstance(node[key], (dict, list)):
                node[key] = _container_for(step)
            node = node[key]
        if step[0] == "items":
            if not node:
                node.append(None)
            key = 0
            location = "%s[0]" % location
        else:
            key = step[1] if step[0] == "prop" else EXTRA_KEY
            location = vs._child(location, key)
    return node, key, location


def _breaking_value(keyword, value, current):
    """A value that breaks ``keyword: value``, or None when nothing can."""
    if keyword == "enum":
        return "zz_not_one_of_the_values"
    if keyword == "const":
        return "zz_not_the_constant"
    if keyword == "pattern":
        for candidate in ("", "Not A-Match!", "0"):
            if re.search(value, candidate) is None:
                return candidate
        return None
    if keyword == "type":
        names = [value] if isinstance(value, str) else list(value)
        for candidate in ("zz_text", 12345, ["zz"], {"zz": 1}, True, None):
            if not any(vs._is_json_type(candidate, n) for n in names):
                return candidate
        return None
    if keyword == "minLength":
        return "" if value >= 1 else None
    if keyword in ("minimum", "maximum"):
        return value - 1 if keyword == "minimum" else value + 1
    if keyword in ("exclusiveMinimum", "exclusiveMaximum"):
        return value
    if keyword == "minItems":
        return [] if value >= 1 else None
    if keyword == "maxItems":
        filler = current[0] if isinstance(current, list) and current else 0
        return [filler] * (value + 1)
    if keyword == "minProperties":
        return {} if value >= 1 else None
    return UNKNOWN


def _planted_cases():
    """One manifest per constraint, each breaking exactly that constraint at a known place."""
    schema = _shipped_schema_as_written()
    cases = []
    for steps, keyword, value in _constraints(schema):
        if keyword == "required":
            for name in value:
                instance = _reference_manifest()
                if steps:
                    parent, key, location = _locate(instance, steps)
                    target = parent.get(key) if isinstance(parent, dict) else parent[key]
                    if not isinstance(target, dict):
                        parent[key] = target = {}
                else:
                    target, location = instance, ""
                target.pop(name, None)
                cases.append(("%s required %s" % (location or "(root)", name), instance, location))
            continue
        instance = _reference_manifest()
        if steps:
            parent, key, location = _locate(instance, steps)
            current = parent[key] if isinstance(parent, list) or key in parent else None
        else:
            parent, key, location, current = None, None, "", instance
        bad = _breaking_value(keyword, value, current)
        if bad is None:
            continue                              # e.g. minLength 0: nothing can break it
        name = "%s %s" % (location or "(root)", keyword)
        if bad is UNKNOWN:
            cases.append((name, None, location))  # fails in the test, naming the keyword
            continue
        if parent is None:
            instance = bad
        else:
            parent[key] = bad
        cases.append((name, instance, location))
    return cases


PLANTED = _planted_cases()


# --------------------------------------------------------------------------- #
# Coverage.
# --------------------------------------------------------------------------- #
def test_the_published_schema_loads_and_the_walker_applies_every_keyword_it_uses():
    schema, problem = vs.load_manifest_schema()
    assert problem is None and schema is not None, problem
    assert vs.schema_unsupported(schema) == []


def test_every_keyword_in_the_schema_is_a_known_assertion_or_annotation():
    unknown = sorted({keyword for _, keyword, _ in _constraints(_shipped_schema_as_written())
                      if keyword not in vs.SCHEMA_ASSERTIONS})
    assert unknown == [], "the schema uses keyword(s) the walker does not apply: %s" % unknown


def test_the_planted_cases_reach_every_enum_const_and_pattern_in_the_schema():
    """The agreement test is only as good as its reach: every such site gets a planted case."""
    for keyword in ("enum", "const", "pattern"):
        sites = sum(1 for _, kw, _ in _constraints(_shipped_schema_as_written()) if kw == keyword)
        planted = sum(1 for name, _, _ in PLANTED if name.endswith(" " + keyword))
        assert sites > 0 and planted == sites, (keyword, sites, planted)


# --------------------------------------------------------------------------- #
# Agreement.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name,instance,location", PLANTED, ids=[c[0] for c in PLANTED])
def test_each_planted_constraint_is_rejected_where_the_independent_validator_rejects_it(name, instance, location):
    assert instance is not None, ("%s: this test has no way to break that keyword; teach it the keyword "
                                  "before the schema uses it" % name)
    schema = _published_schema()
    walker = _walker_places(instance, schema)
    assert location in walker, "the walker missed %s; it reported %s" % (name, sorted(walker))
    assert walker == _oracle_places(instance, schema)


def _whole_manifests():
    out = [("reference", _reference_manifest())]
    for pkg in sorted(p for p in PRODUCER_PACKAGES.iterdir() if p.is_dir()):
        out.append((pkg.name, yaml.safe_load((pkg / "manifest.yaml").read_text(encoding="utf-8"))))
    planted = _reference_manifest()
    planted["modality"] = "anything_goes"
    planted["id"] = "Bad-ID"
    planted["invocation"]["timeout_s"] = 0
    planted["inputs"].append({"name": "geom", "type": "file", "file_kind": "exe", "required": False})
    planted["provenance"]["artifacts"][0]["bytes"] = "not-a-number"
    planted.pop("lineage")
    out.append(("several defects at once", planted))
    return out


@pytest.mark.parametrize("name,instance", _whole_manifests(), ids=[n for n, _ in _whole_manifests()])
def test_the_walker_and_the_independent_validator_report_the_same_places(name, instance):
    schema = _published_schema()
    assert _walker_places(instance, schema) == _oracle_places(instance, schema)


def test_the_reference_manifest_is_clean_under_both():
    schema = _published_schema()
    assert vs.schema_errors(_reference_manifest(), schema) == []
    assert _oracle_places(_reference_manifest(), schema) == set()


# --------------------------------------------------------------------------- #
# The walker on its own: each keyword, including the bounds the shipped schema
# does not use yet, and the JSON meaning of types and equality.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("schema,good,bad", [
    ({"type": "integer"}, 2.0, True),
    ({"type": "number"}, 1, False),
    ({"type": ["string", "null"]}, None, 0),
    ({"enum": [1, "a"]}, 1.0, True),
    ({"const": "stdio_json"}, "stdio_json", "http"),
    ({"pattern": "^[a-z]+$"}, "abc", "aBc"),
    ({"minLength": 1}, "x", ""),
    ({"minimum": 0}, 0, -1),
    ({"maximum": 1}, 1, 2),
    ({"exclusiveMinimum": 0}, 1, 0),
    ({"exclusiveMaximum": 1}, 0.5, 1),
    ({"minItems": 2}, [1, 2], [1]),
    ({"maxItems": 2}, [1, 2], [1, 2, 3]),
    ({"minProperties": 1}, {"a": 1}, {}),
    ({"required": ["a"]}, {"a": 1}, {"b": 1}),
    ({"properties": {"a": {"type": "string"}}}, {"a": "x"}, {"a": 1}),
    ({"additionalProperties": {"type": "object"}}, {"a": {}}, {"a": 1}),
    ({"additionalProperties": False, "properties": {"a": {}}}, {"a": 1}, {"a": 1, "b": 2}),
    ({"items": {"type": "number"}}, [1, 2.5], [1, "x"]),
])
def test_each_keyword_accepts_what_it_should_and_rejects_what_it_should(schema, good, bad):
    assert vs.schema_unsupported(schema) == []
    assert vs.schema_errors(good, schema) == []
    assert vs.schema_errors(bad, schema) != []
    assert (vs.schema_errors(good, schema) == []) == (_oracle_places(good, schema) == set())
    assert (vs.schema_errors(bad, schema) == []) == (_oracle_places(bad, schema) == set())


def test_a_keyword_applies_only_to_the_type_it_governs():
    assert vs.schema_errors(5, {"pattern": "^a$", "minLength": 3, "required": ["x"], "minItems": 1}) == []
    assert vs.schema_errors("abc", {"minimum": 10, "items": {"type": "number"}}) == []


# --------------------------------------------------------------------------- #
# Falsifiability: a constraint the walker cannot apply is refused, never ignored.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("plant,expected", [
    (lambda s: s["properties"]["id"].__setitem__("maxLength", 64), "#/properties/id/maxLength"),
    (lambda s: s["properties"]["modality"].__setitem__("oneOf", [{"const": "x"}]), "#/properties/modality/oneOf"),
    (lambda s: s["properties"]["version"].__setitem__("type", "text"), "#/properties/version/type"),
    (lambda s: s["properties"]["id"].__setitem__("pattern", "^[a-z"), "#/properties/id/pattern"),
], ids=["an unapplied keyword", "a combinator", "an unknown type", "a pattern that does not compile"])
def test_a_schema_the_walker_cannot_apply_in_full_is_refused(plant, expected):
    schema = copy.deepcopy(_published_schema())
    plant(schema)
    problems = vs.schema_unsupported(schema)
    assert len(problems) == 1 and problems[0].startswith(expected + " "), problems


def test_the_checker_reports_e003_rather_than_skip_a_schema_it_cannot_apply(monkeypatch, tmp_path):
    import shutil
    pkg = tmp_path / "pkg"
    shutil.copytree(REFERENCE_PACKAGE, pkg)
    schema = copy.deepcopy(_published_schema())
    schema["properties"]["id"]["maxLength"] = 64
    monkeypatch.setattr(vs, "_manifest_schema_text", lambda: json.dumps(schema))
    findings = vs.check_package(pkg)
    assert {f.rule for f in findings} == {"E003"}
    assert any("maxLength" in f.message for f in findings)
    assert not vs.summarize(findings)["conformant"]
