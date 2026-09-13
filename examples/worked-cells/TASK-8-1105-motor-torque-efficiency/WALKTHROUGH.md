# TASK-8-1105 — Predicting Motor Torque, Efficiency, and Loss

### A step-by-step worked example for CAE engineers — no ML background needed

> Part of the CAE-ML step-by-step examples arc — project task 8
> (`EXAMPLES-ARC-SCOPING.md`). This is example **`TASK-8-1105`**: the
> ID encodes its slide-9 grid cell — `n=1` (parametric-input row),
> `m=1` (scalar-output column), example `05` — i.e. Bucket B1, the
> tabular surrogate. It is the **fifth B1 example** in the arc (after
> `TASK-8-1101` fatigue-life, `TASK-8-1102` drag-lift, `TASK-8-1103`
> peak-stress, and `TASK-8-1104` peak-temperature), and the first that
> lives in the low-frequency electromagnetics (electric-machine) domain.
>
> You will train a model and use it. You will **not** write code or
> make any machine-learning decisions. Everything runs by
> double-clicking a file.

---

## 1. What this example does

Running a low-frequency electromagnetic finite-element analysis to get
the torque, efficiency, and loss of an electric machine at one operating
point typically takes minutes to hours per point — fast enough for a
single analysis, but slow enough that filling out a full
torque-and-efficiency map across the operating envelope, for every
candidate in a motor-design study, becomes the bottleneck on how broadly
you can search. When you are exploring a motor design space — trying
different stator diameters, stack lengths, air-gaps, magnet thicknesses,
and winding turns, each evaluated across a grid of currents, speeds, and
operating temperatures — running the full EM FE for every combination is
where the time goes.

This example builds a **surrogate**: a fast model that has learned, from
a batch of low-frequency-EM FE runs you have *already* done, the
relationship between a machine's input vector (geometry + winding +
operating point) and the three headline performance responses
(electromagnetic torque, efficiency, total loss). Once trained, it
returns all three numbers in a fraction of a second, so you can screen
hundreds of design-and-operating-point candidates before committing
solver time to the handful that matter.

**Where this sits in the taxonomy.** The model takes a *row of numbers*
(eight geometry / winding / operating-point parameters) and returns a
*short vector of numbers* (three performance scalars). On the BRIDGE-A
slide-9 grid that is the top-left cell — *parametric input → scalar(s)
output* — which is **Bucket B1, the tabular surrogate**. B1 is the
simplest and most production-proven corner of the grid, which is why
this example uses it. This is also where production motor-design
optimisation actually lives: per TASK-1 §6 A.5.1, the *integral*
outputs (torque, efficiency, loss) are the deeper-deployment-maturity
surrogate target, precisely because integrating over the machine
averages out the local-field errors that would dominate a full
magnetic-field regression. Catalog reference: analysis **A.5.1**
(Electromagnetics, Low-frequency — motors, induction) in
`tasks/TASK-1-cae-analysis-catalog.md`. Arc inventory record:
`EXAMPLES-ARC-SCOPING.md` §4 (the fifth B1 entry).

**What's new in this example.** This is the arc's first **three-target**
surrogate. The structural (TASK-8-1103) and thermal (TASK-8-1104)
examples each predicted two numbers; this one predicts three (torque,
efficiency, loss) from one input row. That is the only structural change
— the recipe, the trainer, the predictor, and the reading rules are
otherwise identical. Seeing the same B1 pattern stretch cleanly from two
outputs to three is part of the point.

The four steps ahead:

```
   Step 1                              Step 2                                       Step 3
  Format    ──▶    Train-Motor-Torque-Efficiency.exe   ──▶    Predict-Motor-Torque-Efficiency.exe
  your data        (makes the                                 (use the trained
  (a CSV)          trained model)                              model on new design points)
```

---

## 2. What you'll need before you start

- **A batch of low-frequency-EM FE runs you have already completed.**
  Each run is one machine design at one operating point — geometry +
  winding + current + speed + temperature — analysed through your
  normal low-frequency-EM process (ANSYS Maxwell / JMAG / Altair Flux /
  Infolytica MagNet / COMSOL AC/DC Module — any of the standard
  electric-machine workflows produces the right output shape). For each
  run you must know the eight input parameters you used and the three
  response numbers the run produced (electromagnetic torque, efficiency,
  total loss). Use the *same* mesh-refinement and solver-settings policy
  across all rows — mixing fine and coarse air-gap meshes within one
  dataset gives the surrogate an extra hidden variable it cannot see.
- **At least 80 runs**; 200 – 400 is healthy. The eight-input geometry +
  winding + operating-point space is comparable to the structural
  example's nine-input space, so the minimum is the same as the
  structural and thermal examples. A practical DOE shape: ~30 machine
  designs × ~8 operating points each ≈ 240 rows.
- The eight inputs and three targets are listed in
  `data/data-contract.md`. They are: stator outer diameter, stack
  length, air-gap, magnet thickness, turns per coil, stator-current
  amplitude, rotor speed, operating temperature — and the three targets:
  electromagnetic torque, efficiency, total loss.
- **Single analysis-class per dataset.** Train one surrogate per
  analysis class: 2-D-cross-section *or* 3-D, periodic-steady-state *or*
  transient — not a mix. Per TASK-1 §6 A.5.1 Pitfall (iv), a surrogate
  trained on 2-D-cross-section data is blind to end-region and
  axial-skew effects; per Pitfall (v), a surrogate trained on
  periodic-steady-state data cannot be used for fault-transient analyses
  (start-up, short-circuit, demagnetisation event). The trainer does not
  detect analysis class automatically; honour this constraint upstream.
- **Integral outputs only.** This surrogate predicts the *integral*
  responses (torque, efficiency, loss) — not the full magnetic-field
  map. If you need per-region local losses for a downstream
  thermal-coupling analysis, that is the full-field flavor: a different
  bucket and a different architecture (TASK-1 §6 A.5.1 Pitfall (iii)).
- A Windows PC. See *Setup* at the end of this document — there is no
  install step.

You do **not** need a GPU, an internet connection while training,
Python, or any ML software. Everything the example needs is inside the
executables.

> **If you just want to see it work first:** this example ships with a
> synthetic `data/sample-dataset.csv` (250 rows generated by an
> analytical interior-permanent-magnet-machine pastiche with a magnetic-
> saturation rolloff and a permanent-magnet temperature derate). You can
> run Steps 2 and 3 on that immediately, before you have prepared any
> real data. The sample data is **illustrative only** — it is *not* real
> FE data and its accuracy figures tell you nothing about what you will
> get on your own runs.

---

## 3. Step 1 — Format your data

The trainer reads one CSV file. It must have the eleven required columns
in `data/data-contract.md` (plus an optional `notes` column), in that
order, with one row per FE run. Open `data/template.csv` for the empty
starting form; the column header row is already in place.

The required columns, in order, are:

1. `stator_od_mm` — stator outer diameter (mm)
2. `stack_length_mm` — active axial (stack) length (mm)
3. `airgap_mm` — mechanical air-gap, rotor-to-stator radial clearance (mm)
4. `magnet_thickness_mm` — permanent-magnet radial thickness (mm)
5. `turns_per_coil` — conductor turns per stator coil (turns)
6. `current_a` — stator phase-current amplitude at the operating point (A)
7. `speed_rpm` — rotor mechanical speed (rpm)
8. `temperature_c` — magnet / winding operating temperature (°C)
9. `torque_nm` — mean electromagnetic torque (N·m) **— target**
10. `efficiency_pct` — efficiency at the operating point (%) **— target**
11. `total_loss_w` — total loss at the operating point (W) **— target**

`notes` is optional and ignored by the trainer; use it for run IDs or
DOE labels if helpful. The data contract documents the sign conventions:
`current_a` is the phase-current *amplitude* (convert from RMS if your
control parameterisation is RMS); `torque_nm` is the *mean* torque over
an electrical period, not the cogging-ripple amplitude; `efficiency_pct`
is on a 0–100 percent scale (enter `94.2`, not `0.942`); and
`total_loss_w` is the *total* loss (copper + iron + mechanical + stray,
summed into one column).

Your file should look like the sample dataset.

---

## 4. Step 2 — Train the model

Double-click `Train-Motor-Torque-Efficiency.exe`. The trainer asks for
the path to your CSV. Point it at the file from Step 1 (or, to see the
workflow run first, at `data/sample-dataset.csv`).

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
   trained predictor (`Predict-Motor-Torque-Efficiency.exe`) ready to use.

On the synthetic sample dataset (250 rows) the held-out report is:

| Target            | Avg error (MAE) | R²    |
|-------------------|-----------------|-------|
| `torque_nm`       | ~3 N·m          | ~0.87 |
| `efficiency_pct`  | ~1.2 %          | ~0.96 |
| `total_loss_w`    | ~68 W           | ~0.88 |

with an average R² of ~0.90 across the three targets.

**These figures are illustrative.** They come from the synthetic sample
data, not from real FE. Your accuracy on your own data depends on your
data — the number of runs, how well they cover the design-and-operating
space (especially the magnetic-saturation knee), and the smoothness of
the underlying FE response.

---

## 5. Step 3 — Use the trained model

Double-click `Predict-Motor-Torque-Efficiency.exe` in the
`trained-model` folder. It asks how you want to use the model:

- **[1] One new design point by hand.** It prompts for each of the eight
  inputs, then returns the predicted torque, efficiency, and loss, each
  with an *uncertainty band* derived from the held-out accuracy report.
- **[2] A CSV of many points.** Pass a CSV with the eight input columns;
  it writes a `*-predictions.csv` next to your input file with the
  predicted values, the lo/hi uncertainty range for each of the three
  targets, and an extrapolation flag.

Read the uncertainty band as: *"if the model is right on average, the
true answer should be within this range about 70 % of the time."* That
is enough for design screening — narrowing rankings of candidate motors,
weeding out clearly-inefficient or under-torqued designs early — but it
is not enough for design certification. Run the real FE on the few
candidates that survive screening.

The **EXTRAPOLATION flag** fires if any input is outside the range of the
rows you trained on. Treat a flagged prediction as a prompt to run a real
FE simulation at that point — the model has not seen anything like that
geometry / winding / operating-point combination. This matters
especially for `current_a` (the saturation knee) and `temperature_c`
(the magnet derate): predictions past the trained current or temperature
range are exactly where the two dominant failure modes below bite.

---

## 6. Reading the results responsibly

A trained surrogate is a *fast approximation* of a slower but more
trustworthy model — and the slower model is itself an approximation of
the real physical machine. Bathe puts the framing this way:

> "Finite element procedures are at present very widely used in
> engineering analysis, and we can expect this use to increase
> significantly in the years to come."
>
> — Bathe, *Finite Element Procedures*, 2nd ed. (2007 / 4th printing
> 2014), Chapter 1 opening sentence
> ([Q-cae-05](../../QUOTES.md#q-cae-05--bathe-fea-as-engineering-practice-foundational-textbook-framing);
> [Bathe2014]).

Bathe's framing applies to the low-frequency-EM case just as it does to
the structural and thermal cases (TASK-8-1103 / TASK-8-1104): the
electromagnetic FE machinery shares its Galerkin discretisation with the
structural-FE machinery, and the textbook anchor is shared. TASK-1 §6
A.5.1 cites Q-cae-05 / [Bathe2014] / [Hughes2000] for that shared FE
machinery, alongside [Jackson1998] for the Maxwell-equation derivations
and the magneto-quasi-static reduction (`∇×H = J`) that is specific to
the electromagnetic case. That widespread industrial use of FE is the
foundation this example sits on: a surrogate trained on EM-FE results
inherits the FE's strengths *and* its limitations. The surrogate can run
faster than the FE; it cannot be more accurate than the FE. If your FE
runs themselves use the wrong B-H curve, a mis-specified excitation, or a
too-coarse air-gap mesh, the surrogate will reproduce that inaccuracy
faithfully.

Three reading rules:

1. **Trust the surrogate inside the training range; distrust it
   outside.** The trainer captures the min/max of each input column you
   fed it. When you ask for a prediction at an input value outside that
   range, the predictor flags it. A flagged prediction is a candidate
   for a real FE check, not a final answer.
2. **R² ≈ 0.6 is the floor for design screening.** Below that, the
   trainer prints a "weak" warning and you should suspect either too-few
   rows or too-narrow a spread. Above ~0.85 the model is strong enough to
   rank candidates confidently.
3. **Magnetic saturation is the dominant low-frequency-EM surrogate-
   failure mode.** Per TASK-1 §6 A.5.1 Pitfall (i), a surrogate trained
   on below-saturation data systematically *over-predicts* the torque
   available at high current, because it never saw the iron core
   saturate and the torque-per-amp roll off. The remedy is in your DOE:
   make your training runs span below-saturation, knee-of-the-curve, and
   deep-saturation currents. A close second failure mode (Pitfall (ii))
   is **permanent-magnet temperature dependence** — the magnet remanence
   degrades as the machine heats up, so a surrogate trained only at
   nominal temperature over-predicts torque at hot-fault temperatures.
   Cover the operating-temperature range, including the hot end.

The model is a design-screening tool. It is not a design-certification
tool.

---

## 7. What's happening inside (optional, one page)

*This page is strictly optional. Skip it if you just want to use the
model.*

The architecture inside the trainer is a **multi-output gradient-
boosted-tree regressor** (scikit-learn's
`MultiOutputRegressor(HistGradientBoostingRegressor)`). In plain words:
it builds many small decision trees, each trying to fix the mistakes of
the previous one, and averages their answers — one tree ensemble per
target, three ensembles in all (torque, efficiency, loss), sharing the
same eight-input row. Gradient-boosted trees are the bread-and-butter of
structured-data regression and are exactly the architecture TASK-1 §6
A.5.1 lists as the production-mature Bucket-B1 fit for parameter-vector →
torque / efficiency / loss regression — the dominant deployed-in-OEM-
workflows pattern for electric-machine optimisation.

The three-output structure is worth a moment, because it is the one
thing new in this example. A multi-output regressor does *not* squeeze
all three targets into one model that has to compromise between them; it
trains an independent tree ensemble for each target, so torque,
efficiency, and loss each get a model tuned to their own response shape.
From the reader's side it is still one surrogate — one trainer, one
predictor, one input row in, three numbers out — but under the hood the
three targets never fight each other for capacity. That is why the
output vector stretches from the two targets of the structural and
thermal examples to three here with no change to the recipe or the
accuracy story.

The "8 inputs → 3 targets" mapping the model learns is, under the hood,
related to the physics of an interior-permanent-magnet machine. Torque
scales with the product of rotor flux linkage and stator current, but
with a *saturation rolloff* — past a current that depends on the iron
cross-section, the steel B-H curve flattens and each extra amp buys less
torque. Efficiency is output power over output-plus-losses, where the
losses split into copper loss (∝ current², rising with the winding
resistance), iron loss (rising with speed and flux), and mechanical loss
(rising with speed²). The surrogate learns all of this *from your data*
rather than being told it in advance, including the geometry-specific
corrections that no single closed-form motor formula captures cleanly.
That is the entire pedagogical point of the B1 bucket: when you have a
parametric DOE and a few scalar responses, a tabular surrogate gives you
most of the speed of a lumped-parameter formula with most of the
accuracy of the underlying FE.

The **uncertainty band** is the held-out mean absolute error scaled by
1.5 — a rough "one sigma" by analogy. It widens by an extra 2×MAE per
unit of extrapolation distance, so predictions far outside the training
range carry visibly larger ranges. A future iteration of this example
(deferred from the build session that shipped the GBM baseline) may add
an optional **Gaussian-Process variant** that produces calibrated
per-point posterior-variance bands rather than MAE-scaled ones. GP is
attractive here because motor-design optimisation typically runs a
design-of-experiments / Bayesian-optimisation outer loop, and a GP's
native uncertainty quantification feeds that outer loop directly (TASK-1
§6 A.5.1 Trainable-ML-architectures, integral-output bullet); the §4
inventory row for TASK-8-1105 in `EXAMPLES-ARC-SCOPING.md` records that
planned variant. The §4 row also lists an MLP as an alternative tabular
architecture; this session ships the GBM baseline per the arc's
bias-to-simple discipline.

---

## 8. Where to go next

The natural reading order around this example:

- **`TASK-8-1104` — Peak Temperature of a Cooled Component.** The arc's
  thermal-FE B1 and the closest architectural sibling — same multi-output
  gradient-boosted-tree recipe, but two targets instead of three.
  Reading the two together shows the output vector stretching from two to
  three with no change to the recipe.
- **`TASK-8-1103` — Peak Stress of a Loaded Bracket.** The arc's
  structural-FE B1, also two targets. Together with this example and
  TASK-8-1104 it shows the same B1 pattern transferring across three
  physics families (FE-for-structures → FE-for-thermal → FE-for-EM).
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
  predicts the whole H(Q)/η(Q)/NPSHr(Q) curve. Reading them after this
  example shows how *the same physics case* can land in different ML
  buckets depending on the downstream question.
- **The BRIDGE-A deck** in `presentations/` for the conceptual framing of
  the slide-9 grid and how the bucket choice falls out of the
  input/output shape.

---

## Setup

This example runs as standalone executables on Windows. There is no
install step: download the `TASK-8-1105-motor-torque-efficiency/` folder,
double-click `Train-Motor-Torque-Efficiency.exe`, then double-click the
`Predict-Motor-Torque-Efficiency.exe` the trainer drops into a
`trained-model` folder. No Python required.

(If you are running the *interim* form — `Train.bat` / `Predict.bat` in
`trainer/` — Python 3.10+ with `scikit-learn` installed is required. The
interim form ships in the source repo as a fallback for build hosts that
do not yet have the standalone build; the reader-facing form is the
standalone build.)
