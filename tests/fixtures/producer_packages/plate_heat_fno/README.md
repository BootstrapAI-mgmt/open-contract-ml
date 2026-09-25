# plate_heat_fno

A fixture copy of the contract package `plate_heat_fno` (version 1.0.0,
Contract 1.0) as its producer emitted it: a Fourier Neural Operator field
surrogate for steady conduction in a convectively cooled plate, trained on a
64x64 grid.

Its validation report says `overall: FAIL`: `B1_monotonicity` and `B2_bounds`
are NOT_RUN and `B4_conservation` is a measured FAIL. The package is
nevertheless conformant -- conformance is about whether a package states its
evidence in the Contract's terms, not about whether the model passed -- and it
is kept here so that a change to the checker that would reject what a real
producer ships fails this repository's CI first. See `../README.md`.

## Provenance of this copy

Copied on 2026-09-25. Each file is listed with its digest in this directory,
which the manifest pins where the file is an artifact, and with what the copy
changed. The digests of the producer's originals are not recorded in this
fixture copy.

| File | This copy (sha256, bytes) | What changed |
|---|---|---|
| `manifest.yaml` | `60c49b687831df215439650f50ecc83c546c6dc622b4fee05730917894b49c0a`, 6762 | the package id renamed; comments and free-text values that referred to tools, repositories or contacts that do not ship with this repository reworded; `provenance.code.commit` and `provenance.dataset.sha256` set to all-zero values; both artifact pins re-pinned to this copy |
| `model_card.md` | `9a49918ac07bd9eb7fbe7ee7a0c32b2aeed1d9d98cc4d95792069482271f1af2`, 12124 | the producer's prose, with lines that referred to documents, tools, repositories or the producer's own repository reworded; `model_id` renamed; the Provenance table's artifact rows state this copy's digests, and its dataset and code rows read "not recorded in this fixture copy" |
| `validation_report.json` | `7241cce634a200711fae31e3ce74d41ca228060647677d0537ca7c80d1e607e4`, 9182 | `model_id` renamed with the package and `dataset_sha256` set to all zeros; `produced_by`, `source_gate_card`, the `B5_invariance` reason, the `B6_integrated_quantities` reason, `C4_deployment_readiness.declarations.retrain_cadence`, `C4_deployment_readiness.declarations.owner_escalation` reworded where they referred to files, tools or contacts that do not ship with this repository; one free-text classification key the Contract does not define removed; every status, metric and threshold unchanged |
| `predict.py` | `0780bca18917aa6fa0e0791fd9916bf9cece47419e81709e5f93880cdcbd6615`, 17103 | comments and docstrings reworded where they referred to tools, files, repositories or a component that do not ship with this repository; code, normalisation statistics and weights handling unchanged |
| `fno_weights.npz` | `654b3c9e5e7e791ad10b6aae0fbbbcbf4359ac427d95dcc001600c850821df40`, 230 | replaced by a text stub and re-pinned in the manifest; the checker hashes this file (rule M013) and never loads it, so the entrypoint cannot run from this copy |

Fields that identified the producer's repository or a contact (`owner.team`,
`owner.contact`, `provenance.code.repo`, and the report's escalation contact)
read "not recorded in this fixture copy". The checker requires them to be
present and non-empty, not to hold any particular value, so the copy is graded
exactly as the producer's package was.
`provenance.code.commit` and `provenance.dataset.sha256` are not recorded either: the
producer's values pointed at material that does not ship with this repository, so each
field holds an all-zero value of the form the checker requires (git's null object id
for the commit, 64 zeros for the digest), and the validation report's
`dataset_sha256` holds the same zeros so that rule V003 still binds the report to the
manifest.
