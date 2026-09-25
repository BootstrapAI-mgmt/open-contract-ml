---
model_id: brake_disc_tmf_v1
version: 1.2.0
---

# Brake Disc TMF Life Surrogate

> Illustrative model card paired with `manifest.yaml` in this folder.
> Numbers below are demonstrative, not benchmark results — there is no
> corresponding `.exe` on disk.

## TL;DR

This model predicts the thermomechanical fatigue (TMF) life of a vented
brake disc subjected to repeated braking cycles. Given a peak
temperature, a cycle count, and a material designation, it returns the
expected number of cycles to crack initiation along with a 90%
predictive interval. It is intended for early-stage concept screening,
not as a replacement for full TMF simulation or physical testing.

## Intended use

- Comparing rotor geometries during the conceptual design phase
- Sweeping operating envelopes (peak temperature, cycle count) for a
  fixed material choice
- Producing a calibrated point estimate plus interval that flags
  designs warranting full FEA TMF analysis
- Generating consistent prediction reports across a design team

## Out of scope

- Non-vented disc geometries (training data is vented-only)
- Ceramic composite, aluminum metal-matrix, or any non-iron-based
  rotor materials
- Thermal soak durations exceeding 600 seconds (cyclic regime only)
- Safety-critical certification or homologation — this is a screening
  surrogate, not a certified analysis
- Predicting crack propagation past initiation (only initiation is
  modeled)

## Training data

- **Source:** Internal FEA TMF suite (ABAQUS + thermal-mechanical
  coupled solve), 2024-2026 program
- **Size:** 1,200 simulations, 4 input features
- **Time period:** Q1 2024 through Q4 2025
- **Known biases:**
  - GGG70 over-represented (~40% of samples) due to active program work
  - Peak temperatures below 300°C under-represented (only 8% of samples)
  - All training data uses the same vent topology family — novel vent
    geometries should be treated cautiously even when within input ranges
- **Distribution:**
  - peak_temp: 200°C to 850°C
  - cycle_count: 10 to 100,000
  - material: GG20, GG25, GGG70
  - vent_geometry: variants within Family-A topology only

## Architecture

Ensemble of 8 gradient-boosted decision-tree regressors (LightGBM) for
the life prediction, plus a separate 3-class gradient-boosted
classifier for the failure mode. Scalar inputs are standardized;
categorical material is one-hot encoded; the optional vent geometry is
processed by a small CNN that produces a 32-dimensional embedding
concatenated with the scalar features. The ensemble's life predictions
are passed through a split-conformal calibrator that produces the 90%
predictive intervals.

## Training configuration

Illustrative, like every number on this card: the package's entrypoint is
the deterministic stub `fake_model.py`, not a trained ensemble. A real card
states the objective (here it would be squared error on `log(life)` for the
regressors and multinomial log-loss for the failure-mode classifier), the
split (grouped by disc design family, so that two discs from one family
cannot land on both sides of it), the calibration split the conformal
intervals are fitted on, the stopping rule, and which hyperparameters were
tuned and how.

## Performance

| Slice                       | MAPE | n   |
|-----------------------------|------|-----|
| All test set                | 12%  | 240 |
| GG25 only                   | 9%   | 87  |
| GGG70 only                  | 11%  | 96  |
| GG20 only                   | 17%  | 57  |
| Peak temp <= 500°C          | 8%   | 92  |
| Peak temp 500-700°C         | 11%  | 88  |
| Peak temp > 700°C           | 18%  | 60  |
| Cycle count <= 1,000        | 14%  | 71  |
| Cycle count 1,000-10,000    | 10%  | 102 |
| Cycle count > 10,000        | 13%  | 67  |

## Uncertainty quantification

Predictive intervals are produced via split-conformal prediction
calibrated on a 30% holdout (n=240) drawn at random from the training
distribution. The nominal interval level is 90%; empirical coverage on
the holdout is 89%. Intervals widen monotonically with peak temperature
and with cycle count, reflecting under-representation of
high-temperature and high-cycle regimes in training data. Coverage is
miscalibrated (overconfident, ~83%) for the GG20 / high-temperature
intersection — flagged with a runtime warning when both conditions hold.

## Known failure modes

- **High-temperature overprediction (GG20):** model overpredicts life
  by 15-25% for GG20 above 750°C. Use the upper bound of the interval
  as a conservative estimate, or prefer full FEA in this regime.
- **Confidence collapse at low cycle counts:** for cycle_count < 50,
  the conformal interval collapses to a thin band that is not honest —
  the model has very few samples in this regime. Treat the point
  estimate as low-confidence regardless of the interval width.
- **Novel vent geometries:** the CNN embedding is well-behaved within
  Family-A topologies but extrapolates poorly to radial-only or
  serpentine vents. Add new vent geometries to training data before
  trusting predictions on them.

## Provenance

This example's manifest declares no `provenance` block. It is the worked
example for the manifest and card validators in `opencontractml.manifest`,
which do not require one, and it is deliberately not a contract package:
`open-contract-ml check` rejects it because its manifest has no
`spec_version`, `provenance` or `validation` entry and this card has no
`spec_version`. `examples/reference-package/` is the contract package whose
entrypoint, weights and dataset are all pinned by sha256.

## Version history

- **1.2.0** (2026-03-14) — Retrained on Q1 2026 dataset, added GGG70
  support, recalibrated conformal intervals.
- **1.1.0** (2025-11-02) — Switched from quantile regression to split
  conformal UQ to improve empirical coverage.
- **1.0.0** (2025-08-15) — Initial release; GG20 and GG25 only.

## References

- Mitchell, M. et al. (2019). *Model Cards for Model Reporting.* FAT*
  2019. https://arxiv.org/abs/1810.03677
- Angelopoulos, A. & Bates, S. (2021). *A Gentle Introduction to
  Conformal Prediction and Distribution-Free Uncertainty
  Quantification.* https://arxiv.org/abs/2107.07511
- (Internal) TMG-2026-Q1 validation report (Thermal Mech Group,
  March 2026)
