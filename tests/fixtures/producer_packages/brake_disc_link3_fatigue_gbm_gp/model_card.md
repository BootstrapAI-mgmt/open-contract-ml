---
model_id: brake_disc_link3_fatigue_gbm_gp
version: 1.0.0
spec_version: "1.0"
---

# Brake-Disc Chain Link 3 -- TMF Life (GBM primary + GP UQ companion)

> Fixture copy of a producer's Contract v1 model card. The front-matter and the
> sequence of H2 sections are the producer's, exactly; the prose under each heading
> is a neutral summary written for this repository, because the producer's prose
> cites documents that do not ship with it. See README.md in this directory.

## TL;DR

Contract fixture for link 3 of the brake-disc thermomechanical-fatigue chain: the
fatigue life of the rotor's hot spots, from a gradient-boosted model with a Gaussian-process
companion for the uncertainty. It fixes the I/O signature, the architecture family and the
training recipe so that a build can be commissioned against it. No model has been trained,
and the validation rollup is FAIL.

## Intended use

1. **As a contract.** A build team commissioning the link-3 surrogate takes the I/O
   signature, the architecture family and the training recipe from this package, and owes
   the measurements its validation report marks NOT_RUN.
2. **As a conformance fixture.** A registry, dispatcher or checker can validate against a
   package that is well formed and whose model is openly unvalidated.

## Out of scope

Every engineering decision. No model has been trained against this contract and nothing in
this package has been measured; any output of this family is advisory decision-support at
best, and a licensed engineer must remain in the loop.

## Training data

No corpus has been generated. The producer declared the digest of its dataset-card
contract for this link, a document that does not ship with this repository; this copy does
not record it. The manifest and the report carry the same all-zero placeholder, so the
report / manifest binding (rule V003) still holds.

## Architecture

A gradient-boosted tree ensemble (GBM) gives the production point estimate of the minimum
log10 life across the hot spots, from the link-2 plastic strains, the material class and the
duty-cycle count; a Gaussian-process (GP) companion gives the posterior used for the
5th-percentile life `p5_log10_n_f_min`, the reliability deliverable.

## Training configuration

No fit has been run, so nothing here is tuned. The recipe this contract fixes fits the GBM
and the GP on the same rows, with an aleatoric scatter floor on the GP from the fatigue
data's own scatter.

## Performance

No metric has been measured. Fourteen of the fifteen ladder keys in `validation_report.json`
are NOT_RUN or NOT_APPLICABLE; the one PASS is `C3_provenance_integrity`, which re-hashes the
entrypoint. `overall` is FAIL by recomputation, which is the correct and intended verdict: a
NOT_RUN check blocks the rollup (spec section 5.3).

## Uncertainty quantification

Contracted, not calibrated: a Gaussian-process posterior predictive interval with an
aleatoric scatter floor, cross-checked against the GBM ensemble spread, at a nominal level
of 0.95, for both declared outputs. `A3_uq_calibration` is NOT_RUN, so no empirical coverage
exists yet.

## Known failure modes

- **Illustrative values read as measurements.** Tree depth, kernel and scatter floor are
  defaults, not results.
- **A mean reported without its scatter.** `log10_n_f_min` is the eye-catching number;
  `p5_log10_n_f_min` is the one that matters.
- **Long-life extrapolation.** Beyond the coupon data there is nothing to interpolate, and a
  tree ensemble is flat, confident and silent outside its training hull.
- **Out-of-distribution flags dropped between links**, and **chain error compounding** over
  three surrogate hops.

## Provenance

The entrypoint `predict.py` is pinned by sha256 and byte count in the manifest and re-verified
by `open-contract-ml check` (rule M013); it is a runnable, hashed refusal, not a model. The
dataset sha256 is not recorded in this fixture copy (see Training data). This card and the
validation report are not self-hashed: both are written after the artifacts they describe,
and are bound instead by the model_id / version / dataset_sha256 triple (rules C002, V002,
V003).

## Version history

- **1.0.0** -- the producer's first Contract v1 issue of this card, restructured into the
  eleven required sections from an earlier nine-section worked-instance card.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| GBM only | No calibrated uncertainty and no 5th-percentile life |
| GP only | Scales poorly with rows, and is slower at inference than the GBM |
| MLP regressor | Weaker inductive bias for tabular data than a GBM |
| Conformal wrapper around the GBM | Coverage without an epistemic / aleatoric split; useful as a calibration check |
| Bayesian neural network | Heavyweight for tabular data of this size |

## Disclosure

| Element | Status |
|---|---|
| Every number in the brake-disc worked instance | **Illustrative**, not measured |
| The I/O signature, architecture family and training recipe | **Contracted** -- fixed so a build can be commissioned against them |
| The validation ladder | **Owed** -- every check that needs a trained model is NOT_RUN |
| Fitness for an engineering decision | **Not claimed** -- decision support only, with a licensed engineer in the loop |

## Open questions

- Which corpus, solver and training budget will the commissioned build use? None is chosen;
  the ladder stays NOT_RUN until a training run exists.

## References

- `docs/spec/CONTRACT-v1.md` in this repository -- the contract this card conforms to.
