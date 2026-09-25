---
model_id: brake_disc_link2_thermo_mech_rom
version: 1.0.0
spec_version: "1.0"
---

# Brake-Disc Chain Link 2 -- Thermo-Mechanical Plastic Strain (Autoencoder + Neural-ODE ROM)

> Fixture copy of a producer's Contract v1 model card. The front-matter and the
> sequence of H2 sections are the producer's, exactly; the prose under each heading
> is a neutral summary written for this repository, because the producer's prose
> cites documents that do not ship with it. See README.md in this directory.

## TL;DR

Contract fixture for link 2 of the brake-disc thermomechanical-fatigue chain: the
plastic strain a descent leaves in the rotor, from an autoencoder with Neural-ODE latent
dynamics (a reduced-order model). It fixes the I/O signature, the architecture family and
the training recipe so that a build can be commissioned against it. No model has been
trained, and the validation rollup is FAIL.

## Intended use

1. **As a contract.** A build team commissioning the link-2 surrogate takes the I/O
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

An autoencoder compresses the thermo-mechanical state into a latent space and a Neural ODE
integrates the latent dynamics along the descent, driven by the link-1 temperature history,
the material class and the coupling class. The manifest declares only the reduced scalars
Contract v1.0 can type: the peak equivalent plastic strain `peak_eps_p_eq_value` and the
ensemble's `latent_disagreement`.

## Training configuration

No fit has been run, so nothing here is tuned. The recipe this contract fixes trains the
autoencoder and the latent dynamics jointly, with independently seeded ensemble members
providing the disagreement signal the manifest declares as an output.

## Performance

No metric has been measured. Fourteen of the fifteen ladder keys in `validation_report.json`
are NOT_RUN or NOT_APPLICABLE; the one PASS is `C3_provenance_integrity`, which re-hashes the
entrypoint. `overall` is FAIL by recomputation, which is the correct and intended verdict: a
NOT_RUN check blocks the rollup (spec section 5.3).

## Uncertainty quantification

Contracted, not calibrated: latent-space ensemble disagreement over independently seeded
autoencoder / Neural-ODE members, at a nominal interval level of 0.95, for both declared
outputs. `A3_uq_calibration` is NOT_RUN, so no empirical coverage exists yet.

## Known failure modes

- **Illustrative values read as measurements.** Latent size, solver tolerances and training
  budget are defaults, not results.
- **Symmetric-tensor convention broken.** A six-component strain tensor that is re-ordered
  loses the symmetry the plasticity model assumes; B5 is the check that would catch it.
- **Latent drift over long integrations.** Neural-ODE error accumulates along the descent;
  `latent_disagreement` is the intended tell, and its calibration is NOT_RUN.
- **Coupling class silently mismatched,** and **out-of-distribution flags dropped between
  links**: both are contracted and neither is built.
- **Chain error compounding.** Two surrogate hops precede the fatigue model.

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
| POD with per-mode regression | A linear modal basis struggles with strongly coupled nonlinear dynamics; kept as a low-fidelity baseline |
| DeepONet | Time-resolved rollout favours continuous-time latent integration |
| Direct graph-network regression | Loses the latent slow-manifold structure that makes inference cheap |
| Physics-informed Neural ODE by default | Kept as an ablation; residual losses struggle with multi-scale coupling |

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
