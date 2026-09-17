# What this repository is, and what it deliberately does not contain

`open-contract-ml` is an **extraction**, not a fork. Its contents were copied,
file by file, out of named commits of four sibling repositories in the
BootstrapAI-mgmt ecosystem. No git history was grafted, no source repository is
configured as a remote, and no source repository was modified.

That shape is deliberate and it is the point. The repositories this came from
contain material that cannot be published — most decisively
`CAE-ML-data-pipelines/QUOTES.md`, which holds verbatim third-party published
text (187 blockquote lines, 169 quote records, 428 DOI/arXiv references) that
the organisation cannot sublicense. A second store of the same class,
`Evidence/TASK-9-verification-ledgers/`, holds a further 296 verbatim records.
**Relicensing those repositories was never available**; extracting the open core
into a clean tree was. Seeding fresh is what guarantees that history cannot
travel, because there is no history here to travel in.

Publishing is irreversible. Every rule below exists because the two directions
of error are not symmetric: a file wrongly left out can be added next week, and
a file wrongly published cannot be unpublished.

## Where the line came from

The open/closed line is not this repository's judgement. It was derived from
`MASTER-PRODUCTIZATION-STRATEGY.md` §4.3 into a per-file `OPEN-CLOSED-MAP.yaml`
in each source repository, and the 16 paths §4.3 did not reach were settled by
owner ruling **D18**. Every file here that came from a mapped repository traces
to a map entry carrying `extract_to: trust-standard`.

The maps themselves are **not** here. They are governance metadata *about* the
line rather than content on either side of it, and the same goes for their
checker. `PROVENANCE.yaml` records each map's digest so the derivation stays
auditable without vendoring the closed inventory.

## Never extracted

`tests/test_provenance.py` enforces this list as a parametrized test, against
both the paths in this tree and the recorded source path of every extracted
file — so a forbidden file renamed on the way in fails too.

| Excluded | Why |
|---|---|
| `TASK-8-1101-fatigue-life`, `TASK-8-1107-pump-operating-point`, `TASK-8-1401-pump-performance-curve` | D18: IP-encumbered — shown to non-open-source end users. **The clean-room rewrites are also excluded**: they exist but are unreviewed, and they extract in a later pass. |
| `QUOTES.md`, `Evidence/` | verbatim third-party published text the organisation cannot sublicense |
| `trainer/**` | §4.3 CLOSED, "calibrated per-vertical rules packs" |
| `*.physics_rules.json` (`pv-c2`, `pv-f1`, `pv-f3`) | same: the calibrated thresholds are the commercial artifact |
| the surrogate-selector tool and its three populated `spec-*.yaml` | D18 CLOSED. Only `problem-spec-contract.md` and `problem-spec-template.yaml` are open, and both are here. |
| `presentations/`, `scoping/`, `sessions/`, `cards/`, `outputs/`, `*.pptx`, `slide-config.json`, `make_orientation_slide.py` | slide and session artifacts, closed everywhere |
| `examples/packaging`, `examples/TASK-10-fea-automation-v0` | not in the extraction set |
| `OPEN-CLOSED-MAP.yaml` and its checker | governance metadata about the line |

## Extractable, but deliberately deferred

Recorded as `deferred` in `PROVENANCE.yaml`, with a reason and a remedy each.
The reconciliation test asserts that shipped ∪ deferred covers every extractable
file in each source map exactly — so a silent drop cannot pass for a clean
extraction.

**Six documents carrying verbatim third-party text.** These were the single most
consequential finding of the extraction, and they are worth reading carefully
because the failure they represent is the one this repository exists to prevent.

All six are bucketed `open` and carry `extract_to: trust-standard`. That
bucketing is correct — they are documentation of open components. They are
nonetheless barred, because the map carries a rule that **overrides the bucket**:

> **R5.** Third-party content (verbatim quoted text, licensed datasets, vendored
> snippets) is never extracted, *whatever its bucket*.

What they contain:

| File | Content |
|---|---|
| `TASK-8-1103`, `TASK-8-1104`, `TASK-8-1105` walkthroughs | an 8-line verbatim blockquote from Bathe, *Finite Element Procedures* — a copyrighted textbook — each carrying a relative markdown link into `QUOTES.md` |
| `TASK-8-1102-drag-lift/WALKTHROUGH.md` | a 14-line verbatim blockquote of the NASA CFD Vision 2030 Study abstract, labelled in-file as a keyed quote block in `QUOTES.md` |
| `TASK-9-falsifier-benchmark/README.md` | verbatim sentences attributed to (Jin2001) and to Kaw2012 — the latter annotated in-file as "the legal stand-in anchor for Burden §2.1" — plus two more |
| `TASK-9-falsifier-benchmark/WALKTHROUGH.md` | no verbatim text, but it points into `QUOTES.md` and its numbers are transcribed from the README above; incoherent once that is gone, so the pair defers together |

Excluding `QUOTES.md` itself was never sufficient. Roughly 460 verbatim spans
were known to sit in two *files*, and the response was to exclude those files —
but D18 opened a set of worked cells and a benchmark whose prose had
**transcribed excerpts inlined into it**, each pointing back at `QUOTES.md` by
anchor. A path-based exclusion cannot see that. It took a content scan.

`tests/test_no_verbatim_third_party_text` now encodes each excerpt as a
whitespace-insensitive fragment, so a copy that is reflowed, un-indented or
pasted inline still fails the build.

**A related measurement, because the existing figure is badly wrong.** The
extraction manifest records the dangling-citation hazard as five `Q-` anchors
across three worked model cards. Measured across the post-D18 extraction set it
is **129 anchor references, 32 distinct anchors, across 21 files.** The manifest's
figure predates D18 and nobody re-measured after the worked cells and the
benchmark were opened. The remaining anchors (after the six removals above) were
citation keys rather than quoted text — a dangling-reference problem, not an R5
problem — but every one resolved to a file that will not be published. They have
since been re-sourced; see **Citations** below.

**The corpus-gate test suite** (`test_corpus_gate.py`, `test_model_gate.py`,
their `conftest.py` and `__init__.py`). Every test in both files takes a fixture
that loads `rules/pv-c2.physics_rules.json`, a CLOSED calibrated rules pack, and
`test_model_gate.py` additionally names two closed corpora. The gate engine
itself is here and imports cleanly; its tests cannot run until the engine ships
with a **rules-file schema plus a synthetic example pack**, which is the
documented remedy and needs an owner decision on what the synthetic thresholds
should be. Shipping the tests without it would produce a suite that skips or
errors on 100% of the gate cases — which reads as coverage and is not.

**`.github/workflows/validate-model-package.yml`.** CI is a separate pass: it
also requires re-pointing fifteen `python -m server.manifest` references across
two repositories to the console script this package now installs.

## Known gaps in what *is* here

Stated plainly rather than left to be discovered.

1. **Nine walkthroughs instruct the reader to run software that is not in this
   repository.** Every `examples/worked-cells/*/WALKTHROUGH.md` walks through a
   training step implemented by a CLOSED `trainer/`, or by a packaged
   `Train-*.exe` built from one. This is an editorial gap, not a bucketing
   error — the walkthroughs are unambiguously open and the trainers are
   unambiguously closed. The fix is to re-point the training step at
   `examples/reference-package/`, to end each walkthrough at the data contract
   and hand off to the gate engine, or to ship a minimal open reference trainer.
   **Until it is fixed, do not read the worked cells as runnable end to end.**

2. **`safeload.py` ships without its test suite.** Its upstream tests are bound
   to `physics-surrogates` internals (`physsur.cloud`, `physsur.mesh`,
   `physsur.models.registry`) and to `torch`, so they could not travel. Its
   sibling `safe_artifact.py` *is* tested here.

3. **Two independent safe-load implementations.** `safe_artifact.py` restricts
   `pickle` unpickling; `safeload.py` loads tensor checkpoints. They share
   `sha256_file` and two exception types and nothing else — they are siblings,
   not duplicates. The shared core is worth factoring; it was not factored here
   because refactoring security-critical code during an extraction is how
   subtle bugs get introduced.

4. **The worked datasets are synthetic, and that claim is checkable** — each
   cell ships the generator that produced its `sample-dataset.csv`. Only two of
   the nine data contracts say "synthetic" in prose. The generator is stronger
   evidence than prose, but the published contracts would read better with an
   explicit provenance line.

## Citations

The shipped documents once cited an internal quote ledger by anchor. That ledger
is not published, so every one of those anchors was a dead end for the only
reader who matters here: someone outside the organisation. They were removed in
two passes and replaced by `docs/REFERENCES.md`, a bibliography whose every entry
carries a DOI, ISBN or stable URL.

The two passes are worth recording separately, because the second exists only
because the first verified itself too narrowly:

| Pass | Scope | Removed |
|---|---|---|
| markdown | 13 `.md` files | 36 references, 15 distinct keys |
| everything else | `falsifier_benchmark.py` and its captured `falsifier_results.txt` | 36 references, 15 distinct keys |

The first pass confirmed itself with `git ls-files '*.md' | xargs grep`, which
reported zero remaining and was **true of markdown and false of the repository**.
A benchmark script and its output file carried exactly as many references as the
markdown had, and none of them were in scope of the check that declared the job
done. Re-running that same `.md`-only command today still reports zero against a
planted defect in a `.txt` file.

Two standing gates in `tests/test_link_integrity.py` close the class:

- `test_no_retired_citation_anchor_survives_anywhere` reads **the whole tracked
  set**, not one file type. Its two exemptions are `PROVENANCE.yaml` and
  `tests/test_provenance.py`, which are the record of the removal rather than a
  use of it.
- `test_every_citation_key_resolves_to_the_bibliography` requires every `[Key]`
  in the tree to have a table row in `docs/REFERENCES.md`. Keys are parsed from
  the table rows, not from bracketed tokens anywhere in the file, because the
  prose above the table cites invented keys to explain the scheme.

At the time of writing the bibliography defines **38 keys** and the tree cites
**38**, with nothing dangling and nothing unused in either direction.

## Divergences from upstream

Fixes made in the extracted copy only. The source repositories were not modified;
these are carried here so they are not lost.

| File | Change |
|---|---|
| `manifest.py` | `server.paths.resource_path` (PyInstaller `sys._MEIPASS` resolution) replaced with `importlib.resources`. This was the only open→closed import edge in `cae-ml-gui`, and removing it also removes the frozen-bundle special case: the schema now travels inside the wheel. |
| `safeload.py` | self-references re-pointed from `physsur.safeload` to `opencontractml.safeload`; pointers at the external converter now name the package that provides it. `_METADATA_KEY`, `_FORMAT` and the `PHYSSUR_*` environment variables are deliberately unchanged — the first two are an on-disk format identifier and the others are the names of live security controls. |
| `falsifier_benchmark.py`, `falsifier_results.txt` | 18 citation anchors each, pointing into the unpublished ledger, replaced by the bracket keys of the works they stood for. The pair is edited together and kept in step: each narrative line in the captured output is a string literal in the script, so a substitution applied to one and not the other is visible as a line that no longer matches. |
| `.gitattributes` | authored here. `cae-ml-gui` has none, and without `eol=lf` a clone on a machine with `core.autocrlf=true` rewrites `examples/reference-package/predict.py` from 2429 to 2495 bytes and all four `M013` pins fail. |
| `tests/test_verify.py` | schema parity now resolves through `importlib.resources`, so it measures the installed package rather than the source tree. |

## Renaming

`spine` was internal shorthand; `contract` is the public identity. Every path,
import, schema `$id`, identifier, CLI string and the `schema_version` key were
renamed — 177 occurrences across 13 files.

`grep -ri spine` over this tree returns hits in exactly three files, and all
three are deliberate: `PROVENANCE.yaml`, whose `source_ref` and `source_path`
fields must name the upstream branch and paths accurately — renaming them would
falsify the provenance record; this document, which explains the rename; and
`tests/test_provenance.py`, the detector itself, which unavoidably contains the
string it searches for.
`test_internal_shorthand_does_not_leak_into_published_content` asserts that —
its `SHORTHAND_EXEMPT` set is exactly those three files — so the rename cannot
quietly regress.

The rename shortened `examples/reference-package/predict.py` by six bytes, which
made the reference manifest's `sha256`/`bytes` pin stale, and `M013` caught it.
The pin was then updated to the real values. That is recorded because it is the
best available evidence that the anti-vacuity property survived the move: the
pin fired on a real, unintended content change, before anybody went looking.
