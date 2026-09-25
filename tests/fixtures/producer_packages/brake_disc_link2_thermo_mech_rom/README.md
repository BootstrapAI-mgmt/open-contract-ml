# brake_disc_link2_thermo_mech_rom

A fixture copy of the contract package `brake_disc_link2_thermo_mech_rom` (version 1.0.0,
Contract 1.0) as its producer emitted it: link 2 (thermo-mechanical plastic strain, autoencoder + Neural-ODE reduced-order model) of the brake-disc thermomechanical-fatigue worked instance.

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
| `manifest.yaml` | `d04fefd6a1884626a537a2705c4a82f83267540136ab70673a2d9dd90ed0a722`, 5134 | the package id and its labels renamed; comments and free-text values that referred to files, repositories or contacts that do not ship with this repository reworded; `provenance.code.commit` and `provenance.dataset.sha256` set to all-zero values; the entrypoint's `sha256` and `bytes` re-pinned to this copy |
| `model_card.md` | `e2914d3b6a640f7a0adb2d6648ca9b1f91035e11b32fdaae905cddef7d49fc77`, 5881 | the sequence of H2 sections kept exactly and the front-matter kept but for the renamed `model_id`; the prose under each heading rewritten, because the producer's prose cites documents that do not ship with this repository |
| `validation_report.json` | `0b9b077b0847ae1ec24913e1a895f9dc26eb76b88cf30f66d74ff26b35976cdd`, 5066 | `model_id` renamed with the package and `dataset_sha256` set to all zeros; `produced_by`, the `B4_conservation` reason, the `B5_invariance` reason, the `C1_ood_guard` reason reworded where they referred to files, tools or contacts that do not ship with this repository; one free-text classification key the Contract does not define removed; every status, metric and threshold unchanged |
| `predict.py` | `ab18cfd3a80e8de4117270dfd27f2b849b71f794420dc4e79b3d156cca47d93e`, 2568 | the model id renamed with the package; a docstring line and the refusal message reworded where they cited documents that do not ship with this repository; the logic unchanged |

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
