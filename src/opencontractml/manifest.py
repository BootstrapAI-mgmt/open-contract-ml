"""Manifest validation: the contract-as-code contract (arc TC-102).

A model registers with a machine-checkable ``manifest.yaml``. This module is
the single authority that decides whether a manifest is admissible, and it
gives the rest of the server a typed, validated view of one.

Validation is layered, and the order is load-bearing:

1. **Structure** — the manifest is validated against the canonical
   ``schemas/manifest.schema.json`` (JSON Schema Draft 2020-12). The schema is
   the source of truth for required fields, enums, and shapes; jsonschema runs
   *first* so a structurally-broken manifest never reaches the typed layer.
2. **Typed model** — a valid manifest is parsed into the :class:`Manifest`
   Pydantic model, which mirrors the schema and gives downstream code
   (registry, runner, API) attribute access with real types.
3. **Semantics** — cross-field invariants the JSON Schema cannot express are
   checked on the typed model. The keystone is **every output must be covered
   by an ``uncertainty.per_output`` block** (design ``gui-design.md`` §3 step 6;
   Wall A): a model with an uncovered output is *rejected*, never warned.

Rejection is always **loud**: any failure raises
:class:`ManifestValidationError`, which carries *all* discovered problems
(``.errors``) and the source (``.source``) so the registry (TC-104) can surface
them at ``/admin/rejected-models``. The non-raising :func:`collect_manifest_errors`
returns the same list for callers that prefer to aggregate.

Out of scope here (deliberately): scanning ``./models/``, hot-reload, the admin
surface (all TC-104), and checking that ``invocation.executable`` exists on disk
(design §3 step 3 — TC-104/TC-201). Keeping the executable check out of the
contract layer is what lets the worked example — which ships no ``.exe`` — stay
contract-valid. Patterns (e.g. the ``id`` regex) live only in the JSON Schema to
avoid the schema/code divergence Wall A exists to catch; the typed layer mirrors
required fields and enums, which downstream code switches on.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as SchemaError
from pydantic import BaseModel, ConfigDict
from pydantic import ValidationError as PydanticValidationError

from .model_card import ModelCard, collect_model_card_errors, load_model_card

__all__ = [
    "MANIFEST_SCHEMA_PATH",
    "DEFERRED_VIEWERS",
    "SUPPORTED_SPEC_MAJOR",
    "DEFAULT_SPEC_VERSION",
    "Modality",
    "InputType",
    "OutputType",
    "Viewer",
    "FileKind",
    "UncertaintyForm",
    "Owner",
    "InputField",
    "OutputField",
    "Calibration",
    "Uncertainty",
    "Invocation",
    "Lineage",
    "Example",
    "Manifest",
    "ValidatedModel",
    "ManifestValidationError",
    "schema_errors",
    "semantic_errors",
    "collect_manifest_errors",
    "manifest_warnings",
    "parse_manifest_data",
    "load_manifest",
    "load_model",
    "deferred_viewer_outputs",
    "validate_package",
    "package_warnings",
]

# The canonical schema — package data, resolved out of the installed wheel.
#
# Upstream this was `resource_path("schemas", "manifest.schema.json")`, a helper
# that resolved assets under `sys._MEIPASS` when running inside a PyInstaller
# bundle. That helper is part of the packaged application, not of the standard,
# and it was the only thing standing between this module and being installable
# on its own. Shipping the schema as package data removes the frozen-bundle
# special case entirely: the schema travels inside the wheel, so there is one
# resolution path and it is the same in a source tree, a wheel and a frozen exe.
MANIFEST_SCHEMA_PATH = Path(
    str(resources.files(__package__) / "schemas" / "package-v1" / "manifest.schema.json")
)


# --------------------------------------------------------------------------- #
# Enums — mirror schemas/manifest.schema.json exactly. test_manifest.py asserts
# parity against the schema file so a future schema edit that is not reflected
# here fails CI (the divergence Wall A guards against).
# --------------------------------------------------------------------------- #
class Modality(StrEnum):
    scalar_in_scalar_out = "scalar_in_scalar_out"
    tabular_in_scalar_out = "tabular_in_scalar_out"
    timeseries_in_scalar_out = "timeseries_in_scalar_out"
    timeseries_in_timeseries_out = "timeseries_in_timeseries_out"
    geometry_in_scalar_out = "geometry_in_scalar_out"
    geometry_in_field_out = "geometry_in_field_out"
    field_in_field_out = "field_in_field_out"


class InputType(StrEnum):
    float = "float"
    integer = "integer"
    categorical = "categorical"
    boolean = "boolean"
    file = "file"
    string = "string"


class OutputType(StrEnum):
    float = "float"
    integer = "integer"
    categorical = "categorical"
    timeseries = "timeseries"
    field = "field"
    distribution = "distribution"


class Viewer(StrEnum):
    scalar_with_uq = "scalar_with_uq"
    categorical_with_confidence = "categorical_with_confidence"
    timeseries_with_band = "timeseries_with_band"
    field_contour = "field_contour"
    histogram = "histogram"


class FileKind(StrEnum):
    stl = "stl"
    step = "step"
    csv = "csv"
    vtk = "vtk"
    npz = "npz"


class UncertaintyForm(StrEnum):
    predictive_interval = "predictive_interval"
    ensemble = "ensemble"
    quantiles = "quantiles"
    monte_carlo = "monte_carlo"
    class_probabilities = "class_probabilities"


# Viewers the schema accepts but the viewer layer does not implement in v1.
# Accepted at validation time, surfaced via deferred_viewer_outputs() so the
# registry/UI can flag them rather than silently mis-render (design §14, Wall A).
DEFERRED_VIEWERS: frozenset[Viewer] = frozenset({Viewer.field_contour})


# Manifest-spec (schema) versioning + back-compat policy (TC-GUI17; design §13
# decision 15). `spec_version` is MAJOR.MINOR; a manifest omitting it is assumed
# to target the v1 spec (DEFAULT_SPEC_VERSION). The GUI loads any manifest whose
# MAJOR is <= SUPPORTED_SPEC_MAJOR — minor bumps are additive and back-compatible,
# and unknown additive fields are ignored by the typed model — and rejects a
# higher MAJOR loud. This is the version-independence that lets one GUI build load
# models authored against a later same-major spec without a rebuild (operator
# Requirement 4); a breaking (major) spec is refused honestly, never mis-rendered.
SUPPORTED_SPEC_MAJOR = 1
DEFAULT_SPEC_VERSION = "1.0"


# --------------------------------------------------------------------------- #
# Typed model. extra fields are ignored (the schema sets no
# additionalProperties:false, so manifests may carry extras; the typed view just
# does not surface them). protected_namespaces=() lets the `model_card` field
# coexist with Pydantic's reserved `model_` namespace without a warning.
# --------------------------------------------------------------------------- #
class Owner(BaseModel):
    team: str
    contact: str


class InputField(BaseModel):
    name: str
    type: InputType
    units: str | None = None
    canonical_units: str | None = None
    range: tuple[float, float] | None = None
    choices: list[str] | None = None
    file_kind: FileKind | None = None
    required: bool
    default: Any = None
    description: str | None = None


class OutputField(BaseModel):
    name: str
    type: OutputType
    units: str | None = None
    choices: list[str] | None = None
    viewer: Viewer


class Calibration(BaseModel):
    holdout_size: int | None = None
    empirical_coverage: float | None = None
    method: str | None = None


class Uncertainty(BaseModel):
    form: UncertaintyForm
    # per_output maps an output name -> its UQ field declarations. The inner
    # shape varies by form (predictive_interval uses lower_field/upper_field/
    # level; class_probabilities uses field; ...), so it stays free-form here
    # and is interpreted by the viewer/runner layers.
    per_output: dict[str, dict[str, Any]]
    calibration: Calibration | None = None


class Invocation(BaseModel):
    executable: str
    protocol: str  # schema const "stdio_json"; structural check is in the schema
    timeout_s: int
    expected_runtime_s: float | None = None
    batch_supported: bool = False


class Lineage(BaseModel):
    training_data_version: str
    training_date: str
    metrics: dict[str, Any]
    retrain_cadence: str | None = None


class Example(BaseModel):
    label: str
    inputs: dict[str, Any]
    expected_hint: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    name: str
    version: str
    # Manifest-spec version (MAJOR.MINOR). Optional: an absent value defaults
    # here, so a pre-spec_version manifest parses as the v1 spec. Compatibility
    # against SUPPORTED_SPEC_MAJOR is enforced in semantic_errors (the schema
    # cannot know the GUI's supported major). See design §13 decision 15.
    spec_version: str = DEFAULT_SPEC_VERSION
    owner: Owner
    domain: str
    modality: Modality
    tags: list[str] | None = None
    # Plain-language analysis category for non-expert discovery (TC-GUI15).
    # Optional + additive (like tags); dynamically populated, not a hardcoded
    # vocabulary. See design §13 decision 16.
    analysis_type: str | None = None
    purpose: str
    when_to_use: str | None = None
    when_not_to_use: str | None = None
    inputs: list[InputField]
    outputs: list[OutputField]
    primary_inputs: list[str] | None = None
    primary_outputs: list[str] | None = None
    uncertainty: Uncertainty
    invocation: Invocation
    lineage: Lineage
    model_card: str
    examples: list[Example] | None = None


@dataclass(frozen=True)
class ValidatedModel:
    """A model whose *contract* (manifest + sibling card) is fully validated."""

    manifest: Manifest
    card: ModelCard
    manifest_path: Path


class ManifestValidationError(Exception):
    """Raised when a manifest is inadmissible. Carries every discovered problem.

    Mirrors :class:`server.model_card.ModelCardValidationError` in shape so the
    registry can catch ``(ManifestValidationError, ModelCardValidationError)``
    and surface ``.source`` + ``.errors`` uniformly.
    """

    def __init__(self, source: str, errors: list[str]) -> None:
        self.source = source
        self.errors = list(errors)
        joined = "\n".join(f"  - {e}" for e in self.errors)
        super().__init__(f"{source}: {len(self.errors)} manifest error(s):\n{joined}")


# --------------------------------------------------------------------------- #
# Structural validation (JSON Schema).
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    raw = MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8")
    schema = json.loads(raw)
    if not isinstance(schema, dict):
        raise RuntimeError(f"manifest schema is not a JSON object: {MANIFEST_SCHEMA_PATH}")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _format_schema_error(err: SchemaError) -> str:
    # json_path renders like "$.inputs[0].name" — a precise, copy-pasteable
    # pointer to the offending node.
    return f"{err.json_path}: {err.message}"


def schema_errors(data: object) -> list[str]:
    """Return all JSON Schema violations for ``data`` (empty == structurally ok)."""
    validator = _validator()
    return sorted(_format_schema_error(err) for err in validator.iter_errors(data))


# --------------------------------------------------------------------------- #
# Semantic validation (cross-field invariants the schema cannot express).
# --------------------------------------------------------------------------- #
def _duplicate_errors(names: list[str], kind: str) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for name in names:
        if name in seen and name not in dupes:
            dupes.append(name)
        seen.add(name)
    return [f"duplicate {kind} name {name!r}" for name in dupes]


def _spec_version_errors(manifest: Manifest) -> list[str]:
    """Reject a manifest authored against a newer-MAJOR spec than this GUI supports.

    The JSON Schema validates `spec_version`'s *shape* (``^\\d+\\.\\d+$``) but
    cannot enforce *compatibility* — it does not know the GUI's
    :data:`SUPPORTED_SPEC_MAJOR`. That back-compat policy (design §13 decision 15)
    lives here. A missing ``spec_version`` has already defaulted to
    :data:`DEFAULT_SPEC_VERSION` on the typed model, so it always passes; a higher
    MINOR within a supported MAJOR is additive and tolerated; only a higher MAJOR
    is refused — loud, never silent.
    """
    raw = manifest.spec_version
    try:
        major = int(raw.split(".", 1)[0])
    except (ValueError, AttributeError):
        # Unreachable for a schema-validated manifest (the pattern guarantees
        # MAJOR.MINOR); guards a Manifest constructed directly in code/tests.
        return [f"spec_version {raw!r} is not a valid MAJOR.MINOR version string"]
    if major > SUPPORTED_SPEC_MAJOR:
        return [
            f"spec_version {raw!r} targets manifest-spec major {major}, but this GUI "
            f"supports major <= {SUPPORTED_SPEC_MAJOR}; upgrade the GUI to load this "
            "model (back-compat policy, design §13 decision 15)"
        ]
    return []


def semantic_errors(manifest: Manifest) -> list[str]:
    """Cross-field checks beyond the JSON Schema. Empty == semantically ok.

    The keystone is per_output coverage (design §3 step 6 / Wall A); the rest
    protect downstream surfaces (auto-form, viewers, history, runner) from
    manifests the schema accepts but that cannot be rendered or dispatched.
    """
    errors: list[str] = []

    # Manifest-spec compatibility gate (design §13 decision 15): a newer-major
    # spec than this GUI supports is refused before its (possibly reinterpreted)
    # contents are trusted.
    errors += _spec_version_errors(manifest)

    input_names = [i.name for i in manifest.inputs]
    output_names = [o.name for o in manifest.outputs]
    errors += _duplicate_errors(input_names, "input")
    errors += _duplicate_errors(output_names, "output")

    # Keystone: every output must declare UQ; no per_output block may name a
    # non-existent output (a typo that would silently drop UQ).
    declared = set(output_names)
    covered = set(manifest.uncertainty.per_output)
    for name in output_names:
        if name not in covered:
            errors.append(
                f"uncertainty.per_output is missing a block for output {name!r} "
                "(every output must declare uncertainty)"
            )
    for name in sorted(covered - declared):
        errors.append(
            f"uncertainty.per_output declares {name!r}, which is not a declared output"
        )

    # Type-conditional requirements the schema documents in prose only.
    for inp in manifest.inputs:
        if inp.type is InputType.categorical and not inp.choices:
            errors.append(f"input {inp.name!r} is categorical but declares no choices")
        if inp.type is InputType.file and inp.file_kind is None:
            errors.append(f"input {inp.name!r} is a file but declares no file_kind")
    for out in manifest.outputs:
        if out.type is OutputType.categorical and not out.choices:
            errors.append(f"output {out.name!r} is categorical but declares no choices")

    # primary_inputs / primary_outputs must name real fields (history columns).
    for name in manifest.primary_inputs or []:
        if name not in declared and name not in set(input_names):
            errors.append(f"primary_inputs names {name!r}, which is not a declared input")
    for name in manifest.primary_outputs or []:
        if name not in declared:
            errors.append(f"primary_outputs names {name!r}, which is not a declared output")

    return errors


def deferred_viewer_outputs(manifest: Manifest) -> list[str]:
    """Output names whose viewer is accepted but deferred (e.g. field_contour)."""
    return [o.name for o in manifest.outputs if o.viewer in DEFERRED_VIEWERS]


def manifest_warnings(manifest: Manifest) -> list[str]:
    """Advisory, non-rejecting checks for non-expert discoverability (TC-GUI15).

    These never block a model from loading — they are warnings, not errors
    (parity with ``chain_enforcement: informational``). They nudge authors toward
    the lay-readable, analysis-first metadata operator Requirement 1 needs so a
    non-CAE/ML user with an analysis in mind can find the model. Surfaced by the
    pre-publish gate CLI today and, once it lands, by the catalog/registry UI.
    """
    warnings: list[str] = []
    if not (manifest.analysis_type and manifest.analysis_type.strip()):
        warnings.append(
            "analysis_type is unset — set a plain-language analysis category "
            "(e.g. 'fatigue life', 'vibration response') so non-experts can browse to it"
        )
    if not (manifest.when_to_use and manifest.when_to_use.strip()):
        warnings.append(
            "when_to_use is empty — non-experts rely on this plain-language "
            "'is this the right model for my analysis?' guidance"
        )
    return warnings


# --------------------------------------------------------------------------- #
# Orchestration.
# --------------------------------------------------------------------------- #
def _pydantic_messages(exc: PydanticValidationError) -> list[str]:
    messages: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "(root)"
        messages.append(f"{loc}: {err['msg']}")
    return messages


def _validate(data: object) -> tuple[Manifest | None, list[str]]:
    if not isinstance(data, dict):
        return None, [f"manifest root must be a mapping, got {type(data).__name__}"]
    structural = schema_errors(data)
    if structural:
        return None, structural
    try:
        manifest = Manifest.model_validate(data)
    except PydanticValidationError as exc:
        # Reaching here means the schema accepted something the typed model
        # rejected — a schema/model divergence. Surfaced loudly, never silent.
        return None, _pydantic_messages(exc)
    return manifest, semantic_errors(manifest)


def collect_manifest_errors(data: object) -> list[str]:
    """Return every validation problem for ``data`` without raising (empty == ok)."""
    return _validate(data)[1]


def parse_manifest_data(data: dict[str, Any], *, source: str = "<manifest>") -> Manifest:
    """Validate an already-parsed manifest mapping; raise on any problem."""
    manifest, errors = _validate(data)
    if errors or manifest is None:
        raise ManifestValidationError(source, errors)
    return manifest


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestValidationError(str(path), [f"cannot read manifest: {exc}"]) from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ManifestValidationError(str(path), [f"YAML parse error: {exc}"]) from exc
    if not isinstance(loaded, dict):
        raise ManifestValidationError(
            str(path), [f"manifest root must be a mapping, got {type(loaded).__name__}"]
        )
    return loaded


def load_manifest(path: Path) -> Manifest:
    """Read, structurally + semantically validate a manifest file; raise on any problem."""
    data = _read_yaml_mapping(path)
    return parse_manifest_data(data, source=str(path))


def load_model(manifest_path: Path) -> ValidatedModel:
    """Validate a model's full contract: its manifest and its sibling model card.

    Implements design §3 steps 1, 2, 4, 5, 6. It does **not** check that
    ``invocation.executable`` exists (step 3) — that filesystem check belongs to
    the registry/runner (TC-104/TC-201), and leaving it out keeps the worked
    example (no ``.exe`` on disk) contract-valid.
    """
    manifest = load_manifest(manifest_path)
    card_path = (manifest_path.parent / manifest.model_card).resolve()
    card = load_model_card(
        card_path,
        expected_model_id=manifest.id,
        expected_version=manifest.version,
    )
    return ValidatedModel(manifest=manifest, card=card, manifest_path=manifest_path)


# --------------------------------------------------------------------------- #
# Pre-publish gate (TC-GUI18). Aggregate a *package*'s contract errors without
# raising, so an author can fix a candidate model before it is dropped into
# ./models/. Reuses the very validators the registry uses, so the gate can never
# diverge from registry-load validation.
# --------------------------------------------------------------------------- #
def validate_package(path: Path) -> list[str]:
    """Validate a model *package* (manifest + sibling card); return every error.

    ``path`` is a package directory (containing ``manifest.yaml``) or a manifest
    file path. Aggregates schema + typed + semantic manifest errors (incl. the
    ``spec_version`` and ``uncertainty.per_output`` gates) via
    :func:`collect_manifest_errors`, and the nine-mandatory-section + id/version
    card checks via :func:`collect_model_card_errors`. Empty list == admissible.

    Deliberately does **not** check that ``invocation.executable`` exists on disk
    (design §3 step 3): that is the registry/runner's check at load time, and
    skipping it lets a contract-only worked example (which ships no ``.exe``) pass
    the gate. A real package's executable is verified when the registry loads it.
    """
    manifest_path = (path / "manifest.yaml") if path.is_dir() else path
    try:
        data = _read_yaml_mapping(manifest_path)
    except ManifestValidationError as exc:
        return [f"{exc.source}: {e}" for e in exc.errors]

    errors = [f"{manifest_path}: {e}" for e in collect_manifest_errors(data)]

    card_ref = data.get("model_card")
    if isinstance(card_ref, str):
        card_path = (manifest_path.parent / card_ref).resolve()
        try:
            card_text = card_path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{card_path}: cannot read model card: {exc}")
        else:
            raw_id = data.get("id")
            raw_version = data.get("version")
            card_errors = collect_model_card_errors(
                card_text,
                expected_model_id=raw_id if isinstance(raw_id, str) else None,
                expected_version=raw_version if isinstance(raw_version, str) else None,
            )
            errors += [f"{card_path}: {e}" for e in card_errors]
    return errors


def package_warnings(path: Path) -> list[str]:
    """Advisory non-expert-discoverability warnings for a package.

    Empty if the package does not validate (fix errors first). Companion to
    :func:`validate_package`; the checks live in :func:`manifest_warnings`.
    """
    manifest_path = (path / "manifest.yaml") if path.is_dir() else path
    try:
        manifest = load_manifest(manifest_path)
    except ManifestValidationError:
        return []
    return manifest_warnings(manifest)


def main(argv: list[str] | None = None) -> int:
    """CLI: validate one or more model packages; exit nonzero if any fail.

    ``python -m server.manifest <package-dir-or-manifest> [...]``. This is the
    engine the pre-publish gate (``.github/workflows/validate-model-package.yml``)
    invokes, and the same command an author — or the sibling CAE-ML-data-pipelines
    repo — runs against a candidate package before publishing it.
    """
    parser = argparse.ArgumentParser(
        prog="python -m server.manifest",
        description="Validate model package(s) against the manifest + card contract.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="one or more package directories (or manifest.yaml paths) to validate",
    )
    args = parser.parse_args(argv)

    failed = 0
    for path in args.paths:
        errors = validate_package(path)
        if errors:
            failed += 1
            print(f"FAIL {path}")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"OK   {path}")
            for warn in package_warnings(path):
                print(f"  warn: {warn}")
    if failed:
        print(f"\n{failed} package(s) failed validation.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
