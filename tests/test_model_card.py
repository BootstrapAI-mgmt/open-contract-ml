"""Tests for opencontractml.model_card — front-matter + the mandatory H2 sections."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import resources
from pathlib import Path

import pytest

from opencontractml import verify
from opencontractml.model_card import (
    MANDATORY_SECTIONS,
    ModelCardValidationError,
    collect_model_card_errors,
    load_model_card,
)
REPO_ROOT = Path(__file__).resolve().parents[1]

EXAMPLE_CARD = REPO_ROOT / "examples" / "brake_disc_tmf_v1" / "model_card.md"
# Resolved out of the installed package, like the schemas, so this measures the
# template a consumer actually gets.
TEMPLATE = Path(str(resources.files("opencontractml") / "templates" / "model_card.template.md"))


def _card(
    *,
    model_id: str = "demo_model",
    version: str = "1.0.0",
    sections: Iterable[str] = MANDATORY_SECTIONS,
    extra_after: Iterable[str] = (),
    with_front_matter: bool = True,
) -> str:
    lines: list[str] = []
    if with_front_matter:
        lines += ["---", f"model_id: {model_id}", f"version: {version}", "---", ""]
    lines += ["# Demo Model", ""]
    for section in sections:
        lines += [f"## {section}", "Body prose.", ""]
    for section in extra_after:
        lines += [f"## {section}", "Extra prose.", ""]
    return "\n".join(lines)


def _write(tmp_path: Path, text: str) -> Path:
    target = tmp_path / "model_card.md"
    target.write_text(text, encoding="utf-8")
    return target


def test_valid_card_passes(tmp_path: Path) -> None:
    card = load_model_card(
        _write(tmp_path, _card()),
        expected_model_id="demo_model",
        expected_version="1.0.0",
    )
    assert card.model_id == "demo_model"
    assert card.version == "1.0.0"
    assert card.headings == MANDATORY_SECTIONS
    assert collect_model_card_errors(_card()) == []


def test_brake_disc_example_card_is_valid() -> None:
    card = load_model_card(
        EXAMPLE_CARD,
        expected_model_id="brake_disc_tmf_v1",
        expected_version="1.2.0",
    )
    assert card.model_id == "brake_disc_tmf_v1"
    # The example ends with the optional ## References after the mandatory set.
    assert card.headings[: len(MANDATORY_SECTIONS)] == MANDATORY_SECTIONS
    assert "References" in card.headings


def test_missing_section_rejected() -> None:
    sections = [s for s in MANDATORY_SECTIONS if s != "Performance"]
    errors = collect_model_card_errors(_card(sections=sections))
    assert any("Performance" in e for e in errors)


def test_out_of_order_sections_rejected() -> None:
    reordered = list(MANDATORY_SECTIONS)
    reordered[0], reordered[1] = reordered[1], reordered[0]  # swap TL;DR and Intended use
    errors = collect_model_card_errors(_card(sections=reordered))
    assert any("section #1" in e and "TL;DR" in e for e in errors)


def test_extra_h2_before_the_mandatory_sections_rejected() -> None:
    # An interloping H2 pushes the mandatory order off by one.
    sections = ["TL;DR", "Surprise", *MANDATORY_SECTIONS[1:]]
    errors = collect_model_card_errors(_card(sections=sections))
    assert errors  # the second heading is "Surprise", not "Intended use"


def test_extra_h2_after_the_mandatory_sections_allowed() -> None:
    assert collect_model_card_errors(_card(extra_after=["References", "Appendix"])) == []


def test_missing_front_matter_rejected() -> None:
    errors = collect_model_card_errors(_card(with_front_matter=False))
    assert any("front-matter" in e for e in errors)


def test_model_id_mismatch_rejected() -> None:
    errors = collect_model_card_errors(_card(model_id="other"), expected_model_id="demo_model")
    assert any("model_id" in e for e in errors)


def test_version_mismatch_rejected() -> None:
    errors = collect_model_card_errors(_card(version="9.9.9"), expected_version="1.0.0")
    assert any("version" in e for e in errors)


def test_headings_inside_code_fence_are_ignored(tmp_path: Path) -> None:
    # A fenced "## not a heading" must not be counted as a section, so a card
    # that is otherwise exactly the mandatory set stays valid and its headings are clean.
    body = _card().replace(
        "## Architecture\nBody prose.\n",
        "## Architecture\n```yaml\n## not a heading\n```\nBody prose.\n",
    )
    card = load_model_card(_write(tmp_path, body))
    assert card.headings == MANDATORY_SECTIONS


def test_unreadable_card_path_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "nope.md"
    with pytest.raises(ModelCardValidationError) as exc:
        load_model_card(missing)
    assert any("cannot read" in e for e in exc.value.errors)


# --------------------------------------------------------------------------- #
# One section list for both card validators in this package. They used to
# disagree: this module demanded nine sections and `open-contract-ml check`
# eleven, so the same card passed one entry point and failed the other.
# --------------------------------------------------------------------------- #
LEGACY_NINE = (
    "TL;DR",
    "Intended use",
    "Out of scope",
    "Training data",
    "Architecture",
    "Performance",
    "Uncertainty quantification",
    "Known failure modes",
    "Version history",
)


def test_mandatory_sections_are_the_checkers_eleven() -> None:
    assert MANDATORY_SECTIONS == verify.CARD_SECTIONS
    assert MANDATORY_SECTIONS is verify.CARD_SECTIONS, "one tuple, so there is nothing to keep in step"
    assert len(MANDATORY_SECTIONS) == 11


def test_a_nine_section_card_fails_the_eleven_section_validator() -> None:
    """A card written to the old nine-section list is rejected, naming the two it lacks."""
    errors = collect_model_card_errors(_card(sections=LEGACY_NINE))
    assert errors, "a nine-section card must not pass"
    joined = "\n".join(errors)
    assert "Training configuration" in joined and "Provenance" in joined, errors


@pytest.mark.parametrize(
    "sections,extra",
    [
        (MANDATORY_SECTIONS, ()),
        (MANDATORY_SECTIONS, ("References",)),
        (MANDATORY_SECTIONS, ("Appendix",)),
        (LEGACY_NINE, ()),
        (tuple(reversed(MANDATORY_SECTIONS)), ()),
        (MANDATORY_SECTIONS[:5] + ("Surprise",) + MANDATORY_SECTIONS[5:], ()),
    ],
    ids=["eleven", "eleven-then-reserved", "eleven-then-unreserved", "legacy-nine", "reversed", "interloper"],
)
def test_both_card_validators_agree_on_the_section_rule(sections, extra) -> None:
    text = _card(sections=sections, extra_after=extra)
    this_module_rejects = bool(collect_model_card_errors(text))
    findings: list = []
    verify.check_card(text, None, "model_card.md", findings)
    checker_rejects = any(f.rule == "C003" for f in findings)
    assert this_module_rejects == checker_rejects, (this_module_rejects, sorted({f.rule for f in findings}))


def test_the_template_carries_the_eleven_sections_and_spec_version() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    front, body, error = verify.split_front_matter(text)
    assert error is None, error
    assert front.get("spec_version") == verify.CONTRACT_VERSION
    assert {"model_id", "version", "spec_version"} <= set(front)
    headings = verify.h2_headings(body)
    assert tuple(headings[: len(MANDATORY_SECTIONS)]) == MANDATORY_SECTIONS
    extras = headings[len(MANDATORY_SECTIONS):]
    assert all(h in verify.CARD_SECTIONS_RESERVED for h in extras), extras
    assert collect_model_card_errors(text) == []
