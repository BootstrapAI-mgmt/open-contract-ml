# TASK-8-1106 — Predicting Injection-Molding Warpage, Spring-back, and Residual Stress

### A step-by-step worked example for CAE engineers — no ML background needed

> Part of the CAE-ML step-by-step examples arc — project task 8
> (`EXAMPLES-ARC-SCOPING.md`). This is example **`TASK-8-1106`**: the
> ID encodes its slide-9 grid cell — `n=1` (parametric-input row),
> `m=1` (scalar-output column), example `06` — i.e. Bucket B1, the
> tabular surrogate. It is the **sixth B1 example** in the arc (after
> `TASK-8-1101` fatigue-life, `TASK-8-1102` drag-lift, `TASK-8-1103`
> peak-stress, `TASK-8-1104` peak-temperature, and `TASK-8-1105` motor
> torque/efficiency), and the first that lives in the manufacturing-
> process (injection-molding) domain — closing the iteration-0 domain
> spread.
>
> You will train a model and use it. You will **not** write code or
> make any machine-learning decisions. Everything runs by
> double-clicking a file.

---

## 1. What this example does

Running an injection-molding process simulation — a full
fill → pack → cool → warp solve to get the warpage, spring-back, and
residual stress of a molded part for one process recipe — typically
takes minutes to hours per run, depending on mesh density and whether
the fibre-orientation solve is included. Fast enough for a single check,
but slow enough that exploring the process window — sweeping melt and
mold temperatures, packing pressures, cooling times, and part-design
choices to pull warpage into tolerance — becomes the bottleneck on how
broadly you can search. When you are tuning a tool to hit a flatness
spec, running the full simulation for every candidate recipe is where
the time goes.

This example builds a **surrogate**: a fast model that has learned, from
a batch of injection-molding simulation runs you have *already* done, the
relationship between a part's input vector (process parameters + part
design) and the three headline as-molded-quality responses (peak
warpage, spring-back, peak residual stress). Once trained, it returns all
three numbers in a fraction of a second, so you can screen hundreds of
process-and-design candidates before committing solver time to the
handful that matter.

**Where this sits in the taxonomy.** The model takes a *row of numbers*
(eight process / part-design parameters) and returns a *short vector of
numbers* (three quality scalars). On the BRIDGE-A slide-9 grid that is
the top-left cell — *parametric input → scalar(s) output* — which is
**Bucket B1, the tabular surrogate**. B1 is the simplest and most
production-proven corner of the grid, which is why this example uses it.
This is also where deployed injection-molding ML actually lives: per
TASK-1 §6 A.10.2, the headline as-molded-quality scalars (warpage,
shrinkage, peak-stress, weld-line strength) are the production-mature
tabular-surrogate target, regressed from the process-and-design
parameter vector — the deployed industrial pattern at injection-molded-
component design organisations. (The full fibre-orientation-tensor
*field* is a different, research-active flavor — a different bucket and a
different architecture.) Catalog reference: analysis **A.10.2**
(Manufacturing, Injection molding) in
`tasks/TASK-1-cae-analysis-catalog.md`. Arc inventory record:
`EXAMPLES-ARC-SCOPING.md` §4 (the sixth B1 entry).

**What's in this example.** Like TASK-8-1105 (motor torque/efficiency),
this is a **three-target** surrogate: it predicts warpage, spring-back,
and residual stress from one input row. It applies that identical
three-target B1 pattern in a new physics domain — the manufacturing
process rather than the electromagnetic device. The recipe, the trainer,
the predictor, and the reading rules are otherwise identical to the
earlier examples. Seeing the same B1 pattern transfer cleanly across yet
another physics family is part of the point.

The four steps ahead:

```
   Step 1                          Step 2                                   Step 3
  Format    ──▶    Train-Injection-Warpage.exe   ──▶    Predict-Injection-Warpage.exe
  your data        (makes the                            (use the trained
  (a CSV)          trained model)                         model on new design points)
```

---

## 2. What you'll need before you start

- **A batch of injection-molding simulation runs you have already
  completed.** Each run is one part design at one process recipe —
  process parameters + part-design parameters — analysed through your
  normal molding-simulation process (Autodesk Moldflow / Moldex3D /
  SIGMASOFT / 3D TIMON — any of the standard injection-molding workflows
  produces the right output shape). For each run you must know the eight
  input parameters you used and the three response numbers the run
  produced (peak warpage, spring-back, peak residual stress). Use the
  *same* solver, mesh-density policy, and analysis settings across all
  rows — mixing a coarse 2.5-D fill model and a fine 3-D model within one
  dataset gives the surrogate an extra hidden variable it cannot see.
- **At least 80 runs**; 200 – 400 is healthy. The eight-input process +
  part-design space is comparable to the motor example's eight-input
  space, so the minimum is the same as the structural / thermal / motor
  examples. A practical DOE shape: ~30 part-design variants × ~8 process
  recipes each ≈ 240 rows.
- The eight inputs and three targets are listed in
  `data/data-contract.md`. They are: melt temperature, mold temperature,
  packing pressure, cooling time, injection rate, wall thickness, part
  size, glass-fibre content — and the three targets: peak warpage,
  spring-back, peak residual stress.
- **Single polymer-class per dataset.** Train one surrogate per polymer
  base-resin class — one PP-GF family, or one PA6-GF family, not a mix.
  Per TASK-1 §6 A.10.2 Pitfall (ii), a surrogate trained on one polymer
  class is blind to the different rheology, pvT behaviour, and
  crystallisation kinetics of another. Glass-fibre *content* is carried
  as a continuous input (it varies within a resin family and drives
  warpage), but the base-resin class itself is a categorical you must
  hold fixed per dataset. The trainer does not detect polymer class
  automatically; honour this constraint upstream.
- **One flow-formulation class per dataset.** Per TASK-1 §6 A.10.2
  Pitfall (iii), a surrogate trained on Hele-Shaw / 2.5-D fill data
  inherits the thin-walled-cavity assumption and cannot be silently used
  on thick-walled parts where the 3-D flow physics matters. Keep the
  formulation class uniform (all 2.5-D *or* all 3-D).
- A Windows PC. See *Setup* at the end of this document — there is no
  install step.

You do **not** need a GPU, an internet connection while training,
Python, or any ML software. Everything the example needs is inside the
executables.

> **If you just want to see it work first:** this example ships with a
> synthetic `data/sample-dataset.csv` (250 rows generated by an
> analytical warpage-and-shrinkage pastiche — differential shrinkage from
> the melt-to-mold contraction span, a cooling-asymmetry term driven by
> wall thickness and cooling time, and a glass-fibre anisotropy term).
> You can run Steps 2 and 3 on that immediately, before you have prepared
> any real data. The sample data is **illustrative only** — it is *not*
> real simulation data and its accuracy figures tell you nothing about
> what you will get on your own runs.

---

## 3. Step 1 — Format your data

The trainer reads one CSV file. It must have the eleven required columns
in `data/data-contract.md` (plus an optional `notes` column), in that
order, with one row per simulation run. Open `data/template.csv` for the
empty starting form; the column header row is already in place.

The required columns, in order, are:

1. `melt_temp_c` — polymer-melt (barrel) temperature at injection (°C)
2. `mold_temp_c` — mold-coolant / cavity-wall temperature (°C)
3. `pack_pressure_mpa` — packing (hold) pressure (MPa)
4. `cooling_time_s` — packing + cooling time in the mold (s)
5. `injection_rate_ccs` — injection (fill) volumetric flow rate (cm³/s)
6. `wall_thickness_mm` — nominal part wall thickness (mm)
7. `part_size_mm` — projected part size / characteristic flow length (mm)
8. `glass_fibre_pct` — glass-fibre weight content of the grade (%)
9. `warpage_mm` — peak out-of-plane warpage (mm) **— target**
10. `springback_mm` — elastic spring-back recovered on ejection (mm) **— target**
11. `peak_residual_stress_mpa` — peak frozen-in residual stress (MPa) **— target**

`notes` is optional and ignored by the trainer; use it for run IDs, DOE
labels, or — importantly — your polymer grade (see the single-polymer-
class rule above). The data contract documents the sign conventions:
`mold_temp_c` is the coolant / cavity-wall temperature, not the part
temperature; `warpage_mm` is the *peak out-of-plane deflection magnitude*
relative to nominal CAD (the headline warp number, not a signed per-node
displacement); `springback_mm` is the elastic-recovery component released
on ejection; and `peak_residual_stress_mpa` is the peak locked-in stress
that remains after cooling.

Your file should look like the sample dataset.

---

## 4. Step 2 — Train the model

Double-click `Train-Injection-Warpage.exe`. The trainer asks for the path
to your CSV. Point it at the file from Step 1 (or, to see the workflow
run first, at `data/sample-dataset.csv`).

The trainer:

1. Checks every column matches the data contract; if not, prints exactly
   which column is wrong and stops.
2. Trains a multi-output gradient-boosted-tree surrogate — one tree
   ensemble per target, all three sharing the same input vector. The
   training takes a few seconds on a 250-row dataset, up to ~30 seconds
   on a 2000-row dataset.
3. Prints a **held-out accuracy report**: it sets aside ~20 % of your
   rows, does not look at them while learning, then checks itself against
   them. The report shows the average absolute error and the R² for each
   of the three targets separately.
4. Writes a `trained-model` folder next to your CSV, containing the
   trained predictor (`Predict-Injection-Warpage.exe`) ready to use.

On the synthetic sample dataset (250 rows) the held-out report is:

| Target                     | Avg error (MAE) | R²    |
|----------------------------|-----------------|-------|
| `warpage_mm`               | ~0.26 mm        | ~0.85 |
| `springback_mm`            | ~0.13 mm        | ~0.83 |
| `peak_residual_stress_mpa` | ~4.6 MPa        | ~0.92 |

with an average R² of ~0.87 across the three targets.

**These figures are illustrative.** They come from the synthetic sample
data, not from real simulation. Your accuracy on your own data depends on
your data — the number of runs, how well they cover the
process-and-design space (especially the thin-wall / large-part and
over-pack corners), and the smoothness of the underlying simulation
response.

---

## 5. Step 3 — Use the trained model

Double-click `Predict-Injection-Warpage.exe` in the `trained-model`
folder. It asks how you want to use the model:

- **[1] One new design point by hand.** It prompts for each of the eight
  inputs, then returns the predicted warpage, spring-back, and residual
  stress, each with an *uncertainty band* derived from the held-out
  accuracy report.
- **[2] A CSV of many points.** Pass a CSV with the eight input columns;
  it writes a `*-predictions.csv` next to your input file with the
  predicted values, the lo/hi uncertainty range for each of the three
  targets, and an extrapolation flag.

Read the uncertainty band as: *"if the model is right on average, the
true answer should be within this range about 70 % of the time."* That
is enough for design screening — narrowing rankings of candidate recipes,
weeding out clearly-out-of-tolerance settings early — but it is not
enough for tolerance certification. Run the real simulation on the few
candidates that survive screening.

The **EXTRAPOLATION flag** fires if any input is outside the range of the
rows you trained on. Treat a flagged prediction as a prompt to run a real
simulation at that point — the model has not seen anything like that
process-and-design combination. This matters especially near the
process-window corners (very high or low packing pressure, very thin
walls, very large parts), which is exactly where the dominant failure
mode below bites.

---

## 6. Reading the results responsibly

A trained surrogate is a *fast approximation* of a slower but more
trustworthy model — and the slower model is itself an approximation of
the real physical molding process. Injection-molding simulation is a
mature, widely-deployed engineering discipline: the canonical numerical-
modelling reference is Kennedy's *Flow Analysis of Injection Molds*
([Kennedy2013]; Kennedy is the founding scientist of Moldflow, the
commercial tool built on this methodology), which lays out the
Hele-Shaw / 2.5-D fill formulation, the packing and cooling phases that
drive residual stress and warpage, and the Folgar-Tucker fibre-
orientation evolution that drives anisotropic shrinkage in fibre-
reinforced grades. That widespread industrial use of molding simulation
is the foundation this example sits on: a surrogate trained on
simulation results inherits the simulation's strengths *and* its
limitations. The surrogate can run faster than the simulation; it cannot
be more accurate than the simulation. If your simulation runs themselves
use the wrong material card, a mis-specified packing profile, or a
too-coarse cooling model, the surrogate will reproduce that inaccuracy
faithfully.

Three reading rules:

1. **Trust the surrogate inside the training range; distrust it
   outside.** The trainer captures the min/max of each input column you
   fed it. When you ask for a prediction at an input value outside that
   range, the predictor flags it. A flagged prediction is a candidate
   for a real simulation check, not a final answer.
2. **R² ≈ 0.6 is the floor for design screening.** Below that, the
   trainer prints a "weak" warning and you should suspect either too-few
   rows or too-narrow a spread. Above ~0.85 the model is strong enough to
   rank candidates confidently.
3. **Process-parameter-envelope extrapolation is the dominant deployed
   surrogate-failure mode.** Per TASK-1 §6 A.10.2 Pitfall (iv), a
   surrogate trained on one narrow process-parameter envelope mispredicts
   qualitatively when deployed outside it — the warpage physics is highly
   nonlinear near the short-shot (under-pack) and over-pack boundaries
   and near the thin-wall / large-part corner. The remedy is in your DOE:
   make your training runs span the full process window, not just the
   nominal recipe. A close second failure mode (Pitfall (ii)) is
   **polymer-class mismatch** — a surrogate trained on one base resin
   cannot be silently used on another, because the rheology, pvT, and
   crystallisation behaviour all differ. Hold the resin class fixed per
   dataset and record it.

The model is a design-screening tool. It is not a tolerance-
certification tool.

---

## 7. What's happening inside (optional, one page)

*This page is strictly optional. Skip it if you just want to use the
model.*

The architecture inside the trainer is a **multi-output gradient-
boosted-tree regressor** (scikit-learn's
`MultiOutputRegressor(HistGradientBoostingRegressor)`). In plain words:
it builds many small decision trees, each trying to fix the mistakes of
the previous one, and averages their answers — one tree ensemble per
target, three ensembles in all (warpage, spring-back, residual stress),
sharing the same eight-input row. Gradient-boosted trees are the
bread-and-butter of structured-data regression and are exactly the
architecture TASK-1 §6 A.10.2 lists as the deployed Bucket-B1 fit for
parameter-vector → headline-as-molded-quality-metric regression — the
dominant deployed-in-OEM-and-tool-shop pattern for injection-molding
process optimisation.

The three-output structure works exactly as it did in the motor example
(TASK-8-1105): a multi-output regressor does *not* squeeze all three
targets into one model that has to compromise between them; it trains an
independent tree ensemble for each target, so warpage, spring-back, and
residual stress each get a model tuned to their own response shape. From
the reader's side it is still one surrogate — one trainer, one predictor,
one input row in, three numbers out.

The "8 inputs → 3 targets" mapping the model learns is, under the hood,
related to the physics of injection-molding shrinkage. Warpage is the
part-level consequence of *differential shrinkage*: as the polymer cools
and solidifies, it shrinks, and any non-uniformity in that shrinkage
across the part thickness or plan area locks in residual stress and bows
the part out of plane. Packing pressure feeds extra melt in to compensate
shrinkage; thick walls in a hot mold with a short cooling time cool
unevenly through-thickness and lock in a bowing moment; glass fibre flips
and amplifies the cross-flow-vs-flow shrinkage differential. The surrogate
learns all of this *from your data* rather than being told it in advance.

It is worth seeing this in the model's own behaviour. On the shipped
sample data, a permutation-importance ranking (which inputs the trained
model actually leans on) puts **packing pressure** first by a wide margin,
**wall thickness** second, then **cooling time**, **part size**, and
**melt temperature** in the middle — and **injection rate** essentially
last, near zero. That ranking is physically honest: packing pressure and
wall thickness are exactly the two levers a molding engineer reaches for
first to pull warpage into tolerance, while injection (fill) *rate*
mostly governs fill-stage defects like weld lines and short shots rather
than the post-fill pack-and-cool shrinkage that sets final warpage. A
surrogate that recovers that ordering from data alone is doing the right
thing for the right reason — and it is the entire pedagogical point of
the B1 bucket: when you have a parametric DOE and a few scalar responses,
a tabular surrogate gives you most of the speed of a lumped-parameter
rule with most of the accuracy of the underlying simulation.

The **uncertainty band** is the held-out mean absolute error scaled by
1.5 — a rough "one sigma" by analogy. It widens by an extra 2×MAE per
unit of extrapolation distance, so predictions far outside the training
range carry visibly larger ranges. A future iteration of this example
(deferred from the build session that shipped the GBM baseline) may add
an optional **Gaussian-Process variant** that produces calibrated
per-point posterior-variance bands rather than MAE-scaled ones. GP is
attractive here because process-window optimisation typically runs a
design-of-experiments / Bayesian-optimisation outer loop, and a GP's
native uncertainty quantification feeds that outer loop directly (TASK-1
§6 A.10.2 Trainable-ML-architectures); the §4 inventory row for
TASK-8-1106 in `EXAMPLES-ARC-SCOPING.md` records that planned variant.
The §4 row also lists an MLP as an alternative tabular architecture; this
session ships the GBM baseline per the arc's bias-to-simple discipline.

---

## 8. Where to go next

The natural reading order around this example:

- **`TASK-8-1105` — Motor Torque, Efficiency, and Loss.** The arc's other
  **three-target** B1 and the closest architectural sibling — same
  multi-output gradient-boosted-tree recipe, three targets. Reading the
  two together shows the identical three-target pattern transferring from
  an electromagnetic device to a manufacturing process.
- **`TASK-8-1104` — Peak Temperature of a Cooled Component.** The arc's
  thermal-FE B1, a two-target sibling. Injection-molding warpage is, at
  its core, a thermal-contraction phenomenon, so the thermal example is a
  natural companion.
- **`TASK-8-1103` — Peak Stress of a Loaded Bracket.** The arc's
  structural-FE B1, also two targets. The residual-stress target here is
  the *upstream input* to a downstream structural analysis like 1103 —
  per TASK-1 §6 A.10.2 the architecturally-correct treatment chains the
  manufacturing surrogate into the structural one.
- **`TASK-8-1101` — Fatigue Life of a Loaded Bracket.** The arc's first
  B1 and the example that calibrated the standalone-`.exe` packaging
  path; demonstrates a log-scale target rather than the linear-scale
  targets in this example.
- **`TASK-8-1102` — Drag and Lift of an Off-Road Vehicle.** The arc's
  external-aero B1 — same bucket, different physics. Demonstrates a
  dual-channel input vocabulary (assembly catalog → physical attributes)
  that this example does not need but is worth seeing.
- **`TASK-8-1107` + `TASK-8-1401` — Pump operating-point and performance
  curve.** The arc's authoritative B1-vs-B7 worked instance — same CFD
  case, but PCS predicts scalars at a query operating point while PCC
  predicts the whole curve. Reading them after this example shows how
  *the same physics case* can land in different ML buckets depending on
  the downstream question.
- **The BRIDGE-A deck** in `presentations/` for the conceptual framing of
  the slide-9 grid and how the bucket choice falls out of the
  input/output shape.

---

## Setup

This example runs as standalone executables on Windows. There is no
install step: download the `TASK-8-1106-injection-warpage/` folder,
double-click `Train-Injection-Warpage.exe`, then double-click the
`Predict-Injection-Warpage.exe` the trainer drops into a `trained-model`
folder. No Python required.

(If you are running the *interim* form — `Train.bat` / `Predict.bat` in
`trainer/` — Python 3.10+ with `scikit-learn` installed is required. The
interim form ships in the source repo as a fallback for build hosts that
do not yet have the standalone build; the reader-facing form is the
standalone build.)
