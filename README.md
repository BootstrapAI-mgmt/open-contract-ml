# open-contract-ml

[![CI](https://github.com/BootstrapAI-mgmt/open-contract-ml/actions/workflows/ci.yml/badge.svg)](https://github.com/BootstrapAI-mgmt/open-contract-ml/actions/workflows/ci.yml)

**The Contract v1** — a model-card / manifest / provenance / validation standard
for engineering ML, and the checker that decides whether a given package obeys it.

A machine-learning surrogate that replaces a solver has to be trusted by someone
who did not train it. The Contract is what that person reads. It says what a
model package must declare — what it takes, what it returns, how uncertain it
is, what data it came from, and what was measured to justify shipping it — and
`opencontractml.verify` decides whether a directory actually declares it.

```console
$ pip install open-contract-ml
$ open-contract-ml check examples/reference-package
OK   examples/reference-package  (contract 1.1, 0 warning(s))
```

Exit code 0 means conformant. 1 means it told you exactly which rule failed and why.

## What is in a contract package

A directory containing:

| File | What it carries |
|---|---|
| `manifest.yaml` | the machine contract: identity, inputs, outputs, the uncertainty contract, how to invoke it, lineage, **provenance**, **validation** |
| `model_card.md` | the human contract: eleven required sections, in order |
| `validation_report.json` | what was measured, against what threshold |
| the artifacts | the entrypoint and the weights, each pinned by sha256 and byte count |

`examples/reference-package/` is a worked conformant instance. Every hash in its
manifest is the real digest of the file beside it and every number in its
validation report was measured, so it is a fixture you can check the checker against.
`examples/reference-field-package/` is the same for a model whose output is a
field: its entrypoint writes VTK XML PolyData files, one for the field and one for
each edge of its band, and answers with references to them, each carrying the
file's digest and size, and
`examples/build_reference_field_package.py --check` rebuilds every number and
digest in it byte for byte.

## The property that makes this worth anything

**A gate must be able to fail.** A conformance checker that has only ever been
seen passing is indistinguishable from one that returns `OK` unconditionally, so
the suite plants a defect for every `ERROR` rule and asserts that the rule
fires. `test_every_error_rule_has_a_negative_test` then asserts the mutation
table covers the rule table — adding a rule without proving it can fail breaks
the build.

You can see it directly. Change one byte of the pinned entrypoint:

```console
$ printf '# tampered\n' >> examples/reference-package/predict.py
$ open-contract-ml check examples/reference-package
FAIL examples/reference-package  (2 error(s), 0 warning(s))
  [ERROR M013] manifest.yaml provenance.artifacts[0]: sha256 mismatch for './predict.py': declared b88997634053fed8990a5044d61c9729bbcedf735d7ee08adb2f11e41b580c8a, on disk d7928c126802abdda8fb9cce0cf2feda2a704beddab1c37790175398fc8c75f3
  [ERROR M013] manifest.yaml provenance.artifacts[0]: bytes mismatch for './predict.py': declared 5141, on disk 5152
```

(That is real output, not an illustration — restore the file with
`git checkout examples/reference-package/predict.py` and it returns to `OK`.)

The second principle it holds itself to: **presence is not compliance.** A check
that reports `PASS` has to carry at least one numeric measurement *and* at least
one numeric threshold. A declaration string is never a pass. That rule (`V006`)
exists because a real scalar validation ladder green-stamped a model whose card
declared the conservation check unimplemented — the check tested that a
free-text field was a non-empty string, and a test enshrined the pass.

From contract 1.1 the status must also follow from the numbers. A check that
reports `PASS` or `FAIL` names its comparison — `{metric: r2, op: ">=", bar:
r2_min}` — and the checker recomputes the status from it, so a `PASS` whose `r2`
misses its `r2_min` is rejected (`V013`).

Contract 1.1 was amended again before 0.2.0, the first release to implement it. A
`type: field` output states what it holds — its kind, units, support and payload
format (`M019`) — and a run answers it with a reference to the file it wrote. A
`licence` block names the licences of the model, its weights and its training
data (`M020`; `M021` warns when there is none). A conservation check that applies
but was not run may say so, and still blocks. A point predictor may declare
`uncertainty.form: none`. A package may record a detached signature, whose
declaration is checked (`M017`) and which nothing verifies. Section 11 of
`docs/spec/CONTRACT-v1.md` lists every change since 1.0 and what each means for a
package that conformed to 1.0.

Two switches go further. `open-contract-ml check --smoke` runs the package's
entrypoint the way a consumer dispatches it, in the `stdio_json` frame that
section 12 of the Contract defines: each example the manifest declares as a
request of its own, in a fresh working directory, and all of them as one batch
where the manifest declares batch support. Every answer must carry the declared
outputs and uncertainty keys (`S001`), and every artifact reference in it must
match the file the entrypoint wrote (`S003`). It executes the package's code, so
it is off by default and the plain check runs nothing. `--json <file>` writes a
conformance record: the checker's version, the digests of the documents it read,
when it ran, and for every rule whether it was evaluated, fired, or not evaluated
and why.

## Installing

```console
pip install open-contract-ml            # the checker + the validation library
pip install open-contract-ml[gate]      # + the corpus/model gate engine
pip install open-contract-ml[tensors]   # + safe tensor-checkpoint loading
```

`opencontractml.verify` — the conformance checker — is standard-library-only on
purpose, so it runs from a bare interpreter in any CI. The extras are separated
because a consumer *validating* a package does not need a training stack to do it.

| Module | Needs |
|---|---|
| `opencontractml.verify` | nothing (PyYAML used if importable) |
| `opencontractml.manifest`, `.model_card` | pyyaml, jsonschema, pydantic |
| `opencontractml.safe_artifact` | nothing |
| `opencontractml.gate`, `.corpus_gate` | `[gate]` |
| `opencontractml.safeload` | `[tensors]` |

## Layout

```
docs/spec/CONTRACT-v1.md            the normative text
docs/spec/PROVENANCE-SIGNING.md     design for an optional signature; 1.1 defines the field, nothing verifies one
docs/EXTRACTION.md                  where the files came from, and the known gaps
docs/STANDARDS-ALIGNMENT.md         where this sits against ASME VVUQ, and where it does not reach
docs/REFERENCES.md                  the bibliography every [Key] citation resolves to
src/opencontractml/
  verify.py                         the conformance checker
  manifest.py, model_card.py        the validation library
  gate.py, corpus_gate.py           the gate engine
  safe_artifact.py, safeload.py     safe deserialization
  schemas/contract-v1/              manifest schema, conformance-record schema, machine-readable vocabulary
examples/reference-package/         a worked conformant instance
examples/reference-field-package/   a worked conformant instance whose output is a field
examples/build_reference_field_package.py  writes that package from a seeded corpus; --check rebuilds it
examples/worked-cells/              nine worked data contracts with synthetic datasets
examples/falsifier-benchmark/       the adversarial benchmark
tests/fixtures/producer_packages/   copies of real producer packages, checked in CI
PROVENANCE.yaml                     where every file in this repo came from
CHANGELOG.md                        what changed in each release
CONTRIBUTING.md                     running the checks, and how the Contract is amended
SECURITY.md                         reporting a vulnerability; the safe-loading policy
CLAUDE.md                           notes for coding agents working on this repository
```

## Provenance

This repository's public history starts at a single snapshot. Its files were
either written for this package, carried over from the maintainer's earlier
work on these tools, or — the producer fixtures — copied from packages other
producers emit, with the changes stated beside each copy.

`PROVENANCE.yaml` records which of the three each file is, why it is here and
its content digest. `tests/test_provenance.py` fails if a file appears that no
record covers, if a record names a file that is not here, or if a file's
committed bytes no longer match its recorded digest.

## Licence

Apache-2.0. See `LICENSE`, and `NOTICE` for the MIT-licensed component.
