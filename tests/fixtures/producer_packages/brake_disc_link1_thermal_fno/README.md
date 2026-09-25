# brake_disc_link1_thermal_fno

A fixture copy of the contract package `brake_disc_link1_thermal_fno` (version 1.0.0,
Contract 1.0) as its producer emitted it: link 1 (transient thermal, FNO) of the brake-disc thermomechanical-fatigue worked instance.

Its validation report says `overall: FAIL`: no model has been trained, so every
check that needs one is NOT_RUN. The package is nevertheless conformant --
conformance is about whether a package states its evidence in the Contract's
terms, not about whether the model passed -- and it is kept here so that a
change to the checker that would reject what a real producer ships fails this
repository's CI first. See `../README.md`.

## Provenance of this copy

Copied on 2026-09-25. Each file is listed with its digest in this directory,
which the manifest pins where the file is an artifact, and with what the copy
changed. The digests of the producer's originals are not recorded in this
fixture copy.

| File | This copy (sha256, bytes) | What changed |
|---|---|---|
| `manifest.yaml` | `32446a4af2425bd6a4fe896813452997e1838cbfb8a453f0ac9276ae21bdc548`, 4900 | the package id and its labels renamed; comments and free-text values that referred to files, repositories or contacts that do not ship with this repository reworded; `provenance.code.commit` and `provenance.dataset.sha256` set to all-zero values; the entrypoint's `sha256` and `bytes` re-pinned to this copy |
| `model_card.md` | `d436a5c7c00e024d4ecaa584cf44b356f6f052f9fbed6a6e6eb0c3b1292dd1e9`, 5643 | the sequence of H2 sections kept exactly and the front-matter kept but for the renamed `model_id`; the prose under each heading rewritten, because the producer's prose cites documents that do not ship with this repository |
| `validation_report.json` | `2337b901c3f5153bd279fde3c4df69a959ab697b8d525dbef00b6f772555938c`, 5057 | `model_id` renamed with the package and `dataset_sha256` set to all zeros; `produced_by`, the `B4_conservation` reason, the `C1_ood_guard` reason reworded where they referred to files, tools or contacts that do not ship with this repository; one free-text classification key the Contract does not define removed; every status, metric and threshold unchanged |
| `predict.py` | `f8f30088d31330b1b1133834393ffe2e0d9ddfa7a9e97e6540d4834fae7f7a0c`, 2541 | the model id renamed with the package; a docstring line and the refusal message reworded where they cited documents that do not ship with this repository; the logic unchanged |

Fields that identified the producer's repository or a contact (`owner.team`,
`owner.contact`, `provenance.code.repo`) read "not recorded in this fixture
copy". The checker requires them to be present and non-empty, not to hold any
particular value, so the copy is graded exactly as the producer's package was.
`provenance.code.commit` and `provenance.dataset.sha256` are not recorded either: the
producer's values pointed at material that does not ship with this repository, so each
field holds an all-zero value of the form the checker requires (git's null object id
for the commit, 64 zeros for the digest), and the validation report's
`dataset_sha256` holds the same zeros so that rule V003 still binds the report to the
manifest.
