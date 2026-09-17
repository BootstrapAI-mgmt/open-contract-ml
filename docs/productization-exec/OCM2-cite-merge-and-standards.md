# OCM2 — citation merge, standards alignment, signing design, publication checklist

Agent **OCM2**, repository `open-contract-ml`, branch
`w2/ocm2-cite-merge-standards`, worktree `C:/wt/ocm2-ocm`, forked from
`origin/main` at `55cff12`.

> **Notation.** This report is scanned by the gates it describes, and naming any
> of their targets inside a tracked file is itself a build failure. So: retired
> citation anchors have their prefix replaced by `<K>`; the unpublished quote
> ledger is written `<LEDGER>`; the retired internal shorthand is written `<S>`;
> and the planted citation key used to prove a gate hyphenates its year. Those
> four elisions are the only changes made to any quoted output — everything else,
> including every digest and byte count, is verbatim.

---

## Verdict

| # | Deliverable | Verdict |
|---|---|---|
| 1 | Merge `origin/fix/dangling-citations`, verify | **done, and the verification failed as briefed** — see below |
| 2 | `docs/STANDARDS-ALIGNMENT.md` | done |
| 3 | `docs/spec/PROVENANCE-SIGNING.md` | done |
| 4 | `docs/PUBLICATION-CHECKLIST.md` | done, with a blocking finding |
| 5 | No card infrastructure; follow-ups in the report | done |

### 1 — merge and verify

The merge landed. **The brief's expected result, "zero dangling citation
anchors", was false when measured**, and the larger part of this deliverable was
closing that.

- **`python -m pytest -q` → 225 passing.** Exactly as the brief predicted, after
  the merge. Now **227**, with the two gates added below.
- **Link-integrity gate passes and can fail.** Proven both directions.
- **Zero dangling anchors — only after further work.** The merge alone left 36
  references across 15 distinct keys in two non-markdown files. Now zero outside
  the two files that are the *record of* the removal.
- **`REFERENCES.md` defined-vs-used → 0 dangling, 0 unused**, a 38 ↔ 38
  bijection, now a standing gate.
- **Checker exits 0; tamper demo exits 1 with `M013`**, reproducing the README's
  output byte-for-byte including both digests and `2429 → 2440`.

```console
$ python -m pytest -q
227 passed in 16.90s
```

---

## What changed

### The merge (`04acd22`)

`docs/EXTRACTION.md` **auto-merged cleanly**. The brief said it "conflicts in 2
hunks"; it does not — the two sides' hunks are about 90 lines apart. The only
conflict was one hunk of `PROVENANCE.yaml`: `main` had pinned
`docs/EXTRACTION.md` at `7385d6cc` after the staleness sweep and the citation
branch at `4c392263`. Since both hunks merged, the merged blob matches neither;
recomputed from the staged blob as `708fc804…`. The citation branch's three new
`authored` records were kept.

### The citation gap the merge did not close (`3d74fbe`)

| File | Change |
|---|---|
| `examples/falsifier-benchmark/falsifier_benchmark.py` | 18 anchors → bracket keys (15 lines) |
| `examples/falsifier-benchmark/falsifier_results.txt` | the same 18, same lines, kept in step |
| `docs/REFERENCES.md` | +9 entries: Grinsztajn2022, Hastie2009, Jin2001, Kaw2012, KimeldorfWahba1970, Misic2020, Trefethen2013, WangShan2007, Xu2021 |
| `tests/test_link_integrity.py` | +2 gates: whole-tree anchor scan, and citation-key resolution |
| `docs/EXTRACTION.md` | known-gap 2 closed and removed, 3–5 renumbered; new **Citations** section; Divergences row for the falsifier pair |
| `PROVENANCE.yaml` | re-pinned 5 files; the two falsifier files become `transformed: true` |

### New documents (`8bd0fe0`)

- `docs/STANDARDS-ALIGNMENT.md` — deliverable 2.
- `docs/spec/PROVENANCE-SIGNING.md` — deliverable 3.
- `docs/PUBLICATION-CHECKLIST.md` — deliverable 4.

### Staleness (`e7c583b`)

- `README.md` Layout listed 4 docs; the repo ships 8.
- `docs/spec/CONTRACT-v1.md` §10.4 now cross-references the signing design and
  records that the manifest, card and report are hashed by nothing.

### Housekeeping (`ab50074`)

`.agent-scratch/BRIEF-OCM2.md`, committed by the shepherd in `fc43acb`,
un-tracked — see **Context**.

---

## Evidence

### Baseline was not green, and why

```console
$ python -m pytest -q          # first command of the session
FAILED tests/test_provenance.py::test_every_tracked_file_has_a_provenance_record
FAILED tests/test_provenance.py::test_forbidden_content_is_absent_from_the_tree[(^|/)\.agent-scratch(/|$)]
2 failed, 220 passed in 26.61s
```

`FORBIDDEN` bars `.agent-scratch` — "agent working files never travel". After
un-tracking the brief (the file stays on disk; `.git/info/exclude` already
carries `.agent-scratch/`):

```console
$ python -m pytest -q
222 passed in 15.03s
```

### The merge

```console
$ git merge --no-commit --no-ff origin/fix/dangling-citations
Auto-merging PROVENANCE.yaml
CONFLICT (content): Merge conflict in PROVENANCE.yaml
Auto-merging docs/EXTRACTION.md          <- no conflict, contrary to the brief

$ python -m pytest -q
225 passed in 15.30s
```

### Link gate can fail

```console
$ printf '\n[planted defect](docs/this-file-is-not-shipped.md)\n' >> docs/REFERENCES.md
$ python -m pytest tests/test_link_integrity.py -q
E   AssertionError: 1 markdown link(s) resolve to a path this repository does not ship:
E       docs/REFERENCES.md:69: [..](docs/this-file-is-not-shipped.md) -> docs/docs/this-file-is-not-shipped.md
1 failed, 2 passed in 0.35s

$ git checkout -- docs/REFERENCES.md && python -m pytest tests/test_link_integrity.py -q
3 passed in 0.09s
```

### The false clear, reproduced

The merged branch reported zero remaining anchors. It had searched markdown only:

```console
$ git grep -nE '\bQ-[A-Za-z]+-[0-9]+\b|\bQ-[0-9]+\b'
PROVENANCE.yaml:1015:    the file itself labels ''quote block <K>-cae-03 in <LEDGER>''.'
examples/falsifier-benchmark/falsifier_benchmark.py:1191: ... anchors <K>-surr-15, <K>-surr-19).
examples/falsifier-benchmark/falsifier_results.txt:812:  ... anchors <K>-surr-15, <K>-surr-19).
[… 32 more lines across those two files …]
tests/test_provenance.py:357: "Bathe, *Finite Element Procedures* … anchor <K>-cae-05",
```

Measured with a multi-hyphen-tolerant pattern as a cross-check — both agree:

```
WIDE  pattern: 4 files, 42 occurrences, 17 distinct
NARROW pattern: 4 files, 42 occurrences
files WIDE finds that NARROW misses: (none)
```

Non-exempt: **2 files, 36 occurrences, 15 distinct keys**.

### Anchors resolved

Mapping built from the upstream ledger's **bibliographic metadata lines only** —
every blockquote line was skipped by the extractor, never read. Each DOI was then
checked against its *registered* record by content negotiation, not by trusting
the ledger:

```
DOI 10.1007/s00158-001-0160-4  Comparative studies of metamodelling techniques …  Jin, R.; Chen, W.; Simpson, T.W.  2001
DOI 10.1115/1.2429697          Review of Metamodeling Techniques …                Wang, G. Gary; Shan, S.            2006*
DOI 10.1214/aoms/1177697089    A Correspondence Between Bayesian Estimation …     Kimeldorf; Wahba                   1970
DOI 10.1287/opre.2019.1928     Optimization of Tree Ensembles                     Mišić, Velibor V.                  2020
DOI 10.1007/978-0-387-84858-7  The Elements of Statistical Learning               Hastie; Tibshirani; Friedman       2009
                                                                    ISBN ['9780387848570', '9780387848587']
```

\* Crossref registers the online date (2006); the issue, *J. Mech. Des.* 129(4),
is 2007, which is the year the entry and the key use.

The two publisher pages that returned HTTP 403 to a bare `curl` (ASME, INFORMS)
are bot-blocks, not bad DOIs — both resolved fine through content negotiation.
**The SIAM DOI for Trefethen is genuinely unregistered** (`doi.org` → 404), so
that entry cites the ISBN and the author's own page instead; the ISBN was read
off that page (`1611972396`).

### Both new gates can fail

Anchor gate, planted in a **`.txt`** — the blind spot:

```console
$ printf 'anchor <K>-surr-99 planted in a .txt file\n' >> examples/falsifier-benchmark/falsifier_results.txt
$ python -m pytest tests/test_link_integrity.py::test_no_retired_citation_anchor_survives_anywhere -q
E   AssertionError: 1 retired citation anchor(s) remain; each points into a ledger this repository does not publish:
E       examples/falsifier-benchmark/falsifier_results.txt:1161: <K>-surr-99
1 failed in 0.67s

$ git ls-files '*.md' | xargs grep -lE 'Q-[A-Za-z]+-[0-9]+'     # the old sweep
    md-only sweep exit=123 -> finds nothing: this is the FALSE CLEAR reproduced
```

Citation gate, both directions:

```console
$ printf '\nSee [Nonexistent-2099] for the claim.\n' >> docs/model-packages.md
E   AssertionError: 1 citation key(s) are cited but not defined in docs/REFERENCES.md:
E       [Nonexistent-2099] at docs/model-packages.md:60

$ # and deleting a row that IS cited
E       [Xu2021] at examples/falsifier-benchmark/falsifier_benchmark.py:1267, …:1284,
E                   examples/falsifier-benchmark/falsifier_results.txt:874, …:885
```

### Bibliography reconciliation

```
defined in the table : 38
distinct keys used   : 38
DANGLING (used, never defined): 0
defined but not cited anywhere: 0
```

### Checker and tamper demo

Module identity checked first — see **Context**:

```console
$ PYTHONPATH=C:/wt/ocm2-ocm/src python -c "import opencontractml.verify as v; print(v.__file__)"
C:\wt\ocm2-ocm\src\opencontractml\verify.py

$ python -m opencontractml.verify check examples/reference-package
OK   examples\reference-package  (contract 1.0, 0 warning(s))
EXIT=0

$ printf '# tampered\n' >> examples/reference-package/predict.py
$ python -m opencontractml.verify check examples/reference-package
FAIL examples\reference-package  (2 error(s), 0 warning(s))
  [ERROR M013] manifest.yaml provenance.artifacts[0]: sha256 mismatch for './predict.py': declared 6842bee2…, on disk c4b2b439…
  [ERROR M013] manifest.yaml provenance.artifacts[0]: bytes mismatch for './predict.py': declared 2429, on disk 2440
EXIT=1

$ git checkout -- examples/reference-package/predict.py
$ python -m opencontractml.verify check examples/reference-package
OK   examples\reference-package  (contract 1.0, 0 warning(s))     EXIT=0
```

Identical to the README, including both digests and the byte counts.

### Deliverable 3 — the schema claim, verified

```console
baseline reference manifest      : VALID
with provenance.signature added  : VALID  <- no schema change required
removing provenance.dataset      : REJECTED -> 'dataset' is a required property
```

The third line is the negative control: the schema is permissive additively, not
vacuously. At checker level, a package carrying the field passes 1.0 unchanged.

### Deliverable 4 — publication checks

```console
$ python -m pip index versions open-contract-ml   -> ERROR: No matching distribution found
$ https://pypi.org/pypi/open-contract-ml/json     -> HTTP 404
$ https://pypi.org/pypi/opencontractml/json       -> HTTP 404

$ python -m build
Successfully built open_contract_ml-0.1.0.tar.gz and open_contract_ml-0.1.0-py3-none-any.whl

$ <clean venv outside the worktree>/python -c "import opencontractml.verify as v; print(v.__file__)"
…\ocm2-clean-venv\Lib\site-packages\opencontractml\verify.py
$ <clean venv>/python -m opencontractml.verify check examples/reference-package
OK   …  (contract 1.0, 0 warning(s))
$ <clean venv>/open-contract-ml.exe check examples/reference-package
OK   …  (contract 1.0, 0 warning(s))

$ # scan 1, structural          -> 42 passed
$ # scan 2, content-based       -> 1 passed
$ git grep -nE 'ghp_|AKIA|sk-[A-Za-z0-9]|BEGIN (RSA|OPENSSH)'   -> exit 1, no matches
```

### Institutional IP — the blocking finding

```
authors of every commit touching an extracted source path, at the recorded ref:
    117  jcoleman@captechu.edu
      3  bsaipersonal@gmail.com
      3  claude-cowork@anthropic.com
      2  jpcoleman12@gmail.com

extracted files total             : 87
  every commit university-authored: 80
  mixed authorship                :  4
  no university commit at all     :  3
```

---

## Blocked — needs a file I do not own

**Nothing blocked.** Every change was inside the OWNED set.

Two notes on the boundary:

1. **`PROVENANCE.yaml`** is excluded "beyond what the merge itself requires (the
   provenance test must stay green)". I edited it further: three new `authored`
   records, and re-pins for eight changed files. Both are forced by the gate —
   `test_every_tracked_file_has_a_provenance_record` fails on any new file
   without a record, and `test_recorded_digests_match_the_committed_content`
   fails on any edited file without a re-pin. I read the parenthetical as the
   operative constraint. **Re-pins were applied only to an explicit list of paths
   I had deliberately changed**, never as a blanket sweep, because a blanket
   re-pin would make that test vacuous for exactly this session's edits.

2. **`LICENSE`, `NOTICE`, `pyproject.toml` `version`** — untouched. Verified:
   `git diff origin/main...HEAD --stat` lists none of them.

---

## Staleness sweep

| Document | Result |
|---|---|
| `README.md` Layout | **fixed** — listed 4 docs, ships 8. `docs/REFERENCES.md` had been missing since the citation branch merged, which predates this session. |
| `README.md` tamper demo | **correct** — reproduced byte-for-byte. |
| `README.md` install/extras table | correct; no dependency changed. |
| `docs/EXTRACTION.md` known gaps | **fixed** — gap 2 (the dangling anchors) is closed; removed and 3–5 renumbered. |
| `docs/EXTRACTION.md` anchor measurement | **fixed** — the "129 references / 32 anchors / 21 files" paragraph now closes the loop instead of trailing off. |
| `docs/EXTRACTION.md` Divergences table | **extended** — the falsifier pair is now recorded as transformed here. |
| `docs/spec/CONTRACT-v1.md` §10.4 | **extended** — cross-references the signing design. |
| `docs/spec/CONTRACT-v1.md` §8 "35 rules" | **correct, left alone** — `len(verify.RULES) == 35` (33 ERROR, 2 WARN). I added tests, not checker rules. |
| `docs/productization-exec/CITE-dangling-citations.md` 222/225 | **left alone** — a record of that session, not a claim about the tree now. |
| `PROVENANCE.yaml` | 103 records against 103 tracked files. |
| `pyproject.toml` version | 0.1.0, consistent with `opencontractml.__version__` and the built wheel's metadata. No tags exist. |

---

## Context not captured anywhere else

### 1. The test suite silently validates a different worktree

**The most dangerous thing I found.** A user-level editable install puts another
worktree on `sys.path`:

```console
$ python -c "import opencontractml.verify as v; print(v.__file__)"
C:\wt\open-contract-ml\src\opencontractml\verify.py        # NOT C:\wt\ocm2-ocm
```

`__editable__.open_contract_ml-0.1.0.pth` in the user site-packages points at
`C:\wt\open-contract-ml\src`, which is checked out on `fix/dangling-citations`.
Four test files import the package. `pytest` does not put `src/` on the path, so
**every run in every worktree exercises whatever that `.pth` points at.**

My results survive only because I checked: `src/` is byte-identical between the
two trees (`git diff HEAD 30dfc34 -- src/` empty; `diff -r` shows only
`__pycache__` and `egg-info`), and re-running with `PYTHONPATH` pinned gives the
same 227. Had another agent been editing `src/` in that worktree, my whole run
would have been measuring their code.

Anyone working in a worktree of this repo should print `__file__` before
believing a before/after. This is recorded in `PUBLICATION-CHECKLIST.md` §5 and
is worth a `conftest.py` — but note `EXTRACTION.md` says `test_verify.py`
resolves schema parity through `importlib.resources` *deliberately*, "so it
measures the installed package rather than the source tree", so a fix has to
preserve that intent rather than blindly prepend `src/`.

### 2. `git checkout -- <file>` restores from the index, not from a moment ago

While proving the anchor gate could fail, I planted a defect in a file I had
**unstaged** edits in, then reverted with `git checkout --`. That threw away my
anchor fix on that file and restored the 18 original anchors. The only reason I
caught it is that the post-revert re-run was still red and I read the output
instead of assuming the revert worked.

Stage before planting. I did for every subsequent mutation.

### 3. The brief was wrong in four places, all measurable

| Brief said | Measured |
|---|---|
| `docs/EXTRACTION.md` "conflicts in 2 hunks" | auto-merges cleanly; only `PROVENANCE.yaml` conflicts |
| "zero dangling citation anchors" after the merge | 36 references, 15 keys, in two non-markdown files |
| ASME "V&V 20-2016" | no such edition — **V&V 20-2009**, reaffirmed 2016 and 2021; current designation **V&V 20-2009 (R2021)** |
| institutional IP "NOT this repo" | 84 of 87 extracted files have a university-authored commit upstream; 80 have nothing else |

Plus two smaller ones: MLTE is led by the **US Army AI Integration Center**, with
CMU SEI one of four contributing organisations — not "SEI MLTE"; and the PyPI
name is `mlte` (2.7.0), while `mlte-python` (1.0.3) also exists and is stale. The
brief's warning that `grep "Q-[0-9]"` gives a false clear was right in spirit and
wrong in specifics — the actual false clear was `git ls-files '*.md' | xargs grep`,
a correct pattern over the wrong file set.

### 4. `V006` does not compare the metric to the threshold

`V006` asserts `metrics` has ≥1 numeric leaf and `thresholds` has ≥1 numeric
leaf. It never pairs them. A report declaring `A1_accuracy: PASS` with
`r2: 0.996` against `r2_min: 900.0` is accepted:

```console
$ # thresholds multiplied by 1000, status left at PASS
$ python -m opencontractml.verify check .
OK   .  (contract 1.0, 0 warning(s))
```

Architecturally defensible — the producing gate computes the verdict, the
checker validates the report's form, and there is no naming convention telling
the checker which threshold governs which metric. But §2 of the spec says a bar
must be "stated and compared against a measurement", and the checker only
enforces *stated*. That is the same gap in kind as the one that produced `V009`.
Recorded in `STANDARDS-ALIGNMENT.md` §4 and as a follow-up.

### 5. The manifest, card and report are not tamper-evident

`provenance.artifacts` pins the entrypoint and the weights. Nothing pins
`manifest.yaml`, `model_card.md` or `validation_report.json`. Both of these
exited 0:

- injecting "This model is certified for safety-critical primary structure."
  into the card;
- multiplying `A1_accuracy`'s thresholds by 1000.

I also rewrote `manifest.yaml` wholesale through `yaml.safe_dump` and the
package still passed. For the card and report this is a *documented* consequence
of not self-hashing (§6.3) — but the manifest not being covered is the load-
bearing one, and §10.4 said only "signing is a v2 concern" without saying what
was exposed meanwhile. Now stated in both files.

### 6. A coincidence that will mislead the next reader

The citation branch removed **36 occurrences across 15 distinct keys**. I removed
**36 occurrences across 15 distinct keys**. Different keys entirely — theirs were
`cae-*` / `ml-*` / `surr-04`, mine all `surr-*` — and different files. The
identical totals are chance. Do not read the two sessions' numbers as the same
measurement re-reported.

### 7. The session transcript cannot go in this repository, and I did not commit it

The wave contract's session-end protocol requires `git add -f .agent-scratch`,
naming `transcript.jsonl` specifically. This repository's `FORBIDDEN` list bars
`.agent-scratch` — "agent working files never travel" — and `--cached` sees a
tracked file regardless of ignore rules. The shepherd's own `fc43acb` made the
suite 2-red from the first command of the session.

I predicted in an earlier draft of this report that the capture commit would be
"2-red". **I ran it and it was 6-red**, which is the more interesting result:

```console
FAILED tests/test_link_integrity.py::test_no_retired_citation_anchor_survives_anywhere
FAILED tests/test_link_integrity.py::test_every_citation_key_resolves_to_the_bibliography
FAILED tests/test_provenance.py::test_every_tracked_file_has_a_provenance_record
FAILED tests/test_provenance.py::test_forbidden_content_is_absent_from_the_tree[(^|/)\.agent-scratch(/|$)]
FAILED tests/test_provenance.py::test_internal_shorthand_does_not_leak_into_published_content
FAILED tests/test_provenance.py::test_no_verbatim_third_party_text
```

The reason is the transcript. Scanned with the repository's own detectors:

```
.agent-scratch/transcript.jsonl:
   R5 verbatim fragments present : ['Bathe textbook', 'NASA CFD Vision 2030 abstract',
                                    'Jin 2001', 'Kaw 2012', 'ReLU paper']
   names the ledger              : yes
   contains the retired shorthand: yes
```

**All five** of the third-party excerpt fragments that `R5` exists to keep out of
this tree are in the transcript — not because I read those sources, but because I
read `tests/test_provenance.py`, and the detector's own `THIRD_PARTY_EXCERPTS`
table contains the fragments it searches for. Recording the session recorded the
detector's payload along with it.

So committing the transcript would put verbatim third-party text into a
repository whose stated purpose is preventing exactly that, and would require
four publication-safety gates to be red to do it. `EXTRACTION.md`'s first
paragraph is that "a file wrongly published cannot be unpublished," and this
repository is a publication candidate under D21.

**Decision: I committed `BRIEF-OCM2.md`, `provpin.py` and `stderr.log`, and not
`transcript.jsonl`.** That is a deliberate, bounded deviation from the session-end
protocol, taken because a rule that is specific to this repository, mechanically
enforced, and about an irreversible harm should outrank a generic
work-preservation convention. The three committed files were scanned first and
carry no third-party text, no ledger reference and no shorthand; the brief does
carry two retired anchors, which is why the anchor gate is among the failures.

Measured on the commit as it stands, rather than predicted a third time:

```console
$ python -m pytest -q
FAILED tests/test_link_integrity.py::test_no_retired_citation_anchor_survives_anywhere
FAILED tests/test_provenance.py::test_every_tracked_file_has_a_provenance_record
FAILED tests/test_provenance.py::test_forbidden_content_is_absent_from_the_tree[(^|/)\.agent-scratch(/|$)]
3 failed, 224 passed in 22.00s
```

Three, not two and not six. Dropping the scratch directory clears all three.

**The transcript is not lost — it is still on disk** at
`C:/wt/ocm2-ocm/.agent-scratch/transcript.jsonl` (~2.1 MB). If the shepherd wants
it, copy it out of the worktree **before the worktree is deleted**; it must not
be committed here.

To restore green before merging, drop the scratch — nothing else depends on it:

```console
$ git rm -r --cached .agent-scratch && git commit -m "chore: drop agent scratch"
```

Worth resolving at the wave level. The launcher should write the brief and the
transcript **outside** the worktree for any repository that bars agent working
files, because in this one the protocol cannot be followed as written without
defeating the gates the repository exists to enforce.

### 8. Smaller traps

- **YAML plain scalars cannot contain `": "`.** A `why:` value beginning
  "D21 preparation: the owner-run checks…" made `PROVENANCE.yaml` unparseable
  and produced **32 errors and 1 failure** — a confusing blast radius for one
  colon. Quote it, as the file already does for `'this file: …'`.
- **The internal-shorthand gate caught my own prose.** I used the retired
  internal name (the one `EXTRACTION.md` "Renaming" describes) as an ordinary
  English noun — "its `<S>` is a negotiation card" — in
  `STANDARDS-ALIGNMENT.md`, and
  `test_internal_shorthand_does_not_leak_into_published_content` failed. The
  word has a perfectly normal meaning, so this will happen again to anyone
  writing prose here. I reworded rather than adding an exemption; the gate is
  live and correct.
- **Writing a report about these gates trips them.** The first version of *this
  file* failed two tests at once — the shorthand gate and
  `test_no_verbatim_third_party_text`, the latter because it flags any file
  containing the ledger's filename, and I had quoted `git grep` output that
  named it. A report in `docs/productization-exec/` is shipped content like any
  other. Budget a test run for the report itself, and agree the elision
  convention before writing rather than after.
- **The Bash tool's cwd persists across calls.** A `cd` into a scratch package
  made it undeletable ("in use") two calls later.
- **`curl` without a User-Agent gets 406 from some hosts.** The Kaw courseware
  PDF returns 406 bare and 200 (`application/pdf`, 866 159 bytes) with a UA.
- **The arXiv Atom API returned nothing over plain HTTP** from this host; the
  `abs/` pages fetched fine.
- **`python -m build` writes `build/` and `dist/`**, both already gitignored, so
  they do not reach a commit. The scratch venv was put outside the worktree
  deliberately.

### 9. Things I deliberately did not do

- Did not add a `conftest.py` to fix §1 — it interacts with a documented design
  decision and belongs in its own change.
- Did not fix `V006` — a contract change, not a docs change.
- Did not regenerate `falsifier_results.txt` by running the benchmark. It needs
  the `[gate]` stack and a long run; instead the pair is edited together and the
  correspondence is **proven** (every edited output line is still a string
  literal in the script). If the benchmark is ever re-run, the new output will
  carry the bracket keys naturally.
- Did not touch `.github/**`, `LICENSE`, `NOTICE`, or the version.

---

## Follow-ups

Card-sized, each with its repository.

| # | Repo | Card |
|---|---|---|
| 1 | `open-contract-ml` | **Contract 1.1: optional `provenance.signature`.** Land the field designed in `docs/spec/PROVENANCE-SIGNING.md`, plus rule `M017` at WARN gated on `spec_version >= 1.1`. No schema bump, no dependency, no signature verification. |
| 2 | `open-contract-ml` | **Make `V006` compare, or say that it does not.** Either adopt a metric↔threshold naming convention and recompute, or amend §2 of the spec so "compared" is not claimed by the checker. Currently a `PASS` can violate its own stated threshold. |
| 3 | `open-contract-ml` | **Pin the test suite to its own tree.** A `conftest.py` that makes imports resolve to the worktree under test, without breaking `test_verify.py`'s deliberate use of `importlib.resources` against the installed package. |
| 4 | `open-contract-ml` | **Contract 1.1: field I/O signatures.** `CONTRACT-v1.md` §10.3 calls this the largest hole in v1.0 and it blocks the physics-surrogates adoption. |
| 5 | `open-contract-ml` | **Contract 1.1: a licence field** for the model, weights and corpus. Surfaced by the Model Openness Framework comparison; absent today. |
| 6 | `open-contract-ml` | **Close `EXTRACTION.md` gap 1** — nine walkthroughs instruct the reader to run a CLOSED trainer. The first thing a new public reader will hit. |
| 7 | `open-contract-ml` | **Generalise `test_no_verbatim_third_party_text`.** It is a list of five known passages, not a detector; the citation session found a live verbatim quotation it missed. At minimum, say so in the docstring. |
| 8 | `physics-surrogates` | **PS04 — PhysicsNeMo-CFD adapter.** Emit a Contract package from a PhysicsNeMo-CFD evaluation. Its L2 field errors map to `A1`, integrated drag/lift to `B6`; `A3`, `B4` and all of Tier C would be `NOT_RUN`, which is the informative part. |
| 9 | **owner** | **Institutional-IP determination.** Blocking for D21. See `docs/PUBLICATION-CHECKLIST.md` §1 — 84 of 87 extracted files trace to university-authored commits. Not an agent decision. |
| 10 | wave/shepherd | **Resolve `.agent-scratch` vs the provenance gate** — see Context §7. |
