# TASK-8-1104 — Predicting Peak Temperature of a Cooled Component

### A step-by-step worked example for CAE engineers — no ML background needed

> Part of the CAE-ML step-by-step examples arc — project task 8
> (`EXAMPLES-ARC-SCOPING.md`). This is example **`TASK-8-1104`**: the
> ID encodes its slide-9 grid cell — `n=1` (parametric-input row),
> `m=1` (scalar-output column), example `04` — i.e. Bucket B1, the
> tabular surrogate. It is the **fourth B1 example** in the arc (after
> `TASK-8-1101` fatigue-life, `TASK-8-1102` drag-lift, and `TASK-8-1103`
> peak-stress), and the first that lives in the steady-state thermal
> finite-element domain.
>
> You will train a model and use it. You will **not** write code or
> make any machine-learning decisions. Everything runs by
> double-clicking a file.

---

## 1. What this example does

Running a steady-state thermal finite-element analysis to get the peak
temperature and hot-spot location of a cooled component typically takes
seconds to minutes per design — fast enough for one analysis, but slow
enough that running the full FE for every candidate during a parameter
sweep across geometry, material, cooling, and operating point adds up
quickly. When you are exploring a thermal-management design space —
trying different fin lengths, cross-sections, materials, coolant flow
rates, ambient conditions, and dissipated power levels — running the
full thermal FE for every combination becomes the bottleneck on how
broadly you can search.

This example builds a **surrogate**: a fast model that has learned,
from a batch of steady-state thermal FE runs you have *already* done,
the relationship between a component's input vector (geometry +
material + cooling boundary + operating point) and the two headline
thermal responses (peak steady-state temperature, hot-spot position
along the cooling axis). Once trained, it returns both numbers in a
fraction of a second, so you can screen hundreds of design candidates
before committing solver time to the handful that matter.

**Where this sits in the taxonomy.** The model takes a *row of
numbers* (seven geometry / material / boundary / operating-point
parameters) and returns a *short vector of numbers* (two thermal-
response scalars). On the BRIDGE-A slide-9 grid that is the top-left
cell — *parametric input → scalar(s) output* — which is **Bucket B1,
the tabular surrogate**. B1 is the simplest and most production-proven
corner of the grid, which is why this example uses it. Catalog
reference: analysis **A.3.1** (FEA family, Thermal Steady-state
conduction / convection) in
`tasks/TASK-1-cae-analysis-catalog.md`. Arc inventory record:
`EXAMPLES-ARC-SCOPING.md` §4 (the fourth B1 entry).

The four steps ahead:

```
   Step 1                          Step 2                                Step 3
  Format    ──▶    Train-Peak-Temperature.exe   ──▶    Predict-Peak-Temperature.exe
  your data        (makes the                          (use the trained
  (a CSV)          trained model)                       model on new design points)
```

---

## 2. What you'll need before you start

- **A batch of steady-state thermal FE runs you have already
  completed.** Each run is one component design — geometry + material
  + boundary conditions + operating point — analysed through your
  normal steady-state thermal FE process (ANSYS Mechanical Steady-
  State Thermal / Abaqus Heat Transfer / MSC Nastran SOL 153 / Simcenter
  3D Thermal / COMSOL Heat Transfer Module — any of the standard
  workflows produces the right output shape). For each run you must
  know the seven input parameters you used and the two response
  numbers the run produced (peak steady-state temperature, hot-spot
  position along the cooling axis). Use the *same* mesh-refinement
  policy across all runs — mixing fine and coarse meshes within one
  dataset gives the surrogate an extra hidden variable it cannot see.
- **At least 80 runs**; 200 – 400 is healthy. The seven-input
  geometry + material + boundary + operating-point space is
  comparable to the pump pair's design + operating-point space, so
  the minimum is the same as the pump pair and the structural
  example. A practical DOE shape: ~30 geometry combinations × ~8
  material / cooling variations each ≈ 240 rows.
- The seven inputs and two targets are listed in
  `data/data-contract.md`. They are: length along the cooling axis,
  cross-section width, cross-section thickness, thermal conductivity,
  convective heat-transfer coefficient, ambient temperature, total
  internal heat-generation rate — and the two targets: peak steady-
  state temperature, hot-spot position along the cooling axis.
- **Steady-state regime only.** This example assumes steady-state
  thermal FE: temperature field has reached equilibrium under the
  prescribed boundary conditions, no transient warm-up / cool-down,
  no phase change. If your FE problem is transient or includes phase
  change, this surrogate will misrepresent the physics — that is a
  different bucket (A.3.2). The trainer does not detect transient
  inputs automatically; honour this constraint upstream.
- **Single-class boundary conditions per dataset.** Train one
  surrogate per boundary-condition class (Dirichlet attachment
  surface + Robin convection on cooled surfaces is the default).
  Mixing radiation-dominated and convection-dominated runs in one
  dataset gives the surrogate an unobserved hidden variable that
  silently degrades accuracy — this is TASK-1 A.3.1 Pitfall (ii).
- A Windows PC. See *Setup* at the end of this document — there is no
  install step.

You do **not** need a GPU, an internet connection while training,
Python, or any ML software. Everything the example needs is inside the
executables.

> **If you just want to see it work first:** this example ships with a
> synthetic `data/sample-dataset.csv` (250 rows generated by an
> analytical pin-fin pastiche with internal heat generation and
> convective lateral cooling). You can run Steps 2 and 3 on that
> immediately, before you have prepared any real data. The sample data
> is **illustrative only** — it is *not* real FE data and its accuracy
> figures tell you nothing about what you will get on your own runs.

---

## 3. Step 1 — Format your data

The trainer reads one CSV file. It must have the nine required columns
in `data/data-contract.md` (plus an optional `notes` column), in that
order, with one row per FE run. Open `data/template.csv` for the empty
starting form; the column header row is already in place.

The required columns, in order, are:

1. `length_mm` — component length along the cooling axis (mm)
2. `width_mm` — cross-section width (mm)
3. `thickness_mm` — cross-section thickness (mm)
4. `conductivity_W_mK` — thermal conductivity `k` of the component material (W/(m·K))
5. `h_W_m2K` — convective heat-transfer coefficient on cooled surfaces (W/(m²·K))
6. `T_ambient_C` — ambient / coolant temperature `T_∞` (°C)
7. `q_W` — total internal heat-generation rate (W)
8. `peak_temp_C` — peak steady-state temperature (°C) **— target**
9. `hot_spot_x_mm` — position along the length where the peak occurs (mm) **— target**

`notes` is optional and ignored by the trainer; use it for run IDs or
DOE labels if helpful. The data contract documents sign conventions:
`T_ambient_C` and `peak_temp_C` are both on the Celsius scale (pick
one scale and apply it across all rows — the trainer does not non-
dimensionalise); `q_W` is the *total* heat-generation rate in watts
integrated over the component volume, not a volumetric density; and
`hot_spot_x_mm` is measured from the heat-source-attachment face
(`x = 0`) toward the cooled tip (`x = length_mm`).

Your file should look like the sample dataset.

---

## 4. Step 2 — Train the model

Double-click `Train-Peak-Temperature.exe`. The trainer asks for the
path to your CSV. Point it at the file from Step 1 (or, to see the
workflow run first, at `data/sample-dataset.csv`).

The trainer:

1. Checks every column matches the data contract; if not, prints
   exactly which column is wrong and stops.
2. Trains a multi-output gradient-boosted-tree surrogate — one tree
   ensemble per target, sharing the same input vector. The training
   takes a few seconds on a 250-row dataset, up to ~30 seconds on a
   2000-row dataset.
3. Prints a **held-out accuracy report**: it sets aside ~20 % of your
   rows, does not look at them while learning, then checks itself
   against them. The report shows the average absolute error and the
   R² for each target separately.
4. Writes a `trained-model` folder next to your CSV, containing the
   trained predictor (`Predict-Peak-Temperature.exe`) ready to use.

On the synthetic sample dataset (250 rows) the held-out report is:

| Target          | Avg error (MAE) | R²    |
|-----------------|-----------------|-------|
| `peak_temp_C`   | ~10 °C          | ~0.93 |
| `hot_spot_x_mm` | ~15 mm          | ~0.85 |

**These figures are illustrative.** They come from the synthetic
sample data, not from real FE. Your accuracy on your own data
depends on your data — the number of runs, how well they cover the
design space, and the smoothness of the underlying FE response.

---

## 5. Step 3 — Use the trained model

Double-click `Predict-Peak-Temperature.exe` in the `trained-model`
folder. It asks how you want to use the model:

- **[1] One new design point by hand.** It prompts for each of the
  seven inputs, then returns the predicted peak temperature and
  hot-spot position, each with an *uncertainty band* derived from the
  held-out accuracy report.
- **[2] A CSV of many points.** Pass a CSV with the seven input
  columns; it writes a `*-predictions.csv` next to your input file
  with the predicted values, the lo/hi uncertainty range for each
  target, and an extrapolation flag.

Read the uncertainty band as: *"if the model is right on average,
the true answer should be within this range about 70 % of the
time."* That is enough for design screening — narrow rankings of
candidates, weed out clearly-too-hot designs early — but it is
not enough for design certification. Run the real FE on the few
candidates that survive screening.

The **EXTRAPOLATION flag** fires if any input is outside the range
of the rows you trained on. Treat a flagged prediction as a prompt to
run a real FE simulation at that point — the model has not seen
anything like that geometry / material / cooling / operating-point
combination.

---

## 6. Reading the results responsibly

A trained surrogate is a *fast approximation* of a slower but more
trustworthy model — and the slower model is itself an approximation of
the real physical component. Bathe puts the framing this way:

> "Finite element procedures are at present very widely used in
> engineering analysis, and we can expect this use to increase
> significantly in the years to come."
>
> — Bathe, *Finite Element Procedures*, 2nd ed. (2007 / 4th printing
> 2014), Chapter 1 opening sentence
> ([Q-cae-05](../../QUOTES.md#q-cae-05--bathe-fea-as-engineering-practice-foundational-textbook-framing);
> [Bathe2014]).

Bathe's framing applies to the thermal-FE case just as it does to the
structural case (TASK-8-1103): the conduction-equation FE machinery
shares its Galerkin discretisation with the structural-FE machinery,
and the textbook anchor is shared (TASK-1 §6 A.3.1 explicitly cites
Q-cae-05 alongside the thermal-specific textbook
anchors [Bergman2017] and [Patankar1980]). That widespread industrial
use of FE is the foundation this example sits on: a surrogate trained
on thermal-FE results inherits the FE's strengths *and* its
limitations. The surrogate can run faster than the FE; it cannot be
more accurate than the FE. If your FE runs themselves use the wrong
material model, mis-specified boundary conditions, or a too-coarse
mesh, the surrogate will reproduce that inaccuracy faithfully.

Three reading rules:

1. **Trust the surrogate inside the training range; distrust it
   outside.** The trainer captures the min/max of each input column
   you fed it. When you ask for a prediction at an input value
   outside that range, the predictor flags it. A flagged prediction
   is a candidate for a real FE check, not a final answer.
2. **R² ≈ 0.6 is the floor for design screening.** Below that, the
   trainer prints a "weak" warning and you should suspect either
   too-few rows or too-narrow a spread. Above ~0.85 the model is
   strong enough to rank candidates confidently.
3. **Material-property temperature dependence is the dominant
   thermal-surrogate-failure mode.** Per TASK-1 §6 A.3.1 Pitfall (i)
   and ROADMAP A.3, surrogates trained on constant-k data
   systematically mis-predict in regimes where k(T) varies materially
   (high-temperature aerospace alloys, polymer composites near
   glass-transition, electronics packaging materials across wide
   operating-temperature windows). This contract treats
   `conductivity_W_mK` as a single scalar per run; if your high-
   fidelity FE uses temperature-dependent `k(T)`, either report the
   effective k at the run's mean temperature (and accept the
   simplification) or treat the strongly-`k(T)`-dependent regime as
   out of scope for this surrogate.

The model is a design-screening tool. It is not a design-
certification tool.

---

## 7. What's happening inside (optional, one page)

*This page is strictly optional. Skip it if you just want to use the
model.*

The architecture inside the trainer is a **multi-output gradient-
boosted-tree regressor** (scikit-learn's
`MultiOutputRegressor(HistGradientBoostingRegressor)`). In plain
words: it builds many small decision trees, each trying to fix the
mistakes of the previous one, and averages their answers — one tree
ensemble per target. Gradient-boosted trees are the bread-and-butter
of structured-data regression and are exactly the architecture
TASK-1 §6 A.3.1 lists as the canonical Bucket-B1 fit for parameter-
vector → peak-temperature regression — the workhorse pattern for
thermal-architecture trade studies and component-thermal-budget
allocation.

The "7 inputs → 2 targets" mapping the model learns is, under the
hood, related to the analytical pin-fin solution for steady-state
conduction with internal heat generation and convective lateral
cooling. The classic fin equation gives:

```
peak excess temperature  T_peak - T_∞  =  function of (geometry, k, h, q_W)
```

and the analytical solution admits two qualitative regimes: a
*source-dominated* regime where the upstream thermal-budget
allocation puts the hot spot at the attachment face (`x = 0`), and a
*self-heating-dominated* regime where the internal heat generation
pushes the hot spot toward the cooled tip. The surrogate learns both
regimes *from your data* rather than being told them in advance, and
it picks up the geometry-specific corrections that no single
analytical formula captures cleanly. That is the entire pedagogical
point of the B1 bucket: when you have a parametric DOE and a scalar
response, a tabular surrogate gives you most of the speed of an
analytical formula with most of the accuracy of the underlying FE.

The Biot number `Bi = h·L_c / k` and the Fourier number `Fo = α·t /
L_c²` are the load-bearing dimensionless groups for the heat
equation; per ROADMAP A.3, non-dimensionalising the problem in Biot
and Fourier scaling is the single load-bearing surrogate-
generalisation lever for thermal entries. This example ships the
*dimensional* form (raw mm / W / °C inputs) for reader-clarity; a
future iteration may add a non-dimensional variant that trains on
Bi / Fo directly and demonstrates the stronger across-geometric-scale
generalisation that non-dimensionalisation buys.

The **uncertainty band** is the held-out mean absolute error scaled
by 1.5 — a rough "one sigma" by analogy. It widens by an extra 2×MAE
per unit of extrapolation distance, so predictions far outside the
training range carry visibly larger ranges. A future iteration of
this example (deferred from the build session that shipped the GBM
baseline) will add an optional **Gaussian-Process variant** that
produces calibrated per-point posterior-variance bands rather than
MAE-scaled ones. GP is unusually attractive for thermal because the
Gaussian-process predictive variance gives free uncertainty
quantification that feeds thermal-margin sizing decisions directly
(TASK-1 §6 A.3.1 Trainable-ML-architectures third bullet); the §4
inventory row for TASK-8-1104 in `EXAMPLES-ARC-SCOPING.md` records
that planned variant.

---

## 8. Where to go next

The natural reading order around this example:

- **`TASK-8-1103` — Peak Stress of a Loaded Bracket.** The arc's
  structural-FE B1 and the closest architectural sibling — same
  two-target multi-output regressor pattern, same recipe; reading
  the two together shows how the B1 pattern transfers across physics
  families (FE-for-structures → FE-for-thermal).
- **`TASK-8-1101` — Fatigue Life of a Loaded Bracket.** The arc's
  first B1 and the example that calibrated the standalone-`.exe`
  packaging path; demonstrates a log-scale target rather than the
  linear-scale targets in this example.
- **`TASK-8-1102` — Drag and Lift of an Off-Road Vehicle.** The arc's
  external-aero B1 — same bucket, different physics. Demonstrates a
  dual-channel input vocabulary (assembly catalog → physical
  attributes) that this example does not need but is worth seeing.
- **`TASK-8-1107` + `TASK-8-1401` — Pump operating-point and
  performance curve.** The arc's authoritative B1-vs-B7 worked
  instance — same CFD case, but PCS predicts scalars at a query
  operating point while PCC predicts the whole H(Q)/η(Q)/NPSHr(Q)
  curve. Reading them after this example shows how *the same physics
  case* can land in different ML buckets depending on the downstream
  question.
- **The BRIDGE-A deck** in `presentations/` for the conceptual
  framing of the slide-9 grid and how the bucket choice falls out of
  the input/output shape.

---

## Setup

This example runs as standalone executables on Windows. There is no
install step: download the `TASK-8-1104-peak-temperature/` folder,
double-click `Train-Peak-Temperature.exe`, then double-click the
`Predict-Peak-Temperature.exe` the trainer drops into a `trained-model`
folder. No Python required.

(If you are running the *interim* form — `Train.bat` / `Predict.bat`
in `trainer/` — Python 3.10+ with `scikit-learn` installed is
required. The interim form ships in the source repo as a fallback
for build hosts that do not yet have the standalone build; the
reader-facing form is the standalone build.)
