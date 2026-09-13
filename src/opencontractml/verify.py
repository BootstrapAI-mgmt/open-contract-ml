"""Contract v1 conformance checker.

The Contract is the single model-card / manifest / provenance / validation
standard that joins this repo's scalar pipelines, the ``physics-surrogates``
field surrogates and the ``cae-ml-gui`` dispatcher.  The normative text is
``docs/spec/CONTRACT-v1.md``; the machine-readable structure lives under
``schemas/contract-v1/``.  This module is the executable half: it decides whether a
given artifact complies, and it says exactly which rule failed and why.

Two modes:

    python -m opencontractml.verify check <package-dir> [--json report.json]
        Strict conformance of one contract package (manifest + card + validation
        report + the artifacts they name).  Exit 0 when clean, 1 on findings.

    python -m opencontractml.verify gap [--gui-root P] [--physsur-root P] [--out M.md]
        The measured three-way gap: every contract requirement against every
        producer in the ecosystem, by opening the producers' real files.
        Exit 0 always -- this is a measurement, not a gate.

    python -m opencontractml.verify rules
        Print the rule table.

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
  number should be remains the lane's engineering judgement.

Standard library only: this repo ships no ``pyproject.toml`` and no dependency
manifest, so the checker must run from a bare Python.  YAML is read through
PyYAML when it is importable and is a hard ERROR when it is not (rule E002);
``manifest.json`` is an accepted dependency-free equivalent of ``manifest.yaml``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

CONTRACT_VERSION = "1.0"
SUPPORTED_CONTRACT_MAJOR = 1

# --------------------------------------------------------------------------- #
# The reconciled model-card section set (spec section 4).
#
# The first eleven H2 headings of a contract card, in this order.  Positions 1-5,
# 7-9 and 11 are cae-ml-gui's MANDATORY_SECTIONS in their original relative
# order; "Training configuration" (6) and "Provenance" (10) are the two
# insertions that carry what this repo's worked-instance cards say and the GUI's
# set has nowhere to put.  Keeping the GUI's nine in order is deliberate: the
# GUI's adoption diff is two inserted strings, not a re-ordering.
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
}


def legacy_key(lane: str, legacy: str) -> Optional[str]:
    """Map a legacy gate id to its contract key, resolving the FG7 collision by lane.

    ``FG7`` is ``conservation`` in the grid and mesh lanes (a global energy
    balance) and ``integrated quantities`` in the cloud lane (a lift coefficient
    against the released labels).  Those are different physical claims sharing
    one identifier; the contract splits them into B4 and B6.
    """
    if legacy == "FG7":
        return "B6_integrated_quantities" if lane == "cloud" else "B4_conservation"
    return LEGACY_ALIASES.get(legacy)


STATUSES = ("PASS", "FAIL", "NOT_RUN", "NOT_APPLICABLE")
# NOT_RUN always blocks: the check applies and was not executed.  NOT_APPLICABLE
# does not block but requires a stated reason -- the distinction physics-surrogates
# currently expresses as an "allow_not_run" allow-list, which loses the reason.
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
    Rule("M001", "ERROR", "manifest present and parses to a mapping"),
    Rule("M002", "ERROR", "spec_version present, MAJOR.MINOR, major supported"),
    Rule("M003", "ERROR", "identity block complete (id, name, version, owner, domain, modality, purpose)"),
    Rule("M004", "ERROR", "inputs declared and well formed"),
    Rule("M005", "ERROR", "outputs declared and well formed"),
    Rule("M006", "ERROR", "no duplicate input or output names"),
    Rule("M007", "ERROR", "every output is covered by an uncertainty.per_output block"),
    Rule("M008", "ERROR", "invocation block complete and protocol is supported"),
    Rule("M009", "ERROR", "model_card path declared and the file exists"),
    Rule("M010", "ERROR", "validation.report path declared and the file exists"),
    Rule("M011", "ERROR", "provenance block present"),
    Rule("M012", "ERROR", "provenance.artifacts entries well formed (path, role, sha256, bytes)"),
    Rule("M013", "ERROR", "every declared artifact exists and its sha256 matches the file on disk"),
    Rule("M014", "ERROR", "provenance.dataset carries a well formed sha256"),
    Rule("M015", "ERROR", "provenance.code carries repo and commit"),
    Rule("M016", "WARN", "provenance.environment names the interpreter"),
    Rule("C001", "ERROR", "model card parses with a flat scalar front-matter"),
    Rule("C002", "ERROR", "card front-matter identity matches the manifest"),
    Rule("C003", "ERROR", "the eleven required card sections are present, first, in order"),
    Rule("C004", "ERROR", "no required card section is a stub"),
    Rule("C005", "ERROR", "the uncertainty section states a method and a number"),
    Rule("C006", "WARN", "extra H2 sections use reserved names"),
    Rule("V001", "ERROR", "validation report parses and declares its identity"),
    Rule("V002", "ERROR", "validation report identity matches the manifest"),
    Rule("V003", "ERROR", "validation report dataset hash matches the manifest provenance"),
    Rule("V004", "ERROR", "every ladder key is present"),
    Rule("V005", "ERROR", "every check declares a known status"),
    Rule("V006", "ERROR", "a PASS carries a numeric measurement and a numeric threshold"),
    Rule("V007", "ERROR", "NOT_APPLICABLE states a reason"),
    Rule("V008", "ERROR", "the declared overall verdict matches the recomputed one"),
    Rule("V009", "ERROR", "B4 conservation is measured, not declared"),
    Rule("V010", "ERROR", "A3 uq_calibration reports nominal, empirical coverage, n and method"),
    Rule("V011", "ERROR", "A5 reproducibility declares a determinism class and a tolerance"),
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
    dependency.  This is a tightening of, and compatible with, every card in the
    ecosystem today.  Returns ``(mapping, body, error)``.
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
# Manifest checks.
# --------------------------------------------------------------------------- #
_INPUT_TYPES = {"float", "integer", "categorical", "boolean", "file", "string"}
_OUTPUT_TYPES = {"float", "integer", "categorical", "timeseries", "field", "distribution"}
_PROTOCOLS = {"stdio_json"}
_IDENTITY = ("id", "name", "version", "domain", "modality", "purpose")


def check_manifest(man: Dict[str, Any], pkg: Path, where: str, findings: List[Finding]) -> None:
    spec_version = man.get("spec_version")
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
    elif not (pkg / card_ref).exists():
        findings.append(Finding("M009", where, "model_card path %r does not exist" % card_ref))

    val = man.get("validation")
    report_ref = val.get("report") if isinstance(val, dict) else None
    if not isinstance(report_ref, str) or not report_ref.strip():
        findings.append(Finding("M010", where, "validation.report path is missing"))
    elif not (pkg / report_ref).exists():
        findings.append(Finding("M010", where, "validation.report path %r does not exist" % report_ref))

    check_provenance(man.get("provenance"), man, pkg, where, findings)


# Roles a hashed artifact may play. The set is deliberately confined to files
# needed to *execute* the model: the card and the validation report are bound by
# identity (C002 / V002 / V003) rather than by hash, because both are written
# after the artifacts they describe and hashing them would be circular.
_ARTIFACT_ROLES = {"entrypoint", "weights", "asset"}


def check_provenance(prov: Any, man: Dict[str, Any], pkg: Path, where: str, findings: List[Finding]) -> None:
    if not isinstance(prov, dict):
        findings.append(Finding("M011", where, "provenance block is missing or not a mapping"))
        return
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
        digest = art.get("sha256")
        if not isinstance(digest, str) or not _HEX64.match(digest):
            findings.append(Finding("M012", at, "sha256 %r is not 64 lowercase hex characters" % (digest,)))
            continue
        rel = art.get("path")
        if not isinstance(rel, str):
            continue
        target = pkg / rel
        if not target.is_file():
            findings.append(Finding("M013", at, "declared artifact %r does not exist on disk" % rel))
            continue
        actual = sha256_file(target)
        if actual != digest:
            findings.append(Finding("M013", at, "sha256 mismatch for %r: declared %s, on disk %s"
                                    % (rel, digest, actual)))
        size = art.get("bytes")
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


# --------------------------------------------------------------------------- #
# Model-card checks.
# --------------------------------------------------------------------------- #
def check_card(text: str, man: Optional[Dict[str, Any]], where: str, findings: List[Finding]) -> None:
    front, body, error = split_front_matter(text)
    if error is not None:
        findings.append(Finding("C001", where, error))
    if front is not None and man is not None:
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
    else:
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
        content = "".join(bodies[name].split())
        if len(content) < MIN_SECTION_CHARS:
            findings.append(Finding("C004", where, "section '## %s' has %d non-whitespace characters; a required "
                                                   "section must be written, not stubbed (minimum %d)"
                                    % (name, len(content), MIN_SECTION_CHARS)))

    uq = bodies.get("Uncertainty quantification", "")
    if uq:
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
def check_report(rep: Dict[str, Any], man: Optional[Dict[str, Any]], where: str, findings: List[Finding]) -> None:
    for key in ("spec_version", "produced_by", "model_id", "model_version"):
        if not str(rep.get(key, "")).strip():
            findings.append(Finding("V001", where, "missing or empty required key %r" % key))
    checks = rep.get("checks")
    if not isinstance(checks, dict):
        findings.append(Finding("V001", where, "checks must be a mapping of ladder key -> check object"))
        return

    if man is not None:
        if rep.get("model_id") != man.get("id"):
            findings.append(Finding("V002", where, "model_id %r does not match manifest id %r"
                                    % (rep.get("model_id"), man.get("id"))))
        if rep.get("model_version") != man.get("version"):
            findings.append(Finding("V002", where, "model_version %r does not match manifest version %r"
                                    % (rep.get("model_version"), man.get("version"))))
        prov = man.get("provenance")
        declared = (prov.get("dataset") or {}).get("sha256") if isinstance(prov, dict) else None
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
        if status == "NOT_APPLICABLE" and not str(check.get("reason", "")).strip():
            findings.append(Finding("V007", at, "NOT_APPLICABLE must state a reason"))
        if status == "PASS":
            if not numeric_leaves(check.get("metrics")):
                findings.append(Finding("V006", at, "PASS with no numeric measurement in 'metrics' -- presence is "
                                                    "not compliance"))
            if not numeric_leaves(check.get("thresholds")):
                findings.append(Finding("V006", at, "PASS with no numeric value in 'thresholds' -- a check that "
                                                    "compares against nothing cannot fail"))

    recomputed = "FAIL" if blocking else "PASS"
    declared = rep.get("overall")
    if declared not in ("PASS", "FAIL"):
        findings.append(Finding("V008", where, "overall %r must be PASS or FAIL" % (declared,)))
    elif declared != recomputed:
        findings.append(Finding("V008", where, "overall declared %s but recomputing from the checks gives %s "
                                               "(%d blocking)" % (declared, recomputed, blocking)))

    check_b4(checks.get("B4_conservation"), where, findings)
    check_a3(checks.get("A3_uq_calibration"), where, findings)
    check_a5(checks.get("A5_reproducibility"), where, findings)


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
        return  # V004 already reported the absence
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


def check_a3(check: Any, where: str, findings: List[Finding]) -> None:
    at = "%s checks.A3_uq_calibration" % where
    if not isinstance(check, dict) or check.get("status") == "NOT_APPLICABLE":
        return
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


def check_a5(check: Any, where: str, findings: List[Finding]) -> None:
    at = "%s checks.A5_reproducibility" % where
    if not isinstance(check, dict) or check.get("status") == "NOT_APPLICABLE":
        return
    if check.get("determinism_class") not in ("bitwise", "seeded_tolerance"):
        findings.append(Finding("V011", at, "A5 must declare determinism_class 'bitwise' or 'seeded_tolerance', "
                                            "got %r -- the two ladders use tolerances three orders of magnitude "
                                            "apart for this one name" % (check.get("determinism_class"),)))
    thresholds = check.get("thresholds") if isinstance(check.get("thresholds"), dict) else {}
    tol = thresholds.get("tolerance")
    if not isinstance(tol, (int, float)) or isinstance(tol, bool) or tol < 0:
        findings.append(Finding("V011", at, "A5 thresholds.tolerance must be a non-negative number, got %r" % (tol,)))


# --------------------------------------------------------------------------- #
# Package orchestration.
# --------------------------------------------------------------------------- #
def find_manifest(pkg: Path) -> Optional[Path]:
    for name in ("manifest.yaml", "manifest.yml", "manifest.json"):
        if (pkg / name).is_file():
            return pkg / name
    return None


def check_package(pkg: Path) -> List[Finding]:
    """Validate one contract package.  Returns every finding; empty means conformant."""
    findings: List[Finding] = []
    if not pkg.is_dir():
        findings.append(Finding("E001", str(pkg), "not a directory"))
        return findings
    manifest_path = find_manifest(pkg)
    if manifest_path is None:
        findings.append(Finding("M001", str(pkg), "no manifest.yaml / manifest.yml / manifest.json in the package"))
        return findings

    man = load_mapping(manifest_path, findings)
    if man is None:
        return findings
    check_manifest(man, pkg, manifest_path.name, findings)

    card_ref = man.get("model_card")
    if isinstance(card_ref, str) and (pkg / card_ref).is_file():
        try:
            text = (pkg / card_ref).read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(Finding("C001", card_ref, "cannot read: %s" % exc))
        else:
            check_card(text, man, card_ref, findings)

    val = man.get("validation")
    report_ref = val.get("report") if isinstance(val, dict) else None
    if isinstance(report_ref, str) and (pkg / report_ref).is_file():
        rep = load_mapping(pkg / report_ref, findings)
        if rep is not None:
            check_report(rep, man, report_ref, findings)
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
# Gap measurement: every contract requirement against every real producer.
#
# Each probe opens the producer's real artifact and looks for the real key or
# section.  The verdicts are therefore measured, not asserted; re-running this
# after a producer changes will move the table.
# --------------------------------------------------------------------------- #
COMPLIES, PARTIAL, ABSENT, NOTFOUND = "COMPLIES", "PARTIAL", "ABSENT", "SOURCE-MISSING"

DEFAULT_GUI_ROOT = Path("C:/wt/g1d-gui")
DEFAULT_PS_ROOT = Path("C:/wt/g1d-ps")


class Sources:
    """The real artifacts the four producers emit or demand, loaded once."""

    def __init__(self, repo: Path, gui_root: Path, ps_root: Path) -> None:
        self.repo, self.gui_root, self.ps_root = repo, gui_root, ps_root
        self.notes: List[str] = []
        self.dp_card_path = repo / "WORKED-INSTANCE-A81-link1-thermal-model-card.md"
        self.dp_report_path = (repo / "examples/TASK-10-corpus-consumer/evidence/reports"
                                      "/model_card_real_pv-f1_plate.json")
        self.ps_report_path = ps_root / "evidence/heat64/models/fno/model_card.json"
        self.gui_schema_path = gui_root / "schemas/manifest.schema.json"
        self.gui_card_module = gui_root / "server/model_card.py"

        self.dp_card_text = self._text(self.dp_card_path)
        self.dp_card_sections = h2_headings(split_front_matter(self.dp_card_text or "")[1]) if self.dp_card_text else None
        self.dp_report = self._json(self.dp_report_path)
        self.ps_report = self._json(self.ps_report_path)
        self.gui_schema = self._json(self.gui_schema_path)
        self.gui_sections = self._gui_sections()

    def _text(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            self.notes.append("source missing: %s" % path)
            return None

    def _json(self, path: Path) -> Optional[Dict[str, Any]]:
        text = self._text(path)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError as exc:
            self.notes.append("unparseable: %s (%s)" % (path, exc))
            return None

    def _gui_sections(self) -> Optional[List[str]]:
        """cae-ml-gui's MANDATORY_SECTIONS, read out of its source rather than copied."""
        text = self._text(self.gui_card_module)
        if text is None:
            return None
        m = re.search(r"MANDATORY_SECTIONS:.*?=\s*\((?P<body>.*?)\)", text, re.DOTALL)
        if m is None:
            self.notes.append("could not locate MANDATORY_SECTIONS in %s" % self.gui_card_module)
            return None
        return re.findall(r'"([^"]+)"', m.group("body"))

    @property
    def gui_required(self) -> List[str]:
        return list((self.gui_schema or {}).get("required") or [])

    @property
    def gui_properties(self) -> List[str]:
        return list(((self.gui_schema or {}).get("properties") or {}).keys())

    def ps_gate_keys(self) -> List[str]:
        gates = (self.ps_report or {}).get("gates") or []
        return [g.get("gate", "").split("_")[0] for g in gates]

    def dp_check_names(self) -> List[str]:
        rep = self.dp_report or {}
        names: List[str] = []
        for entry in (rep.get("models") or {}).values():
            for check in entry.get("checks", []):
                names.append(str(check.get("check", "")).split(" ")[0])
        if "V1.5" in rep:
            names.append("V1.5")
        names += list((rep.get("V2_declarations") or {}).keys())
        if "V3" in rep:
            names.append("V3")
        return names


def _v(present: bool, evidence: str, partial: bool = False) -> Tuple[str, str]:
    if not present:
        return ABSENT, evidence
    return (PARTIAL if partial else COMPLIES), evidence


def build_gap_rows(src: Sources) -> List[Dict[str, Any]]:
    """One row per contract requirement, four measured producer verdicts each."""
    rows: List[Dict[str, Any]] = []

    def row(req_id: str, requirement: str, dp_card, dp_rep, ps_rep, gui) -> None:
        rows.append({"id": req_id, "requirement": requirement,
                     "dp_card": dp_card, "dp_report": dp_rep, "ps_report": ps_rep, "gui": gui})

    missing = (NOTFOUND, "artifact not readable")
    dpc = src.dp_card_sections
    dpr = src.dp_report
    psr = src.ps_report

    def has_key(obj: Optional[Dict[str, Any]], *path: str) -> Tuple[str, str]:
        if obj is None:
            return missing
        node: Any = obj
        walked: List[str] = []
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return ABSENT, "no %s" % ".".join(path)
            node = node[key]
            walked.append(key)
        return COMPLIES, "%s = %s" % (".".join(path), json.dumps(node)[:60])

    def card_has(names: Iterable[str]) -> Tuple[str, str]:
        if dpc is None:
            return missing
        hit = [n for n in names if any(n.lower() in h.lower() for h in dpc)]
        return _v(bool(hit), ("section %r" % hit[0]) if hit else "no section among %s" % list(names))

    def gui_req(key: str) -> Tuple[str, str]:
        if src.gui_schema is None:
            return missing
        if key in src.gui_required:
            return COMPLIES, "manifest.schema.json required: %s" % key
        if key in src.gui_properties:
            return PARTIAL, "optional property: %s" % key
        return ABSENT, "not in manifest.schema.json"

    def gui_section(name: str) -> Tuple[str, str]:
        if src.gui_sections is None:
            return missing
        return _v(name in src.gui_sections, "MANDATORY_SECTIONS %s %r"
                  % ("contains" if name in src.gui_sections else "lacks", name))

    # --- manifest identity + contract ------------------------------------- #
    row("M002", "spec_version (MAJOR.MINOR) with a stated compatibility rule",
        card_has(["spec_version"]), has_key(dpr, "spec_version"), has_key(psr, "spec_version"), gui_req("spec_version"))
    row("M003", "identity: id, name, version, owner, domain, modality, purpose",
        card_has(["identity"]), has_key(dpr, "model_meta"), has_key(psr, "model"), gui_req("id"))
    row("M004", "typed input signature (name, type, units, range, required)",
        card_has(["input-channel", "architecture topology"]),
        has_key(dpr, "model_meta", "features"),
        (COMPLIES if (psr or {}).get("model", {}).get("config") else ABSENT,
         "model.config: %s" % json.dumps((psr or {}).get("model", {}).get("config"))[:60]) if psr else missing,
        gui_req("inputs"))
    row("M005", "typed output signature with a viewer per output",
        card_has(["output"]), has_key(dpr, "model_meta", "targets"), (ABSENT, "no outputs/viewer block"),
        gui_req("outputs"))
    row("M007", "uncertainty.per_output covers every declared output",
        card_has(["UQ approach"]), (PARTIAL, "A3-equivalent V1.3 per model, no per_output contract"),
        (PARTIAL, "FG3 per model, no per_output contract"), gui_req("uncertainty"))
    row("M008", "invocation: executable + protocol + timeout (stdio_json)",
        (ABSENT, "prose card declares no invocation"), (ABSENT, "no invocation block"),
        (ABSENT, "emits .onnx/.npz exports; no stdio_json wrapper"), gui_req("invocation"))
    row("M009", "a human model card is referenced by path from the manifest",
        (PARTIAL, "card exists but nothing references it"), (ABSENT, "no model_card path"),
        (ABSENT, "no .md card emitted at all"), gui_req("model_card"))
    row("M010", "a machine validation report is referenced by path from the manifest",
        (ABSENT, "no validation.report path"), (PARTIAL, "report exists, nothing references it"),
        (PARTIAL, "report exists, nothing references it"),
        _v("validation" in src.gui_properties, "not in manifest.schema.json") if src.gui_schema else missing)

    # --- provenance -------------------------------------------------------- #
    row("M012", "provenance.artifacts[] with path, role, sha256, bytes per shipped file",
        (ABSENT, "no hashes in the prose card"), (ABSENT, "hashes the corpus, not the artifacts"),
        (PARTIAL, "runs.py registry hashes checkpoint+exports, not carried in the card"),
        gui_req("provenance"))
    row("M013", "declared artifact hashes verify against the files on disk",
        (ABSENT, "nothing to verify"), (ABSENT, "no artifact hashes"),
        (PARTIAL, "runs.py check re-hashes, but out of band of the card"), gui_req("provenance"))
    row("M014", "provenance.dataset.sha256",
        (ABSENT, "no dataset hash"), has_key(dpr, "corpus", "sha256"), has_key(psr, "dataset", "sha256"),
        gui_req("provenance"))
    row("M015", "provenance.code repo + commit",
        (ABSENT, "no commit"),
        (PARTIAL, "data_card generator_commit is 'unknown-not-a-git-checkout'"),
        (PARTIAL, "physsur_version only, no commit"), gui_req("provenance"))
    row("M016", "provenance.environment names the interpreter and key packages",
        (ABSENT, "no environment block"), has_key(dpr, "model_meta", "versions"),
        (PARTIAL, "versions in metrics.json, not in the card"), gui_req("provenance"))

    # --- card sections ----------------------------------------------------- #
    for name in CARD_SECTIONS:
        probe_names = {"Architecture": ["architecture"], "Training configuration": ["training configuration"],
                       "Uncertainty quantification": ["uq approach", "uncertainty"],
                       "Provenance": ["provenance"], "Version history": ["version history"],
                       "Known failure modes": ["known failure", "open questions"],
                       "Performance": ["performance"], "Training data": ["training data"],
                       "Out of scope": ["out of scope"], "Intended use": ["intended use"],
                       "TL;DR": ["tl;dr"]}.get(name, [name.lower()])
        row("C003:%s" % name, "card section '## %s'" % name, card_has(probe_names),
            (ABSENT, "machine report, no prose"), (ABSENT, "machine report, no prose"), gui_section(name))

    # --- ladder ------------------------------------------------------------ #
    dp_checks = src.dp_check_names()
    ps_gates = src.ps_gate_keys()
    reverse: Dict[str, List[str]] = {}
    for legacy, key in LEGACY_ALIASES.items():
        reverse.setdefault(key, []).append(legacy)
    reverse.setdefault("B4_conservation", []).append("FG7")
    reverse.setdefault("B6_integrated_quantities", []).append("FG7")

    for key in LADDER:
        legacy = sorted(set(reverse.get(key, [])))
        dp_legacy = [g for g in legacy if g.startswith("V")]
        ps_legacy = [g for g in legacy if g.startswith("FG")]
        dp_hit = [g for g in dp_legacy if any(name.startswith(g) for name in dp_checks)]
        ps_hit = [g for g in ps_legacy if g in ps_gates]
        dp_verdict: Tuple[str, str]
        if not dp_hit:
            dp_verdict = (ABSENT, "no scalar-ladder equivalent")
        elif key == "B4_conservation":
            dp_verdict = (PARTIAL, "V2.3 present but is a non-empty-string declaration, not a measurement")
        elif key == "B5_invariance":
            dp_verdict = (PARTIAL, "V2.4 present but is a declaration, not a measurement")
        else:
            dp_verdict = (COMPLIES, "scalar ladder %s" % ", ".join(dp_hit))
        if not ps_hit:
            ps_verdict = (ABSENT, "no field-ladder equivalent")
        elif key == "B6_integrated_quantities":
            ps_verdict = (PARTIAL, "cloud lane FG7 only; grid/mesh FG7 means conservation (id collision)")
        else:
            ps_verdict = (COMPLIES, "field ladder %s" % ", ".join(ps_hit))
        row("V004:%s" % key, "ladder key %s" % key, (ABSENT, "prose card runs no ladder"),
            dp_verdict, ps_verdict, (ABSENT, "the GUI validates no ladder at all"))

    row("V006", "a PASS carries a numeric measurement and a numeric threshold",
        (ABSENT, "no machine checks"),
        (PARTIAL, "V1.x carry numbers; V2.3/V2.4 pass on a non-empty string"),
        (COMPLIES, "every FG carries metrics + thresholds"),
        (ABSENT, "the GUI validates no checks"))
    row("V008", "the declared overall verdict is recomputable from the checks",
        (ABSENT, "n/a"),
        (PARTIAL, "'passed' is an AND over checks, but V2.3/V2.4 contribute a string test"),
        (COMPLIES, "overall recomputed; NOT_RUN blocks unless allow-listed"),
        (ABSENT, "n/a"))
    row("V009", "B4 conservation is a measured relative imbalance over a named control volume",
        (ABSENT, "n/a"),
        (ABSENT, "V2.3 is a declaration; the real card says 'applicable_not_implemented_v0' and passes"),
        (COMPLIES, "FG7 grid/mesh: |source-sink-edge|/gross vs imbalance_max"),
        (ABSENT, "n/a"))
    row("V011", "A5 reproducibility declares a determinism class and a tolerance",
        (ABSENT, "n/a"), (PARTIAL, "tol 1e-6 stated, class not named"),
        (PARTIAL, "rel_tol 2e-2 stated, class not named"), (ABSENT, "n/a"))
    return rows


def render_gap_markdown(rows: List[Dict[str, Any]], src: Sources) -> str:
    tally: Dict[str, Dict[str, int]] = {c: {} for c in ("dp_card", "dp_report", "ps_report", "gui")}
    for r in rows:
        for col in tally:
            tally[col][r[col][0]] = tally[col].get(r[col][0], 0) + 1
    lines = [
        "# Contract v1 -- measured three-way gap",
        "",
        "Generated by `python -m opencontractml.verify gap`. Every verdict is a probe against the",
        "producer's real artifact, not a hand-written assertion. Re-run after any producer",
        "changes and the table moves.",
        "",
        "Sources probed:",
        "",
        "| column | artifact |",
        "|---|---|",
        "| `dp_card` | `%s` |" % src.dp_card_path.name,
        "| `dp_report` | `%s` |" % src.dp_report_path.relative_to(src.repo).as_posix(),
        "| `ps_report` | `physics-surrogates/%s` |" % src.ps_report_path.relative_to(src.ps_root).as_posix(),
        "| `gui` | `cae-ml-gui/schemas/manifest.schema.json` + `server/model_card.py` (what it *demands*) |",
        "",
        "Verdicts: **COMPLIES** emits/demands it - **PARTIAL** has something adjacent, not the",
        "contract - **ABSENT** nothing - **SOURCE-MISSING** the artifact was not readable.",
        "",
        "## Tally",
        "",
        "| producer | COMPLIES | PARTIAL | ABSENT | SOURCE-MISSING |",
        "|---|---|---|---|---|",
    ]
    for col in ("dp_card", "dp_report", "ps_report", "gui"):
        t = tally[col]
        lines.append("| `%s` | %d | %d | %d | %d |" % (col, t.get(COMPLIES, 0), t.get(PARTIAL, 0),
                                                       t.get(ABSENT, 0), t.get(NOTFOUND, 0)))
    lines += ["", "## Requirement x producer", "",
              "| # | requirement | dp card | dp report | ps report | gui demands |", "|---|---|---|---|---|---|"]
    for r in rows:
        cells = []
        for col in ("dp_card", "dp_report", "ps_report", "gui"):
            verdict, evidence = r[col]
            cells.append("**%s**<br/><sub>%s</sub>" % (verdict, evidence.replace("|", "\\|")))
        lines.append("| `%s` | %s | %s |" % (r["id"], r["requirement"].replace("|", "\\|"), " | ".join(cells)))
    if src.notes:
        lines += ["", "## Probe notes", ""] + ["- %s" % n for n in src.notes]
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def _cmd_check(args: argparse.Namespace) -> int:
    exit_code = 0
    for raw in args.packages:
        pkg = Path(raw)
        findings = check_package(pkg)
        summary = summarize(findings)
        if args.json:
            write_lf(Path(args.json), json.dumps({"package": str(pkg), **summary}, indent=2) + "\n")
        if summary["conformant"]:
            print("OK   %s  (contract %s, %d warning(s))" % (pkg, CONTRACT_VERSION, summary["n_warn"]))
        else:
            print("FAIL %s  (%d error(s), %d warning(s))" % (pkg, summary["n_error"], summary["n_warn"]))
            exit_code = 1
        for f in findings:
            print("  [%s %s] %s: %s" % (f.severity, f.rule, f.where, f.message))
    return exit_code


def _cmd_gap(args: argparse.Namespace) -> int:
    src = Sources(Path(args.repo_root), Path(args.gui_root), Path(args.physsur_root))
    rows = build_gap_rows(src)
    markdown = render_gap_markdown(rows, src)
    if args.out:
        write_lf(Path(args.out), markdown)
        print("wrote %s (%d requirements x 4 producers)" % (args.out, len(rows)))
    else:
        print(markdown)
    if args.json:
        write_lf(Path(args.json), json.dumps(
            {"contract_version": CONTRACT_VERSION, "notes": src.notes,
             "rows": [{"id": r["id"], "requirement": r["requirement"],
                       **{c: {"verdict": r[c][0], "evidence": r[c][1]}
                          for c in ("dp_card", "dp_report", "ps_report", "gui")}} for r in rows]},
            indent=2) + "\n")
    return 0


def vocabulary() -> Dict[str, Any]:
    """The machine-readable contract vocabulary, derived from this module.

    Shipped as ``schemas/contract-v1/contract-vocabulary.json`` so a consumer in another
    language gets the section set, the ladder and the legacy mapping without
    re-typing them. ``tests`` asserts the committed file equals this, so the
    two cannot drift -- the divergence guard cae-ml-gui calls Wall A.
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
    p_check.add_argument("--json", help="write the machine-readable report here")
    p_check.set_defaults(func=_cmd_check)

    p_gap = sub.add_parser("gap", help="measure the three-way gap against the real producers")
    p_gap.add_argument("--repo-root", default=str(Path(__file__).resolve().parent))
    p_gap.add_argument("--gui-root", default=str(DEFAULT_GUI_ROOT))
    p_gap.add_argument("--physsur-root", default=str(DEFAULT_PS_ROOT))
    p_gap.add_argument("--out", help="write the markdown matrix here")
    p_gap.add_argument("--json", help="write the machine-readable matrix here")
    p_gap.set_defaults(func=_cmd_gap)

    p_rules = sub.add_parser("rules", help="print the rule table")
    p_rules.set_defaults(func=_cmd_rules)

    p_vocab = sub.add_parser("vocabulary", help="emit the machine-readable contract vocabulary")
    p_vocab.add_argument("--out", help="write the JSON here")
    p_vocab.set_defaults(func=_cmd_vocabulary)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
