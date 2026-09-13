# TASK-8-1202 -- Predicting the Temperature Field of a Cooled Plate

### A step-by-step worked example for CAE engineers -- no ML background needed

This example builds a fast surrogate for the **steady-state temperature
field of a flat cooled plate** carrying a discrete heat source -- a
heat-spreader / cold-plate, the everyday geometry of electronics cooling.
You hand the model the plate's design and operating numbers; it hands back
the whole temperature map across the plate, in a fraction of a second.

It is the arc's **second field-output example**, and it is deliberately
the *same* kind of model as `TASK-8-1201` (the cooling-fin temperature
field) on a **different component geometry**. If you have read
`TASK-8-1201`, you will meet **no new machine-learning idea here** -- only
a different physical setup wearing the same data contract. That is the
point of the pairing: it shows the field-output recipe is not tied to one
component shape.

---

## 1. What this example does

Running a steady-state thermal finite-element analysis to get the
temperature field of a cooled plate typically takes seconds to minutes
per design -- fast enough for one analysis, but slow enough that running
the full FE for every candidate during a parameter sweep across plate
size, material, cooling, source size, and source power adds up quickly.
When you are laying out a heat-spreader or sizing a cold-plate, running
the full thermal FE for every combination becomes the bottleneck on how
broadly you can search.

`TASK-8-1201` built a field surrogate for an extruded **cooling fin** --
heat conducting along a length from a hot base to a cooled tip. This
example builds the same kind of surrogate for a different geometry: a
**flat plate with a localised heat source** on its top face, where heat
**spreads in-plane** away from the source as the plate carries it off to
the coolant. The fin's field is a profile along its length; the plate's
field is a spreading map -- hot under the source, cooling radially
outward. Same physics family (steady-state conduction with convective
cooling, TASK-1 A.3.1), different geometry and boundary conditions.

This example builds a **field surrogate**: a fast model that has learned,
from a batch of steady-state thermal FE runs you have *already* done, the
relationship between a plate's input vector (size + material + cooling +
source size + source power) and the **whole temperature field** laid out
on a fixed grid. Once trained, it returns the entire field in a fraction
of a second, so you can see the predicted temperature map for hundreds of
plate designs before committing solver time to the handful that matter.

**Where this sits in the taxonomy.** The model takes a *row of numbers*
(eight plate design / operating parameters) and returns a *field on a
regular grid* (a temperature at every voxel of a fixed 16 x 16 x 4
lattice -- 1024 numbers). On the BRIDGE-A slide-9 grid that is one cell to
the **right** of the top-left corner -- *parametric input -> regular-grid-
field output* (cell `n=1, m=2`) -- which is **Bucket B2, the regular-grid
field surrogate**. It is the arc's **second** example in this cell, after
`TASK-8-1201`.

> **Why this example is admitted (the admission record).** The arc built
> its first six examples in the simplest grid cell (B1, scalar output),
> then stepped one cell right with `TASK-8-1201` and one cell down with
> `TASK-8-2101`. This example is a **second instance of the rightward
> (n=1, m=2) cell** rather than a step to a new cell. It clears the arc's
> admission checklist (`EXAMPLES-ARC-SCOPING.md` section 7, the "S-4"
> gate) on these points:
> 1. **Its grid cell and bucket are named explicitly:** slide-9 cell
>    `n=1, m=2`; Bucket **B2**. B2's defining test is "the output is a
>    field on a regular Cartesian grid; spatial structure is
>    exploitable" -- which this plate temperature field is.
> 2. **It cites the canonical catalog row it instantiates:** TASK-4
>    Bucket-B2 roster, the **A.3.1 row** -- "volumetric temperature
>    scalar field T(x) on regular voxel grids (electronics-cooling ...)
>    -> 3-D U-Net / dense 3-D CNN for regular-grid thermal fields." A flat
>    heat-spreader with a discrete source is a textbook electronics-
>    cooling instance of that row.
> 3. **It is the cheapest kind of new example: a second-domain-family add
>    to a built cell.** It introduces **no new ML idea** relative to
>    `TASK-8-1201` -- same Bucket B2, same dense field-decoder, same data-
>    contract shape -- and changes only the *geometry / boundary-condition
>    family* (a plate with an in-plane-spreading source instead of a fin)
>    and the *grid shape* (16 x 16 x 4 instead of 12 x 8 x 8). Its
>    pedagogical job is to show the field-output template generalises
>    across geometry families within a domain, not only across domains.
>    (This admission basis is recorded as the Direction-1, second-domain-
>    add candidate in `EXAMPLES-ARC-SCOPING.md` section 12.2; note it
>    differs from the new-physics-domain rationale section 12.2 sketches
>    for the aero / EM alternatives -- this build chose the same-domain,
>    different-geometry variant, which is an even smaller step.)

Catalog reference: analysis **A.3.1** (FEA family, Thermal Steady-state
conduction / convection) in `tasks/TASK-1-cae-analysis-catalog.md`. Arc
inventory record: `EXAMPLES-ARC-SCOPING.md` section 12.2 (the
second-domain-add lead candidate) and section 4.2.

The four steps ahead:

```
   Step 1                              Step 2                                        Step 3
  Format    -->    Train-Plate-Temperature-Field.exe   -->    Predict-Plate-Temperature-Field.exe
  your data        (makes the                                  (use the trained model on
  (a CSV)          trained model)                               new plate designs -> fields)
```

---

## 2. What you'll need before you start

- **A batch of steady-state thermal FE runs you have already
  completed.** Each run is one plate design -- size + material + cooling
  boundary + source footprint + source power -- analysed through your
  normal steady-state thermal FE process (ANSYS Mechanical Steady-State
  Thermal / Abaqus Heat Transfer / MSC Nastran SOL 153 / Simcenter 3D
  Thermal / COMSOL Heat Transfer Module -- any of the standard workflows
  produces a temperature field). For each run you must know the eight
  input parameters you used **and** the temperature field the run
  produced, resampled onto the fixed grid (see Step 1 -- this resampling
  is the one genuinely new piece of work this example asks of you, exactly
  as in `TASK-8-1201`).
- **At least 80 runs**; 400 - 600 is healthy, and a field with in-plane
  spreading structure rewards the larger end. The plate's field *shape*
  varies more across the design space than the fin's did (the spreading
  pattern changes a lot between a tiny hot source on a big copper plate
  and a broad source on a small low-conductivity plate), so the dense
  decoder benefits from more examples than `TASK-8-1201` needed. A
  practical DOE shape: ~50 plate / source-geometry combinations x ~10
  material / cooling variations, about 500 rows.
- The eight inputs are listed in `data/data-contract.md`: plate length,
  plate width, plate thickness, thermal conductivity, convective
  heat-transfer coefficient, ambient temperature, **heat-source footprint
  size**, and total source power. The seventh input -- the source size --
  is the new geometry knob this plate introduces; the fin example had no
  localised source. The **target is the temperature field**: 1024 voxel
  temperatures on the fixed 16 x 16 x 4 grid.
- **Steady-state regime only.** This example assumes steady-state thermal
  FE: the field has reached equilibrium, no transient warm-up /
  cool-down, no phase change. A transient or phase-change problem is a
  different bucket. The trainer does not detect transient inputs
  automatically; honour this constraint upstream.
- **Single-class boundary conditions per dataset.** Train one surrogate
  per boundary-condition class (a localised top-face source + Robin
  convection on the plate faces is the default here). Mixing a
  face-convection-cooled plate with a liquid-cold-plate (heat pulled out
  through the bottom face) in one dataset gives the surrogate an
  unobserved hidden variable that silently degrades accuracy -- this is
  TASK-1 A.3.1 Pitfall (ii).
- A Windows PC. See *Setup* at the end of this document -- there is no
  install step.

You do **not** need a GPU, an internet connection while training, Python,
or any ML software. Everything the example needs is inside the
executables. (The dense field-decoder this example ships is deliberately
CPU-trainable; see Step 2 and section 7.)

> **If you just want to see it work first:** this example ships with a
> synthetic `data/sample-dataset.csv` (500 rows generated by an
> analytical plate-spreading field pastiche -- a Gaussian-blurred source
> on a fixed grid with a small through-thickness gradient). You can run
> Steps 2 and 3 on that immediately, before you have prepared any real
> data. The sample data is **illustrative only** -- it is *not* real FE
> data and its accuracy figures tell you nothing about what you will get
> on your own runs.

---

## 3. Step 1 -- Format your data

The trainer reads one CSV file. It must have the eight input columns,
then 1024 field columns (`T_0000` ... `T_1023`), then an optional `notes`
column, in that order, with one row per FE run. Open `data/template.csv`
for the empty starting form; the column header row is already in place.

The input columns, in order, are:

1. `length_mm` -- plate length, an in-plane direction (mm)
2. `width_mm` -- plate width, the other in-plane direction (mm)
3. `thickness_mm` -- plate thickness, the short through-thickness dim (mm)
4. `conductivity_W_mK` -- thermal conductivity `k` of the plate material (W/(m K))
5. `h_W_m2K` -- convective heat-transfer coefficient on the cooled faces (W/(m^2 K))
6. `T_ambient_C` -- ambient / coolant temperature (deg C)
7. `src_size_mm` -- heat-source footprint side, a square source on the top face (mm)
8. `q_W` -- total heat-source power deposited on the plate (W)

The 1024 target columns are the temperature field. Here is the one new
idea this example asks you to absorb (the same idea as `TASK-8-1201`):

> **You must resample your FE field onto a fixed grid.** Your solver
> produces a temperature field on its own mesh, which is unstructured
> and different for every run. Before filling the template, sample that
> field onto a normalised **16 x 16 x 4** grid spanning the plate's
> bounding box: 16 points along the length, 16 across the width, 4 through
> the thickness. Every run reports its field on this *same* grid, so every
> row of the dataset has the same 1024 field columns in the same order.
> The flatten order is documented in `data/data-contract.md`: column
> `T_<flat>` is voxel `(i, j, k)` with `flat = (i * 16 + j) * 4 + k` --
> `i` and `j` the two in-plane directions, `k` through the thickness
> (`k = 0` is the cooled bottom face, `k = 3` is the heated top face). Use
> the **same** bounding-box and interpolation convention for every run; a
> mis-ordered or differently-gridded field silently corrupts the
> surrogate, and the trainer can only check the column *count* and
> *names*, not the physical ordering.

Note the grid shape (16 x 16 x 4) is **different** from `TASK-8-1201`'s
(12 x 8 x 8): a plate's structure lives in-plane, so the grid is dense in
the two face directions and thin through the thickness. The contract is
keyed to a *fixed* grid, not to one particular shape -- a different
geometry naturally wants a different grid, and that is fine as long as it
is fixed across every row of *this* dataset.

Most FE post-processors can export a field sampled on a regular grid
(ANSYS "Export -> Grid", a probe grid in Abaqus/CAE, a structured
interpolation in ParaView / pyvista). Set up the grid sampling once and
reuse it across the DOE.

`notes` is optional and ignored by the trainer; use it for run IDs or
DOE labels if helpful. The data contract documents the sign conventions:
`T_ambient_C` and every `T_<flat>` are on the Celsius scale (pick one
scale and apply it across all rows -- the trainer does not
non-dimensionalise); `q_W` is the *total* source power in watts, not a
flux density; the grid orientation is fixed (`k = 0` cooled bottom face,
`k = 3` heated top face carrying the source).

> **One modelling assumption to know about.** The shipped sample data
> places the heat source at the **centre** of the plate's top face for
> every run. If in your real data the source position moves around
> run-to-run, that position is an *extra input* the model needs -- add
> `src_x_frac` / `src_y_frac` columns and extend the contract, or hold the
> source centred as the sample does. Do not let the source wander while
> leaving its position out of the inputs; that is a hidden variable the
> model cannot see. (See `data/data-contract.md` rule 8.)

Your file should look like the sample dataset.

---

## 4. Step 2 -- Train the model

Double-click `Train-Plate-Temperature-Field.exe`. The trainer asks for the
path to your CSV. Point it at the file from Step 1 (or, to see the
workflow run first, at `data/sample-dataset.csv`).

The trainer:

1. Checks every column matches the data contract -- the eight inputs and
   all 1024 field columns, in order; if not, it prints exactly which
   column is wrong and stops.
2. Trains a **field-decoder surrogate** -- a model that maps the eight
   inputs to all 1024 voxel temperatures at once. The training takes a
   little longer than a scalar model (a field has many more output values
   per run) but is still CPU-only and finishes in well under a minute on a
   500-row dataset.
3. Prints a **held-out field-accuracy report**: it sets aside ~20 % of
   your rows, does not look at them while learning, then checks itself
   against them. Because the output is a field, the report shows
   field-level figures rather than a single per-target error (see "What
   field accuracy means" below).
4. Writes a `trained-model` folder next to your CSV, containing the
   trained predictor (`Predict-Plate-Temperature-Field.exe`) ready to use.

On the synthetic sample dataset (500 rows) the held-out report is:

| Field-accuracy figure              | Value      |
|------------------------------------|------------|
| Mean relative L2 error (fraction)  | ~0.12      |
| Per-voxel mean absolute error      | ~3.1 deg C |
| Peak-temperature mean abs error    | ~5.9 deg C |

**These figures are illustrative.** They come from the synthetic sample
data, not from real FE. Your accuracy on your own data depends on your
data -- the number of runs, how well they cover the design space, and the
smoothness of the underlying FE response. (The relative-L2 here, ~0.12,
is a touch higher than `TASK-8-1201`'s ~0.08 because the plate's in-plane
spreading field varies more in *shape* across the design space than the
fin's did; a larger dataset closes the gap, which is why the sample ships
500 rows rather than 250 -- see the data contract, rule 10.)

**What field accuracy means.** A scalar surrogate reports one error
number per target. A field surrogate reports an error over the whole grid,
so the trainer prints two field-level figures (plus a peak summary):

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
  single hottest voxel of the predicted field is, on average. For a plate
  with a localised source the peak sits right under the source, so this
  number tells you how well the surrogate nails the worst-case
  temperature -- usually the number you care about most.

---

## 5. Step 3 -- Use the trained model

Double-click `Predict-Plate-Temperature-Field.exe` in the `trained-model`
folder. It asks how you want to use the model:

- **[1] One new design point by hand.** It prompts for each of the eight
  inputs, then prints a **summary of the predicted field** -- the peak
  temperature and where it sits on the grid, the mean temperature, the
  coolest voxel, and a per-voxel uncertainty band -- and writes the full
  1024-voxel field to `predicted-field.csv` in the `trained-model` folder.
- **[2] A CSV of many points.** Pass a CSV with the eight input columns.
  It writes two files next to your input: a `*-field-summary.csv` with one
  row per design point (the inputs, the peak / mean / coolest
  temperatures, the hot-spot grid location, and an extrapolation flag),
  and a `*-fields.csv` with the full 1024-voxel field for every point (one
  row per point, voxel columns `T_0000` ... `T_1023`).

Because a field is 1024 numbers, the predictor does not print it to the
screen -- it prints the summary and writes the field to a file you can
open or plot. The next section shows how to turn that file back into a
picture.

Read the uncertainty band as: *"if the model is right on average, a
typical voxel's true temperature should be within this band of the
prediction most of the time."* That is enough for design screening --
compare predicted fields, spot the designs whose hot region is too hot or
too broad, weed out clearly-too-hot designs early -- but it is not enough
for design certification. Run the real FE on the few candidates that
survive screening.

The **EXTRAPOLATION flag** fires if any input is outside the range of the
rows you trained on. Treat a flagged prediction as a prompt to run a real
FE simulation at that point -- the model has not seen anything like that
plate size / material / cooling / source combination, and a field
prediction far outside the training range can be physically nonsensical
(the band widens to signal this, but a widened band is a warning, not a
correction).

### Seeing the field -- turning 1024 numbers back into a picture

The whole point of a field surrogate is that you can *look* at the
predicted temperature map. The field CSV the predictor writes has one row
per voxel with columns `flat_index, i, j, k, temp_C` (single-point mode)
or one row per design point with 1024 voxel columns (batch mode). To plot
it, re-fold the 1024 numbers back into a 16 x 16 x 4 array using the
documented ordering (`i` and `j` in-plane, `k` through the thickness) and
slice it. For a plate the most useful view is the **top face** (the
heated surface, `k = 3`). For example, in Python:

```
import numpy as np, csv
# single-point mode file:
vals = {}
with open("predicted-field.csv") as f:
    for row in csv.DictReader(f):
        vals[(int(row["i"]), int(row["j"]), int(row["k"]))] = float(row["temp_C"])
T = np.zeros((16, 16, 4))
for (i, j, k), v in vals.items():
    T[i, j, k] = v
# the heated top face (k = 3), the usual "what does the hot spot look like" view:
import matplotlib.pyplot as plt
plt.imshow(T[:, :, 3].T, origin="lower", aspect="equal")
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
example sits on is the same widely-used finite-element practice the scalar
thermal example (`TASK-8-1104`) and the fin field example (`TASK-8-1201`)
build on; TASK-1 A.3.1 anchors it in the standard heat-transfer
references ([Bergman2017] for the conduction equation and the Biot /
Fourier dimensionless framework, [Patankar1980] for the discretisation
family). A surrogate trained on thermal-FE fields inherits the FE's
strengths *and* its limitations: the surrogate can run faster than the FE;
it cannot be more accurate than the FE. If your FE runs themselves use the
wrong material model, mis-specified boundary conditions, or a too-coarse
mesh, the surrogate will reproduce that inaccuracy faithfully.

Three reading rules:

1. **Trust the surrogate inside the training range; distrust it
   outside.** The trainer captures the min/max of each input column you
   fed it. When you ask for a prediction at an input value outside that
   range, the predictor flags it. A flagged prediction is a candidate for
   a real FE check, not a final answer -- and for a *field* the failure is
   more visible than for a scalar: an out-of-range field can show
   physically impossible structure (sub-ambient interior, an inverted
   gradient), which is the field-level tell that you have left the training
   envelope.
2. **What a field error looks like, and where to look for it.** A field
   surrogate's error is not spread evenly. The mean relative L2 error is a
   whole-field average; the *worst* error is almost always at the sharpest
   feature -- for a plate with a localised source, that is **the hot spot
   right under the source**, where the field is most peaked. When you
   compare a predicted field to a real FE field, look first at (a) the
   peak value and its location on the top face, (b) how fast the
   temperature falls off away from the source (the spreading gradient),
   and (c) the grid edges. A surrogate that gets the cool perimeter right
   but rounds off the peak under the source is the typical failure mode;
   the per-voxel MAE will look reassuring while the peak-temperature MAE
   tells the more honest story. Read both numbers, and trust the predicted
   *hot-spot location* more than its exact value.
3. **Material-property temperature dependence is the dominant thermal-
   surrogate-failure mode.** Per TASK-1 A.3.1 Pitfall (i) and ROADMAP A.3,
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
   spreading gradient around the hot source, which a top-face plot shows
   at a glance even when the peak value looks plausible.

The model is a design-screening tool. It is not a design-certification
tool.

---

## 7. What's happening inside (optional, one page)

*This page is strictly optional. Skip it if you just want to use the
model.*

The architecture inside the trainer is a **dense field decoder**: a
fully-connected neural network (scikit-learn's `MLPRegressor`, two hidden
layers) that maps the eight standardised inputs to all 1024 standardised
voxel temperatures at once. In plain words: it learns one big smooth
function from "the eight design numbers" to "the temperature at every
point of the grid," with the field's values standardised during training
(so every voxel trains evenly) and de-standardised on output. The eight
inputs and the field are both scaled to comparable ranges first, which is
what lets the network converge quickly on a CPU. **This is exactly the
same architecture as `TASK-8-1201`** -- only the input count (8 vs 7), the
grid shape (16 x 16 x 4 vs 12 x 8 x 8), and the training data differ. That
is the whole point of a second-instance example: the recipe is unchanged.

The "8 inputs -> 1024-voxel field" mapping the model learns is, under the
hood, related to the analytical solution for steady-state heat spreading
from a localised source on a convectively-cooled plate -- a hot patch
whose temperature rise decays as the plate carries heat away in-plane,
with a small drop through the thickness from the heated top face to the
cooled bottom. The surrogate learns the whole field *from your data*
rather than being told the closed form, and it picks up the
geometry-specific corrections no single analytical formula captures
cleanly. Where `TASK-8-1201`'s fin field was governed by conduction along
a length, this plate's field is governed by **in-plane spreading** -- the
balance between how far the conductivity carries heat sideways and how
fast the convection pulls it out. That balance (high-k / low-h plates
spread heat far and run cooler and flatter; low-k / high-h plates keep the
heat local and run hotter and more peaked) is the structure the decoder
learns.

**Why a dense decoder and not a convolutional network.** TASK-4's Bucket-
B2 roster names the canonical *production* architecture for this row as a
**3-D U-Net / dense 3-D CNN** -- a network with spatial convolutions that
share filters across the grid and exploit the field's spatial structure
directly. That architecture typically reaches a tighter field accuracy and
scales to larger grids, but it is GPU-friendly and materially heavier to
train and to package as a double-click executable. This example ships the
simpler dense decoder so it trains on a CPU in well under a minute and
keeps the arc's click-to-run promise -- the same choice `TASK-8-1201`
made. The convolutional / U-Net variant is the **planned-but-deferred
upgrade** -- the field-example analogue of the scalar examples' deferred
Gaussian-Process variant -- and is recorded in `EXAMPLES-ARC-SCOPING.md`
section 12. The bucket is **B2 either way**: the classifier attribute is
the regular-grid field *output*, not the decoder's internals.

The Biot number `Bi = h * L_c / k` is the load-bearing dimensionless group
for the heat equation; per ROADMAP A.3, non-dimensionalising the problem
in Biot / Fourier scaling is the single load-bearing surrogate-
generalisation lever for thermal entries. This example ships the
*dimensional* form (raw mm / W / deg C inputs) for reader-clarity; a
future iteration may add a non-dimensional variant.

The **uncertainty band** is the held-out per-voxel mean absolute error
scaled by 1.5 -- a rough "one sigma" by analogy -- widened by an extra 2x
per unit of extrapolation distance, so predictions far outside the
training range carry visibly larger bands. The convolutional upgrade would
also open the door to a calibrated per-voxel posterior-variance band (the
field analogue of the scalar GP variant), which the dense decoder shipped
here does not provide.

---

## 8. Where to go next

The natural reading order around this example:

- **`TASK-8-1201` -- Temperature Field of a Cooled Component (fin).** The
  closest sibling -- the *same* Bucket-B2 field-output recipe on a
  *different* geometry (an extruded cooling fin instead of a flat plate)
  and a different grid (12 x 8 x 8 instead of 16 x 16 x 4). Reading the two
  back to back is the cleanest way to see that the field-output template
  generalises across geometry families, not just across physics domains --
  which is exactly why this example exists.
- **`TASK-8-1104` -- Peak Temperature of a Cooled Component.** The scalar
  (Bucket B1) thermal ancestor of the field line: the same physics family,
  output a single peak number instead of a whole field. The B1 -> B2 step
  (scalar -> field) is what `TASK-8-1201` and this example both build on.
- **`TASK-8-2101` -- Drag of a Body from its Shape Image.** The arc's
  *downward* single-step move off B1 (a richer input -- a shape image --
  rather than a richer output). Reading it alongside the field examples
  shows the two directions you can step away from the simple tabular
  corner.
- **The BRIDGE-A deck** in `presentations/` for the conceptual framing of
  the slide-9 grid and how the bucket choice falls out of the input/output
  shape. This example is a worked instance of the grid's `n=1, m=2` cell.

---

## Setup

This example runs as standalone executables on Windows. There is no
install step: download the `TASK-8-1202-plate-temperature-field/` folder,
double-click `Train-Plate-Temperature-Field.exe`, then double-click the
`Predict-Plate-Temperature-Field.exe` the trainer drops into a
`trained-model` folder. No Python required.

(If you are running the *interim* form -- `Train.bat` / `Predict.bat` in
`trainer/` -- Python 3.10+ with `scikit-learn` and `numpy` installed is
required. The interim form ships in the source repo as a fallback for
build hosts that do not yet have the standalone build; the reader-facing
form is the standalone build.)
