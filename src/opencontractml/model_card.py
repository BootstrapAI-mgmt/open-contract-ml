"""Model-card validation: front-matter + the nine mandatory H2 sections.

The model card is the mandatory human-prose companion to the manifest (design
``gui-design.md`` §10). This module implements steps 4-5 of the registry-load
validation contract (§3):

* **Front-matter** — YAML between leading ``---`` fences declaring ``model_id``
  and ``version``. When the manifest's id/version are supplied (the registry
  always supplies them), the card's must match — this catches a stale card
  pasted next to a newer manifest.
* **Structure** — the nine mandatory H2 sections, in the exact order given in
  §10, as the card's *first nine* H2 headings. ``## References`` and any other
  extra H2s are permitted, but only *after* the nine.

Headings inside fenced code blocks are ignored, so a ``## ...`` line in an
example block is never mistaken for a section.

Problems are aggregated and raised as a single loud
:class:`ModelCardValidationError` (``.source`` + ``.errors``), mirroring
:class:`server.manifest.ManifestValidationError`. The non-raising
:func:`collect_model_card_errors` returns the same list. This module imports
nothing from :mod:`server.manifest` — the dependency runs one way (manifest ->
card) so there is no import cycle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "MANDATORY_SECTIONS",
    "ModelCard",
    "ModelCardValidationError",
    "collect_model_card_errors",
    "load_model_card",
]

# The nine mandatory H2 sections, in the exact required order (design §10).
MANDATORY_SECTIONS: tuple[str, ...] = (
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

# Leading YAML front-matter delimited by `---` fences at the very top of the file.
_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(?P<body>.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)
# An ATX H2 heading: exactly two `#`, then whitespace, then a non-empty title.
# `### ...` (H3) has `#` where the whitespace must be, so it does not match.
_H2_RE = re.compile(r"^##[ \t]+(?P<title>\S.*?)[ \t]*$")
# Opening/closing of a fenced code block (``` or ~~~).
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")


@dataclass(frozen=True)
class ModelCard:
    """A validated model card: its front-matter identity and ordered H2 headings."""

    model_id: str
    version: str
    headings: tuple[str, ...]


class ModelCardValidationError(Exception):
    """Raised when a model card is inadmissible. Carries every discovered problem."""

    def __init__(self, source: str, errors: list[str]) -> None:
        self.source = source
        self.errors = list(errors)
        joined = "\n".join(f"  - {e}" for e in self.errors)
        super().__init__(f"{source}: {len(self.errors)} model-card error(s):\n{joined}")


def _split_front_matter(text: str) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Return ``(front_matter, body, errors)``.

    ``front_matter`` is ``None`` when absent or not a YAML mapping; ``body`` is
    the card text after the front-matter (or the whole text when absent).
    """
    match = _FRONT_MATTER_RE.match(text)
    if match is None:
        return None, text, ["missing YAML front-matter (--- model_id / version ---) at top of card"]
    body = text[match.end() :]
    try:
        loaded = yaml.safe_load(match.group("body"))
    except yaml.YAMLError as exc:
        return None, body, [f"front-matter is not valid YAML: {exc}"]
    if not isinstance(loaded, dict):
        return None, body, ["front-matter must be a YAML mapping with model_id and version"]
    return loaded, body, []


def _front_matter_errors(
    front: dict[str, Any] | None,
    expected_model_id: str | None,
    expected_version: str | None,
) -> list[str]:
    if front is None:
        return []  # the absence/parse error was already reported by _split_front_matter
    errors: list[str] = []
    model_id = front.get("model_id")
    version = front.get("version")
    if model_id is None:
        errors.append("front-matter is missing required key 'model_id'")
    elif expected_model_id is not None and str(model_id) != expected_model_id:
        errors.append(
            f"front-matter model_id {str(model_id)!r} does not match manifest id "
            f"{expected_model_id!r}"
        )
    if version is None:
        errors.append("front-matter is missing required key 'version'")
    elif expected_version is not None and str(version) != expected_version:
        errors.append(
            f"front-matter version {str(version)!r} does not match manifest version "
            f"{expected_version!r}"
        )
    return errors


def _h2_headings(body: str) -> list[str]:
    headings: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _H2_RE.match(line)
        if match is not None:
            headings.append(match.group("title"))
    return headings


def _section_errors(headings: list[str]) -> list[str]:
    required = len(MANDATORY_SECTIONS)
    if len(headings) < required:
        missing = [s for s in MANDATORY_SECTIONS if s not in headings]
        detail = ", ".join(missing) if missing else "none missing — check ordering"
        return [
            f"card has {len(headings)} H2 section(s); all {required} mandatory sections are "
            f"required, in order (missing: {detail})"
        ]
    errors: list[str] = []
    for index, expected in enumerate(MANDATORY_SECTIONS):
        actual = headings[index]
        if actual != expected:
            errors.append(
                f"H2 section #{index + 1} must be '## {expected}' but is '## {actual}' "
                "(the nine mandatory sections must come first, in order)"
            )
    return errors


def collect_model_card_errors(
    text: str,
    *,
    expected_model_id: str | None = None,
    expected_version: str | None = None,
) -> list[str]:
    """Return every problem with a card's text without raising (empty == ok)."""
    front, body, errors = _split_front_matter(text)
    errors = list(errors)
    errors += _front_matter_errors(front, expected_model_id, expected_version)
    errors += _section_errors(_h2_headings(body))
    return errors


def load_model_card(
    path: Path,
    *,
    expected_model_id: str | None = None,
    expected_version: str | None = None,
) -> ModelCard:
    """Read and validate a model card file; raise :class:`ModelCardValidationError`."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelCardValidationError(str(path), [f"cannot read model card: {exc}"]) from exc

    front, body, errors = _split_front_matter(text)
    errors = list(errors)
    errors += _front_matter_errors(front, expected_model_id, expected_version)
    headings = _h2_headings(body)
    errors += _section_errors(headings)
    if errors or front is None:
        raise ModelCardValidationError(str(path), errors)

    return ModelCard(
        model_id=str(front["model_id"]),
        version=str(front["version"]),
        headings=tuple(headings),
    )
