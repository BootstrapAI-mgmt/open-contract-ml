---
model_id: demo_surrogate
version: 1.0.0
---

# Demo Surrogate

> Minimal conformant model card fixture for the TC-GUI18 pre-publish gate.

## TL;DR

Predicts a demo scalar `y` from one input `x`, returning a point estimate
plus a 90% predictive interval. Exists only as a validation fixture.

## Intended use

- Exercising the pre-publish validation gate on a known-good package.

## Out of scope

- Any real prediction task — this is a test fixture, not a trained model.

## Training data

- **Source:** synthetic; none.

## Architecture

- Placeholder; no real model behind this fixture.

## Performance

- Not applicable (fixture).

## Uncertainty quantification

- `predictive_interval` at a nominal 90% level via `y_lower` / `y_upper`.

## Known failure modes

- None catalogued — fixture only.

## Version history

- **1.0.0** — initial fixture.
