"""Contract v1 conformance checker.

The Contract is the single model-card / manifest / provenance / validation
standard shared by scalar-surrogate pipelines, field-surrogate libraries and
the applications that dispatch their models.  The normative text is
``docs/spec/CONTRACT-v1.md``; the machine-readable structure lives under
``schemas/contract-v1/``.  This module is the executable half: it decides whether a
given artifact complies, and it says exactly which rule failed and why.

Commands:

    python -m opencontractml.verify check <package-dir> [--smoke] [--json report.json]
        Strict conformance of one contract package (manifest + card + validation
        report + the artifacts they name).  Exit 0 when clean, 1 on findings.
        ``--smoke`` also runs the entrypoint on the manifest's examples; without
        it the check executes nothing.  ``--json`` writes the conformance record:
        the checker's version, the digests of the documents it read, when it
        ran, and a state for every rule (evaluated, fired, not evaluated and why).

    python -m opencontractml.verify rules
        Print the rule table.

    python -m opencontractml.verify vocabulary [--out vocab.json]
        Emit the machine-readable contract vocabulary.

Design rules this checker holds itself to (see the spec, section 9):

* **A gate must be able to fail.**  ``tests/`` plants a defect for every
  ERROR rule and asserts the rule fires.
* **Presence is not compliance.**  A check that reports ``PASS`` must carry at
  least one numeric measurement *and* at least one numeric threshold.  A
  declaration string is never a pass.  This is rule V006, and it exists because
  the scalar ladder's V2.3 conservation check is a non-empty-string test that
  green-stamped a model whose card declared the check unimplemented.
* **Never silent.**  A missing YAML parser, an unreadable file or an unknown
  status is an ERROR finding, never a skip.
* **No new science.**  This checker sets no physics thresholds.  It requires
  that a threshold be *stated and compared against a measurement*; what the
  number should be remains the producer's engineering judgement.

Standard library only, so the checker runs from a bare Python.  YAML is read through
PyYAML when it is importable and is a hard ERROR when it is not (rule E002);
``manifest.json`` is an accepted dependency-free equivalent of ``manifest.yaml``.
The manifest is also held to the contract-v1 JSON Schema this package ships,
applied by a standard-library walker (rule M018); a schema the walker cannot
apply in full is likewise an ERROR, never a skip (rule E003).
"""

from __future__ import annotations

import argparse
import contextvars
import hashlib
import json
import operator
import os
import re
import sys
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List, Optional, Sequence, Tuple

CONTRACT_VERSION = "1.1"
SUPPORTED_CONTRACT_MAJOR = 1

# --------------------------------------------------------------------------- #
# The reconciled model-card section set (spec section 4).
#
# The first eleven H2 headings of a contract card, in this order.  Positions 1-5,
# 7-9 and 11 are the nine package-v1 card sections in their original relative
# order; "Training configuration" (6) and "Provenance" (10) are the two
# insertions that carry what the worked-instance cards say and the nine have
# nowhere to put.  Keeping the nine in order is deliberate: moving a nine-section
# validator to the eleven is two inserted strings, not a re-ordering.
# --------------------------------------------------------------------------- #
CARD_SECTIONS: Tuple[str, ...] = (
    "TL;DR",
    "Intended use",
    "Out of scope",
    "Training data",
    "Architecture",
    "Training configuration",
    "Performance",
    "Uncertainty quantification",
    "Known failure modes",
    "Provenance",
    "Version history",
)

# Named sections a card MAY carry, only after the required eleven.  Reserved so
# that the worked-instance cards' "Disclosure" (anchored vs illustrative) and
# "Alternatives considered" survive the reconciliation instead of being dropped.
CARD_SECTIONS_RESERVED: Tuple[str, ...] = (
    "Alternatives considered",
    "Disclosure",
    "Open questions",
    "References",
)

# --------------------------------------------------------------------------- #
# The tiered validation vocabulary (spec section 5).  One ladder; the scalar and
# field ladders are tiers of it, not rivals.
# --------------------------------------------------------------------------- #
TIER_A: Tuple[str, ...] = (
    "A1_accuracy",
    "A2_extrapolation",
    "A3_uq_calibration",
    "A4_baseline_beat",
    "A5_reproducibility",
)
TIER_B: Tuple[str, ...] = (
    "B1_monotonicity",
    "B2_bounds",
    "B3_residual",
    "B4_conservation",
    "B5_invariance",
    "B6_integrated_quantities",
)
TIER_C: Tuple[str, ...] = (
    "C1_ood_guard",
    "C2_serve_parity",
    "C3_provenance_integrity",
    "C4_deployment_readiness",
)
LADDER: Tuple[str, ...] = TIER_A + TIER_B + TIER_C

# Legacy identifier -> contract key.  The cloud lane's FG7 is deliberately absent
# from the flat map: FG7 denotes two different physical claims depending on the
# lane, which is the one genuine collision the unification has to break.  Use
# legacy_key(lane, legacy) instead of this dict directly.
LEGACY_ALIASES: Dict[str, str] = {
    "V1.1": "A1_accuracy",
    "V1.2": "A2_extrapolation",
    "V1.3": "A3_uq_calibration",
    "V1.4": "A4_baseline_beat",
    "V1.5": "A5_reproducibility",
    "V2.1": "B1_monotonicity",
    "V2.2": "B2_bounds",
    "V2.3": "B4_conservation",
    "V2.4": "B5_invariance",
    "V3": "C4_deployment_readiness",
    "FG1": "A1_accuracy",
    "FG2": "A2_extrapolation",
    "FG3": "A3_uq_calibration",
    "FG4": "A4_baseline_beat",
    "FG5": "A5_reproducibility",
    "FG6": "B3_residual",
    "FG8": "C1_ood_guard",
    "FG9": "C2_serve_parity",
    "FG10": "B5_invariance",
    # The cloud ladder's integrated-quantities check, renamed from FG7 so that
    # FG7 means conservation everywhere it is still emitted.  FG11 has one
    # meaning, so it needs no qualifier.
    "FG11": "B6_integrated_quantities",
}

# Legacy ids a producer has stopped emitting, mapped to the id that replaced
# them, per ladder.  A retired id still resolves through legacy_key(), because a
# report written before the rename is a record and is never rewritten; a new
# report should carry the replacement.  The retired id and its replacement must
# resolve to the same contract key (tests assert it).
RETIRED_ALIASES: Dict[str, Dict[str, str]] = {
    "FG7": {"cloud": "FG11"},
}


def legacy_key(lane: str, legacy: str) -> Optional[str]:
    """Map a legacy gate id to its contract key, resolving the FG7 collision by lane.

    ``FG7`` is ``conservation`` in the grid and mesh lanes (a global energy
    balance) and ``integrated quantities`` in the cloud lane (a lift coefficient
    against the released labels).  Those are different physical claims sharing
    one identifier; the contract splits them into B4 and B6.

    The cloud check has since been renamed ``FG11``, which resolves to B6 on its
    own.  ``FG7`` on the cloud ladder is retired (see ``RETIRED_ALIASES``) and
    still resolves to B6, so a report written before the rename stays readable.
    """
    if legacy == "FG7":
        return "B6_integrated_quantities" if lane == "cloud" else "B4_conservation"
    return LEGACY_ALIASES.get(legacy)


STATUSES = ("PASS", "FAIL", "NOT_RUN", "NOT_APPLICABLE")
# NOT_RUN always blocks: the check applies and was not executed.  NOT_APPLICABLE
# does not block but requires a stated reason -- the distinction an
# "allow_not_run" allow-list expresses without recording the reason.
BLOCKING_STATUSES = ("FAIL", "NOT_RUN")

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX7 = re.compile(r"^[0-9a-f]{7,40}$")
_SEMVERISH = re.compile(r"^\d+\.\d+")
_MAJOR_MINOR = re.compile(r"^\d+\.\d+$")
_NUMERAL = re.compile(r"\d")
_FRONT_MATTER = re.compile(r"\A---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)
_H2 = re.compile(r"^##[ \t]+(?P<title>\S.*?)[ \t]*$")
_FENCE = re.compile(r"^[ \t]*(```|~~~)")
_FM_LINE = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*):[ \t]*(?P<value>.*?)[ \t]*$")

# Minimum non-whitespace body characters a required card section must carry to
# count as written rather than stubbed.
MIN_SECTION_CHARS = 40


# --------------------------------------------------------------------------- #
# Rule table.  Every finding names one of these.
# --------------------------------------------------------------------------- #
class Rule:
    __slots__ = ("id", "severity", "title")

    def __init__(self, rid: str, severity: str, title: str) -> None:
        self.id = rid
        self.severity = severity
        self.title = title


RULES: Tuple[Rule, ...] = (
    Rule("E001", "ERROR", "package directory exists and is readable"),
    Rule("E002", "ERROR", "a YAML parser is available for a .yaml artifact"),
    Rule("E003", "ERROR", "the contract-v1 manifest schema loads and the checker applies every keyword it uses"),
    Rule("M001", "ERROR", "manifest present and parses to a mapping"),
    Rule("M002", "ERROR", "spec_version present, MAJOR.MINOR, major supported"),
    Rule("M003", "ERROR", "identity block complete (id, name, version, owner, domain, modality, purpose)"),
    Rule("M004", "ERROR", "inputs declared and well formed (float inputs state units; a range is [min, max], "
                          "min < max)"),
    Rule("M005", "ERROR", "outputs declared and well formed (float outputs state units)"),
    Rule("M006", "ERROR", "no duplicate input or output names"),
    Rule("M007", "ERROR", "every output is covered by an uncertainty.per_output block"),
    Rule("M008", "ERROR", "invocation block complete and protocol is supported"),
    Rule("M009", "ERROR", "model_card path declared, inside the package, and the file exists"),
    Rule("M010", "ERROR", "validation.report path declared, inside the package, and the file exists"),
    Rule("M011", "ERROR", "provenance block present"),
    Rule("M012", "ERROR", "provenance.artifacts entries well formed (a path inside the package, a role, "
                          "a sha256, an integer byte count)"),
    Rule("M013", "ERROR", "every declared artifact exists and its sha256 matches the file on disk"),
    Rule("M014", "ERROR", "provenance.dataset carries a well formed sha256"),
    Rule("M015", "ERROR", "provenance.code carries repo and commit"),
    Rule("M016", "WARN", "provenance.environment names the interpreter"),
    # M017 is reserved for the signature warning designed in docs/spec/PROVENANCE-SIGNING.md.
    Rule("M018", "ERROR", "the manifest conforms to the contract-v1 manifest schema "
                          "(required keys, types, enumerations, patterns, bounds)"),
    Rule("C001", "ERROR", "model card parses with a flat scalar front-matter"),
    Rule("C002", "ERROR", "card front-matter identity matches the manifest"),
    Rule("C003", "ERROR", "the eleven required card sections are present, first, in order"),
    Rule("C004", "ERROR", "no required card section is a stub"),
    Rule("C005", "ERROR", "the uncertainty section states a method and a number"),
    Rule("C006", "WARN", "extra H2 sections use reserved names"),
    Rule("V001", "ERROR", "validation report parses and declares its identity"),
    Rule("V002", "ERROR", "validation report identity (model_id, model_version, spec_version) matches the manifest"),
    Rule("V003", "ERROR", "validation report dataset hash matches the manifest provenance"),
    Rule("V004", "ERROR", "every ladder key is present"),
    Rule("V005", "ERROR", "every check declares a known status"),
    Rule("V006", "ERROR", "a PASS carries a numeric measurement and a numeric threshold"),
    Rule("V007", "ERROR", "NOT_APPLICABLE states a reason"),
    Rule("V008", "ERROR", "the declared overall verdict matches the recomputed one"),
    Rule("V009", "ERROR", "B4 conservation is measured, not declared"),
    Rule("V010", "ERROR", "A3 uq_calibration reports nominal, empirical coverage, n and method"),
    Rule("V011", "ERROR", "A5 reproducibility declares a determinism class and a tolerance (bitwise means "
                          "tolerance 0, from contract 1.1)"),
    Rule("V012", "ERROR", "comparators are well formed, and every PASS or FAIL check has one from contract 1.1"),
    Rule("V013", "ERROR", "each measured check's declared status agrees with the status its comparators give"),
    Rule("S001", "ERROR", "check --smoke: the entrypoint answers every declared example within its timeout, with "
                          "every declared output and uncertainty field"),
    Rule("S002", "WARN", "check --smoke: the smoke test could run (examples declared, the entrypoint verified and "
                         "launchable here)"),
)
RULES_BY_ID: Dict[str, Rule] = {r.id: r for r in RULES}


class Finding:
    __slots__ = ("rule", "severity", "where", "message")

    def __init__(self, rule: str, where: str, message: str) -> None:
        self.rule = rule
        self.severity = RULES_BY_ID[rule].severity
        self.where = where
        self.message = message

    def as_dict(self) -> Dict[str, str]:
        return {"rule": self.rule, "severity": self.severity, "where": self.where, "message": self.message}

    def __repr__(self) -> str:
        return "[%s %s] %s: %s" % (self.severity, self.rule, self.where, self.message)


# --------------------------------------------------------------------------- #
# Which rules a check evaluated.  The conformance record (``check --json``) says,
# for every rule, whether it was evaluated, fired, or not evaluated and why, so a
# reader can tell a rule that passed from one that never ran.  The checks mark a
# rule where they test its condition; a context variable carries the ledger, so
# the check functions keep their signatures and a plain ``check_package`` call
# records nothing.
# --------------------------------------------------------------------------- #
class _Ledger:
    __slots__ = ("evaluated", "reasons", "documents", "smoke_reason", "spec_version")

    def __init__(self) -> None:
        self.evaluated: set = set()
        self.reasons: Dict[str, str] = {}
        self.documents: Dict[str, Path] = {}
        self.smoke_reason: Optional[str] = None
        self.spec_version: Optional[str] = None


_LEDGER: "contextvars.ContextVar[Optional[_Ledger]]" = contextvars.ContextVar("opencontractml_ledger", default=None)


def _ran(*rules: str) -> None:
    ledger = _LEDGER.get()
    if ledger is not None:
        ledger.evaluated.update(rules)


def _not_run(reason: str, *rules: str) -> None:
    ledger = _LEDGER.get()
    if ledger is not None:
        for rule in rules:
            ledger.reasons.setdefault(rule, reason)


def _document(kind: str, path: Path) -> None:
    ledger = _LEDGER.get()
    if ledger is not None:
        ledger.documents[kind] = path


# --------------------------------------------------------------------------- #
# Loaders.
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_lf(path: Path, text: str) -> None:
    """Write with LF line endings unconditionally.

    Contract packages pin artifacts by byte hash, and this repo's ``.gitattributes``
    is ``* text=auto eol=lf``. A file written with the platform default on Windows
    is CRLF on disk and LF in the git blob, so its pinned hash breaks on the next
    checkout and rule M013 fires on a package that was conformant when built. Every
    file this module emits goes through here so the checker never creates that
    problem itself.
    """
    path.write_text(text, encoding="utf-8", newline="\n")


def outside_package(pkg: Path, rel: str) -> Optional[str]:
    """Why ``rel`` does not name a path inside the package directory, or None when it does.

    A package is a directory (spec section 3): every file the manifest names lives
    in it.  A path that is absolute, or that resolves -- through ``..`` or a
    symbolic link -- to somewhere outside the directory, names a file the package
    does not carry, so the checker neither hashes nor reads it.
    """
    if not rel.strip():
        return "is empty"
    if Path(rel).is_absolute() or PureWindowsPath(rel).is_absolute() or PureWindowsPath(rel).drive:
        return "is absolute"
    root = pkg.resolve()
    target = (pkg / rel).resolve()
    if target != root and root not in target.parents:
        return "resolves outside the package directory"
    return None


def load_mapping(path: Path, findings: List[Finding]) -> Optional[Dict[str, Any]]:
    """Read a .json / .yaml / .yml mapping.  Records a finding and returns None on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        findings.append(Finding("M001", str(path), "cannot read: %s" % exc))
        return None
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except ValueError as exc:
            findings.append(Finding("M001", str(path), "not valid JSON: %s" % exc))
            return None
    else:
        _ran("E002")
        try:
            import yaml  # noqa: PLC0415 -- optional; its absence is an ERROR, never a skip
        except ImportError:
            findings.append(Finding(
                "E002", str(path),
                "no YAML parser available (pip install PyYAML), and this artifact is YAML; "
                "ship manifest.json instead for a dependency-free package"))
            return None
        try:
            data = yaml.safe_load(text)
        except Exception as exc:  # yaml.YAMLError, but do not import the name for a bare env
            findings.append(Finding("M001", str(path), "not valid YAML: %s" % exc))
            return None
    if not isinstance(data, dict):
        findings.append(Finding("M001", str(path), "root must be a mapping, got %s" % type(data).__name__))
        return None
    return data


def split_front_matter(text: str) -> Tuple[Optional[Dict[str, str]], str, Optional[str]]:
    """Parse a strict flat-scalar YAML front-matter block.

    The contract deliberately narrows front-matter to a flat mapping of scalars
    (spec section 4.1) so that a card's identity is readable without a YAML
    dependency.  This is a tightening of, and compatible with, every card the
    Contract was reconciled against.  Returns ``(mapping, body, error)``.
    """
    match = _FRONT_MATTER.match(text)
    if match is None:
        return None, text, "missing YAML front-matter (--- ... ---) at the top of the card"
    body = text[match.end():]
    out: Dict[str, str] = {}
    for lineno, line in enumerate(match.group("body").splitlines(), start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = _FM_LINE.match(line)
        if m is None:
            return None, body, ("front-matter line %d is not a flat 'key: value' scalar: %r "
                                "(contract front-matter must be flat)" % (lineno, line))
        value = m.group("value")
        if value.startswith(("'", '"')) and len(value) >= 2 and value[-1] == value[0]:
            value = value[1:-1]
        out[m.group("key")] = value
    return out, body, None


def h2_headings(body: str) -> List[str]:
    """Ordered H2 titles, ignoring anything inside a fenced code block."""
    headings: List[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _H2.match(line)
        if m is not None:
            headings.append(m.group("title"))
    return headings


def section_bodies(body: str) -> Dict[str, str]:
    """Map each H2 title to its body text (up to the next H2), fences included."""
    out: Dict[str, str] = {}
    current: Optional[str] = None
    buf: List[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            if current is not None:
                buf.append(line)
            continue
        m = None if in_fence else _H2.match(line)
        if m is not None:
            if current is not None:
                out[current] = "\n".join(buf)
            current, buf = m.group("title"), []
        elif current is not None:
            buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf)
    return out


def numeric_leaves(obj: Any) -> List[float]:
    """Every int/float anywhere inside a nested structure.  bools are not numbers."""
    out: List[float] = []
    stack = [obj]
    while stack:
        node = stack.pop()
        if isinstance(node, bool):
            continue
        if isinstance(node, (int, float)):
            out.append(float(node))
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
    return out


# --------------------------------------------------------------------------- #
# The contract-v1 manifest schema, applied with the standard library.
#
# The schema ships inside this package (``schemas/contract-v1/manifest.schema.json``)
# and states the manifest's structure: required keys, types, enumerations,
# patterns and bounds.  The checker applies it itself (rule M018) with the small
# walker below, which implements the part of JSON Schema 2020-12 the schema uses,
# so that ``verify`` still needs nothing beyond the standard library.
#
# A schema the walker cannot apply in full -- missing, unreadable, malformed, or
# using a keyword outside that part -- is an ERROR (rule E003), never a skip.  It
# is the same rule E002 applies to a missing YAML parser: a checker that quietly
# ignored a constraint would call a manifest conformant that is not.
# --------------------------------------------------------------------------- #
#: The keywords the walker applies.
SCHEMA_ASSERTIONS: Tuple[str, ...] = (
    "type", "enum", "const", "pattern", "minLength", "minimum", "maximum",
    "exclusiveMinimum", "exclusiveMaximum", "required", "properties",
    "additionalProperties", "minProperties", "items", "minItems", "maxItems",
)
#: Keywords that describe and constrain nothing.  JSON Schema 2020-12 treats
#: ``format`` as an annotation unless a validator opts into asserting it.
SCHEMA_ANNOTATIONS: Tuple[str, ...] = (
    "$schema", "$id", "$comment", "title", "description", "default", "examples",
    "format", "deprecated", "readOnly", "writeOnly",
)
#: Where the manifest schema lives inside this package.
MANIFEST_SCHEMA_PATH: Tuple[str, ...] = ("schemas", "contract-v1", "manifest.schema.json")

_JSON_TYPES = ("object", "array", "string", "integer", "number", "boolean", "null")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_json_type(value: Any, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if name == "number":
        return _is_number(value)
    # "integer": JSON Schema counts a number with no fractional part, 2.0 included
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and value.is_integer())


def _json_equal(a: Any, b: Any) -> bool:
    """Equality as JSON means it: true is not 1, and 1 equals 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _is_number(a) and _is_number(b):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _child(at: str, key: str) -> str:
    return "%s.%s" % (at, key) if at else key


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def schema_unsupported(schema: Any, at: str = "#") -> List[str]:
    """Every place in ``schema`` that :func:`schema_errors` could not apply faithfully.

    Returns JSON-pointer-like locations, each with what is wrong: a keyword the
    walker does not implement, or a keyword whose value is malformed (an unknown
    type name, a pattern that does not compile, a bound that is not a number).
    An empty list means the walker applies every constraint the schema states.
    """
    if isinstance(schema, bool):
        return []
    if not isinstance(schema, dict):
        return ["%s (a schema must be an object or a boolean)" % at]
    out: List[str] = []
    for key, value in schema.items():
        here = "%s/%s" % (at, key)
        if key in SCHEMA_ANNOTATIONS:
            continue
        if key not in SCHEMA_ASSERTIONS:
            out.append("%s (keyword not applied by this checker)" % here)
        elif key == "type":
            names = [value] if isinstance(value, str) else value
            if not isinstance(names, list) or not names or any(n not in _JSON_TYPES for n in names):
                out.append("%s (unknown type %r)" % (here, value))
        elif key == "enum":
            if not isinstance(value, list) or not value:
                out.append("%s (enum must be a non-empty array)" % here)
        elif key == "pattern":
            try:
                re.compile(value)
            except (re.error, TypeError):
                out.append("%s (pattern %r does not compile)" % (here, value))
        elif key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
            if not _is_number(value):
                out.append("%s (bound %r is not a number)" % (here, value))
        elif key in ("minLength", "minProperties", "minItems", "maxItems"):
            if not _is_count(value):
                out.append("%s (%r is not a non-negative integer)" % (here, value))
        elif key == "required":
            if not isinstance(value, list) or not all(isinstance(k, str) for k in value):
                out.append("%s (required must be an array of key names)" % here)
        elif key == "properties":
            if not isinstance(value, dict):
                out.append("%s (properties must be an object)" % here)
            else:
                for name, sub in value.items():
                    out.extend(schema_unsupported(sub, "%s/%s" % (here, name)))
        elif key in ("items", "additionalProperties"):
            out.extend(schema_unsupported(value, here))
    return out


def schema_errors(instance: Any, schema: Any, at: str = "") -> List[Tuple[str, str]]:
    """``(location, message)`` for every way ``instance`` breaks ``schema``.

    Applies the keywords in :data:`SCHEMA_ASSERTIONS`, each to the JSON type it
    governs (``pattern`` reads only a string, ``required`` only an object), as
    JSON Schema 2020-12 does.  A location reads like ``inputs[3].file_kind``; the
    manifest's root is the empty string.  Run :func:`schema_unsupported` on the
    schema first: a keyword this function does not know is not applied.
    """
    if schema is True:
        return []
    if schema is False or not isinstance(schema, dict):
        return [(at, "no value is allowed here")]
    errors: List[Tuple[str, str]] = []
    if "type" in schema:
        names = [schema["type"]] if isinstance(schema["type"], str) else list(schema["type"])
        if not any(_is_json_type(instance, n) for n in names):
            errors.append((at, "%r is not of type %s" % (instance, " or ".join(repr(n) for n in names))))
    if "enum" in schema and not any(_json_equal(instance, v) for v in schema["enum"]):
        errors.append((at, "%r is not one of %r" % (instance, schema["enum"])))
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append((at, "%r is not %r" % (instance, schema["const"])))
    if isinstance(instance, str):
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append((at, "%r does not match %r" % (instance, schema["pattern"])))
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append((at, "%r is shorter than %d character(s)" % (instance, schema["minLength"])))
    if _is_number(instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append((at, "%r is less than the minimum %r" % (instance, schema["minimum"])))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append((at, "%r is greater than the maximum %r" % (instance, schema["maximum"])))
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append((at, "%r must be greater than %r" % (instance, schema["exclusiveMinimum"])))
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append((at, "%r must be less than %r" % (instance, schema["exclusiveMaximum"])))
    if isinstance(instance, dict):
        for key in schema.get("required", ()):
            if key not in instance:
                errors.append((at, "missing required key %r" % key))
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            errors.append((at, "has %d key(s), fewer than the minimum %d" % (len(instance), schema["minProperties"])))
        properties = schema.get("properties", {})
        for key, sub in properties.items():
            if key in instance:
                errors.extend(schema_errors(instance[key], sub, _child(at, key)))
        if "additionalProperties" in schema:
            for key in instance:
                if key not in properties:
                    errors.extend(schema_errors(instance[key], schema["additionalProperties"], _child(at, key)))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append((at, "has %d item(s), fewer than the minimum %d" % (len(instance), schema["minItems"])))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append((at, "has %d item(s), more than the maximum %d" % (len(instance), schema["maxItems"])))
        if "items" in schema:
            for i, item in enumerate(instance):
                errors.extend(schema_errors(item, schema["items"], "%s[%d]" % (at, i)))
    return errors


def _manifest_schema_text() -> str:
    package = __package__ or ""
    if package:
        from importlib import resources  # noqa: PLC0415 -- standard library; works from a wheel and a zip
        node = resources.files(package)
        for part in MANIFEST_SCHEMA_PATH:
            node = node / part
        return node.read_text(encoding="utf-8")
    # run as a loose file rather than as part of the package
    return Path(__file__).resolve().parent.joinpath(*MANIFEST_SCHEMA_PATH).read_text(encoding="utf-8")


def load_manifest_schema() -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """``(schema, None)``, or ``(None, why it cannot be applied)``."""
    try:
        text = _manifest_schema_text()
    except (OSError, ImportError, TypeError, ValueError) as exc:
        return None, "cannot read the contract-v1 manifest schema this checker ships (%s: %s)" % (
            type(exc).__name__, exc)
    try:
        schema = json.loads(text)
    except ValueError as exc:
        return None, "the contract-v1 manifest schema is not valid JSON: %s" % exc
    problems = schema_unsupported(schema)
    if problems:
        return None, "the contract-v1 manifest schema cannot be applied in full: %s" % "; ".join(problems)
    return schema, None


def check_manifest_schema(man: Dict[str, Any], where: str, findings: List[Finding]) -> None:
    """M018: the manifest against the contract-v1 schema; E003 when the schema cannot be applied."""
    _ran("E003")
    schema, problem = load_manifest_schema()
    if schema is None:
        findings.append(Finding("E003", where, "%s -- the manifest's structure is unchecked, which is an error, "
                                               "never a skip" % problem))
        _not_run("the contract-v1 manifest schema could not be applied (E003)", "M018")
        return
    _ran("M018")
    for location, message in schema_errors(man, schema):
        findings.append(Finding("M018", "%s %s" % (where, location) if location else where, message))


# --------------------------------------------------------------------------- #
# Manifest checks.
# --------------------------------------------------------------------------- #
_INPUT_TYPES = {"float", "integer", "categorical", "boolean", "file", "string"}
_OUTPUT_TYPES = {"float", "integer", "categorical", "timeseries", "field", "distribution"}
_PROTOCOLS = {"stdio_json"}
_IDENTITY = ("id", "name", "version", "domain", "modality", "purpose")


def check_manifest(man: Dict[str, Any], pkg: Path, where: str, findings: List[Finding]) -> None:
    check_manifest_schema(man, where, findings)
    _ran("M002", "M003", "M004", "M005", "M006", "M007", "M008", "M009", "M010")
    spec_version = man.get("spec_version")
    ledger = _LEDGER.get()
    if ledger is not None and isinstance(spec_version, str):
        ledger.spec_version = spec_version
    if not isinstance(spec_version, str) or not _MAJOR_MINOR.match(spec_version):
        findings.append(Finding("M002", where, "spec_version must be a MAJOR.MINOR string, got %r" % (spec_version,)))
    else:
        major = int(spec_version.split(".", 1)[0])
        if major > SUPPORTED_CONTRACT_MAJOR:
            findings.append(Finding("M002", where, "spec_version %s targets contract major %d; this checker "
                                                   "supports major <= %d" % (spec_version, major, SUPPORTED_CONTRACT_MAJOR)))

    for key in _IDENTITY:
        value = man.get(key)
        if not isinstance(value, str) or not value.strip():
            findings.append(Finding("M003", where, "missing or empty required key %r" % key))
    owner = man.get("owner")
    if not isinstance(owner, dict) or not str(owner.get("team", "")).strip() or not str(owner.get("contact", "")).strip():
        findings.append(Finding("M003", where, "owner must be a mapping with non-empty team and contact"))

    inputs = man.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        findings.append(Finding("M004", where, "inputs must be a non-empty list"))
        inputs = []
    for i, field in enumerate(inputs):
        at = "%s inputs[%d]" % (where, i)
        if not isinstance(field, dict):
            findings.append(Finding("M004", at, "input must be a mapping"))
            continue
        if not str(field.get("name", "")).strip():
            findings.append(Finding("M004", at, "input has no name"))
        if field.get("type") not in _INPUT_TYPES:
            findings.append(Finding("M004", at, "type %r not in %s" % (field.get("type"), sorted(_INPUT_TYPES))))
        if not isinstance(field.get("required"), bool):
            findings.append(Finding("M004", at, "input must declare required: true|false"))
        if field.get("type") == "categorical" and not field.get("choices"):
            findings.append(Finding("M004", at, "categorical input declares no choices"))
        if field.get("type") == "file" and not field.get("file_kind"):
            findings.append(Finding("M004", at, "file input declares no file_kind"))
        if field.get("type") == "float" and not str(field.get("units") or "").strip():
            findings.append(Finding("M004", at, "float input %r declares no units -- a number without units is not "
                                                "an input a consumer can supply (a dimensionless one says so)"
                                    % (field.get("name"),)))
        bounds = field.get("range")
        if (isinstance(bounds, list) and len(bounds) == 2 and all(_is_number(b) for b in bounds)
                and not bounds[0] < bounds[1]):
            findings.append(Finding("M004", at, "range %r is not [min, max] with min < max" % (bounds,)))

    outputs = man.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        findings.append(Finding("M005", where, "outputs must be a non-empty list"))
        outputs = []
    for i, field in enumerate(outputs):
        at = "%s outputs[%d]" % (where, i)
        if not isinstance(field, dict):
            findings.append(Finding("M005", at, "output must be a mapping"))
            continue
        if not str(field.get("name", "")).strip():
            findings.append(Finding("M005", at, "output has no name"))
        if field.get("type") not in _OUTPUT_TYPES:
            findings.append(Finding("M005", at, "type %r not in %s" % (field.get("type"), sorted(_OUTPUT_TYPES))))
        if not str(field.get("viewer", "")).strip():
            findings.append(Finding("M005", at, "output declares no viewer"))
        if field.get("type") == "categorical" and not field.get("choices"):
            findings.append(Finding("M005", at, "categorical output declares no choices"))
        if field.get("type") == "float" and not str(field.get("units") or "").strip():
            findings.append(Finding("M005", at, "float output %r declares no units -- a number without units is not "
                                                "a result anyone can read (a dimensionless one says so)"
                                    % (field.get("name"),)))

    in_names = [f.get("name") for f in inputs if isinstance(f, dict)]
    out_names = [f.get("name") for f in outputs if isinstance(f, dict)]
    for kind, names in (("input", in_names), ("output", out_names)):
        seen: set = set()
        for name in names:
            if name in seen:
                findings.append(Finding("M006", where, "duplicate %s name %r" % (kind, name)))
            seen.add(name)

    unc = man.get("uncertainty")
    if not isinstance(unc, dict) or not isinstance(unc.get("per_output"), dict) or not str(unc.get("form", "")).strip():
        findings.append(Finding("M007", where, "uncertainty must declare form and a per_output mapping"))
    else:
        covered = set(unc["per_output"])
        for name in out_names:
            if name not in covered:
                findings.append(Finding("M007", where, "uncertainty.per_output has no block for output %r "
                                                       "(every output must declare uncertainty)" % name))
        for name in sorted(covered - set(out_names)):
            findings.append(Finding("M007", where, "uncertainty.per_output declares %r, which is not an output" % name))

    inv = man.get("invocation")
    if not isinstance(inv, dict):
        findings.append(Finding("M008", where, "invocation must be a mapping"))
    else:
        if not str(inv.get("executable", "")).strip():
            findings.append(Finding("M008", where, "invocation.executable is missing"))
        if inv.get("protocol") not in _PROTOCOLS:
            findings.append(Finding("M008", where, "invocation.protocol %r not in %s"
                                    % (inv.get("protocol"), sorted(_PROTOCOLS))))
        if not isinstance(inv.get("timeout_s"), int) or isinstance(inv.get("timeout_s"), bool):
            findings.append(Finding("M008", where, "invocation.timeout_s must be an integer"))

    card_ref = man.get("model_card")
    if not isinstance(card_ref, str) or not card_ref.strip():
        findings.append(Finding("M009", where, "model_card path is missing"))
    elif outside_package(pkg, card_ref):
        findings.append(Finding("M009", where, "model_card path %r %s -- the card must be a file inside the package"
                                % (card_ref, outside_package(pkg, card_ref))))
    elif not (pkg / card_ref).exists():
        findings.append(Finding("M009", where, "model_card path %r does not exist" % card_ref))

    val = man.get("validation")
    report_ref = val.get("report") if isinstance(val, dict) else None
    if not isinstance(report_ref, str) or not report_ref.strip():
        findings.append(Finding("M010", where, "validation.report path is missing"))
    elif outside_package(pkg, report_ref):
        findings.append(Finding("M010", where, "validation.report path %r %s -- the report must be a file inside "
                                               "the package" % (report_ref, outside_package(pkg, report_ref))))
    elif not (pkg / report_ref).exists():
        findings.append(Finding("M010", where, "validation.report path %r does not exist" % report_ref))

    check_provenance(man.get("provenance"), man, pkg, where, findings)


# Roles a hashed artifact may play. The set is deliberately confined to files
# needed to *execute* the model: the card and the validation report are bound by
# identity (C002 / V002 / V003) rather than by hash, because both are written
# after the artifacts they describe and hashing them would be circular.
_ARTIFACT_ROLES = {"entrypoint", "weights", "asset"}


def check_provenance(prov: Any, man: Dict[str, Any], pkg: Path, where: str, findings: List[Finding]) -> None:
    _ran("M011")
    if not isinstance(prov, dict):
        findings.append(Finding("M011", where, "provenance block is missing or not a mapping"))
        _not_run("the provenance block is missing (M011)", "M012", "M013", "M014", "M015", "M016")
        return
    _ran("M012", "M014", "M015", "M016")
    artifacts = prov.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        findings.append(Finding("M012", where, "provenance.artifacts must be a non-empty list"))
        artifacts = []
    entrypoints: List[str] = []
    for i, art in enumerate(artifacts):
        at = "%s provenance.artifacts[%d]" % (where, i)
        if not isinstance(art, dict):
            findings.append(Finding("M012", at, "artifact must be a mapping"))
            continue
        for key in ("path", "role", "sha256", "bytes"):
            if key not in art:
                findings.append(Finding("M012", at, "artifact is missing %r" % key))
        if art.get("role") not in _ARTIFACT_ROLES:
            findings.append(Finding("M012", at, "role %r not in %s" % (art.get("role"), sorted(_ARTIFACT_ROLES))))
        elif art.get("role") == "entrypoint":
            entrypoints.append(str(art.get("path")))
        size = art.get("bytes")
        if "bytes" in art and (not isinstance(size, int) or isinstance(size, bool) or size < 0):
            findings.append(Finding("M012", at, "bytes %r is not a non-negative integer -- a byte count the "
                                                "checker cannot compare is a pin that is never checked" % (size,)))
        digest = art.get("sha256")
        if not isinstance(digest, str) or not _HEX64.match(digest):
            findings.append(Finding("M012", at, "sha256 %r is not 64 lowercase hex characters" % (digest,)))
            continue
        rel = art.get("path")
        if not isinstance(rel, str):
            continue
        outside = outside_package(pkg, rel)
        if outside:
            findings.append(Finding("M012", at, "path %r %s -- an artifact must be a file inside the package, and "
                                                "the checker hashes nothing outside it" % (rel, outside)))
            continue
        target = pkg / rel
        _ran("M013")
        if not target.is_file():
            findings.append(Finding("M013", at, "declared artifact %r does not exist on disk" % rel))
            continue
        actual = sha256_file(target)
        if actual != digest:
            findings.append(Finding("M013", at, "sha256 mismatch for %r: declared %s, on disk %s"
                                    % (rel, digest, actual)))
        real_size = target.stat().st_size
        if isinstance(size, int) and not isinstance(size, bool) and size != real_size:
            findings.append(Finding("M013", at, "bytes mismatch for %r: declared %d, on disk %d"
                                    % (rel, size, real_size)))

    # The executable the manifest dispatches must be one of the hashed artifacts:
    # an unhashed entrypoint is an unverifiable model however good the rest of the
    # provenance block is.
    inv = man.get("invocation")
    executable = inv.get("executable") if isinstance(inv, dict) else None
    if len(entrypoints) != 1:
        findings.append(Finding("M012", where, "provenance.artifacts must declare exactly one role 'entrypoint', "
                                               "found %d" % len(entrypoints)))
    elif isinstance(executable, str):
        _ran("M013")
        want = executable[2:] if executable.startswith("./") else executable
        have = entrypoints[0][2:] if entrypoints[0].startswith("./") else entrypoints[0]
        if want != have:
            findings.append(Finding("M013", where, "invocation.executable %r is not the hashed entrypoint artifact "
                                                   "%r -- the dispatched file is unverifiable"
                                    % (executable, entrypoints[0])))

    dataset = prov.get("dataset")
    digest = dataset.get("sha256") if isinstance(dataset, dict) else None
    if not isinstance(digest, str) or not _HEX64.match(digest):
        findings.append(Finding("M014", where, "provenance.dataset.sha256 %r is not 64 lowercase hex characters"
                                % (digest,)))

    code = prov.get("code")
    if not isinstance(code, dict) or not str(code.get("repo", "")).strip():
        findings.append(Finding("M015", where, "provenance.code must declare repo"))
    else:
        commit = code.get("commit")
        if not isinstance(commit, str) or not _HEX7.match(commit):
            findings.append(Finding("M015", where, "provenance.code.commit %r is not a >=7 hex commit id" % (commit,)))

    env = prov.get("environment")
    if not isinstance(env, dict) or not str(env.get("python", "")).strip():
        findings.append(Finding("M016", where, "provenance.environment.python is not declared"))
    _not_run("no artifact reached the hash comparison and no single entrypoint was declared (M012)", "M013")


# --------------------------------------------------------------------------- #
# Model-card checks.
# --------------------------------------------------------------------------- #
def check_card(text: str, man: Optional[Dict[str, Any]], where: str, findings: List[Finding]) -> None:
    _ran("C001", "C003")
    front, body, error = split_front_matter(text)
    if error is not None:
        findings.append(Finding("C001", where, error))
    if front is None or man is None:
        _not_run("the card's front-matter did not parse (C001)", "C002")
    if front is not None and man is not None:
        _ran("C002")
        for card_key, man_key in (("model_id", "id"), ("version", "version"), ("spec_version", "spec_version")):
            have, want = front.get(card_key), man.get(man_key)
            if have is None:
                findings.append(Finding("C002", where, "front-matter is missing %r" % card_key))
            elif want is not None and str(have) != str(want):
                findings.append(Finding("C002", where, "front-matter %s %r does not match manifest %s %r"
                                        % (card_key, have, man_key, want)))

    headings = h2_headings(body)
    need = len(CARD_SECTIONS)
    if len(headings) < need:
        missing = [s for s in CARD_SECTIONS if s not in headings]
        findings.append(Finding("C003", where, "card has %d H2 section(s); all %d required sections must come first, "
                                               "in order (missing: %s)"
                                % (len(headings), need, ", ".join(missing) or "none -- check ordering")))
        _not_run("the card has fewer H2 sections than the eleven required (C003)", "C006")
    else:
        _ran("C006")
        for i, expected in enumerate(CARD_SECTIONS):
            if headings[i] != expected:
                findings.append(Finding("C003", where, "H2 section #%d must be '## %s' but is '## %s'"
                                        % (i + 1, expected, headings[i])))
        for extra in headings[need:]:
            if extra not in CARD_SECTIONS_RESERVED:
                findings.append(Finding("C006", where, "extra H2 '## %s' is not a reserved section name %s"
                                        % (extra, list(CARD_SECTIONS_RESERVED))))

    bodies = section_bodies(body)
    for name in CARD_SECTIONS:
        if name not in bodies:
            continue
        _ran("C004")
        content = "".join(bodies[name].split())
        if len(content) < MIN_SECTION_CHARS:
            findings.append(Finding("C004", where, "section '## %s' has %d non-whitespace characters; a required "
                                                   "section must be written, not stubbed (minimum %d)"
                                    % (name, len(content), MIN_SECTION_CHARS)))

    _not_run("no required section is present to measure (C003)", "C004")
    uq = bodies.get("Uncertainty quantification", "")
    if not uq:
        _not_run("the card has no Uncertainty quantification section to read (C003)", "C005")
    if uq:
        _ran("C005")
        if not _NUMERAL.search(uq):
            findings.append(Finding("C005", where, "section '## Uncertainty quantification' states no number; "
                                                   "a UQ section must report a level or a measured coverage"))
        lowered = uq.lower()
        if not any(word in lowered for word in ("conformal", "ensemble", "quantile", "bayes", "dropout",
                                                "interval", "monte carlo", "bootstrap", "gaussian process")):
            findings.append(Finding("C005", where, "section '## Uncertainty quantification' names no method"))


# --------------------------------------------------------------------------- #
# Validation-report checks.
# --------------------------------------------------------------------------- #
# A check reporting PASS or FAIL states how its measurement was compared with
# its bar, as comparators: ``{"metric": <key of metrics>, "op": <operator>,
# "bar": <key of thresholds>}``, read "metric op bar".  The status follows from
# them -- PASS when every comparator holds, FAIL when one does not -- and a check
# whose declared status disagrees is rejected (V013), as V008 rejects a rollup
# that disagrees with its checks.  A package declaring contract 1.1 or later must
# give every PASS and FAIL check at least one (V012); in a 1.0 package they are
# optional and checked when present.  NOT_RUN and NOT_APPLICABLE carry no
# measurement, so comparators on them are not read.
COMPARATOR_OPS: Dict[str, Any] = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge, "==": operator.eq,
}
#: The contract version from which a measured check must carry comparators and
#: ``bitwise`` reproducibility means a tolerance of exactly 0.
COMPARATORS_REQUIRED_FROM: Tuple[int, int] = (1, 1)


def _major_minor(value: Any) -> Optional[Tuple[int, int]]:
    if isinstance(value, str) and _MAJOR_MINOR.match(value):
        major, minor = value.split(".")
        return int(major), int(minor)
    return None


def _declared_version(rep: Dict[str, Any], man: Optional[Dict[str, Any]]) -> Optional[Tuple[int, int]]:
    """The contract version the package declares: its manifest's, else its report's."""
    version = _major_minor(man.get("spec_version")) if isinstance(man, dict) else None
    return version if version is not None else _major_minor(rep.get("spec_version"))


def check_comparators(check: Dict[str, Any], required: bool, at: str, findings: List[Finding]) -> None:
    """V012 and V013 for one check whose status is PASS or FAIL."""
    status = check.get("status")
    comparators = check.get("comparators")
    if comparators is None:
        if required:
            _ran("V012")
            findings.append(Finding("V012", at, "a %s check in a contract 1.1 package must state its comparators: "
                                                "a list of {metric, op, bar} naming the measurement and the "
                                                "threshold it was compared with" % status))
        return
    _ran("V012")
    if not isinstance(comparators, list) or not comparators:
        findings.append(Finding("V012", at, "comparators must be a non-empty list of {metric, op, bar}, got %r"
                                % (comparators,)))
        return
    metrics = check.get("metrics") if isinstance(check.get("metrics"), dict) else {}
    thresholds = check.get("thresholds") if isinstance(check.get("thresholds"), dict) else {}
    outcomes: List[Tuple[str, bool]] = []
    well_formed = True
    for i, comparator in enumerate(comparators):
        cat = "%s comparators[%d]" % (at, i)
        if not isinstance(comparator, dict):
            findings.append(Finding("V012", cat, "a comparator must be a mapping {metric, op, bar}, got %r"
                                    % (comparator,)))
            well_formed = False
            continue
        metric, op, bar = comparator.get("metric"), comparator.get("op"), comparator.get("bar")
        value = metrics.get(metric) if isinstance(metric, str) else None
        bound = thresholds.get(bar) if isinstance(bar, str) else None
        problems = []
        if op not in COMPARATOR_OPS:
            problems.append("op %r is not one of %s" % (op, list(COMPARATOR_OPS)))
        if not _is_number(value):
            problems.append("metric %r names no number in this check's metrics" % (metric,))
        if not _is_number(bound):
            problems.append("bar %r names no number in this check's thresholds" % (bar,))
        if problems:
            findings.append(Finding("V012", cat, "; ".join(problems)))
            well_formed = False
            continue
        holds = bool(COMPARATOR_OPS[op](value, bound))
        outcomes.append(("%s = %r %s %s = %r" % (metric, value, op, bar, bound), holds))
    if not well_formed:
        return
    _ran("V013")
    recomputed = "PASS" if all(holds for _, holds in outcomes) else "FAIL"
    if recomputed != status:
        if recomputed == "FAIL":
            detail = "; ".join("%s does not hold" % text for text, holds in outcomes if not holds)
        else:
            detail = "every comparator holds"
        findings.append(Finding("V013", at, "declares %s, but its comparators give %s: %s -- the status must "
                                            "follow from the numbers" % (status, recomputed, detail)))


def check_report(rep: Dict[str, Any], man: Optional[Dict[str, Any]], where: str, findings: List[Finding]) -> None:
    _ran("V001")
    for key in ("spec_version", "produced_by", "model_id", "model_version"):
        if not str(rep.get(key, "")).strip():
            findings.append(Finding("V001", where, "missing or empty required key %r" % key))
    checks = rep.get("checks")
    if not isinstance(checks, dict):
        findings.append(Finding("V001", where, "checks must be a mapping of ladder key -> check object"))
        _not_run("the report has no checks mapping (V001)", *[r.id for r in RULES if r.id.startswith("V")])
        return
    _ran("V004", "V005", "V008")
    version = _declared_version(rep, man)
    comparators_required = version is not None and version >= COMPARATORS_REQUIRED_FROM

    if man is not None:
        _ran("V002")
        if rep.get("model_id") != man.get("id"):
            findings.append(Finding("V002", where, "model_id %r does not match manifest id %r"
                                    % (rep.get("model_id"), man.get("id"))))
        if rep.get("model_version") != man.get("version"):
            findings.append(Finding("V002", where, "model_version %r does not match manifest version %r"
                                    % (rep.get("model_version"), man.get("version"))))
        if rep.get("spec_version") != man.get("spec_version"):
            findings.append(Finding("V002", where, "spec_version %r does not match manifest spec_version %r -- the "
                                                   "report and the package must declare one contract version"
                                    % (rep.get("spec_version"), man.get("spec_version"))))
        prov = man.get("provenance")
        declared = (prov.get("dataset") or {}).get("sha256") if isinstance(prov, dict) else None
        if declared is None:
            _not_run("the manifest declares no provenance dataset sha256 to compare with (M014)", "V003")
        else:
            _ran("V003")
        if declared is not None and rep.get("dataset_sha256") != declared:
            findings.append(Finding("V003", where, "dataset_sha256 %r does not match the manifest's provenance "
                                                   "dataset sha256 %r -- the report describes a different corpus "
                                                   "than the package ships" % (rep.get("dataset_sha256"), declared)))

    for key in LADDER:
        if key not in checks:
            findings.append(Finding("V004", where, "ladder key %r is absent; every key must be reported with a "
                                                   "status (a skipped check is never a silent pass)" % key))

    blocking = 0
    for key, check in sorted(checks.items()):
        at = "%s checks.%s" % (where, key)
        if key not in LADDER:
            findings.append(Finding("V004", at, "%r is not a contract ladder key %s" % (key, list(LADDER))))
            continue
        if not isinstance(check, dict):
            findings.append(Finding("V005", at, "check must be a mapping, got %s -- a declaration string is not a "
                                                "check" % type(check).__name__))
            blocking += 1
            continue
        status = check.get("status")
        if status not in STATUSES:
            findings.append(Finding("V005", at, "status %r not in %s" % (status, list(STATUSES))))
            blocking += 1
            continue
        if status in BLOCKING_STATUSES:
            blocking += 1
        if status == "NOT_APPLICABLE":
            _ran("V007")
        if status == "PASS":
            _ran("V006")
        if status == "NOT_APPLICABLE" and not str(check.get("reason", "")).strip():
            findings.append(Finding("V007", at, "NOT_APPLICABLE must state a reason"))
        if status in ("PASS", "FAIL"):
            check_comparators(check, comparators_required, at, findings)
        if status == "PASS":
            if not numeric_leaves(check.get("metrics")):
                findings.append(Finding("V006", at, "PASS with no numeric measurement in 'metrics' -- presence is "
                                                    "not compliance"))
            if not numeric_leaves(check.get("thresholds")):
                findings.append(Finding("V006", at, "PASS with no numeric value in 'thresholds' -- a check that "
                                                    "compares against nothing cannot fail"))

    _not_run("no check reports PASS", "V006")
    _not_run("no check reports NOT_APPLICABLE", "V007")
    _not_run("the package declares contract 1.0, where comparators are optional, and no measured check "
             "declares any", "V012")
    _not_run("no measured check declares well-formed comparators to recompute its status from", "V013")
    recomputed = "FAIL" if blocking else "PASS"
    declared = rep.get("overall")
    if declared not in ("PASS", "FAIL"):
        findings.append(Finding("V008", where, "overall %r must be PASS or FAIL" % (declared,)))
    elif declared != recomputed:
        findings.append(Finding("V008", where, "overall declared %s but recomputing from the checks gives %s "
                                               "(%d blocking)" % (declared, recomputed, blocking)))

    check_b4(checks.get("B4_conservation"), where, findings)
    check_a3(checks.get("A3_uq_calibration"), where, findings)
    check_a5(checks.get("A5_reproducibility"), where, findings, version=version)


def check_b4(check: Any, where: str, findings: List[Finding]) -> None:
    """B4 conservation: a number over a named control volume, or a stated inapplicability.

    This is the rule the scalar ladder's V2.3 cannot satisfy.  V2.3 passes when a
    free-text field is a non-empty string, so the string
    ``"applicable_not_implemented_v0 (...)"`` -- which asserts the check applies
    and supplies no measurement -- is graded PASS today.  Under B4 that is a FAIL,
    because asserting applicability obliges a number.
    """
    at = "%s checks.B4_conservation" % where
    if check is None:
        _not_run("B4_conservation is absent (V004)", "V009")
        return  # V004 already reported the absence
    _ran("V009")
    if not isinstance(check, dict):
        findings.append(Finding("V009", at, "B4 must be a check object, got %s -- a declaration string is not a "
                                            "conservation measurement" % type(check).__name__))
        return
    applicable = check.get("applicable")
    if not isinstance(applicable, bool):
        findings.append(Finding("V009", at, "B4 must declare applicable: true|false"))
        return
    if not applicable:
        if not str(check.get("reason", "")).strip():
            findings.append(Finding("V009", at, "B4 applicable: false must state why no quantity is conserved"))
        if check.get("status") != "NOT_APPLICABLE":
            findings.append(Finding("V009", at, "B4 applicable: false must carry status NOT_APPLICABLE, not %r"
                                    % (check.get("status"),)))
        return
    for key in ("quantity", "control_volume"):
        if not str(check.get(key, "")).strip():
            findings.append(Finding("V009", at, "B4 applicable: true must name %r" % key))
    if check.get("scope") not in ("local", "control_volume"):
        findings.append(Finding("V009", at, "B4 scope must be 'local' or 'control_volume', got %r"
                                % (check.get("scope"),)))
    metrics = check.get("metrics")
    imbalance = metrics.get("relative_imbalance") if isinstance(metrics, dict) else None
    if not isinstance(imbalance, (int, float)) or isinstance(imbalance, bool):
        findings.append(Finding("V009", at, "B4 applicable: true must report metrics.relative_imbalance as a "
                                            "number, got %r -- declaring the check applicable obliges a "
                                            "measurement" % (imbalance,)))
    elif imbalance < 0:
        findings.append(Finding("V009", at, "B4 metrics.relative_imbalance must be non-negative, got %r" % imbalance))
    if not numeric_leaves(check.get("thresholds")):
        findings.append(Finding("V009", at, "B4 applicable: true must state a numeric threshold"))
    comparators = check.get("comparators")
    if check.get("status") in ("PASS", "FAIL") and isinstance(comparators, list) and not any(
            isinstance(c, dict) and c.get("metric") == "relative_imbalance" and c.get("op") in ("<", "<=")
            for c in comparators):
        findings.append(Finding("V009", at, "B4's comparators must compare metrics.relative_imbalance against its "
                                            "threshold with '<=' or '<' -- that comparison is what B4 measures"))


# Statuses under which the per-key legibility rules V010 and V011 have nothing
# to read.  NOT_APPLICABLE means the check cannot apply; NOT_RUN means it
# applies and was not executed.  Neither carries a measurement, so demanding one
# made NOT_RUN -- a status spec section 5.3 defines for every key -- impossible
# to report honestly for A3 and A5: a package whose model has not been trained
# was rejected for saying so, while a NOT_APPLICABLE claim with any reason at
# all was accepted.
#
# This narrows what V010 and V011 read; it does not loosen the verdict.  NOT_RUN
# is in BLOCKING_STATUSES, so it forces the recomputed overall to FAIL and V008
# rejects a report that claims otherwise.  V010 and V011 ask "when this check
# was run, is its instrument legible?", and only a check that ran can answer.
# PASS and FAIL are both measured verdicts and stay fully graded.
_UNMEASURED_STATUSES: Tuple[str, ...] = ("NOT_APPLICABLE", "NOT_RUN")


def check_a3(check: Any, where: str, findings: List[Finding]) -> None:
    at = "%s checks.A3_uq_calibration" % where
    if not isinstance(check, dict) or check.get("status") in _UNMEASURED_STATUSES:
        _not_run("A3_uq_calibration carries no measurement to read (NOT_RUN, NOT_APPLICABLE or absent)", "V010")
        return
    _ran("V010")
    metrics = check.get("metrics") if isinstance(check.get("metrics"), dict) else {}
    for key in ("nominal", "empirical_coverage"):
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            findings.append(Finding("V010", at, "metrics.%s must be a number, got %r" % (key, value)))
        elif not 0.0 <= float(value) <= 1.0:
            findings.append(Finding("V010", at, "metrics.%s must be a probability in [0, 1], got %r" % (key, value)))
    n = metrics.get("n")
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        findings.append(Finding("V010", at, "metrics.n must be a positive integer sample count, got %r" % (n,)))
    if not str(check.get("method", "")).strip():
        findings.append(Finding("V010", at, "A3 must name the UQ method it calibrated"))


def check_a5(check: Any, where: str, findings: List[Finding],
             version: Optional[Tuple[int, int]] = None) -> None:
    at = "%s checks.A5_reproducibility" % where
    if not isinstance(check, dict) or check.get("status") in _UNMEASURED_STATUSES:
        _not_run("A5_reproducibility carries no measurement to read (NOT_RUN, NOT_APPLICABLE or absent)", "V011")
        return
    _ran("V011")
    if check.get("determinism_class") not in ("bitwise", "seeded_tolerance"):
        findings.append(Finding("V011", at, "A5 must declare determinism_class 'bitwise' or 'seeded_tolerance', "
                                            "got %r -- the two ladders use tolerances four orders of magnitude "
                                            "apart for this one name" % (check.get("determinism_class"),)))
    thresholds = check.get("thresholds") if isinstance(check.get("thresholds"), dict) else {}
    tol = thresholds.get("tolerance")
    if not isinstance(tol, (int, float)) or isinstance(tol, bool) or tol < 0:
        findings.append(Finding("V011", at, "A5 thresholds.tolerance must be a non-negative number, got %r" % (tol,)))
    elif (check.get("determinism_class") == "bitwise" and tol != 0
          and version is not None and version >= COMPARATORS_REQUIRED_FROM):
        findings.append(Finding("V011", at, "A5 declares determinism_class 'bitwise' at tolerance %r; from contract "
                                            "1.1 bitwise means a tolerance of 0, and a non-zero tolerance is "
                                            "'seeded_tolerance'" % (tol,)))


# --------------------------------------------------------------------------- #
# The smoke test: ``check --smoke`` runs the entrypoint on the manifest's examples.
#
# The default check reads files and runs nothing.  ``--smoke`` also runs the
# package's entrypoint the way a consumer dispatches it under ``stdio_json``: once
# per ``examples[]`` entry, with that example's inputs as the request, in the
# package directory, within ``invocation.timeout_s``.  Each answer must carry every
# declared output and every uncertainty field the manifest's ``per_output`` blocks
# name (S001).  A smoke test that cannot run -- no examples, an entrypoint the static
# check did not verify, a host that cannot launch it, a module the entrypoint
# imports missing from the checking environment -- is reported as a warning with
# its reason (S002), never as a pass.
#
# It runs only an entrypoint the static check verified: inside the package, its
# bytes matching their pin.  It still executes the package's code, so run it only
# on a package you would run.
# --------------------------------------------------------------------------- #
SMOKE_RULES: Tuple[str, ...] = ("S001", "S002")
#: Static findings after which the entrypoint is not one the checker will run.
_SMOKE_BLOCKERS: Tuple[str, ...] = ("M008", "M012", "M013")
_MODULE_NOT_FOUND = re.compile(r"ModuleNotFoundError: No module named '([^']+)'")


def _last_json_object(text: str) -> Optional[Dict[str, Any]]:
    """The answer frame: all of stdout as one JSON object, else its last line that is one."""
    try:
        whole = json.loads(text)
    except ValueError:
        whole = None
    if isinstance(whole, dict):
        return whole
    for line in reversed([ln for ln in text.splitlines() if ln.strip()]):
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        if isinstance(frame, dict):
            return frame
    return None


def _tail(text: str, limit: int = 200) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return ""
    last = lines[-1]
    return ": " + (last if len(last) <= limit else last[:limit] + "...")


def _smoke_command(pkg: Path, executable: str) -> Tuple[Optional[List[str]], Optional[str]]:
    # absolute, because the process runs with the package directory as its cwd
    target = (pkg / executable).resolve()
    if target.suffix.lower() == ".py":
        return [sys.executable, str(target)], None
    if os.access(str(target), os.X_OK) and not target.is_dir():
        return [str(target)], None
    return None, "the checker cannot launch a %r entrypoint on this host" % (target.suffix or target.name)


def smoke_test(man: Dict[str, Any], pkg: Path, where: str, findings: List[Finding]) -> Optional[str]:
    """Run S001 over the manifest's examples.  Returns None, or why the smoke test could not run."""
    blockers = sorted({f.rule for f in findings if f.rule in _SMOKE_BLOCKERS})
    if blockers:
        return ("the static check did not verify the entrypoint (%s), and the smoke test runs only a verified one"
                % ", ".join(blockers))
    inv = man.get("invocation") if isinstance(man.get("invocation"), dict) else {}
    executable = inv.get("executable")
    timeout = inv.get("timeout_s")
    if not isinstance(executable, str) or outside_package(pkg, executable):
        return "invocation.executable does not name a file inside the package"
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        return "invocation.timeout_s is not a positive integer"
    examples = man.get("examples")
    if not isinstance(examples, list) or not examples:
        return "the manifest declares no examples[] to run"
    argv, problem = _smoke_command(pkg, executable)
    if argv is None:
        return problem
    outputs = [f.get("name") for f in man.get("outputs") or [] if isinstance(f, dict)]
    unc = man.get("uncertainty") if isinstance(man.get("uncertainty"), dict) else {}
    per_output = unc.get("per_output") if isinstance(unc.get("per_output"), dict) else {}
    uq_fields = sorted({value for block in per_output.values() if isinstance(block, dict)
                        for key, value in block.items() if key.endswith("_field") and isinstance(value, str)})
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    import subprocess  # noqa: PLC0415 -- imported only when --smoke asks for a run
    for i, example in enumerate(examples):
        at = "%s examples[%d]" % (where, i)
        if not isinstance(example, dict) or not isinstance(example.get("inputs"), dict):
            findings.append(Finding("S001", at, "the example has no inputs mapping to send"))
            continue
        request = json.dumps({"inputs": example["inputs"]}) + "\n"
        try:
            proc = subprocess.run(argv, input=request, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout, cwd=str(pkg.resolve()), env=env)
        except subprocess.TimeoutExpired:
            findings.append(Finding("S001", at, "no answer within invocation.timeout_s = %d s" % timeout))
            continue
        except OSError as exc:
            return "the entrypoint could not be launched here (%s: %s)" % (type(exc).__name__, exc)
        if proc.returncode != 0:
            missing = _MODULE_NOT_FOUND.search(proc.stderr or "")
            if missing and not proc.stdout.strip():
                return ("the entrypoint imports %r, which is not installed in the checking environment"
                        % missing.group(1))
            findings.append(Finding("S001", at, "the entrypoint exited with code %d%s"
                                    % (proc.returncode, _tail(proc.stdout) or _tail(proc.stderr))))
            continue
        frame = _last_json_object(proc.stdout)
        if frame is None:
            findings.append(Finding("S001", at, "the answer on stdout is not a JSON object%s" % _tail(proc.stdout)))
            continue
        if "status" in frame and frame["status"] != "ok":
            said = frame.get("error") or frame.get("reason") or ""
            findings.append(Finding("S001", at, "the entrypoint declined the example: status %r%s"
                                    % (frame["status"], _tail(said if isinstance(said, str) else json.dumps(said)))))
            continue
        answer = frame.get("outputs")
        if not isinstance(answer, dict):
            findings.append(Finding("S001", at, "the answer carries no outputs mapping"))
            continue
        missing_outputs = [name for name in outputs if name not in answer]
        if missing_outputs:
            findings.append(Finding("S001", at, "the answer omits declared output(s) %s" % missing_outputs))
        missing_uq = [name for name in uq_fields if name not in answer]
        if missing_uq:
            findings.append(Finding("S001", at, "the answer omits the uncertainty field(s) %s that "
                                                "uncertainty.per_output names" % missing_uq))
    return None


# --------------------------------------------------------------------------- #
# Package orchestration.
# --------------------------------------------------------------------------- #
def find_manifest(pkg: Path) -> Optional[Path]:
    for name in ("manifest.yaml", "manifest.yml", "manifest.json"):
        if (pkg / name).is_file():
            return pkg / name
    return None


def check_package(pkg: Path, smoke: bool = False) -> List[Finding]:
    """Validate one contract package.  Returns every finding; empty means conformant.

    ``smoke=True`` also runs the entrypoint on the manifest's examples (rules S001
    and S002); without it nothing is executed.
    """
    findings: List[Finding] = []
    _ran("E001")
    if not pkg.is_dir():
        findings.append(Finding("E001", str(pkg), "not a directory"))
        return findings
    _ran("M001")
    manifest_path = find_manifest(pkg)
    if manifest_path is None:
        findings.append(Finding("M001", str(pkg), "no manifest.yaml / manifest.yml / manifest.json in the package"))
        return findings

    man = load_mapping(manifest_path, findings)
    if man is None:
        return findings
    _document("manifest", manifest_path)
    check_manifest(man, pkg, manifest_path.name, findings)

    card_ref = man.get("model_card")
    if isinstance(card_ref, str) and not outside_package(pkg, card_ref) and (pkg / card_ref).is_file():
        try:
            text = (pkg / card_ref).read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(Finding("C001", card_ref, "cannot read: %s" % exc))
        else:
            _document("model_card", pkg / card_ref)
            check_card(text, man, card_ref, findings)

    val = man.get("validation")
    report_ref = val.get("report") if isinstance(val, dict) else None
    if isinstance(report_ref, str) and not outside_package(pkg, report_ref) and (pkg / report_ref).is_file():
        rep = load_mapping(pkg / report_ref, findings)
        if rep is not None:
            _document("validation_report", pkg / report_ref)
            check_report(rep, man, report_ref, findings)

    if smoke:
        _ran("S002")
        reason = smoke_test(man, pkg, manifest_path.name, findings)
        if reason is None:
            _ran("S001")
        else:
            findings.append(Finding("S002", manifest_path.name, "the smoke test could not run: %s" % reason))
            ledger = _LEDGER.get()
            if ledger is not None:
                ledger.smoke_reason = reason
    return findings


def summarize(findings: Sequence[Finding]) -> Dict[str, Any]:
    errors = [f for f in findings if f.severity == "ERROR"]
    warns = [f for f in findings if f.severity == "WARN"]
    return {
        "contract_version": CONTRACT_VERSION,
        "conformant": not errors,
        "n_error": len(errors),
        "n_warn": len(warns),
        "rules_failed": sorted({f.rule for f in findings}),
        "findings": [f.as_dict() for f in findings],
    }


# --------------------------------------------------------------------------- #
# The conformance record: what ``check --json`` writes.
#
# One record per package: the package and contract versions, the checker and its
# version, when the check ran, whether ``--smoke`` was asked for, the sha256 and
# size of the manifest, card and report it read, the verdict, a state for every
# rule this checker has -- ``evaluated``, ``fired`` (with how many findings) or
# ``not_evaluated`` (with the reason) -- and the findings.  Its JSON Schema ships
# as ``schemas/contract-v1/conformance-record.schema.json``.
# --------------------------------------------------------------------------- #
RECORD_VERSION = "1.0"
RULE_STATES: Tuple[str, ...] = ("evaluated", "fired", "not_evaluated")


def checker_version() -> str:
    """This checker's own version: the package's ``__version__``, else the installed distribution's."""
    package = sys.modules.get(__package__ or "")
    version = getattr(package, "__version__", None)
    if isinstance(version, str) and version:
        return version
    try:
        from importlib.metadata import version as installed_version  # noqa: PLC0415
        return installed_version("open-contract-ml")
    except Exception:  # noqa: BLE001 -- a loose copy of this file has no distribution
        return "unknown"


def _fallback_reason(rule: str, ledger: _Ledger, smoke: bool) -> str:
    if rule in SMOKE_RULES:
        if not smoke:
            return "check --smoke was not requested; the default check runs nothing"
        return ledger.smoke_reason or "the manifest could not be read"
    if "manifest" not in ledger.documents:
        return "the manifest could not be found or read"
    if rule.startswith("C"):
        return "the model card was not read"
    if rule.startswith("V"):
        return "the validation report was not read"
    if rule == "E002":
        return "no file the checker read is YAML"
    return "not reached"


def _describe(path: Optional[Path], pkg: Path) -> Optional[Dict[str, Any]]:
    if path is None or not path.is_file():
        return None
    try:
        rel = path.resolve().relative_to(pkg.resolve()).as_posix()
    except ValueError:
        return None
    return {"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size}


def check_package_with_record(pkg: Path, smoke: bool = False,
                              now: Optional[Any] = None) -> Tuple[List[Finding], Dict[str, Any]]:
    """``check_package`` and the conformance record of the same run."""
    import datetime  # noqa: PLC0415
    ledger = _Ledger()
    previous = _LEDGER.set(ledger)
    try:
        findings = check_package(pkg, smoke=smoke)
    finally:
        _LEDGER.reset(previous)
    fired: Dict[str, int] = {}
    for f in findings:
        fired[f.rule] = fired.get(f.rule, 0) + 1
    rules: Dict[str, Dict[str, Any]] = {}
    for rule in RULES:
        if rule.id in fired:
            rules[rule.id] = {"severity": rule.severity, "state": "fired", "findings": fired[rule.id]}
        elif rule.id in ledger.evaluated:
            rules[rule.id] = {"severity": rule.severity, "state": "evaluated"}
        else:
            reason = ledger.reasons.get(rule.id) or _fallback_reason(rule.id, ledger, smoke)
            rules[rule.id] = {"severity": rule.severity, "state": "not_evaluated", "reason": reason}
    stamp = now if now is not None else datetime.datetime.now(datetime.timezone.utc)
    record = {
        "record_version": RECORD_VERSION,
        "package": str(pkg),
        "contract_version": CONTRACT_VERSION,
        "spec_version": ledger.spec_version,
        "checker": {"name": "open-contract-ml", "version": checker_version()},
        "checked_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "smoke": bool(smoke),
        "documents": {kind: _describe(ledger.documents.get(kind), pkg)
                      for kind in ("manifest", "model_card", "validation_report")},
    }
    summary = summarize(findings)
    for key in ("conformant", "n_error", "n_warn", "rules_failed"):
        record[key] = summary[key]
    record["rules"] = rules
    record["findings"] = summary["findings"]
    return findings, record


def conformance_record(pkg: Path, smoke: bool = False, now: Optional[Any] = None) -> Dict[str, Any]:
    """The conformance record of checking ``pkg`` (what ``check --json`` writes for it)."""
    return check_package_with_record(pkg, smoke=smoke, now=now)[1]


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _cmd_check(args: argparse.Namespace) -> int:
    exit_code = 0
    records: List[Dict[str, Any]] = []
    for raw in args.packages:
        pkg = Path(raw)
        findings, record = check_package_with_record(pkg, smoke=args.smoke)
        records.append(record)
        summary = summarize(findings)
        versions = "contract %s" % CONTRACT_VERSION
        if record["spec_version"] not in (None, CONTRACT_VERSION):
            versions += ", package declares %s" % record["spec_version"]
        if summary["conformant"]:
            print("OK   %s  (%s, %d warning(s))" % (pkg, versions, summary["n_warn"]))
        else:
            print("FAIL %s  (%d error(s), %d warning(s))" % (pkg, summary["n_error"], summary["n_warn"]))
            exit_code = 1
        for f in findings:
            print("  [%s %s] %s: %s" % (f.severity, f.rule, f.where, f.message))
    if args.json:
        # one record for one package; an array of records, in argument order, for several
        payload: Any = records[0] if len(records) == 1 else records
        write_lf(Path(args.json), json.dumps(payload, indent=2) + "\n")
    return exit_code


def vocabulary() -> Dict[str, Any]:
    """The machine-readable contract vocabulary, derived from this module.

    Shipped as ``schemas/contract-v1/contract-vocabulary.json`` so a consumer in another
    language gets the section set, the ladder and the legacy mapping without
    re-typing them. ``tests`` asserts the committed file equals this, so the
    two cannot drift.
    """
    return {
        "contract_version": CONTRACT_VERSION,
        "supported_major": SUPPORTED_CONTRACT_MAJOR,
        "card_sections_required": list(CARD_SECTIONS),
        "card_sections_reserved": list(CARD_SECTIONS_RESERVED),
        "min_section_chars": MIN_SECTION_CHARS,
        "ladder": {"A": list(TIER_A), "B": list(TIER_B), "C": list(TIER_C)},
        "statuses": list(STATUSES),
        "blocking_statuses": list(BLOCKING_STATUSES),
        "artifact_roles": sorted(_ARTIFACT_ROLES),
        "input_types": sorted(_INPUT_TYPES),
        "output_types": sorted(_OUTPUT_TYPES),
        "protocols": sorted(_PROTOCOLS),
        "legacy_aliases": dict(sorted(LEGACY_ALIASES.items())),
        "legacy_aliases_lane_dependent": {
            "FG7": {"grid": "B4_conservation", "mesh": "B4_conservation",
                    "cloud": "B6_integrated_quantities"}
        },
        "legacy_aliases_retired": {old: dict(sorted(replaced.items()))
                                   for old, replaced in sorted(RETIRED_ALIASES.items())},
        "rules": [{"id": r.id, "severity": r.severity, "title": r.title} for r in RULES],
    }


def _cmd_vocabulary(args: argparse.Namespace) -> int:
    text = json.dumps(vocabulary(), indent=2) + "\n"
    if args.out:
        write_lf(Path(args.out), text)
        print("wrote %s" % args.out)
    else:
        print(text, end="")
    return 0


def _cmd_rules(args: argparse.Namespace) -> int:
    print("Contract v%s -- %d rules" % (CONTRACT_VERSION, len(RULES)))
    for r in RULES:
        print("  %-5s %-5s %s" % (r.id, r.severity, r.title))
    print("\nLadder keys (%d): %s" % (len(LADDER), ", ".join(LADDER)))
    print("Card sections (%d): %s" % (len(CARD_SECTIONS), ", ".join(CARD_SECTIONS)))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="verify.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="validate contract package(s)")
    p_check.add_argument("packages", nargs="+")
    p_check.add_argument("--json", help="write the conformance record here: one record for one package, an array "
                                         "of records for several")
    p_check.add_argument("--smoke", action="store_true",
                         help="also run the entrypoint on the manifest's examples[] under stdio_json (rules S001, "
                              "S002); this executes the package's code, so use it only on a package you would run")
    p_check.set_defaults(func=_cmd_check)

    p_rules = sub.add_parser("rules", help="print the rule table")
    p_rules.set_defaults(func=_cmd_rules)

    p_vocab = sub.add_parser("vocabulary", help="emit the machine-readable contract vocabulary")
    p_vocab.add_argument("--out", help="write the JSON here")
    p_vocab.set_defaults(func=_cmd_vocabulary)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
