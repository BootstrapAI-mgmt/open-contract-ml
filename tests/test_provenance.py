"""The provenance falsifier: no file may exist here without a record.

``PROVENANCE.yaml`` is the record. Every tracked file has exactly one entry,
in one of three classes:

  (a) ``authored``: written for this package;
  (b) ``extracted``: carried over from the maintainer's earlier work on these
      tools, byte for byte or edited for publication (``transformed``);
  (c) ``modified_copies``: a file of another producer's package, copied in as
      a test fixture, with what the copy changed stated in the record and in
      the package's README.

Every record says why the file is here and pins its sha256 (the record's own
entry excepted: a file cannot pin its own digest).

The directions this file enforces, and why each one is needed:

  forward   a file here with no record -> something arrived unaccounted for.
            This is the direction that catches a leak.
  reverse   a record for a file that is not here -> the record is stale.
  content   a recorded digest that no longer matches the committed bytes -> a
            file was edited after its record was written.

Two content gates sit beside them, because no record can express what a file
*says*: internal shorthand must not leak into published content, and
third-party text must never be republished verbatim.

Design rule inherited from the checker this repo ships: **never silent**. A
missing PROVENANCE.yaml, an unreadable tree or an absent ``git`` is a failure,
never a skip.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
PROVENANCE = REPO / "PROVENANCE.yaml"
SELF = "PROVENANCE.yaml"

HEX64 = re.compile(r"^[0-9a-f]{64}$")
GLOBBY = re.compile(r"[*?\[\]]")

CLASSES = ("authored", "extracted", "modified_copies")

#: Where modified copies may live: they are test fixtures, nothing else.
COPIES_ROOT = "tests/fixtures/producer_packages/"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def provenance() -> dict:
    assert PROVENANCE.is_file(), f"PROVENANCE.yaml is missing from {REPO}"
    doc = yaml.safe_load(PROVENANCE.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "PROVENANCE.yaml must be a mapping"
    assert doc.get("schema_version") == 2, f"unsupported schema_version {doc.get('schema_version')!r}"
    for key in CLASSES:
        assert isinstance(doc.get(key), list), f"PROVENANCE.yaml: {key!r} must be a list"
    return doc


@pytest.fixture(scope="module")
def records(provenance) -> list[tuple[str, dict]]:
    return [(kind, r) for kind in CLASSES for r in provenance[kind]]


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    """Every file in the tree that is not gitignored.

    ``--others`` matters: a file dropped in but not yet ``git add``-ed is still
    sitting in the tree, and checking only ``--cached`` would let it stay
    invisible right up until somebody commits it. Gitignored paths (build
    output, venvs, caches) are excluded because they are not content.

    A git failure fails the test. It never skips -- a provenance check that
    quietly passes when it could not read the tree is worse than none.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True)
    assert out.returncode == 0, f"git ls-files failed: {out.stderr.strip()}"
    files = sorted({ln.strip() for ln in out.stdout.splitlines() if ln.strip()})
    assert files, "git ls-files returned nothing -- the tree cannot be verified"
    return files


# --------------------------------------------------------------------------- #
# forward and reverse: the record and the tree describe the same set of files
# --------------------------------------------------------------------------- #
def test_every_tracked_file_has_a_provenance_record(records, tracked):
    """THE falsifier. A file with no record means the tree is not accounted for."""
    recorded = {r["path"] for _, r in records}
    orphans = sorted(set(tracked) - recorded)
    assert not orphans, (
        "%d file(s) in this repo have no provenance record:\n  %s\n\n"
        "Every file here must be justifiable. Add an `authored`, `extracted` or "
        "`modified_copies` record that says why it is here."
        % (len(orphans), "\n  ".join(orphans))
    )


def test_no_record_points_at_a_file_that_is_not_here(records, tracked):
    """The reverse of the above: a record for a file nobody can find is stale."""
    present = set(tracked)
    ghosts = sorted("%s (%s)" % (r["path"], kind) for kind, r in records if r["path"] not in present)
    assert not ghosts, f"record(s) for absent file(s): {ghosts}"


def test_no_path_is_recorded_twice(records):
    seen: dict[str, str] = {}
    dupes = []
    for kind, r in records:
        if r["path"] in seen:
            dupes.append(f"{r['path']} ({seen[r['path']]} and {kind})")
        seen[r["path"]] = kind
    assert not dupes, f"path(s) recorded more than once: {dupes}"


def test_every_record_is_a_literal_path_with_a_reason(records):
    """A glob would let arbitrary new files in unnoticed.

    The whole value of the record is that adding a file forces someone to write
    down why it is here. `src/**` would defeat that completely.
    """
    bad = []
    for kind, r in records:
        if GLOBBY.search(r["path"]):
            bad.append(f"{r['path']} ({kind}): glob metacharacter in the path")
        if not str(r.get("why", "")).strip():
            bad.append(f"{r['path']} ({kind}): no `why`")
    assert not bad, "malformed record(s):\n  " + "\n  ".join(bad)


# --------------------------------------------------------------------------- #
# content: every recorded digest is the digest of what is committed
# --------------------------------------------------------------------------- #
def _canonical(rel: str) -> bytes | None:
    """The bytes a consumer gets: the staged blob, falling back to the file.

    These are not always the same. A working tree can drift to CRLF while the
    blob stays LF -- ``text=auto`` normalises on comparison, so ``git status``
    reports clean and nothing warns you. Digesting the working tree then
    produces records that fail for everyone who clones. That happened here to 11
    files and was only visible because the suite was run inside a fresh clone.
    """
    out = subprocess.run(["git", "-C", str(REPO), "cat-file", "blob", f":{rel}"],
                         capture_output=True)
    if out.returncode == 0:
        return out.stdout
    p = REPO / rel
    return p.read_bytes() if p.is_file() else None


def test_every_record_but_its_own_pins_a_digest(records):
    """A record without a digest is a record nothing can falsify."""
    bad = []
    for kind, r in records:
        declared = r.get("sha256")
        if r["path"] == SELF:
            if declared is not None:
                bad.append(f"{SELF}: its own record cannot pin its own digest; declare null")
        elif not isinstance(declared, str) or not HEX64.match(declared):
            bad.append(f"{r['path']} ({kind}): sha256 {declared!r} is not 64 lowercase hex characters")
    assert not bad, "unpinned record(s):\n  " + "\n  ".join(bad)


def test_recorded_digests_match_the_committed_content(records):
    """Catches a file edited after its record was written."""
    stale = []
    for _, r in records:
        declared = r.get("sha256")
        if not declared:
            continue                           # only SELF, by the test above
        content = _canonical(r["path"])
        if content is None:
            continue                           # covered by the ghost test
        actual = hashlib.sha256(content).hexdigest()
        if actual != declared:
            stale.append(f"{r['path']}: recorded {declared[:16]}..., committed {actual[:16]}...")
    assert not stale, "PROVENANCE.yaml is stale for:\n  " + "\n  ".join(stale)


# --------------------------------------------------------------------------- #
# the classes mean what they say
# --------------------------------------------------------------------------- #
def test_every_extracted_record_says_whether_it_was_transformed(provenance):
    bad = [r["path"] for r in provenance["extracted"] if not isinstance(r.get("transformed"), bool)]
    assert not bad, "extracted record(s) without a boolean `transformed`:\n  " + "\n  ".join(bad)


def test_modified_copies_are_fixtures_that_state_their_changes(provenance, tracked):
    """A modified copy is a test fixture, says what changed, and sits beside a README.

    The README is where a reader of the fixture finds the same statement, file by
    file, so a copy whose directory has no README is a copy nobody can audit.
    """
    present = set(tracked)
    bad = []
    for r in provenance["modified_copies"]:
        path = r["path"]
        if not path.startswith(COPIES_ROOT):
            bad.append(f"{path}: a modified copy must live under {COPIES_ROOT}")
        if not str(r.get("copy_of", "")).strip():
            bad.append(f"{path}: no `copy_of` naming the copied package")
        if not str(r.get("changes", "")).strip():
            bad.append(f"{path}: no `changes` saying how the copy differs")
        readme = str(Path(path).parent.as_posix()) + "/README.md"
        if readme not in present:
            bad.append(f"{path}: no {readme} beside it")
    assert not bad, "malformed modified-copy record(s):\n  " + "\n  ".join(bad)


# --------------------------------------------------------------------------- #
# content gates
# --------------------------------------------------------------------------- #
#: The files allowed to say "spine". This file is the detector, and a detector
#: unavoidably contains the string it looks for; the cost is that a genuine leak
#: *inside this file* would not be caught, which is an acceptable blind spot for
#: a file whose entire content is this check.
SHORTHAND_EXEMPT = {"tests/test_provenance.py"}


def test_internal_shorthand_does_not_leak_into_published_content(tracked):
    """`spine` was the internal name; `contract` is the public one.

    A rename that is done once and never asserted comes back the first time
    somebody copies a paragraph out of an old document, so this is a standing
    gate rather than a one-off sweep.
    """
    rx = re.compile(r"spine", re.IGNORECASE)
    hits = []
    for rel in tracked:
        if rel in SHORTHAND_EXEMPT:
            continue
        if rx.search(rel):
            hits.append(f"{rel}: in the path itself")
            continue
        p = REPO / rel
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                hits.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not hits, (
        "internal shorthand 'spine' leaked into published content (%d hit(s)):\n  %s\n\n"
        "Rename to 'contract'. If a hit is a deliberate historical note, add its "
        "file to SHORTHAND_EXEMPT and say why." % (len(hits), "\n  ".join(hits[:25]))
    )


#: Fragments of third-party passages that were found in -- and removed from --
#: the material this repository was built from. Content-based rather than
#: structural, so a copy that was reflowed, un-indented or pasted inline is
#: still caught.
THIRD_PARTY_EXCERPTS = {
    "finite element procedures are at present very widely used":
        "Bathe, *Finite Element Procedures* (a copyrighted textbook)",
    "to enable multi-physics analysis and design":
        "the NASA CFD Vision 2030 Study abstract, NASA/CR-2014-218178",
    "when large sample sizes are used":
        "Jin, Chen & Simpson 2001",
    "has at least one root between":
        "Kaw 2012, the bisection-method chapter",
    "we quantify the observation that relu":
        "a paper on the asymptotic linearity of ReLU networks",
}

_WS = re.compile(r"\s+")


def test_no_verbatim_third_party_text(tracked):
    """Third-party text is cited, never reproduced (docs/REFERENCES.md).

    Five passages of that kind -- transcribed excerpts from published papers
    and a textbook -- were found in documents this repository was built from,
    and were removed rather than republished. This gate keeps them from coming
    back. Republishing text the maintainer cannot sublicense is the one failure
    that cannot be undone after the repository is public.
    """
    hits = []
    for rel in tracked:
        if rel in SHORTHAND_EXEMPT:
            continue
        try:
            raw = (REPO / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # collapse whitespace and drop blockquote markers so wrapping and
        # indentation cannot hide a match
        flat = _WS.sub(" ", raw.replace(">", " ")).lower()
        for needle, source in THIRD_PARTY_EXCERPTS.items():
            if needle in flat:
                hits.append(f"{rel}: {source}")
    assert not hits, (
        "verbatim third-party text found:\n  "
        + "\n  ".join(hits)
        + "\n\nCite the work in docs/REFERENCES.md and restate the finding in your "
          "own words, or remove the passage."
    )
