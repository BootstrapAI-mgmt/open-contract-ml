---
model_id: REPLACE_WITH_MODEL_ID
version: 0.0.0
---

# REPLACE WITH MODEL NAME

> Replace this template's placeholder content with the model's real
> content. The nine H2 sections below are **mandatory** — the registry
> loader rejects model cards missing any of them. The `## References`
> section at the bottom is optional but encouraged.

## TL;DR

One paragraph explaining what this model does, in plain language —
clear both to a second-year CAE engineer and to a non-CAE/ML colleague
who knows the analysis they need but not the modeling. No jargon, no
equations. Three or four sentences maximum. State the input it expects,
the prediction it produces, and the regime it's valid in. (Mirror this
plain-language framing in the manifest's `purpose`, `when_to_use`, and
`analysis_type` — those drive non-expert catalog discovery.)

## Intended use

- Specific use case 1 — actionable enough that a reader knows when to reach for this model
- Specific use case 2
- Specific use case 3

## Out of scope

- Physical regime where the model is invalid (e.g., "not for ceramic composite materials")
- Deployment context where it shouldn't be used (e.g., "not for safety-critical certification")
- Input combinations the model was not trained on (link to the input ranges in the manifest)

## Training data

- **Source:** where the data came from (simulation suite, lab measurements, customer reports, etc.)
- **Size:** number of samples, number of features
- **Time period:** when the data was collected
- **Known biases:** what's underrepresented (geometries, materials, operating regimes)
- **Distribution:** ranges per input — match the `inputs[].range` values in the manifest

## Architecture

Plain prose. Describe the model family ("gradient-boosted decision
trees ensemble", "PINN with Burgers PDE residual", "GNN over mesh"),
the key hyperparameters at a high level, and how predictions are
assembled (e.g., "8 LightGBM regressors averaged, then conformal
calibrator applied"). No equations. The audience is a CAE engineer
who needs to understand the model well enough to trust it, not a
peer reviewer.

## Performance

| Slice                       | Metric | Value | n   |
|-----------------------------|--------|-------|-----|
| All test set                | —      | —     | —   |
| Subset A (e.g., material X) | —      | —     | —   |
| Subset B (e.g., regime Y)   | —      | —     | —   |

Add as many sliced rows as relevant. Sliced performance is more
honest than a single overall number; CAE engineers care which regimes
the model is reliable in.

## Uncertainty quantification

Explain how the intervals / distributions / probabilities are
produced (e.g., "split conformal prediction calibrated on a 30%
holdout"). State what they mean — central interval, predictive
interval, one-sigma ensemble band, etc. State the empirical coverage
on holdout, the nominal level, and where the UQ is known to be
miscalibrated.

## Known failure modes

- Specific regime where the model is known to be wrong, with magnitude (e.g., "overpredicts life by 15-25% for material X above 750°C")
- Input combinations that produce unreliable UQ (e.g., "intervals collapse to zero width when cycle_count < 50 due to undertraining")
- Out-of-distribution behavior (e.g., "predictions extrapolate poorly to vent geometries outside Family-A topology")

## Version history

- **0.0.0** (YYYY-MM-DD) — Initial release.

## References

- (Optional section.) External references — papers, standards, related model cards
- Internal references — validation reports, training data documentation
