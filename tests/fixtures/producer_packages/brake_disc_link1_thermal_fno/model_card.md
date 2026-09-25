---
model_id: brake_disc_link1_thermal_fno
version: 1.0.0
spec_version: "1.0"
---

# Brake-Disc Chain Link 1 -- Transient Thermal (FNO)

> Fixture copy of a producer's Contract v1 model card. The front-matter and the
> sequence of H2 sections are the producer's, exactly; the prose under each heading
> is a neutral summary written for this repository, because the producer's prose
> cites documents that do not ship with it. See README.md in this directory.

## TL;DR

Contract fixture for link 1 of the brake-disc thermomechanical-fatigue chain: the
transient temperature of a brake disc over a descent, from a Fourier Neural Operator. It
fixes the I/O signature, the architecture family and the training recipe so that a build
can be commissioned against it. No model has been trained, and the validation rollup is
FAIL.

## Intended use

1. **As a contract.** A build team commissioning the link-1 surrogate takes the I/O
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

A Fourier Neural Operator (FNO) from the disc design, the descent profile and the material
class to the transient temperature field of the rotor. Its spectral-convolution layers are
FFT based, so the operator accepts grid resolutions other than the training one; that
discretisation invariance is the property the family was chosen for, and B5 is the check
that would measure it. The manifest declares only the reduced scalars Contract v1.0 can
type: the peak rotor temperature `t_max_K` and the time of the peak `t_max_time_s`.

## Training configuration

No fit has been run, so nothing here is tuned. The recipe this contract fixes pairs a data
loss with a heat-equation residual on the predicted field, which is also the intended B3
check; a five-member ensemble of independently seeded FNOs provides the uncertainty band.

## Performance

No metric has been measured. Fourteen of the fifteen ladder keys in `validation_report.json`
are NOT_RUN or NOT_APPLICABLE; the one PASS is `C3_provenance_integrity`, which re-hashes the
entrypoint. `overall` is FAIL by recomputation, which is the correct and intended verdict: a
NOT_RUN check blocks the rollup (spec section 5.3).

## Uncertainty quantification

Contracted, not calibrated: a deep ensemble of N=5 independently seeded FNO members, at a
nominal interval level of 0.95, for both declared outputs. `A3_uq_calibration` is NOT_RUN,
so no empirical coverage exists yet.

## Known failure modes

- **Illustrative values read as measurements.** Every number is a default, not a result.
- **The field is hidden behind two scalars.** The full temperature tensor cannot be typed
  under Contract v1.0 (spec section 10, limitation 3), so `B4_conservation` cannot be formed
  for this package even though thermal energy is conserved by the physics.
- **Stiff multi-scale regime.** Fast surface heating couples to slow bulk diffusion, which is
  where residual-loss training is known to struggle.
- **Chain error compounding.** Link 1 feeds link 2 feeds link 3, so any chain-level number
  must be reported with its per-link breakdown.

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
| 3-D U-Net | Binds training and inference to one grid, and so loses discretisation invariance |
| PINN with a residual loss only | Descent heating is a stiff multi-scale problem, the regime residual-only training struggles with |

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
