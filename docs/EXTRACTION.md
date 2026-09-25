# Where the files in this repository came from

This repository's public history starts at a single snapshot. Its files are of
three kinds, and `PROVENANCE.yaml` records which kind each one is, why it is
here and its content digest:

- **authored** — written for this package: the packaging, the CI workflow, the
  bibliography, the provenance falsifier and the producer-fixture READMEs;
- **extracted** — carried over from the maintainer's earlier work on these
  tools: the checker, the validation library, the gate engine, the
  specification and the worked examples, byte for byte or edited for
  publication;
- **modified copies** — the producer fixture packages under
  `tests/fixtures/producer_packages/`: copies of packages that producers emit,
  each with the changes it made stated in its README.

`tests/test_provenance.py` holds the record to the tree in both directions: a
file with no record fails the build, and so does a record for a file that is
not here, or a digest that no longer matches the committed bytes. Two content
gates sit beside it: third-party text is cited, never reproduced (see
`docs/REFERENCES.md`), and a retired internal name for the Contract must not
come back.

## Known gaps in what is here

Stated plainly rather than left to be discovered.

1. **The worked cells describe software that is not in this repository.**
   Each `examples/worked-cells/*/data/data-contract.md` specifies the dataset
   a trainer expects, and the five walkthroughs walk through a training step,
   a packaged executable or a comparison script; none of that software ships
   here, and each walkthrough says so at the top. The worked cells remain
   useful as worked data contracts with synthetic datasets, but do not read
   them as runnable end to end. In the same way, the problem-spec format in
   `examples/problem-spec/` is read by a surrogate-family selector that is not
   included. The fix is to re-point the training step at
   `examples/reference-package/`, to end each walkthrough at the data contract
   and hand off to the gate engine, or to ship a minimal open reference
   trainer.

2. **`safeload.py` ships without its test suite.** Its original tests depend on
   a training package and on `torch`, so they could not travel. Its sibling
   `safe_artifact.py` *is* tested here.

3. **Two independent safe-load implementations.** `safe_artifact.py` restricts
   `pickle` unpickling; `safeload.py` loads tensor checkpoints. They share
   `sha256_file` and two exception types and nothing else — they are siblings,
   not duplicates. The shared core is worth factoring; it was not factored here
   because refactoring security-critical code while publishing it is how subtle
   bugs get introduced.

4. **The worked datasets are synthetic, and that claim is checkable** — each
   cell ships the generator that produced its `sample-dataset.csv`, and
   running it reproduces the file up to line endings (the plate cell's with
   `--rows 500`). Not every data contract says "synthetic" in prose. The generator is stronger evidence
   than prose, but the contracts would read better with an explicit provenance
   line.

5. **The corpus gate engine's checks have no tests here.** `corpus_gate.py`
   and `gate.py` read a physics rules file, and no example rules file ships
   yet (`examples/corpus-consumer/` documents the engine and records the runs
   it was developed on). The engine imports cleanly, and its bundle loading is covered by
   `tests/test_safe_artifact.py`; tests of the checks themselves can follow a
   rules-file schema and a synthetic example pack.

## Citations

Every `[Key]` citation in the tree resolves to a row of `docs/REFERENCES.md`,
and every entry there carries a DOI, ISBN or stable URL. Two standing gates in
`tests/test_link_integrity.py` keep it that way:

- `test_no_retired_citation_anchor_survives_anywhere` reads **the whole tracked
  set**, not one file type, for anchors of a retired citation scheme that
  resolved to nothing a reader could open;
- `test_every_citation_key_resolves_to_the_bibliography` requires every `[Key]`
  in the tree to have a table row in `docs/REFERENCES.md`. Keys are parsed from
  the table rows, not from bracketed tokens anywhere in the file, because the
  prose above the table cites invented keys to explain the scheme.

## Changes made while publishing

| File | Change |
|---|---|
| `manifest.py` | The schema is package data resolved with `importlib.resources`, so it travels inside the wheel and there is no frozen-bundle special case. |
| `safeload.py` | Self-references point at `opencontractml.safeload`. Its safetensors metadata key and format name are `__opencontractml__` and `opencontractml-safetensors-1`, and migrating an artifact off pickle uses this module's own `load_checkpoint` and `save_checkpoint`. |
| `falsifier_benchmark.py`, `falsifier_results.txt` | Citation anchors replaced by the bracket keys of the works they stood for. The pair is edited together and kept in step: each narrative line in the captured output is a string literal in the script. |
| `.gitattributes` | Authored here. Without `eol=lf`, a clone on a machine with `core.autocrlf=true` rewrites `examples/reference-package/predict.py` from 2418 to 2484 bytes and all four `M013` pins fail. |
| `tests/test_verify.py` | Schema parity resolves through `importlib.resources`, so it measures the installed package rather than the source tree. |
