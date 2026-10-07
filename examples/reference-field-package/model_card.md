---
model_id: contract_reference_plate_field_v1
version: 1.0.0
spec_version: "1.1"
---

# Contract Reference -- Plate Temperature-Rise Field

> The worked field package for Contract 1.1. Its eleven H2 sections are the
> required set (spec section 4.2). examples/build_reference_field_package.py
> computed every number below, and each appears identically in
> `validation_report.json`.

## TL;DR

Predicts the steady temperature rise over a thin rectangular plate, at each node
of a 17 x 17 grid, from the heating power and the plate's length and
width, together with the peak rise at the plate's centre. The field and the two
edges of its 90 percent split-conformal band come back as VTK XML PolyData
files the entrypoint writes; the peak and its band come back as numbers in the
frame. The package exists so that Contract 1.1's field declaration, its artifact
reference and its `stdio_json` frame have a real package to be checked against.
It is a closed-form expression with one fitted coefficient, fitted to a
synthetic corpus drawn from that same expression, and it is not an engineering
surrogate.

## Intended use

- Exercising a consumer's handling of field outputs -- reading `outputs[].field`,
  dispatching the entrypoint, verifying every artifact reference against the file
  it names, drawing the payload -- against a package known to be conformant.
- Showing, in one package, a field output's declaration, a band carried by
  `*_artifact` references, a scalar carried in the frame, a licence block and a
  report measured on a field model.
- Comparing against when a field model is brought onto the Contract: what that
  model must declare in addition is the difference between its package and this one.

## Out of scope

- Any engineering or design decision. The corpus is synthetic, and nothing ties
  the expression to a measured plate.
- Inputs beyond the declared ranges: the entrypoint answers them with an
  `OUT_OF_RANGE` error frame instead of a prediction.
- Any other plate, edge condition or heating pattern. The model knows one plate --
  conductivity 50.0 W/(m K), thickness 0.004 m, every edge held at the reference
  temperature -- heated by the distribution Architecture states.
- Reading the band as a map of nodal uncertainty. One half-width, a fixed fraction
  of the predicted peak, is applied at every node.

## Training data

- **Source:** a synthetic corpus that the builder generates from the expression
  below with amplitude 3, seeded (`random.Random(0)`). Every
  node of every design carries independent noise whose standard deviation is
  1 percent of that design's peak rise (a sum of twelve uniform draws,
  less six, scaled).
- **Size:** 1000 designs of 289 nodes each; 400 train /
  250 calibration / 250 interior test / 100 corner (extrapolation).
- **Distribution:** `power_W` uniform on [5.0, 50.0]; `length_m` and
  `width_m` uniform on [0.05, 0.2], each drawn independently.
- **Split policy:** the corner split holds the 100 designs of highest power,
  every design at or above 45.3817 W. The rest are permuted
  (`random.Random(1)`) into the train, calibration and interior-test
  splits, so the four splits share no design.
- **Known bias:** the corpus follows the very expression the model fits, so the
  accuracy checks mostly measure the noise. The card says so here rather than
  leaving it to be discovered, and it is why C4 claims no validation anchor.

## Architecture

The predicted rise at node (i, j), where x = i L / 16 and y = j W / 16, is

`c * P * L * W / (k * t * (L^2 + W^2)) * (x/L) * (1 - x/L) * (y/W) * (1 - y/W)`

with P the heating power (`power_W`), L and W the plate's length and width, k and
t its conductivity and thickness, and c the one fitted coefficient. With c = 3 the
expression is the exact steady solution of k t (d2T/dx2 + d2T/dy2) + q = 0 with
zero rise on every edge, for the heating density
q(x, y) = 6 P (x (L - x) + y (W - y)) / (L W (L^2 + W^2)), which integrates to P
over the plate. The peak sits at the centre node and equals
c P L W / (16 k t (L^2 + W^2)). The fitted c is 3.00007. `model_weights.json`
holds it with the plate's two properties, the node count, the two band
half-widths and the declared input ranges, and that is the whole model.

## Training configuration

| Element | Value |
|---|---|
| Estimator | least squares for the one coefficient, in closed form: the sum of basis times target over the sum of basis squared, on every node of the training designs |
| Iterations | none |
| Regularisation | none |
| Seeds | corpus `random.Random(0)`; split permutation `random.Random(1)` |
| Rounding | the coefficient and both half-widths to 6 significant digits, as written to `model_weights.json` |
| Measured against | the rounded values the entrypoint loads, not the unrounded fit |
| Calibration | split conformal at level 0.9 on the 250-design calibration split |
| Arithmetic | addition, subtraction, multiplication, division and square roots only, so no number depends on the platform's maths library |

## Performance

Measured against each design's corpus field, over all 289 nodes, with the
shipped coefficient.

| Slice | n | Mean relative L2 | Worst relative L2 | RMSE (K) |
|---|---|---|---|---|
| Interior test | 250 | 0.0199539 | 0.0218028 | 0.115308 |
| Corner (extrapolation) | 100 | 0.0198589 | 0.0218959 | 0.200245 |

The corner's mean relative L2 error is 0.995236 times the interior
test's, against a cap of 3.0 (A2). The model's RMSE is
0.045152 times that of the training mean field, taken node by node,
against a cap of 0.5 (A4). The physics checks, on the same predictions:
the relative residual of the conduction equation is at most 2.33333e-05 (B3), the
worst relative heat imbalance over the whole plate is 1.16665e-05 (B4), and on a
twice-finer grid the shared nodes differ by at most 0.0 K (B5).

## Uncertainty quantification

Split-conformal predictive intervals at a nominal level of 90 percent,
fitted on the 250-design calibration split and never on training or test
designs. For the field, each design's score is its largest absolute nodal
residual divided by its predicted peak, and the 226th smallest of the 250
calibration scores is the half-width: 0.0344997 of the predicted peak, applied
at every node, so that the band is meant to hold every node of a design at once. For the peak, the score is the
absolute residual at the centre node over the predicted peak, and the half-width
is 0.0167865 of it.

On the 250-design interior test split the field band holds every node of
90.4 percent of designs (empirical coverage 0.904) and the
peak band holds the centre value of 89.2 percent (0.892),
both against the accepted band [0.85, 0.96]. Coverage on the corner split
is neither measured nor claimed.

## Known failure modes

- **Flattering corpus.** The corpus and the model share their functional form.
  Real temperature fields will not follow it, and the accuracy above says nothing
  about a real plate.
- **The physics checks pass by construction.** With any coefficient the field is
  zero on the edges and is exactly a product of two parabolas, so the discrete
  Laplacian and the edge fluxes are exact, and B3 and B4 measure only how far the
  fitted c lies from 3. B5 passes because each node's value comes from the
  expression alone, so a finer grid adds nodes and never moves the ones already there.
- **The band edges are not physical.** The lower edge goes below zero near the
  plate's edges, where the predicted rise is zero, because one half-width is used
  at every node.
- **Inputs outside the ranges are refused, not extrapolated.** A consumer that
  ignores the error frame will find no outputs.
- **The scalar band is calibrated on one node.** It covers the centre value
  only, not the largest value of a noisy field.

## Provenance

| Item | Value |
|---|---|
| Entrypoint | `./predict.py` sha256 `704966495bedb1b8209e894acce54c2f789312ce28e4532db988ba66cb88d56c` (9697 bytes) |
| Weights | `./model_weights.json` sha256 `4c4d6467c33ce32557e5793299cd454fbf978d3ff19c3e3eb05113f08bdb8e32` (438 bytes) |
| Dataset | sha256 `3e6c3408c1cdd7b739680b53c212f09976dbf1dfbfa9310c12856757807345e6` (1000 designs, not shipped) |
| Code | `https://github.com/BootstrapAI-mgmt/open-contract-ml` at commit `8dfa2611fba92a67c3077f0b2e2b5d531eb56ad3`, the tree the builder ran on |
| Environment | Python 3.11.15, standard library only |
| Licences | the model and the weights: Apache-2.0, the licence of this repository; the training data: none asserted, because the corpus is not shipped |

Every `python -m opencontractml.verify check` re-hashes both artifacts (rule
M013), as the builder did when it measured C3, so an entrypoint or weights file
edited after the build fails the check. Neither this card nor the validation
report is hashed, since each was written after the artifacts it describes; the
package's id, version and dataset digest tie them to it instead (rules C002, V002,
V003).
Each run's payloads are pinned too, but by the run: every reference carries the
sha256 and length of the file the entrypoint wrote (section 12 of the Contract).

## Version history

- **1.0.0** (2026-10-07) -- first issue, built as the worked field
  instance of Contract 1.1. The coefficient, the half-widths, every metric and
  every digest come from the builder; none was typed by hand.

## Disclosure

| Element | Status |
|---|---|
| The package's shape: the field block, the artifact references, the frame, the sections, the ladder keys | **Normative** -- this package is a reference instance |
| The expression, the corpus and every metric | **Real but illustrative** -- measured and reproducible, and of no engineering significance |
| Threshold values | **Chosen for the fixture** -- fixed before the first measurement; the Contract sets no physics bars |

## References

- `docs/spec/CONTRACT-v1.md` -- the specification this package instantiates.
- `examples/build_reference_field_package.py` -- the builder that wrote it.
- `src/opencontractml/verify.py` -- the checker that grades it.
