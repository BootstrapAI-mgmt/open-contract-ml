"""No pointer may dangle: every in-repo link must resolve to something shipped.

This is the general form of a defect that was found in the shipped documents:
thirteen files carried citation anchors that resolved to nothing a reader of
this repository could open, so there was no way to follow the reference. The
anchors were replaced by ``docs/REFERENCES.md``. This
file is the gate that stops the class of defect coming back, in whatever form --
a link to a doc that was withdrawn, a path that never existed here, a schema
directory at the wrong path.

The check is deliberately against the **tracked set**, not the filesystem. A
target that exists in a working tree but is gitignored or simply never committed
is not shipped, and a reader who clones this repository cannot reach it. Testing
``Path.exists()`` would pass and be wrong.

``KNOWN_DANGLING`` records the links that were already broken when this gate was
written. They are in files outside the change that introduced the gate. The list
is a ratchet, not an amnesty: ``test_no_known_dangling_entry_has_been_fixed``
fails if an entry starts resolving, which forces the list to shrink and keeps it
from quietly becoming a place to hide new breakage.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest

REPO = Path(__file__).resolve().parents[1]

#: ``[text](target)`` but not ``![alt](image)``. The target stops at whitespace
#: so a trailing markdown title -- ``[t](f.md "Title")`` -- is not glued on.
INLINE_LINK = re.compile(r"(?<!!)\[([^\]\n]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

#: ```` ``` ```` or ``~~~``. A link inside a fenced block is illustrative -- it is
#: showing you what a link looks like, not making one -- so fences are stripped
#: before matching. Without this, every code sample that prints a path is a
#: false positive.
FENCE = re.compile(r"^\s*(?:```|~~~)")

#: Anything with a URL scheme (``https:``, ``mailto:``) leaves the repository and
#: is out of scope here -- this gate is about internal consistency, and a network
#: fetch would make the suite non-deterministic and offline-hostile.
HAS_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")

#: Links that were already dangling when this gate was written, as
#: (file, resolved target) pairs. The list started with seven entries and has
#: been worked down to none; an entry may only ever be removed, never added.
KNOWN_DANGLING: set = set()


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    """Every path that ships: committed, or staged-but-not-yet-committed.

    A git failure fails the test rather than skipping it, for the same reason
    the provenance falsifier does: a link check that quietly passes because it
    could not read the tree is worse than no link check.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True)
    assert out.returncode == 0, f"git ls-files failed: {out.stderr.strip()}"
    files = sorted({ln.strip() for ln in out.stdout.splitlines() if ln.strip()})
    assert files, "git ls-files returned nothing -- links cannot be verified"
    return files


@pytest.fixture(scope="module")
def shipped(tracked) -> tuple[set[str], set[str]]:
    """(files, directories) that a clone of this repository would contain."""
    files = set(tracked)
    directories: set[str] = set()
    for rel in tracked:
        parts = rel.split("/")[:-1]
        for i in range(len(parts)):
            directories.add("/".join(parts[: i + 1]))
    return files, directories


def _links(rel: str):
    """Yield ``(line_number, raw_target)`` for each in-repo link in a markdown file."""
    try:
        text = (REPO / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for _, target in INLINE_LINK.findall(line):
            if HAS_SCHEME.match(target) or target.startswith("#"):
                continue
            yield lineno, target


def _resolve(rel: str, target: str) -> str | None:
    """Repo-relative path a link points at, or None if it addresses nothing.

    A bare ``#fragment`` never reaches here. A trailing ``#section`` or ``?query``
    is stripped: this gate answers "does the file exist", not "does the heading".
    """
    path = unquote(target.split("#")[0].split("?")[0])
    if not path:
        return None
    if path.startswith("/"):
        base, path = "", path.lstrip("/")
    else:
        base = str(Path(rel).parent)
    return os.path.normpath(os.path.join(base, path)).replace("\\", "/")


def _dangling(tracked, shipped) -> list[tuple[str, int, str, str]]:
    files, directories = shipped
    out = []
    for rel in tracked:
        if not rel.endswith(".md"):
            continue
        for lineno, target in _links(rel):
            resolved = _resolve(rel, target)
            if resolved is None or resolved in files or resolved in directories:
                continue
            out.append((rel, lineno, target, resolved))
    return out


def test_no_markdown_link_points_outside_the_shipped_tree(tracked, shipped):
    """THE gate. A link to a path this repository does not contain is a dead end
    for every reader who is not the person who wrote it."""
    new = [(f, n, t, r) for f, n, t, r in _dangling(tracked, shipped)
           if (f, r) not in KNOWN_DANGLING]
    assert not new, (
        "%d markdown link(s) resolve to a path this repository does not ship:\n  %s\n\n"
        "Point the link at something the repository actually contains, or drop it. "
        "A citation belongs in docs/REFERENCES.md, not in a pointer to a file only "
        "the author can see."
        % (len(new), "\n  ".join(f"{f}:{n}: [..]({t}) -> {r}" for f, n, t, r in new))
    )


def test_no_known_dangling_entry_has_been_fixed(tracked, shipped):
    """Keeps KNOWN_DANGLING shrinking.

    Without this, the allow-list is indistinguishable from an amnesty: an entry
    whose target has since been shipped would sit there forever, and the next
    person to break that same link would be waved through.
    """
    still_broken = {(f, r) for f, _, _, r in _dangling(tracked, shipped)}
    fixed = sorted(KNOWN_DANGLING - still_broken)
    assert not fixed, (
        "KNOWN_DANGLING lists link(s) that now resolve:\n  "
        + "\n  ".join(f"{f} -> {r}" for f, r in fixed)
        + "\n\nDelete these entries. The list must only ever shrink."
    )


def test_references_file_is_present_and_reachable(shipped):
    """The citation keys in the shipped documents resolve here by convention;
    if the file itself went missing, every one of them would dangle at once."""
    files, _ = shipped
    assert "docs/REFERENCES.md" in files, (
        "docs/REFERENCES.md is not in the shipped tree. Every [Key] citation in "
        "the worked examples and model cards resolves to it."
    )


# --------------------------------------------------------------------------- #
# the retired anchor namespace, and the bibliography it was replaced by
# --------------------------------------------------------------------------- #
#: The prefix of the retired citation-anchor namespace, held as a constant so
#: that this file never contains a literal anchor and therefore needs no
#: exemption from its own gate.
_RETIRED_PREFIX = "Q"

#: A retired anchor: the prefix, one or more hyphenated segments, and a numeric
#: tail. Built from the constant above rather than written out.
#:
#: The segment group **repeats** deliberately. A pattern that allows only one
#: hyphen before the digits cannot match a three-segment key, and that is not a
#: hypothetical: the sweep that retired the namespace lost five of thirteen
#: files to exactly that mistake.
RETIRED_ANCHOR = re.compile(rf"\b{_RETIRED_PREFIX}(?:-[A-Za-z0-9]+)*-[0-9]+[a-z]?\b")

#: Files allowed to name a retired anchor. None needs to: every file in the
#: tree, including the provenance record and its falsifier, writes retired keys
#: without the prefix. The set is kept so that an exemption, if one is ever
#: needed, is written down here rather than hidden in the pattern.
ANCHOR_EXEMPT: set = set()


def test_no_retired_citation_anchor_survives_anywhere(tracked):
    """No file may carry a retired citation anchor.

    **This gate is deliberately not restricted to markdown.** The sweep that
    retired the namespace verified itself with ``git ls-files '*.md' | xargs
    grep`` and reported zero remaining. That was true of markdown and false of
    the repository: the benchmark script and its captured output carried a
    further 36 references across 15 distinct keys, and a reader of the public
    repository could resolve none of them. A gate scoped to the file type where
    the defect was first noticed will keep passing while the defect lives
    somewhere else, so this one reads the whole tracked set.
    """
    hits = []
    for rel in tracked:
        if rel in ANCHOR_EXEMPT:
            continue
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for anchor in RETIRED_ANCHOR.findall(line):
                hits.append(f"{rel}:{lineno}: {anchor}")
    assert not hits, (
        "%d retired citation anchor(s) remain; each points at a reference this "
        "repository does not contain:\n  %s\n\n"
        "Replace the anchor with the bracket key of the work in "
        "docs/REFERENCES.md, adding the entry there first if it is missing."
        % (len(hits), "\n  ".join(hits[:40]))
    )


#: ``[Key]`` where the key is a name followed by a four-digit year — the scheme
#: docs/REFERENCES.md defines. The negative lookahead drops markdown inline
#: links, whose ``[text](target)`` is the link gate's business, not this one.
CITATION = re.compile(r"\[([A-Z][A-Za-z]*[0-9]{4}[a-z]?)\](?!\()")

#: A bibliography table row: ``| Key | Reference | Cited for |``.
BIB_ROW = re.compile(r"^\|\s*([A-Z][A-Za-z0-9]*)\s*\|.*\|.*\|\s*$", re.M)


def _bibliography() -> set[str]:
    """Keys defined by the table rows under ``## Bibliography``.

    Parsed from the rows, not from every bracketed token in the file: the
    prose above the table explains the naming scheme using invented keys, and
    reading those as definitions would let a genuine citation dangle behind an
    example.
    """
    text = (REPO / "docs/REFERENCES.md").read_text(encoding="utf-8")
    _, _, body = text.partition("## Bibliography")
    assert body, "docs/REFERENCES.md has no '## Bibliography' section"
    return set(BIB_ROW.findall(body)) - {"Key"}


def test_every_citation_key_resolves_to_the_bibliography(tracked):
    """A ``[Key]`` a reader cannot look up is the same dead end as a bad link.

    docs/REFERENCES.md itself is skipped: the section that documents the
    scheme cites invented keys as illustrations, and they are not claims that
    such works exist.
    """
    defined = _bibliography()
    used: dict[str, list[str]] = {}
    for rel in tracked:
        if rel == "docs/REFERENCES.md":
            continue
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for key in CITATION.findall(line):
                if key not in defined:
                    used.setdefault(key, []).append(f"{rel}:{lineno}")
    assert not used, (
        "%d citation key(s) are cited but not defined in docs/REFERENCES.md:\n  %s\n\n"
        "Add the work to the bibliography table -- author, title, publication, "
        "year, and a DOI or stable URL -- before citing it."
        % (len(used), "\n  ".join(f"[{k}] at {', '.join(v[:4])}" for k, v in sorted(used.items())))
    )
