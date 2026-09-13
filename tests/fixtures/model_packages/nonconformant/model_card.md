---
model_id: demo_broken
version: 1.0.0
---

# Demo Broken

> Valid model card for the non-conformant fixture. The card is deliberately
> well-formed so the package's only error is the manifest's missing
> uncertainty.per_output coverage for output `z`.

## TL;DR

A fixture whose manifest omits UQ for one output, used to confirm the
pre-publish gate rejects an uncovered-output package.

## Intended use

- Exercising the pre-publish validation gate's rejection path.

## Out of scope

- Any real prediction task — this is a test fixture.

## Training data

- **Source:** synthetic; none.

## Architecture

- Placeholder; no real model behind this fixture.

## Performance

- Not applicable (fixture).

## Uncertainty quantification

- Intentionally incomplete in the manifest (output `z` is uncovered).

## Known failure modes

- By construction: missing per_output coverage for `z`.

## Version history

- **1.0.0** — initial fixture.
