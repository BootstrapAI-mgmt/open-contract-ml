"""Tests for opencontractml.manifest — schema, typed model, and semantic validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from opencontractml.manifest import (
    DEFAULT_SPEC_VERSION,
    MANIFEST_SCHEMA_PATH,
    FileKind,
    InputType,
    Manifest,
    ManifestValidationError,
    Modality,
    OutputType,
    UncertaintyForm,
    Viewer,
    collect_manifest_errors,
    deferred_viewer_outputs,
    load_manifest,
    load_model,
    manifest_warnings,
    package_warnings,
    parse_manifest_data,
    validate_package,
)
REPO_ROOT = Path(__file__).resolve().parents[1]

EXAMPLE_MANIFEST = REPO_ROOT / "examples" / "brake_disc_tmf_v1" / "manifest.yaml"
PACKAGE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "model_packages"


def _valid() -> dict[str, Any]:
    """A minimal manifest satisfying every required field of the schema."""
    return {
        "id": "demo_model",
        "name": "Demo",
        "version": "1.0.0",
        "owner": {"team": "Team", "contact": "team@example.com"},
        "domain": "demo",
        "modality": "scalar_in_scalar_out",
        "purpose": "Predicts a demo scalar value.",
        "inputs": [{"name": "x", "type": "float", "required": True}],
        "outputs": [{"name": "y", "type": "float", "viewer": "scalar_with_uq"}],
        "uncertainty": {
            "form": "predictive_interval",
            "per_output": {"y": {"lower_field": "y_lower", "upper_field": "y_upper", "level": 0.9}},
        },
        "invocation": {"executable": "./m.exe", "protocol": "stdio_json", "timeout_s": 30},
        "lineage": {
            "training_data_version": "v1",
            "training_date": "2026-01-01",
            "metrics": {"mae": 0.1},
        },
        "model_card": "./model_card.md",
    }


# --------------------------------------------------------------------------- #
# Happy paths
# --------------------------------------------------------------------------- #
def test_minimal_manifest_is_valid() -> None:
    assert collect_manifest_errors(_valid()) == []
    manifest = parse_manifest_data(_valid())
    assert manifest.id == "demo_model"
    assert manifest.modality is Modality.scalar_in_scalar_out
    assert manifest.inputs[0].type is InputType.float
    assert manifest.outputs[0].viewer is Viewer.scalar_with_uq
    assert manifest.uncertainty.form is UncertaintyForm.predictive_interval


def test_brake_disc_example_manifest_is_valid() -> None:
    manifest = load_manifest(EXAMPLE_MANIFEST)
    assert manifest.id == "brake_disc_tmf_v1"
    assert [i.name for i in manifest.inputs] == [
        "peak_temp",
        "cycle_count",
        "material",
        "vent_geometry",
    ]
    assert [o.name for o in manifest.outputs] == ["life", "failure_mode"]


def test_load_model_validates_example_contract() -> None:
    # End-to-end: manifest + sibling card together. The example ships no .exe;
    # load_model must NOT require one (executable existence is checked at dispatch).
    model = load_model(EXAMPLE_MANIFEST)
    assert model.manifest.id == "brake_disc_tmf_v1"
    assert model.card.model_id == "brake_disc_tmf_v1"
    assert model.card.version == "1.2.0"


# --------------------------------------------------------------------------- #
# Structural rejection (JSON Schema)
# --------------------------------------------------------------------------- #
def test_missing_uncertainty_rejected() -> None:
    data = _valid()
    del data["uncertainty"]
    with pytest.raises(ManifestValidationError) as exc:
        parse_manifest_data(data)
    assert any("uncertainty" in e for e in exc.value.errors)


def test_bad_modality_enum_rejected() -> None:
    data = _valid()
    data["modality"] = "not_a_modality"
    errors = collect_manifest_errors(data)
    assert any("modality" in e for e in errors)


def test_non_mapping_root_rejected() -> None:
    assert any("mapping" in e for e in collect_manifest_errors(["not", "a", "dict"]))


def test_bad_yaml_file_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "manifest.yaml"
    bad.write_text("key: [unclosed\n", encoding="utf-8")
    with pytest.raises(ManifestValidationError) as exc:
        load_manifest(bad)
    assert any("YAML" in e for e in exc.value.errors)


# --------------------------------------------------------------------------- #
# Semantic rejection (cross-field invariants)
# --------------------------------------------------------------------------- #
def test_uncovered_output_rejected() -> None:
    # The keystone check: an output with no per_output block is rejected.
    data = _valid()
    data["outputs"].append({"name": "z", "type": "float", "viewer": "scalar_with_uq"})
    errors = collect_manifest_errors(data)
    assert any("z" in e and "per_output" in e for e in errors)


def test_stray_per_output_key_rejected() -> None:
    data = _valid()
    data["uncertainty"]["per_output"]["ghost"] = {"field": "ghost_probs"}
    errors = collect_manifest_errors(data)
    assert any("ghost" in e for e in errors)


def test_categorical_input_without_choices_rejected() -> None:
    data = _valid()
    data["inputs"].append({"name": "grade", "type": "categorical", "required": True})
    errors = collect_manifest_errors(data)
    assert any("grade" in e and "choices" in e for e in errors)


def test_file_input_without_file_kind_rejected() -> None:
    data = _valid()
    data["inputs"].append({"name": "geom", "type": "file", "required": False})
    errors = collect_manifest_errors(data)
    assert any("geom" in e and "file_kind" in e for e in errors)


def test_duplicate_output_name_rejected() -> None:
    data = _valid()
    data["outputs"].append({"name": "y", "type": "float", "viewer": "scalar_with_uq"})
    errors = collect_manifest_errors(data)
    assert any("duplicate output" in e for e in errors)


def test_primary_input_referencing_unknown_field_rejected() -> None:
    data = _valid()
    data["primary_inputs"] = ["nonexistent"]
    errors = collect_manifest_errors(data)
    assert any("primary_inputs" in e and "nonexistent" in e for e in errors)


# --------------------------------------------------------------------------- #
# Deferred viewer (accepted, not rejected — but flagged)
# --------------------------------------------------------------------------- #
def test_field_contour_viewer_accepted_but_flagged_deferred() -> None:
    data = _valid()
    data["outputs"].append({"name": "temp_field", "type": "field", "viewer": "field_contour"})
    data["uncertainty"]["per_output"]["temp_field"] = {"form": "monte_carlo", "field": "samples"}
    manifest = parse_manifest_data(data)  # must NOT raise
    assert deferred_viewer_outputs(manifest) == ["temp_field"]


# --------------------------------------------------------------------------- #
# Schema parity — the typed layer must mirror the schema exactly. A schema edit
# that is not reflected in the enums/required fields fails here.
# --------------------------------------------------------------------------- #
def _schema() -> dict[str, Any]:
    loaded = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_enums_mirror_schema() -> None:
    schema = _schema()
    defs = schema["$defs"]
    assert set(schema["properties"]["modality"]["enum"]) == {e.value for e in Modality}
    assert set(defs["input_field"]["properties"]["type"]["enum"]) == {e.value for e in InputType}
    assert set(defs["output_field"]["properties"]["type"]["enum"]) == {e.value for e in OutputType}
    assert set(defs["output_field"]["properties"]["viewer"]["enum"]) == {e.value for e in Viewer}
    assert set(defs["input_field"]["properties"]["file_kind"]["enum"]) == {
        e.value for e in FileKind
    }
    assert set(defs["uncertainty"]["properties"]["form"]["enum"]) == {
        e.value for e in UncertaintyForm
    }
    assert schema["properties"]["invocation"]["properties"]["protocol"]["const"] == "stdio_json"


def test_required_top_level_fields_mirror_schema() -> None:
    schema = _schema()
    required_model = {name for name, field in Manifest.model_fields.items() if field.is_required()}
    assert required_model == set(schema["required"])


def test_spec_version_is_optional_not_in_required_set() -> None:
    # spec_version is additive + optional — it must not appear in
    # the frozen v1 contract's required-field set (schema or typed model).
    assert "spec_version" not in set(_schema()["required"])
    assert not Manifest.model_fields["spec_version"].is_required()


# --------------------------------------------------------------------------- #
# Manifest-spec versioning + back-compat policy
# --------------------------------------------------------------------------- #
def test_spec_version_absent_defaults_to_v1() -> None:
    # A manifest omitting spec_version validates and the typed
    # model carries the v1 default — existing manifests never regress.
    data = _valid()
    assert "spec_version" not in data
    assert collect_manifest_errors(data) == []
    assert parse_manifest_data(data).spec_version == DEFAULT_SPEC_VERSION


def test_brake_disc_example_omits_spec_version_and_still_loads() -> None:
    # The same, against the real worked example, which predates the field.
    assert load_manifest(EXAMPLE_MANIFEST).spec_version == DEFAULT_SPEC_VERSION


def test_supported_spec_version_accepted() -> None:
    data = _valid()
    data["spec_version"] = "1.0"
    assert collect_manifest_errors(data) == []
    # A higher MINOR within the supported MAJOR is additive and still loads.
    data["spec_version"] = "1.7"
    assert collect_manifest_errors(data) == []


def test_higher_major_spec_version_rejected_loud() -> None:
    # A newer-major spec is rejected, not silently dropped.
    data = _valid()
    data["spec_version"] = "2.0"
    errors = collect_manifest_errors(data)
    assert any("spec_version" in e and "major" in e for e in errors)
    with pytest.raises(ManifestValidationError) as exc:
        parse_manifest_data(data)
    assert any("spec_version" in e for e in exc.value.errors)


def test_malformed_spec_version_rejected_structurally() -> None:
    # "1" is not MAJOR.MINOR — the schema's shape check catches it before
    # semantics are reached.
    data = _valid()
    data["spec_version"] = "1"
    assert any("spec_version" in e for e in collect_manifest_errors(data))


# --------------------------------------------------------------------------- #
# Pre-publish package gate — validate_package aggregates manifest + card errors
# without raising, reusing the load-time validators.
# --------------------------------------------------------------------------- #
def test_validate_package_accepts_conformant_fixture() -> None:
    assert validate_package(PACKAGE_FIXTURES / "conformant") == []


def test_validate_package_accepts_manifest_path_directly() -> None:
    # A manifest.yaml path works as well as its containing directory.
    assert validate_package(PACKAGE_FIXTURES / "conformant" / "manifest.yaml") == []


def test_validate_package_accepts_brake_disc_example() -> None:
    # The worked example is a conformant package — and the gate
    # does NOT require its (absent) .exe.
    assert validate_package(EXAMPLE_MANIFEST.parent) == []


def test_validate_package_rejects_nonconformant_citing_failure() -> None:
    # An uncovered-output package is rejected, naming `z`.
    errors = validate_package(PACKAGE_FIXTURES / "nonconformant")
    assert errors
    assert any("per_output" in e and "z" in e for e in errors)


def test_validate_package_missing_manifest_reports_error() -> None:
    errors = validate_package(PACKAGE_FIXTURES / "does_not_exist")
    assert errors
    assert any("manifest" in e.lower() for e in errors)


# --------------------------------------------------------------------------- #
# Non-expert discoverability: analysis_type + advisory warnings
# --------------------------------------------------------------------------- #
def test_analysis_type_is_optional_not_in_required_set() -> None:
    assert "analysis_type" not in set(_schema()["required"])
    assert not Manifest.model_fields["analysis_type"].is_required()


def test_brake_disc_example_declares_analysis_type() -> None:
    # The worked example declares analysis_type and still validates.
    assert load_manifest(EXAMPLE_MANIFEST).analysis_type == "fatigue life"


def test_manifest_warnings_flag_missing_lay_readable_prose() -> None:
    # Missing analysis_type / when_to_use surface advisory warnings.
    warnings = manifest_warnings(parse_manifest_data(_valid()))
    assert any("analysis_type" in w for w in warnings)
    assert any("when_to_use" in w for w in warnings)


def test_manifest_warnings_are_advisory_not_errors() -> None:
    # The same omissions are NOT hard rejections.
    assert collect_manifest_errors(_valid()) == []


def test_manifest_warnings_clean_when_prose_present() -> None:
    data = _valid()
    data["analysis_type"] = "demo analysis"
    data["when_to_use"] = "Use it when you need a demo scalar."
    assert manifest_warnings(parse_manifest_data(data)) == []


def test_package_warnings_clean_for_example() -> None:
    # The example sets analysis_type + when_to_use, so there are no advisories.
    assert package_warnings(EXAMPLE_MANIFEST.parent) == []


def test_package_warnings_flag_sparse_fixture() -> None:
    # The conformant fixture declares neither analysis_type nor when_to_use.
    assert any("analysis_type" in w for w in package_warnings(PACKAGE_FIXTURES / "conformant"))


# --------------------------------------------------------------------------- #
# The Contract's worked package passes this entry point too. It used to fail it
# on two counts -- a nine-section card rule and a lowercase-only input-name
# pattern -- while passing `open-contract-ml check`.
# --------------------------------------------------------------------------- #
REFERENCE_PACKAGE = REPO_ROOT / "examples" / "reference-package"


def test_reference_package_passes_the_package_validator() -> None:
    assert validate_package(REFERENCE_PACKAGE) == []


def test_reference_package_passes_the_manifest_cli(capsys: pytest.CaptureFixture[str]) -> None:
    from opencontractml.manifest import main

    assert main([str(REFERENCE_PACKAGE)]) == 0
    assert capsys.readouterr().out.startswith("OK")


@pytest.mark.parametrize("name", ["x", "cycle_count", "peak_temp_K", "t_max_K", "dT"])
def test_input_names_may_carry_an_uppercase_unit_suffix(name: str) -> None:
    data = _valid()
    data["inputs"][0]["name"] = name
    assert collect_manifest_errors(data) == []


@pytest.mark.parametrize("name", ["Peak_temp_K", "9x", "_x", "peak-temp", "peak temp", ""])
def test_input_names_must_still_start_lowercase_and_stay_identifiers(name: str) -> None:
    """The widened pattern is still a gate: it can fail."""
    data = _valid()
    data["inputs"][0]["name"] = name
    assert any(e.startswith("$.inputs[0].name") for e in collect_manifest_errors(data)), name


def test_nonconformant_fixture_fails_only_for_its_planted_defect() -> None:
    """Its card says the package's only error is the uncovered output `z`; keep that true."""
    errors = validate_package(PACKAGE_FIXTURES / "nonconformant")
    assert errors
    assert all("per_output" in e and "'z'" in e for e in errors), errors
