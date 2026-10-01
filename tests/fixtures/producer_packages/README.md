# Producer fixture packages

Each directory here is a contract package as a real producer emitted it, copied
in so that the checker is tested against what producers actually ship and not
only against packages written for the test suite. A change to
`opencontractml.verify` that would reject one of these fails CI here, before it
reaches the producer that emits packages of that shape. The directories are
named by package id.

| Package id | What it is | Report verdict |
|---|---|---|
| `brake_disc_link1_thermal_fno` | brake-disc thermomechanical-fatigue chain, link 1: transient thermal, FNO | FAIL: untrained, Tier A NOT_RUN |
| `brake_disc_link2_thermo_mech_rom` | brake-disc chain, link 2: plastic strain, autoencoder + Neural-ODE | FAIL: untrained, Tier A NOT_RUN |
| `brake_disc_link3_fatigue_gbm_gp` | brake-disc chain, link 3: fatigue life, GBM + GP | FAIL: untrained, Tier A NOT_RUN |
| `plate_heat_fno` | steady plate conduction, FNO field surrogate, 64x64 grid | FAIL: B1 and B2 NOT_RUN, B4 measured FAIL |

Every one of them reports `overall: FAIL`. That is the point: a conformance
checker has to accept a package that tells the truth about an unvalidated model,
and the three brake-disc packages are the reason `V010` and `V011` read only a
check that ran -- each reports its whole Tier A as NOT_RUN.

`plate_heat_fno` is conformant. The three brake-disc manifests are not, since the
checker applies the contract-v1 manifest schema (rule `M018`), and their copies
are kept as they are because the fix is their producer's:

| Package id | `M018` findings |
|---|---|
| `brake_disc_link1_thermal_fno` | `uncertainty.form` is `ensemble_spread`, which is not one of the schema's forms; `lineage` has no `metrics`; `lineage.training_date` is null, not a string |
| `brake_disc_link2_thermo_mech_rom` | the same three as link 1 |
| `brake_disc_link3_fatigue_gbm_gp` | input `eps_p_eq_hotspots` declares `file_kind: json`, which is not one of the schema's file kinds; `lineage` has no `metrics`; `lineage.training_date` is null |

The package-v1 manifest schema a consumer validates against has the same
constraints. `known-findings.json` records each finding with its rule, location
and message, and why it is the producer's to fix. A JSON input file has no file
kind in either schema, so link 3's first finding needs the producer to declare a
listed kind or an amendment that adds one.

## What CI runs

- `tests/test_producer_fixtures.py`, part of the suite: the pinned set is
  complete, each package passes `opencontractml.verify` or produces exactly the
  findings `known-findings.json` records for it, and each still reports its
  honest FAIL.
- The `package` job in `.github/workflows/ci.yml` checks every directory here
  with the installed wheel, from outside the checkout
  (`open-contract-ml check <package> --json <record>`), and holds each record to
  the same comparison.

`known-findings.json` is a ratchet, not an amnesty: a recorded finding that
stops firing fails both until its entry is deleted, and a finding that is not
recorded fails both at once.

## How a copy differs from what its producer shipped

Every validation status, metric and threshold is the producer's, and so is each
card's sequence of H2 sections. Values the checker only compares with each
other were changed together, so every comparison comes out as it did: the
package id (the directory, the manifest `id`, the card's and the report's
`model_id`) and the dataset digest (the manifest's and the report's). What
differs, file by file, is listed in each package's README:

- the package ids and their labels are names chosen for this repository;
- free text that referred to the producer's own files, tools or contacts, none of
  which ship with this repository, is reworded, and fields that identified the
  producer's repository or a contact read "not recorded in this fixture copy";
- `provenance.code.commit` and `provenance.dataset.sha256` pointed at material
  that does not ship with this repository, so each holds an all-zero value of
  the form the checker requires (rules M014 and M015), and each report's
  `dataset_sha256` holds the same zeros (rule V003);
- each validation report loses one free-text classification key that the
  Contract does not define (spec section 7: unknown keys are ignored);
- the three brake-disc model cards keep their structure and have rewritten prose;
- the plate FNO's 9.0 MiB weights file is a small text stub, re-pinned in its
  manifest; the checker never loads weights, so nothing it grades changes;
- every edited artifact is re-pinned (`sha256` and `bytes`) in its manifest.

`PROVENANCE.yaml` records every copied file in its `modified_copies` class.

## Refreshing a copy

Take the producer's current package, apply the same changes, re-pin the edited
artifacts, update the digests in the package README and in `PROVENANCE.yaml`,
and run the suite. If the producer's package no longer passes, that is the
finding this directory exists to surface: fix the producer or the checker, not
the fixture. A finding whose fix is the producer's is recorded in
`known-findings.json` until the producer ships the fix and the copy is
refreshed; its entry is then deleted.
