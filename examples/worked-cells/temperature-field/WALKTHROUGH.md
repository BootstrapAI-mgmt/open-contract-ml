# Predicting the Temperature Field of a Cooled Component

### A step-by-step worked example for CAE engineers -- no ML background needed

> One of the worked cells in `examples/worked-cells/`. It sits in the
> parametric-input / regular-grid-field-output cell of the input/output
> grid (`n=1, m=2`, Bucket B2): the first worked cell outside Bucket B1
> and the first to predict a whole **field** rather than a scalar. It
> bridges directly from `peak-temperature`: the inputs are the same
> seven thermal parameters; only the output grows, from the single peak
> number to the temperature everywhere in the component.
>
> **What ships here:** this walkthrough, the data contract, the template,
> and a synthetic sample dataset with the script that generates it. The
> trainer and predictor executables Steps 2 and 3 describe are not part
> of this repository, so read those steps as a description of the
> workflow rather than as something this folder can run.
>
> You will train a model and use it. You will **not** write code or
> make any machine-learning decisions. Everything runs by
> double-clicking a file.

---

## 1. What this example does

Running a steady-state thermal finite-element analysis to get the
temperature field of a cooled component typically takes seconds to
minutes per design -- fast enough for one analysis, but slow enough that
running the full FE for every candidate during a parameter sweep across
geometry, material, cooling, and operating point adds up quickly. When
you are exploring a thermal-management design space, running the full
thermal FE for every combination becomes the bottleneck on how broadly
you can search.

The scalar example `peak-temperature` built a surrogate for the *peak*
temperature and the hot-spot location -- two numbers per design. That is
often all you need to screen designs. But sometimes the single peak
number is not enough: you want to see *where* the heat concentrates, how
steep the gradients are across a mounting face, whether a second warm
region is forming away from the main hot spot, or how the whole field
shifts as you change cooling. For that you need the **field**, not just
its maximum.

This example builds a **field surrogate**: a fast model that has learned,
from a batch of steady-state thermal FE runs you have *already* done, the
relationship between a component's input vector (geometry + material +
cooling boundary + operating point) and the **whole temperature field**
laid out on a fixed grid. Once trained, it returns the entire field in a
fraction of a second, so you can see the predicted temperature map for
hundreds of design candidates before committing solver time to the
handful that matter.

**Where this sits in the taxonomy.** The model takes a *row of numbers*
(the same seven geometry / material / boundary / operating-point
parameters as `peak-temperature`) and returns a *field on a regular grid*
(a temperature at every voxel of a fixed 12 x 8 x 8 lattice -- 768
numbers). On the input/output grid that is one cell to the **right** of
the top-left corner -- *parametric input -> regular-grid-field output*
(cell `n=1, m=2`) -- which is **Bucket B2, the regular-grid field
surrogate**.

> **Why this example steps outside B1.** The simplest grid cell (B1,
> scalar output) comes first; this example is a deliberate single step
> away from it, on three grounds:
> 1. **Its grid cell and bucket are named explicitly:** cell
>    `n=1, m=2`; Bucket **B2**. B2's defining test is that the output is
>    a field on a regular Cartesian grid and its spatial structure is
>    exploitable -- which this temperature field is.
> 2. **It is the canonical B2 case:** a volumetric temperature field on
>    a regular voxel grid, whose usual production architecture is a 3-D
>    U-Net or a dense 3-D CNN for regular-grid thermal fields.
> 3. **It is a single-step bridge from a built example:** it changes
>    *one* thing relative to `peak-temperature` -- the output goes from a
>    scalar to a field -- on a problem the reader has already seen as a
>    B1. The inputs, the physics, and the data-gathering discipline are
>    unchanged.

The analysis is steady-state thermal FEA (conduction / convection).

The four steps ahead:

```
   Step 1                          Step 2                                  Step 3
  Format    -->    Train-Temperature-Field.exe   -->    Predict-Temperature-Field.exe
  your data        (makes the                            (use the trained model on
  (a CSV)          trained model)                         new design points -> fields)
```

---

## 2. What you'll need before you start

- **A batch of steady-state thermal FE runs you have already
  completed.** Each run is one component design -- geometry + material +
  boundary conditions + operating point -- analysed through your normal
  steady-state thermal FE process (ANSYS Mechanical Steady-State Thermal
  / Abaqus Heat Transfer / MSC Nastran SOL 153 / Simcenter 3D Thermal /
  COMSOL Heat Transfer Module -- any of the standard workflows produces a
  temperature field). For each run you must know the seven input
  parameters you used **and** the temperature field the run produced,
  resampled onto the fixed grid (see Step 1 -- this resampling is the one
  genuinely new piece of work this example asks of you).
- **At least 80 runs**; 200 - 400 is healthy. The field output does not
  change how many runs you need -- the thing you are sampling is still
  the same seven-parameter design space as `peak-temperature`, so the minimum
  is the same (80). A practical DOE shape: ~30 geometry combinations x ~8
  material / cooling variations each, about 240 rows.
- The seven inputs are listed in `data/data-contract.md`. They are
  identical to `peak-temperature`: length along the cooling axis,
  cross-section width, cross-section thickness, thermal conductivity,
  convective heat-transfer coefficient, ambient temperature, total
  internal heat-generation rate. The **target is the temperature field**:
  768 voxel temperatures on the fixed 12 x 8 x 8 grid.
- **Steady-state regime only.** This example assumes steady-state thermal
  FE: the field has reached equilibrium, no transient warm-up /
  cool-down, no phase change. A transient or phase-change problem is a
  different bucket. The trainer does not detect transient inputs
  automatically; honour this constraint upstream.
- **Single-class boundary conditions per dataset.** Train one surrogate
  per boundary-condition class (Dirichlet attachment surface + Robin
  convection on cooled surfaces is the default). Mixing radiation-
  dominated and convection-dominated runs in one dataset gives the
  surrogate an unobserved hidden variable that silently degrades accuracy
  (boundary-condition class inheritance).
- A Windows PC. See *Setup* at the end of this document -- there is no
  install step.

You do **not** need a GPU, an internet connection while training, Python,
or any ML software. Everything the example needs is inside the
executables. (The dense field-decoder this example ships is deliberately
CPU-trainable; see Step 2 and section 7.)

> **If you just want to see it work first:** this example ships with a
> synthetic `data/sample-dataset.csv` (250 rows generated by an
> analytical pin-fin field pastiche -- the same closed-form profile the
> scalar `peak-temperature` used, evaluated at every voxel of the grid). You
> can run Steps 2 and 3 on that immediately, before you have prepared any
> real data. The sample data is **illustrative only** -- it is *not* real
> FE data and its accuracy figures tell you nothing about what you will
> get on your own runs.

---

## 3. Step 1 -- Format your data

The trainer reads one CSV file. It must have the seven input columns,
then 768 field columns (`T_000` ... `T_767`), then an optional `notes`
column, in that order, with one row per FE run. Open `data/template.csv`
for the empty starting form; the column header row is already in place.

The input columns, in order, are the same seven as `peak-temperature`:

1. `length_mm` -- component length along the cooling axis (mm)
2. `width_mm` -- cross-section width (mm)
3. `thickness_mm` -- cross-section thickness (mm)
4. `conductivity_W_mK` -- thermal conductivity `k` of the material (W/(m K))
5. `h_W_m2K` -- convective heat-transfer coefficient on cooled surfaces (W/(m^2 K))
6. `T_ambient_C` -- ambient / coolant temperature (deg C)
7. `q_W` -- total internal heat-generation rate (W)

The 768 target columns are the temperature field. Here is the one new
idea this example asks you to absorb:

> **You must resample your FE field onto a fixed grid.** Your solver
> produces a temperature field on its own mesh, which is unstructured
> and different for every run. Before filling the template, sample that
> field onto a normalised **12 x 8 x 8** grid spanning your component's
> bounding box: 12 points along the length (the cooling axis), 8 across
> the width, 8 through the thickness. Every run reports its field on this
> *same* grid, so every row of the dataset has the same 768 field columns
> in the same order. The flatten order is documented in
> `data/data-contract.md`: column `T_<flat>` is voxel `(i, j, k)` with
> `flat = (i * 8 + j) * 8 + k` -- `i` along the length, `j` across the
> width, `k` through the thickness. Use the **same** bounding-box and
> interpolation convention for every run; a mis-ordered or
> differently-gridded field silently corrupts the surrogate, and the
> trainer can only check the column *count* and *names*, not the physical
> ordering.

Most FE post-processors can export a field sampled on a regular grid
(ANSYS "Export -> Grid", a probe grid in Abaqus/CAE, a structured
interpolation in ParaView / pyvista). Set up the grid sampling once and
reuse it across the DOE. This resampling step is the field-example
equivalent of the scalar examples' "use the same mesh-refinement policy
across all rows" rule -- it is the discipline that makes the dataset
self-consistent.

`notes` is optional and ignored by the trainer; use it for run IDs or
DOE labels if helpful. The data contract documents the sign conventions:
`T_ambient_C` and every `T_<flat>` are on the Celsius scale (pick one
scale and apply it across all rows -- the trainer does not
non-dimensionalise); `q_W` is the *total* heat-generation rate in watts
integrated over the component volume, not a volumetric density; the grid
orientation is fixed (`i = 0` is the heat-source-attachment / base face,
`i = 11` is the cooled tip).

Your file should look like the sample dataset.

---

## 4. Step 2 -- Train the model

Double-click `Train-Temperature-Field.exe`. The trainer asks for the path
to your CSV. Point it at the file from Step 1 (or, to see the workflow
run first, at `data/sample-dataset.csv`).

The trainer:

1. Checks every column matches the data contract -- the seven inputs and
   all 768 field columns, in order; if not, it prints exactly which
   column is wrong and stops.
2. Trains a **field-decoder surrogate** -- a model that maps the seven
   inputs to all 768 voxel temperatures at once. The training takes a
   little longer than a scalar model (a field has many more output values
   per run) but is still CPU-only and finishes in well under a minute on
   a 250-row dataset.
3. Prints a **held-out field-accuracy report**: it sets aside ~20 % of
   your rows, does not look at them while learning, then checks itself
   against them. Because the output is a field, the report shows
   field-level figures rather than a single per-target error (see "What
   field accuracy means" below).
4. Writes a `trained-model` folder next to your CSV, containing the
   trained predictor (`Predict-Temperature-Field.exe`) ready to use.

On the synthetic sample dataset (250 rows) the held-out report is:

| Field-accuracy figure              | Value      |
|------------------------------------|------------|
| Mean relative L2 error (fraction)  | ~0.08      |
| Per-voxel mean absolute error      | ~5.5 deg C |
| Peak-temperature mean abs error    | ~6.5 deg C |

**These figures are illustrative.** They come from the synthetic sample
data, not from real FE. Your accuracy on your own data depends on your
data -- the number of runs, how well they cover the design space, and the
smoothness of the underlying FE response.

**What field accuracy means.** A scalar surrogate reports one error
number per target. A field surrogate reports an error over the whole
grid, so the trainer prints two field-level figures (plus a peak summary):

- **Mean relative L2 error** -- the size of the prediction error vector
  divided by the size of the true field vector, averaged over the
  held-out runs. Read it as "what fraction of the field's magnitude does
  a typical prediction miss by?" Below ~0.10 (10 %) is a tight field;
  0.10 - 0.20 is usable for screening; above 0.20 wants more or wider
  data.
- **Per-voxel mean absolute error (deg C)** -- the average temperature
  miss at a single voxel, in degrees. This is the field-wide analogue of
  the scalar examples' MAE and the easiest number to reason about
  physically: "the typical voxel is off by about this many degrees."
- **Peak-temperature mean absolute error (deg C)** -- how far off the
  single hottest voxel of the predicted field is, on average. This ties
  the field surrogate back to the scalar `peak-temperature` question: if you
  only cared about the peak, this is the number to compare.

---

## 5. Step 3 -- Use the trained model

Double-click `Predict-Temperature-Field.exe` in the `trained-model`
folder. It asks how you want to use the model:

- **[1] One new design point by hand.** It prompts for each of the seven
  inputs, then prints a **summary of the predicted field** -- the peak
  temperature and where it sits on the grid, the mean temperature, the
  coolest voxel, and a per-voxel uncertainty band -- and writes the full
  768-voxel field to `predicted-field.csv` in the `trained-model` folder.
- **[2] A CSV of many points.** Pass a CSV with the seven input columns.
  It writes two files next to your input: a `*-field-summary.csv` with
  one row per design point (the inputs, the peak / mean / coolest
  temperatures, the hot-spot grid location, and an extrapolation flag),
  and a `*-fields.csv` with the full 768-voxel field for every point (one
  row per point, voxel columns `T_000` ... `T_767`).

Because a field is 768 numbers, the predictor does not print it to the
screen -- it prints the summary and writes the field to a file you can
open or plot. The next section shows how to turn that file back into a
picture.

Read the uncertainty band as: *"if the model is right on average, a
typical voxel's true temperature should be within this band of the
prediction most of the time."* That is enough for design screening --
compare predicted fields, spot the designs whose hot region is in the
wrong place, weed out clearly-too-hot designs early -- but it is not
enough for design certification. Run the real FE on the few candidates
that survive screening.

The **EXTRAPOLATION flag** fires if any input is outside the range of the
rows you trained on. Treat a flagged prediction as a prompt to run a real
FE simulation at that point -- the model has not seen anything like that
geometry / material / cooling / operating-point combination, and a field
prediction far outside the training range can be physically nonsensical
(the band widens to signal this, but a widened band is a warning, not a
correction).

### Seeing the field -- turning 768 numbers back into a picture

The whole point of a field surrogate is that you can *look* at the
predicted temperature map. The field CSV the predictor writes has one row
per voxel with columns `flat_index, i, j, k, temp_C` (single-point mode)
or one row per design point with 768 voxel columns (batch mode). To plot
it, re-fold the 768 numbers back into a 12 x 8 x 8 array using the
documented ordering (`i` along the length, `j` across the width, `k`
through the thickness) and slice it. For example, in Python:

```
import numpy as np, csv
# single-point mode file:
vals = {}
with open("predicted-field.csv") as f:
    for row in csv.DictReader(f):
        vals[(int(row["i"]), int(row["j"]), int(row["k"]))] = float(row["temp_C"])
T = np.zeros((12, 8, 8))
for (i, j, k), v in vals.items():
    T[i, j, k] = v
# a mid-thickness slice along length x width, the usual "top view":
import matplotlib.pyplot as plt
plt.imshow(T[:, :, 4].T, origin="lower", aspect="auto")
plt.xlabel("length index i"); plt.ylabel("width index j")
plt.colorbar(label="temperature (deg C)"); plt.show()
```

You do not need to write code to *use* the model -- the summary the
predictor prints (peak, where it is, mean, coolest) is enough to screen
designs. The plotting is for when you want to see the map. Any tool that
reads a CSV and draws a heat-map works; the reshape order is the only
thing you must get right, and it is the same order documented in the data
contract.

---

## 6. Reading the results responsibly

A trained surrogate is a *fast approximation* of a slower but more
trustworthy model -- and the slower model is itself an approximation of
the real physical component. The conduction-equation FE machinery this
example sits on is the same widely-used finite-element practice the
scalar thermal example (`peak-temperature`) builds on, anchored in the
standard heat-transfer references ([Bergman2017] for the conduction
equation and the Biot / Fourier dimensionless framework, [Patankar1980]
for the discretisation family). A surrogate trained on
thermal-FE fields inherits the FE's strengths *and* its limitations: the
surrogate can run faster than the FE; it cannot be more accurate than the
FE. If your FE runs themselves use the wrong material model, mis-specified
boundary conditions, or a too-coarse mesh, the surrogate will reproduce
that inaccuracy faithfully.

Three reading rules:

1. **Trust the surrogate inside the training range; distrust it
   outside.** The trainer captures the min/max of each input column you
   fed it. When you ask for a prediction at an input value outside that
   range, the predictor flags it. A flagged prediction is a candidate for
   a real FE check, not a final answer -- and for a *field* the failure is
   more visible than for a scalar: an out-of-range field can show
   physically impossible structure (sub-ambient interior, an
   inverted gradient), which is the field-level tell that you have left
   the training envelope.
2. **What a field error looks like, and where to look for it.** A field
   surrogate's error is not spread evenly. The mean relative L2 error is
   a whole-field average; the *worst* error is almost always at the
   sharpest features -- the hottest voxel, the steepest gradient near the
   heat-source-attachment face, and the edges of the grid. When you
   compare a predicted field to a real FE field, look first at (a) the
   peak value and its location, (b) the gradient across the attachment
   face, and (c) the grid edges. A surrogate that gets the smooth interior
   right but rounds off the peak is the typical failure mode; the
   per-voxel MAE will look reassuring while the peak-temperature MAE tells
   the more honest story. Read both numbers, and trust the predicted *hot-
   spot location* more than its exact value.
3. **Material-property temperature dependence is the dominant thermal-
   surrogate-failure mode.** In thermal work,
   surrogates trained on constant-k data systematically mis-predict in
   regimes where k(T) varies materially (high-temperature aerospace
   alloys, polymer composites near glass-transition, electronics-packaging
   materials across wide operating-temperature windows). This contract
   treats `conductivity_W_mK` as a single scalar per run; if your high-
   fidelity FE uses temperature-dependent `k(T)`, either report the
   effective k at the run's mean temperature (and accept the
   simplification) or treat the strongly-`k(T)`-dependent regime as out of
   scope for this surrogate. A field surrogate makes this failure *more
   legible*: a constant-k field surrogate will systematically distort the
   gradient in the hottest region, which a field plot shows at a glance
   even when the peak value looks plausible.

The model is a design-screening tool. It is not a design-certification
tool.

---

## 7. What's happening inside (optional, one page)

*This page is strictly optional. Skip it if you just want to use the
model.*

The architecture inside the trainer is a **dense field decoder**: a
fully-connected neural network (scikit-learn's `MLPRegressor`, two hidden
layers) that maps the seven standardised inputs to all 768 standardised
voxel temperatures at once. In plain words: it learns one big smooth
function from "the seven design numbers" to "the temperature at every
point of the grid," with the field's values standardised during training
(so every voxel trains evenly) and de-standardised on output. The seven
inputs and the field are both scaled to comparable ranges first, which is
what lets the network converge quickly on a CPU.

The "7 inputs -> 768-voxel field" mapping the model learns is, under the
hood, related to the analytical pin-fin solution for steady-state
conduction with internal heat generation and convective lateral cooling
-- the same closed form the scalar `peak-temperature` used for its peak, now
giving the temperature *everywhere along and across* the component rather
than only at the maximum. The classic fin equation produces a temperature
profile along the cooling axis; the cross-section terms (cooler toward the
cooled faces, warmer in the core) give the field its width- and
thickness-direction structure. The surrogate learns the whole field *from
your data* rather than being told the closed form, and it picks up the
geometry-specific corrections no single analytical formula captures
cleanly. That is the pedagogical point of stepping one cell right on the
grid: when your downstream question is "what does the temperature map look
like," not just "how hot does it get," the output shape changes from a
scalar to a field, and the bucket changes from B1 to B2 -- but the input
side, the data discipline, and the click-to-run workflow are unchanged.

**Why a dense decoder and not a convolutional network.** The canonical
*production* architecture for this case is a **3-D U-Net / dense 3-D
CNN** -- a network with spatial convolutions that share filters across
the grid and exploit the field's spatial structure directly. That
architecture typically reaches a tighter field accuracy and scales to
larger grids, but it is GPU-friendly and materially heavier to train and
to package as a double-click executable. This example ships the simpler
dense decoder so it trains on a CPU in well under a minute. The
convolutional / U-Net variant is the natural upgrade -- the
field-example analogue of the scalar examples' Gaussian-Process variant.
The bucket is **B2 either way**: the classifier attribute is the
regular-grid field *output*, not the decoder's internals.

The Biot number `Bi = h * L_c / k` and the Fourier number `Fo` are the
load-bearing dimensionless groups for the heat equation, and
non-dimensionalising the problem in Biot / Fourier scaling is the single
load-bearing surrogate-generalisation lever for thermal problems. This
example ships the *dimensional* form (raw mm / W / deg C inputs) for
reader-clarity; a non-dimensional variant is a natural extension.

The **uncertainty band** is the held-out per-voxel mean absolute error
scaled by 1.5 -- a rough "one sigma" by analogy -- widened by an extra
2x per unit of extrapolation distance, so predictions far outside the
training range carry visibly larger bands. The convolutional upgrade
would also open the door to a calibrated per-voxel posterior-variance
band (the field analogue of the scalar GP variant), which the dense
decoder shipped here does not provide.

---

## 8. Where to go next

The natural reading order around this example:

- **`peak-temperature` -- Peak Temperature of a Cooled Component.** The
  scalar example this one bridges from -- the *same* seven thermal
  inputs, with the output a single peak number instead of the whole
  field. Reading the two back to back is the cleanest way to see what
  "stepping one cell right on the grid" means: same physics, same
  inputs, the output grows from a scalar (Bucket B1) to a field (Bucket
  B2).
- **`drag-lift` -- Drag and Lift of an Off-Road Vehicle.** The
  external-aero B1. Its downward neighbour on the grid (`n=2, m=1`,
  `drag-from-shape`) is the *other* single-step move off B1 -- a richer
  input rather than a richer output.

---

## Setup

The workflow this walkthrough describes runs as standalone executables
on Windows, with no install step: double-click
`Train-Temperature-Field.exe`, then double-click the
`Predict-Temperature-Field.exe` the trainer drops into a
`trained-model` folder. Those executables, and the Python trainer they
are built from, are not part of this repository. What ships here is the
data contract, the template, and the synthetic sample dataset with its
generator (`python data/synthesize_sample.py`).
