# Predicting Drag from a Shape Image

### A step-by-step worked example for CAE engineers -- no ML background needed

> One of the worked cells in `examples/worked-cells/`. It sits in the
> regular-grid (image-like) input / scalar-output cell of the
> input/output grid (`n=2, m=1`): the second worked cell outside Bucket
> B1 and the first to take an **image** as input. It bridges directly
> from `drag-lift` (drag and lift): the target is the same drag
> coefficient CD (and lift CL); only the input grows, from a parameter /
> assembly vector to a picture of the geometry.
>
> **What ships here:** this walkthrough, the data contract, the template,
> and a synthetic sample dataset with the script that generates it. The
> trainer and predictor executables Steps 2 and 3 describe are not part
> of this repository, so read those steps as a description of the
> workflow rather than as something this folder can run.
>
> You will train a model and use it. You will **not** write code or make
> any machine-learning decisions. Everything runs by double-clicking a
> file.

---

## 1. What this example does

Running an external-aero CFD case to get the drag of a body typically
takes hours per shape. When you are exploring a shape design space --
trying different body profiles, tapers, roof lines, ride heights -- running
the full CFD for every candidate is the bottleneck on how broadly you can
search.

The parametric drag-lift example (`drag-lift`) built a surrogate that
took a *row of design numbers* (which assembly options, what speed, what
yaw) and predicted the force coefficients. That works when your design
space is a catalog of discrete options. But sometimes the thing that
drives drag is the *shape itself* -- a subtle taper, a roof curve, how
blunt the tail is -- and two designs with the same option codes can have
quite different drag. For that you want to hand the model the **geometry**,
not a list of option numbers.

This example builds a surrogate that reads a **picture of the body
cross-section** -- a signed-distance-field (SDF) image on a fixed pixel
grid -- and predicts the drag coefficient CD (and lift CL) at a fixed
operating point. Once trained, it returns the coefficients in a fraction
of a second for any shape you can draw, so you can screen hundreds of
candidate profiles before committing CFD time to the few that matter. The
point is that the model sees the *actual silhouette*, so it can pick up
the drag-driving geometry features a parametric vector could not encode.

**Where this sits in the taxonomy.** The model takes a *regular-grid
image* (a 16 x 24 SDF of the body, 384 pixels) and returns a *scalar*
(CD, and CL). On the input/output grid that is one cell **down** from
the top-left corner -- *image-like input -> scalar QoI output* (cell
`n=2, m=1`) -- which is **Bucket B2** routed by the *input* shape.

> **Why this example steps outside B1.** This is the second step off the
> B1 cell (the field example `temperature-field` is the first), on three
> grounds:
> 1. **Its grid cell and bucket are named explicitly:** cell
>    `n=2, m=1`; Bucket **B2**, routed **by input shape**. B2's defining
>    test is written about grid *outputs*, but this example has a grid
>    *input* and a scalar output; it routes to B2 because the
>    convolutional / image inductive bias is the load-bearing classifier
>    attribute. This by-shape edge-case routing is disclosed here rather
>    than smoothed over.
> 2. **It uses a standard image encoding and architecture:** geometry
>    encoded as an SDF (surface-normal maps and unwrapped surface
>    textures are the other usual choices), and the image-input aero CNN
>    (the encoder half of the surface-pressure U-Net, used here for
>    regression).
> 3. **It is a single-step bridge from a built example:** it changes *one*
>    thing relative to `drag-lift` -- the input goes from a parameter
>    vector to a shape image -- on a problem the reader has already seen as
>    a B1. The physics and the CD / CL target are unchanged.

The analysis is external-aero CFD.

The three steps ahead:

```
   Step 1                          Step 2                            Step 3
  Rasterise   -->    Train-Drag-Shape.exe   -->    Predict-Drag-Shape.exe
  your shapes        (makes the                     (use the trained model
  (SDF images)       trained model)                  on new shape images)
```

---

## 2. What you'll need before you start

- **A batch of external-aero CFD runs you have already completed**, each
  at the *same* operating point (a single reference speed / yaw). Each run
  is one body geometry analysed through your normal external-aero CFD
  process. For each run you must know the body's geometry (so you can
  rasterise it -- Step 1) and the drag / lift coefficients the run
  produced.
- **At least 80 runs**; 200 - 400 is healthy. The image input does not
  change how many runs you need -- the thing you are sampling is still the
  space of body shapes you care about -- so the minimum is the same 80 as
  the tabular examples. A richer input generally rewards more rows, so aim
  high if you can.
- The input is an **SDF image** of the body on the fixed 16 x 24 grid; the
  targets are **CD and CL**. All of this is specified in
  `data/data-contract.md`.
- **One operating point per dataset.** This example fixes the operating
  point and varies only the geometry. If your DOE also sweeps speed or
  yaw, either fix them for this surrogate or use the parametric
  `drag-lift` (which takes the operating point as input).
- A Windows PC. See *Setup* at the end -- there is no install step.

You do **not** need a GPU, an internet connection while training, Python,
or any ML software. Everything the example needs is inside the
executables. (The dense image-regressor this example ships is deliberately
CPU-trainable; see Step 2 and section 7.)

> **If you just want to see it work first:** this example ships with a
> synthetic `data/sample-dataset.csv` (250 bodies generated by an
> analytical shape-and-drag pastiche -- a family of tapered bluff bodies
> rasterised to SDFs, with a deterministic drag/lift computed from their
> shape descriptors). You can run Steps 2 and 3 on that immediately. The
> sample data is **illustrative only** -- it is *not* real CFD and its
> accuracy figures tell you nothing about what you will get on your own
> runs.

---

## 3. Step 1 -- Rasterise your shapes into SDF images

This is the one step where you do real work, and it is the new idea in
this example. The trainer reads one CSV file whose first 384 columns are
the SDF image of the body, then `CD` and `CL`, then an optional `notes`
column. Open `data/template.csv` for the empty starting form.

The model does not read your CAD file -- it reads a **picture** of the
body on a fixed grid. So before you can train, you turn each body's
geometry into that picture:

> **Rasterise each body to a signed-distance field on the fixed 16 x 24
> grid.** Pick a fixed physical window (a rectangle in the flow plane,
> flow left-to-right, ground at the bottom) big enough to contain any body
> in your study. Lay the 16 x 24 grid over it. At each of the 384 pixels,
> compute the **signed distance** to the body's surface: negative inside
> the body, positive outside, zero on the surface, in grid-cell units.
> That array of 384 numbers is the image. Flatten it in row-major order --
> column `S_<flat>` is pixel `(iy, ix)` with `flat = iy * 24 + ix`, `iy`
> the vertical index (0 at the bottom), `ix` the streamwise index (0 at
> the front). The data contract documents this convention exactly.

Why an SDF and not just a black-and-white "is this pixel inside the body"
mask? Because the SDF is smooth -- it varies gradually from pixel to pixel
instead of jumping from 0 to 1 at the surface -- which is a far easier
thing for a model to learn from. That is exactly why the SDF is one of
the standard geometry-as-image encodings.

Most CFD pre/post tools can produce a regular-grid sample of a
distance-to-surface field (a level-set / signed-distance utility, or a
short script over your surface mesh). Set the window and grid up **once**
and reuse them for every body -- a body rasterised in a different window
or a flipped orientation is, to the model, a different shape, and the
trainer can only check the column count and names, not the physical
framing. This is the image-example equivalent of the tabular examples'
"use the same parameter definitions across all rows" rule.

`notes` is optional and ignored by the trainer. Your file should look like
the sample dataset.

---

## 4. Step 2 -- Train the model

Double-click `Train-Drag-Shape.exe`. The trainer asks for the path to your
CSV. Point it at the file from Step 1 (or, to see the workflow run first,
at `data/sample-dataset.csv`).

The trainer:

1. Checks every column matches the data contract -- the 384 SDF columns,
   then CD and CL, in order; if not, it prints exactly which column is
   wrong and stops.
2. Trains an **image-regressor surrogate** -- a model that reads the
   flattened 384-pixel SDF and predicts CD and CL. The training takes a
   little longer than a tabular model (an image has many more input values
   per row) but is still CPU-only and finishes in well under a minute on a
   250-shape dataset.
3. Prints a **held-out accuracy report**: it sets aside ~20 % of your
   shapes, does not look at them while learning, then checks itself
   against them. The report shows the average absolute error and the
   R-squared for CD and CL separately -- exactly like a tabular example's
   report, because the *output* is still a scalar.
4. Writes a `trained-model` folder next to your CSV, containing the
   trained predictor (`Predict-Drag-Shape.exe`) ready to use.

On the synthetic sample dataset (250 shapes) the held-out report is:

| Target | Avg error (MAE) | R-squared |
|--------|-----------------|-----------|
| `CD`   | ~0.046          | ~0.93     |
| `CL`   | ~0.038          | ~0.86     |

**These figures are illustrative.** They come from the synthetic sample
data, not from real CFD. Your accuracy on your own data depends on your
data -- the number of shapes, how well they cover the design space, and
how cleanly drag depends on geometry in your regime.

---

## 5. Step 3 -- Use the trained model

Double-click `Predict-Drag-Shape.exe` in the `trained-model` folder. It
asks how you want to use the model. Because the input is an image of 384
numbers, you do not type it in by hand -- you point the predictor at a CSV
that holds the image(s):

- **[1] One new shape.** Point it at a CSV with that one body's 384 SDF
  columns (one data row -- the same format as a single row of the training
  file). It prints the predicted CD and CL, each with an *uncertainty
  band* derived from the held-out accuracy report.
- **[2] Many shapes.** Point it at a CSV with one row per body (the same
  384-SDF-column format as the training file; any `CD` / `CL` columns are
  ignored). It writes a `*-predictions.csv` next to your input with the
  predicted CD / CL, the lo/hi uncertainty range for each, and an
  extrapolation flag.

Read the uncertainty band as: *"if the model is right on average, the true
answer should be within this range most of the time."* That is enough for
design screening -- rank candidate shapes, weed out clearly-too-draggy ones
early -- but it is not enough for design certification. Run the real CFD on
the few shapes that survive screening.

The **EXTRAPOLATION flag** fires when the new shape's overall size or
extent is outside the range of shapes you trained on -- the body is much
larger, smaller, or more extreme than anything the model has seen. (The
predictor checks two summary properties of the image: the body's area on
the grid and the dynamic range of the SDF.) Treat a flagged prediction as
a prompt to run a real CFD case -- the model is being asked about a shape
unlike its training set, and an image-input model far outside its training
distribution can return a physically implausible number.

---

## 6. Reading the results responsibly

A trained surrogate is a *fast approximation* of a slower but more
trustworthy model -- and the slower model (CFD) is itself an approximation
of the real flow. A surrogate trained on CFD drag inherits the CFD's
strengths *and* its limitations: it can run faster than the CFD; it cannot
be more accurate than the CFD. If your CFD itself uses the wrong
turbulence model, a too-coarse mesh, or the wrong operating point, the
surrogate will reproduce that inaccuracy faithfully.

Three reading rules:

1. **Trust the surrogate inside the range of shapes it has seen; distrust
   it outside.** The trainer records the range of body sizes / extents in
   your training set. When you ask about a shape outside that range, the
   predictor flags it. A flagged prediction is a candidate for a real CFD
   check, not a final answer.
2. **Why a shape image beats a parameter vector -- and where that bites.**
   The whole reason to hand the model a picture is that it can see geometry
   the parametric slots did not encode: a subtle taper, a roof curve, how
   blunt the tail is. That is the strength. The matching weakness is that
   the model only knows the geometry features that *varied in your training
   shapes*. If every training body had the same tail and you ask about a
   radically different tail, the model is extrapolating in a way the
   size-based flag may not catch -- because the body's overall area can look
   in-range while its *local shape* is novel. So when you compare a
   predicted CD to a real CFD value, look first at the shapes whose local
   features (tail bluntness, roof line, nose sharpness) sit at the edge of
   what your training set covered; those are where an image surrogate's
   error concentrates, even when the size-based extrapolation flag stays
   quiet.
3. **One operating point only.** This surrogate fixes the speed and yaw and
   varies only the shape. A predicted CD is the drag *at that operating
   point*. Asking it for the drag of the same shape at a different speed or
   in a crosswind is outside its scope -- that is what the parametric
   `drag-lift` (which takes the operating point as input) is for, or a
   more advanced mixed image-plus-parameter surrogate this example does not
   attempt.

The model is a design-screening tool. It is not a design-certification
tool.

---

## 7. What's happening inside (optional, one page)

*This page is strictly optional. Skip it if you just want to use the
model.*

The architecture inside the trainer is a **dense image-regressor**: a
fully-connected neural network (scikit-learn's `MLPRegressor`, two hidden
layers) that reads the flattened 384-pixel SDF and regresses CD and CL,
with the inputs and targets standardised during training. In plain words:
it learns a function from "the 384 numbers that make up the picture of the
body" to "the two drag/lift coefficients," fitting the relationship across
all your training shapes at once.

The "384-pixel image -> CD, CL" mapping the model learns is, under the
hood, related to the way drag depends on a body's silhouette: a larger
frontal area raises drag, a blunter base leaves a bigger wake and raises
drag, a more slender body (higher length-to-height ratio) lowers it, a
roof bump trips the flow and adds both drag and lift, and a smaller ground
gap pulls lift downward. The synthetic sample data is built from exactly
those relationships; the surrogate learns them *from the pictures* rather
than being told the formula, and on your real data it learns whatever
relationship your CFD actually exhibits.

**Why a dense regressor and not a convolutional network.** The
canonical *production* architecture for image-input aero is a **2-D
CNN** -- the encoder half of the surface-pressure U-Net, with shared
convolutional filters that exploit the image's spatial structure and
translation-invariance, topped with a global-pooling head that outputs
the scalar coefficients. That architecture typically reaches a tighter
accuracy and scales to larger, higher-resolution images, but it is
GPU-friendly and materially heavier to train and to package as a
double-click executable. This example ships the simpler dense regressor
so it trains on a CPU in well under a minute. The convolutional CNN is
the natural upgrade -- the image-example analogue of the 3-D U-Net the
field example `temperature-field` names, and of the tabular examples'
Gaussian-Process variant. The bucket is **B2 either way**: the
classifier attribute is the regular-grid image input, not the
regressor's internals.

The **uncertainty band** is the held-out mean absolute error scaled by 1.5
-- a rough "one sigma" by analogy -- widened by an extra 2x per unit of
extrapolation distance (measured on the body-size statistics), so
predictions for shapes far outside the training size range carry visibly
larger bands. The convolutional upgrade would also open the door to a
calibrated per-prediction uncertainty (e.g. a CNN ensemble), which the
dense regressor shipped here does not provide.

---

## 8. Where to go next

The natural reading order around this example:

- **`drag-lift` -- Drag and Lift of an Off-Road Vehicle.** The
  parametric example this one bridges from -- the *same* external-aero
  physics and the *same* CD / CL target, with the input a row of
  assembly / operating numbers instead of a shape image. Reading the two
  back to back is the cleanest way to see what "stepping one cell down
  on the grid" means: same physics, same target, the input grows from a
  parameter vector (Bucket B1) to an image (Bucket B2) -- and it shows
  *why* a shape image can carry information a parameter vector could
  not.
- **`temperature-field` -- Temperature Field of a Cooled Component.** The
  *other* single-step move off the B1 cell -- a richer *output* (a
  field) rather than a richer *input* (an image). The two together show
  the two genuinely-distinct shape steps from the B1 corner:
  richer-output (rightward, `n=1,m=2`) and richer-input (downward,
  `n=2,m=1`).

---

## Setup

The workflow this walkthrough describes runs as standalone executables
on Windows, with no install step: double-click `Train-Drag-Shape.exe`,
then double-click the `Predict-Drag-Shape.exe` the trainer drops into a
`trained-model` folder. Those executables, and the Python trainer they
are built from, are not part of this repository. What ships here is the
data contract, the template, and the synthetic sample dataset with its
generator (`python data/synthesize_sample.py`).
