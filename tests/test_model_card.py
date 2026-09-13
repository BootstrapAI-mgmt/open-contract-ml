"""Tests for server.model_card — front-matter + the nine mandatory H2 sections."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from opencontractml.model_card import (
    MANDATORY_SECTIONS,
    ModelCardValidationError,
    collect_model_card_errors,
    load_model_card,
)
REPO_ROOT = Path(__file__).resolve().parents[1]

EXAMPLE_CARD = REPO_ROOT / "examples" / "brake_disc_tmf_v1" / "model_card.md"


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
    # The example ends with the optional ## References after the nine.
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


def test_extra_h2_before_the_nine_rejected() -> None:
    # An interloping H2 pushes the mandatory order off by one.
    sections = ["TL;DR", "Surprise", *MANDATORY_SECTIONS[1:]]
    errors = collect_model_card_errors(_card(sections=sections))
    assert errors  # the second heading is "Surprise", not "Intended use"


def test_extra_h2_after_the_nine_allowed() -> None:
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
    # that is otherwise exactly the nine stays valid and its headings are clean.
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
