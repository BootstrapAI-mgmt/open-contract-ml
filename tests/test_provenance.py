"""The extraction falsifier: no file may exist here without a traced origin.

This repository was not forked. It was seeded by copying file *contents* out of
named commits of four sibling repositories, deliberately, so that IP-encumbered
history could not travel with them. That is only worth anything if it is
checkable, because the failure mode -- one closed file landing in a repository
that will later be published -- is not reversible.

``PROVENANCE.yaml`` is the record. Every file is either:

  (a) ``extracted``: copied from a named ``source_repo``/``source_ref``/
      ``source_path``, with the source blob's digest recorded; or
  (b) ``authored``: written for this package, on an explicit literal list.

and ``deferred`` names paths a source map marks extractable that are
deliberately *not* here, with the reason.

The three directions this file enforces, and why each one is needed:

  forward   a file here with no record  -> something arrived unaccounted for.
            This is the direction that catches a leak.
  backward  an extractable source file that is neither shipped nor deferred
            -> something was dropped silently. Without this, "we extracted
            everything" and "we extracted half of it" look identical.
  contamination  a path matching the never-copy list, in the tree *or* in any
            recorded ``source_path``. Belt and braces: the map already excludes
            these, so a hit means the map and this repo disagree.

Design rule inherited from the checker this repo ships: **never silent**. A
missing PROVENANCE.yaml, an unreadable tree or an absent ``git`` is a failure,
never a skip. The one genuinely optional check is the deep digest verification
against the source worktrees, which needs those worktrees on disk; it is
reported explicitly rather than quietly passing.
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

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
GLOBBY = re.compile(r"[*?\[\]]")

VALID_MAP_STATUS = {"extractable", "extractable-by-directory-entry", "not-in-map"}

#: Never extractable, on any branch, for any reason. Sources, in order:
#: owner ruling D18 (the three IP-encumbered cells, shown to non-open-source end
#: users); EXTRACTION-MANIFEST 3.1-3.2 (two stores of verbatim third-party
#: published text the org cannot sublicense); 4.3 CLOSED (trainers are
#: calibrated per-vertical rules packs); and R7 (the map and its checker are
#: governance metadata about the line, not on either side of it).
FORBIDDEN = [
    (r"TASK-8-1101-fatigue-life", "D18: IP-encumbered cell (also: no generator exists for its dataset)"),
    (r"TASK-8-1107-pump-operating-point", "D18: IP-encumbered cell"),
    (r"TASK-8-1401-pump-performance-curve", "D18: IP-encumbered cell (its generator does not produce its dataset)"),
    (r"(^|/)QUOTES\.md$", "verbatim third-party published text; 187 blockquote lines, 169 Q- records"),
    (r"(^|/)Evidence/", "TASK-9 verification ledgers: 296 verbatim third-party text records"),
    (r"(^|/)trainer/", "4.3 CLOSED: calibrated per-vertical rules packs"),
    (r"(^|/)presentations/", "closed everywhere"),
    (r"(^|/)scoping/", "closed everywhere"),
    (r"(^|/)sessions/", "closed everywhere"),
    (r"(^|/)cards/", "closed everywhere"),
    (r"(^|/)outputs/", "closed everywhere"),
    (r"\.pptx$", "slide artifact"),
    (r"(^|/)slide-config\.json$", "slide artifact"),
    (r"make_orientation_slide\.py$", "slide artifact"),
    (r"(^|/)OPEN-CLOSED-MAP\.yaml$", "R7: governance metadata about the line, not on either side of it"),
    (r"check_open_closed_map\.py$", "R7: the map's own checker"),
    (r"physics_rules\.json$", "4.3 CLOSED: calibrated rules packs (pv-c2 / pv-f1 / pv-f3)"),
    (r"(^|/)spec-.*\.yaml$", "D18: the three populated surrogate-selector instances are CLOSED"),
    (r"examples/packaging(/|$)", "CLOSED: produces the Train-*/Predict-* executables"),
    (r"TASK-10-fea-automation-v0", "not in the extraction set"),
    (r"(^|/)\.agent-scratch(/|$)", "agent working files never travel"),
]


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def provenance() -> dict:
    assert PROVENANCE.is_file(), f"PROVENANCE.yaml is missing from {REPO}"
    doc = yaml.safe_load(PROVENANCE.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), "PROVENANCE.yaml must be a mapping"
    assert doc.get("schema_version") == 1, f"unsupported schema_version {doc.get('schema_version')!r}"
    for key in ("authored", "extracted", "deferred", "source_maps"):
        assert isinstance(doc.get(key), list), f"PROVENANCE.yaml: {key!r} must be a list"
    return doc


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
# forward: nothing here is unaccounted for
# --------------------------------------------------------------------------- #
def test_every_tracked_file_has_a_provenance_record(provenance, tracked):
    """THE falsifier. A file with no record means the extraction is wrong."""
    recorded = {r["path"] for r in provenance["authored"]} | {r["path"] for r in provenance["extracted"]}
    orphans = sorted(set(tracked) - recorded)
    assert not orphans, (
        "%d file(s) in this repo trace to neither an extraction source nor the "
        "authored allow-list:\n  %s\n\n"
        "Every file here must be justifiable. Add an `extracted` record naming the "
        "source repo/ref/path, or an `authored` record saying why it was written."
        % (len(orphans), "\n  ".join(orphans))
    )


def test_no_record_points_at_a_file_that_is_not_here(provenance, tracked):
    """The reverse of the above: a record for a file nobody can find is stale."""
    present = set(tracked)
    for kind in ("authored", "extracted"):
        ghosts = sorted(r["path"] for r in provenance[kind] if r["path"] not in present)
        assert not ghosts, f"{kind}: record(s) for absent file(s): {ghosts}"


def test_no_path_is_recorded_twice(provenance):
    seen: dict[str, str] = {}
    dupes = []
    for kind in ("authored", "extracted"):
        for r in provenance[kind]:
            if r["path"] in seen:
                dupes.append(f"{r['path']} ({seen[r['path']]} and {kind})")
            seen[r["path"]] = kind
    assert not dupes, f"path(s) recorded more than once: {dupes}"


def test_authored_allow_list_is_data_not_a_wildcard(provenance):
    """A glob in the allow-list would let arbitrary new files in unnoticed.

    The whole value of the allow-list is that adding a file forces someone to
    write down why it is here. `src/**` would defeat that completely.
    """
    for r in provenance["authored"]:
        assert not GLOBBY.search(r["path"]), (
            f"authored entry {r['path']!r} contains a glob metacharacter. The allow-list "
            "must enumerate literal paths, one per file."
        )
        assert r.get("why"), f"authored entry {r['path']!r} has no `why`"


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


def test_recorded_digests_match_the_committed_content(provenance):
    """Catches a file edited after its record was written."""
    stale = []
    for kind in ("authored", "extracted"):
        for r in provenance[kind]:
            declared = r.get("sha256")
            if not declared:
                continue
            content = _canonical(r["path"])
            if content is None:
                continue                       # covered by the ghost test
            actual = hashlib.sha256(content).hexdigest()
            if actual != declared:
                stale.append(f"{r['path']}: recorded {declared[:16]}..., committed {actual[:16]}...")
    assert not stale, "PROVENANCE.yaml is stale for:\n  " + "\n  ".join(stale)


# --------------------------------------------------------------------------- #
# extracted records must actually identify a source
# --------------------------------------------------------------------------- #
def test_every_extracted_record_names_a_resolvable_source(provenance):
    bad = []
    for r in provenance["extracted"]:
        where = r.get("path", "<no path>")
        for key in ("source_repo", "source_ref", "source_ref_sha", "source_path", "source_sha256"):
            if not r.get(key):
                bad.append(f"{where}: missing {key}")
        if r.get("source_ref_sha") and not HEX40.match(str(r["source_ref_sha"])):
            bad.append(f"{where}: source_ref_sha is not a 40-hex commit id")
        if r.get("source_sha256") and not HEX64.match(str(r["source_sha256"])):
            bad.append(f"{where}: source_sha256 is not a 64-hex digest")
        if r.get("map_status") not in VALID_MAP_STATUS:
            bad.append(f"{where}: map_status {r.get('map_status')!r} not in {sorted(VALID_MAP_STATUS)}")
    assert not bad, "malformed extracted record(s):\n  " + "\n  ".join(bad)


def test_files_outside_the_map_carry_an_explicit_justification(provenance):
    """A file the open/closed map does not mark extractable is the risky class.

    It is allowed -- G1D's and G0C's deliverables sit on branches that have not
    merged yet, so the map *cannot* carry entries for them without tripping its
    own stale-entry check -- but it must never be silent.
    """
    bad = []
    for r in provenance["extracted"]:
        if r["map_status"] == "extractable":
            continue
        j = (r.get("justification") or "").strip()
        if not j or j.startswith("UNJUSTIFIED"):
            bad.append(r["path"])
    assert not bad, (
        "file(s) not covered by a map entry and with no justification:\n  "
        + "\n  ".join(bad)
    )


# --------------------------------------------------------------------------- #
# backward: nothing extractable was dropped without saying so
# --------------------------------------------------------------------------- #
def test_every_extractable_source_file_is_shipped_or_deferred(provenance):
    """Without this, a partial extraction is indistinguishable from a complete one."""
    shipped: dict[str, set[str]] = {}
    for r in provenance["extracted"]:
        if r["map_status"] == "extractable":
            shipped.setdefault(r["source_repo"], set()).add(r["source_path"])
    deferred: dict[str, set[str]] = {}
    for r in provenance["deferred"]:
        deferred.setdefault(r["source_repo"], set()).add(r["path"])

    problems = []
    for m in provenance["source_maps"]:
        repo = m["repo"]
        expected = set(m["extractable_files"])
        accounted = shipped.get(repo, set()) | deferred.get(repo, set())
        for missing in sorted(expected - accounted):
            problems.append(f"{repo}: {missing} is extractable but neither shipped nor deferred")
        for phantom in sorted(accounted - expected):
            problems.append(f"{repo}: {phantom} is claimed but is not extractable in that map")
    assert not problems, "map reconciliation failed:\n  " + "\n  ".join(problems)


def test_every_deferral_states_a_reason_and_a_remedy(provenance):
    bad = []
    for r in provenance["deferred"]:
        for key in ("path", "source_repo", "reason", "remedy"):
            if not str(r.get(key, "")).strip():
                bad.append(f"{r.get('path', '<no path>')}: missing {key}")
    assert not bad, "incomplete deferral record(s):\n  " + "\n  ".join(bad)


def test_deferred_files_really_are_absent(provenance):
    """A path recorded as deferred that is actually here is a bookkeeping lie."""
    deferred_sources = {r["path"] for r in provenance["deferred"]}
    here = {r["source_path"] for r in provenance["extracted"]}
    both = sorted(deferred_sources & here)
    assert not both, f"path(s) recorded as deferred but actually shipped: {both}"


# --------------------------------------------------------------------------- #
# contamination: the never-copy list, executable
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pattern,why", FORBIDDEN, ids=[p for p, _ in FORBIDDEN])
def test_forbidden_content_is_absent_from_the_tree(pattern, why, tracked):
    rx = re.compile(pattern)
    hits = sorted(p for p in tracked if rx.search(p))
    assert not hits, f"forbidden content in the tree ({why}):\n  " + "\n  ".join(hits)


@pytest.mark.parametrize("pattern,why", FORBIDDEN, ids=[p for p, _ in FORBIDDEN])
def test_forbidden_content_is_absent_from_every_recorded_source(pattern, why, provenance):
    """Also check where things *came from*, not only where they landed.

    A forbidden file renamed on the way in would pass the tree check and fail
    this one.
    """
    rx = re.compile(pattern)
    hits = sorted(f"{r['source_path']} -> {r['path']}"
                  for r in provenance["extracted"] if rx.search(r["source_path"]))
    assert not hits, f"extracted from a forbidden source ({why}):\n  " + "\n  ".join(hits)


#: The files allowed to say "spine".
#:
#: PROVENANCE.yaml must name the upstream branch and paths accurately --
#: renaming them there would falsify the record. docs/EXTRACTION.md is where the
#: rename is explained. This file is the detector, and a detector unavoidably
#: contains the string it looks for; the cost is that a genuine leak *inside
#: this file* would not be caught, which is an acceptable blind spot for a file
#: whose entire content is this check.
SHORTHAND_EXEMPT = {"PROVENANCE.yaml", "docs/EXTRACTION.md", "tests/test_provenance.py"}


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


# --------------------------------------------------------------------------- #
# R5: third-party verbatim text, barred whatever the bucket
# --------------------------------------------------------------------------- #
#: Fragments of the third-party excerpts that were found in — and removed from —
#: the extracted set. Content-based rather than structural, so a copy that was
#: reflowed, un-indented or pasted inline is still caught.
THIRD_PARTY_EXCERPTS = {
    "finite element procedures are at present very widely used":
        "Bathe, *Finite Element Procedures* (copyrighted textbook), anchor Q-cae-05",
    "to enable multi-physics analysis and design":
        "NASA CFD Vision 2030 Study abstract, NASA/CR-2014-218178, anchor Q-cae-03",
    "when large sample sizes are used":
        "Jin, Chen & Simpson 2001, anchor Q-surr-15",
    "has at least one root between":
        "Kaw 2012 bisection precondition, anchor Q-surr-46",
    "we quantify the observation that relu":
        "ReLU asymptotic-linearity paper, anchor Q-surr-34",
}

_WS = re.compile(r"\s+")


def test_no_verbatim_third_party_text(tracked):
    """Map rule R5, made executable.

    R5: "Third-party content (verbatim quoted text, licensed datasets, vendored
    snippets) is **never extracted, whatever its bucket**." R5 *overrides*
    `extract_to`. Five files in the extraction set were correctly bucketed open
    and correctly marked extractable and were still barred by this rule, because
    they carry transcribed excerpts from published papers and a textbook.

    That is the failure this whole repository exists to prevent: republishing
    text the organisation cannot sublicense. It is also the one failure that
    cannot be undone after the repository goes public.
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
        if "quotes.md" in flat:
            hits.append(f"{rel}: links or points into QUOTES.md, which is not publishable")
    assert not hits, (
        "verbatim third-party text found (map rule R5 -- barred whatever the bucket):\n  "
        + "\n  ".join(hits)
        + "\n\nRe-source the quote to its public DOI/arXiv and paraphrase, or remove the "
          "passage. A correct `extract_to: trust-standard` does not license this content."
    )


def test_no_source_repo_is_wired_in_as_a_git_remote():
    """Seeding fresh is the control that stops encumbered history travelling.

    Adding a source repo as a remote later would undo it, so assert it.
    """
    out = subprocess.run(["git", "-C", str(REPO), "remote", "-v"],
                         capture_output=True, text=True)
    assert out.returncode == 0, f"git remote failed: {out.stderr.strip()}"
    forbidden = ("CAE-ML-data-pipelines", "cae-ml-gui", "physics-surrogates",
                 "cfd-automation", "thermal-mesh-calculators", "diffsim-jax")
    hits = [ln for ln in out.stdout.splitlines() if any(f in ln for f in forbidden)]
    assert not hits, "a source repo is configured as a remote:\n  " + "\n  ".join(hits)


# --------------------------------------------------------------------------- #
# deep check: the recorded source digests are real
# --------------------------------------------------------------------------- #
WORKTREES = {
    "CAE-ML-data-pipelines": Path(r"C:/wt/x-dp"),
    "cae-ml-gui": Path(r"C:/wt/x-gui"),
    "physics-surrogates": Path(r"C:/wt/x-ps"),
}


def test_recorded_source_digests_are_real_blobs(provenance):
    """Verify source_sha256 against the actual blob, where the source is reachable.

    This is the only check here that depends on something outside the repo, so
    it is the only one allowed not to run -- and when it does not, it says so
    loudly rather than passing quietly.
    """
    reachable = {k: v for k, v in WORKTREES.items() if (v / ".git").exists() or v.joinpath(".git").is_file()}
    if not reachable:
        pytest.skip(
            "NOT VERIFIED: no source worktree is on this machine, so source_sha256 "
            "could not be checked against the real blobs. This check is complete only "
            "where the sources are present."
        )
    mismatches, unchecked = [], []
    for r in provenance["extracted"]:
        root = reachable.get(r["source_repo"])
        if root is None:
            unchecked.append(r["path"])
            continue
        out = subprocess.run(["git", "-C", str(root), "cat-file", "blob",
                              f"{r['source_ref_sha']}:{r['source_path']}"], capture_output=True)
        if out.returncode != 0:
            mismatches.append(f"{r['path']}: blob {r['source_ref_sha'][:10]}:{r['source_path']} not found")
            continue
        actual = hashlib.sha256(out.stdout).hexdigest()
        if actual != r["source_sha256"]:
            mismatches.append(f"{r['path']}: recorded {r['source_sha256'][:16]}..., blob {actual[:16]}...")
    assert not mismatches, "source digest mismatch:\n  " + "\n  ".join(mismatches)
    if unchecked:
        pytest.skip(f"PARTIALLY VERIFIED: {len(unchecked)} record(s) had no reachable source worktree")
