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

2. **The three worked model cards cite anchors into `QUOTES.md`**
   (`examples/worked-model-cards/`, five `Q-` anchors across the three). Those
   anchors resolve to nothing here. Each needs re-sourcing to its public
   DOI/arXiv reference, or dropping, before publication.

3. **`safeload.py` ships without its test suite.** Its upstream tests are bound
   to `physics-surrogates` internals (`physsur.cloud`, `physsur.mesh`,
   `physsur.models.registry`) and to `torch`, so they could not travel. Its
   sibling `safe_artifact.py` *is* tested here.

4. **Two independent safe-load implementations.** `safe_artifact.py` restricts
   `pickle` unpickling; `safeload.py` loads tensor checkpoints. They share
   `sha256_file` and two exception types and nothing else — they are siblings,
   not duplicates. The shared core is worth factoring; it was not factored here
   because refactoring security-critical code during an extraction is how
   subtle bugs get introduced.

5. **The worked datasets are synthetic, and that claim is checkable** — each
   cell ships the generator that produced its `sample-dataset.csv`. Only two of
   the nine data contracts say "synthetic" in prose. The generator is stronger
   evidence than prose, but the published contracts would read better with an
   explicit provenance line.

## Divergences from upstream

Fixes made in the extracted copy only. The source repositories were not modified;
these are carried here so they are not lost.

| File | Change |
|---|---|
| `manifest.py` | `server.paths.resource_path` (PyInstaller `sys._MEIPASS` resolution) replaced with `importlib.resources`. This was the only open→closed import edge in `cae-ml-gui`, and removing it also removes the frozen-bundle special case: the schema now travels inside the wheel. |
| `safeload.py` | self-references re-pointed from `physsur.safeload` to `opencontractml.safeload`; pointers at the external converter now name the package that provides it. `_METADATA_KEY`, `_FORMAT` and the `PHYSSUR_*` environment variables are deliberately unchanged — the first two are an on-disk format identifier and the others are the names of live security controls. |
| `.gitattributes` | authored here. `cae-ml-gui` has none, and without `eol=lf` a clone on a machine with `core.autocrlf=true` rewrites `examples/reference-package/predict.py` from 2429 to 2495 bytes and all four `M013` pins fail. |
| `tests/test_verify.py` | schema parity now resolves through `importlib.resources`, so it measures the installed package rather than the source tree. |

## Renaming

`spine` was internal shorthand; `contract` is the public identity. Every path,
import, schema `$id`, identifier, CLI string and the `schema_version` key were
renamed — 177 occurrences across 13 files.

`grep -ri spine` over this tree returns hits in exactly two files, and both are
deliberate: `PROVENANCE.yaml`, whose `source_ref` and `source_path` fields must
name the upstream branch and paths accurately — renaming them would falsify the
provenance record — and this document, which explains the rename.
`test_internal_shorthand_does_not_leak_into_published_content` asserts that,
so the rename cannot quietly regress.

The rename shortened `examples/reference-package/predict.py` by six bytes, which
made the reference manifest's `sha256`/`bytes` pin stale, and `M013` caught it.
The pin was then updated to the real values. That is recorded because it is the
best available evidence that the anti-vacuity property survived the move: the
pin fired on a real, unintended content change, before anybody went looking.
