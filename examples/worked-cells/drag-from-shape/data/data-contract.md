# Drag-from-shape example -- Data Contract

> This is the exact specification of the dataset the trainer expects.
> Fill `template.csv` so that every column below is present, **in this
> order**, with one row per CAE run. If your file matches this contract,
> the trainer will accept it; if it does not, the trainer will tell you
> exactly which column is wrong and stop.
>
> All numeric values are *illustrative* in `sample-dataset.csv` -- that
> file exists only so you can run the workflow once before supplying
> your own real CFD aero results.

## What is different about this example

This is the first **image-input** worked cell. The tabular examples and
the field example (`temperature-field`) all take a *row of design
numbers* as input. This one takes a **picture of the geometry**: a
signed-distance-field (SDF) image of the body cross-section, laid out on
a fixed pixel grid. The output side is the familiar B1 scalar QoI -- the
drag coefficient CD (and lift CL) -- the same target family as the
parametric drag-lift example (`drag-lift`).
Only the input grows, from a parameter vector to a geometry image.

Why hand the model a picture instead of a parameter vector? Because a
shape image carries information the parametric slots did not encode. Two
bodies with the same "length" and "height" numbers can have very
different drag if one has a blunt tail and the other a tapered one, or a
roof bump versus a smooth roof. The parametric drag-lift example
(`drag-lift`) could only see the design choices you gave it columns for;
this example sees the *actual silhouette*, so it can pick up drag-driving
geometry features (frontal bluffness, base bluntness, roof curvature,
ride height) directly from the picture.

Because the input is now an image, the data contract carries one new
idea: a **fixed pixel grid**. Every body reports its SDF on the same
grid shape, so every row of the dataset has the same number of input
columns. The grid is `(NY, NX) = (16, 24) = 384 pixels`. The physical
size of the body varies row to row; the grid topology does not.

## Columns

The first 384 columns are the SDF image (the model input). The next 2
columns are the targets. One optional notes column may follow.

### Input columns (1 - 384): the SDF image

| #        | Column name        | Role     | Quantity                                          | Units          | Typical range |
|----------|--------------------|----------|---------------------------------------------------|----------------|---------------|
| 1 .. 384 | `S_000` .. `S_383` | input    | Signed distance to the body surface at each pixel | grid-cell units| -12 .. +24    |

### Target columns (385 - 386)

| #   | Column name | Role       | Quantity                                  | Units         | Typical range |
|-----|-------------|------------|-------------------------------------------|---------------|---------------|
| 385 | `CD`        | **target** | Drag coefficient at the operating point   | dimensionless | 0.2 - 1.3     |
| 386 | `CL`        | **target** | Lift coefficient at the operating point   | dimensionless | -0.6 - +0.8   |

### Optional column (387)

| #   | Column name | Role       | Quantity                            | Units | Typical range |
|-----|-------------|------------|-------------------------------------|-------|---------------|
| 387 | `notes`     | *optional* | Free-form notes (run ID, DOE label) | text  | --            |

## The pixel grid, the SDF, and the flattening convention

The 384 input columns are the SDF image flattened into a single row of
numbers. The grid is indexed:

- `ix = 0 .. 23` along the **length** (the flow direction; +x is
  downstream),
- `iy = 0 .. 15` in the **vertical** (iy = 0 is the bottom of the
  window, near the ground plane).

The flat column index for pixel `(iy, ix)` is

```
flat = iy * 24 + ix          (row-major: iy outer, ix inner)
```

so `S_000` is pixel `(0, 0)` (bottom-left), `S_024` is `(1, 0)`, and
`S_383` is `(15, 23)` (top-right). To re-fold the 384 numbers back into a
`(16, 24)` array for plotting, reshape in C / row-major order with that
same `(iy, ix)` nesting.

**What an SDF value means.** The signed distance field stores, at every
pixel, the distance from that pixel to the nearest point of the body's
surface, **negative inside the body and positive outside**, zero on the
surface, measured in grid-cell units. The body's silhouette is therefore
the set of pixels where the SDF is negative; the surface is the
zero-contour. An SDF is a smoother, more learnable encoding of a shape
than a hard 0/1 occupancy mask, which is why it is a standard
geometry-as-image encoding.

**You must rasterise your geometry onto this fixed grid as an SDF.** Your
CAD / mesh geometry is run-specific and continuous. Before filling the
template, sample your body's cross-section onto the normalised `(16, 24)`
grid spanning a fixed physical window, and compute the signed distance at
each pixel. Use the **same** window and the **same** orientation
convention (flow left-to-right, ground at the bottom) for every run --
a body rasterised in a different window or orientation silently corrupts
the surrogate, and the trainer can only check the column count and names,
not the physical framing. This rasterisation is the image-example
equivalent of the tabular examples' "use the same parameter definitions
across all rows" rule, and it is the one genuinely new piece of work this
example asks of you.

## Rules

1. **384 image inputs, 2 scalar targets.** Columns 1-384 are the SDF
   image of the body cross-section, rasterised onto the fixed grid.
   Columns 385-386 are the two aero coefficients your CFD run produced at
   the chosen operating point. Column 387 is optional and ignored by the
   trainer. The analysis is external-aero CFD; an SDF, a surface-normal
   map or an unwrapped surface texture are the usual ways to encode
   geometry as an image; [Ronneberger2015] is the U-Net and
   CNN-inductive-bias anchor, and [Slotnick2014] is the CFD-vision anchor
   shared with `drag-lift`.
2. **One row per CFD run.** Each row is one completed external-aero CFD
   case: the SDF image of one body geometry and the two coefficients the
   run produced at the fixed operating point. Use the *same* mesh-
   refinement policy and the *same* rasterisation window across all rows.
3. **One operating point per dataset.** This example fixes the operating
   point (a single reference speed / yaw) and varies only the geometry.
   The drag of a body at a *different* speed or yaw is a different
   surrogate; if your DOE sweeps the operating point as well as the
   shape, either fix the operating point for this surrogate or move the
   operating-point channel into the input vocabulary (which makes it a
   mixed image-plus-parameter input -- a more advanced variant this
   example does not attempt).
4. **Targets are linear-scale, not logarithmic.** CD and CL span less
   than one order of magnitude, so the surrogate trains on the raw
   values. Enter `CD = 0.74`, not `log10(0.74)`.
5. **The same fixed grid, window, and orientation for every row.**
   Because the input is an image, the contract's load-bearing new rule is
   that every row reports the SDF on the SAME `(16, 24)` grid, in the
   SAME flatten order, for a body framed in the SAME physical window with
   the SAME orientation (flow left-to-right, ground at the bottom). A row
   with a different pixel count, a different window, or a flipped
   orientation silently corrupts the surrogate.
6. **No blanks in the numeric columns; all numeric.** Columns 1-386 must
   contain numbers in every row. The optional `notes` column may be
   blank. The trainer rejects a dataset with any missing or non-numeric
   value in columns 1-386.
7. **At least 80 rows; more is better.** An image-input surrogate has
   many more input numbers per row than a tabular one, and a richer input
   space generally rewards more rows -- but the floor is the same 80 as
   the tabular examples, because the thing being sampled is still the
   space of body shapes you care about. 200-400 well-spread shapes is a
   healthy dataset; the sample shipped here has 250.
8. **Spread your shapes across the design space.** The model can only be
   trusted inside the range of geometries it has seen. If every body is a
   blunt box, the model learns nothing about how a tapered tail lowers
   drag. Vary frontal bluffness, fineness (length / height), base
   bluntness, roof curvature, and ride height across their realistic
   ranges.

## Sign conventions

- **`CD` positive** is drag opposing forward motion (the standard
  convention). Larger frontal area, a blunter base, and a more
  prominent roof bump all raise CD; a more slender body (higher
  length / frontal-height ratio) lowers it.
- **`CL` positive** is lift in the upward direction. A prominent roof
  bump adds camber-like positive lift; a small ground gap (low ride
  height) drives lift more negative (ground-effect down-load); a blunt
  base contributes a mild tail-lift.
- **The grid orientation is fixed**: flow is left-to-right (`ix` is the
  streamwise index, +x downstream), and the ground plane is at the
  bottom of the window (`iy = 0` side). Keep this orientation identical
  across all rows -- the model learns geometry features in grid
  coordinates, so a flipped or rotated body is, to the model, a
  different shape.

## What "accuracy" means here

This example's output is a scalar (CD, CL), so the trainer reports the
same per-target metrics as the tabular examples: an average absolute
error (MAE) and an R-squared for each of CD and CL on a held-out slice
of your rows. The only thing that is different from a tabular example is
the *input* -- the model reads a picture, not a row of numbers -- but the
accuracy report reads exactly like a tabular one.

## How this maps to the taxonomy

This example sits one cell **down** from the top-left B1 cell on the
input/output grid: *regular-grid (image-like) input -> scalar QoI
output* (cell `n=2, m=1`). It is the second worked cell outside Bucket
B1 (after the field example `temperature-field`) and the first to take
an image as input.

Anchors:

- External-aero CFD. The geometry-as-image encodings (an SDF, a
  surface-normal map or an unwrapped surface texture) and the
  surface-pressure CNN / U-Net are the standard image-input approaches;
  [Ronneberger2015] is the U-Net anchor, [Slotnick2014] the CFD-vision
  anchor.
- Bucket B2 (regular-grid field surrogate). **Bucket routing nuance:**
  B2's defining test is written about grid *outputs*, but this example
  has a grid *input* and a scalar output. It routes to B2 **by input
  shape** -- the convolutional / image inductive bias is the
  load-bearing classifier attribute -- which is an edge case routed by
  shape, not a schema relaxation.
- The parametric drag-lift row is the B1 tabular surrogate `drag-lift`
  instantiates; this example is the image-input variant of the same
  analysis.

**A note on bucket routing and architecture.** The canonical production
architecture for image-input aero is a **2-D / 3-D CNN** (the encoder
half of the surface-pressure U-Net, used here for regression with a
global-pooling scalar head). This worked example ships a simpler **dense
image-regressor** (a fully-connected network that reads the flattened
384-pixel SDF and regresses CD / CL) so the example trains on a CPU in
seconds-to-minutes. The convolutional CNN -- which exploits the image's
spatial structure with shared filters and translation-invariance, and
typically reaches a tighter accuracy and scales to larger grids -- is
the upgrade, named in WALKTHROUGH.md section 7. This mirrors the field
example `temperature-field`, which ships a dense decoder in place of a
3-D U-Net. The bucket is **B2 either way** -- the classifier attribute
is the regular-grid image, not the regressor internals.

**Companion examples.** `drag-lift` (parametric drag-lift) is the
closest sibling: the same external-aero physics and the same CD / CL
target, with the input stepped from a parameter / assembly vector to a
shape image. Reading the two together is the cleanest way to see what
"stepping one cell down on the grid" means -- and why a shape image can
carry information the parametric slots could not. `temperature-field`
(temperature field) is the *other* single-step move off B1 -- a richer
*output* (a field) rather than a richer *input* (an image); the two
together show the two genuinely-distinct shape steps from the B1
corner.

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../../../docs/REFERENCES.md).*
