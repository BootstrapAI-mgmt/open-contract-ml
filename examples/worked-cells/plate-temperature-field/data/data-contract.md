# Plate temperature-field example -- Data Contract

> This is the exact specification of the dataset the trainer expects.
> Fill `template.csv` so that every column below is present, **in this
> order**, with one row per steady-state thermal FE run. If your file
> matches this contract, the trainer will accept it; if it does not,
> the trainer will tell you exactly which column is wrong and stop.
>
> All numeric values are *illustrative* in `sample-dataset.csv` -- that
> file exists only so you can run the workflow once before supplying
> your own real FE results.

## What is different about this example

This is the **second field-output** worked cell, and it is the second
instance of the *same* grid cell (`n=1, m=2`, Bucket B2) as
`temperature-field` -- but on a **different component geometry and
boundary-condition family**. `temperature-field` modelled an **extruded cooling
fin** (base-temperature heating at one end, an adiabatic tip, heat
conducting along the length): its field is a 1-D fin profile extruded
across the section. This example models a **flat cooled plate** (a
heat-spreader / cold-plate) carrying a **discrete embedded heat source**
on its top face and rejecting heat by convection over its faces: its
field is an in-plane spreading map -- hot under the source, cooling
radially outward as the plate carries heat away.

Both are steady-state thermal problems, and both report a
temperature field on a fixed regular grid (the B2 data-contract shape).
What changes is the *geometry*, the *boundary conditions*, and the
*dominant physics* (in-plane heat spreading from a localised source,
rather than 1-D conduction along a fin). The pedagogical point of pairing
the two is exactly that: **the field-output template generalises across
geometry / boundary-condition families within a domain, not only across
physics domains.** A reader who has done `temperature-field` meets no new ML idea
here -- only a different physical setup wearing the same data contract.

Because the output is a field, the data contract carries the same
**fixed-grid** idea as `temperature-field`: every run reports its temperature
field on the same grid shape, so every row has the same number of output
columns. Here the grid is `(NX, NY, NZ) = (16, 16, 4) = 1024 voxels` --
deliberately a **different shape** from `temperature-field`'s `(12, 8, 8)`, to
make the point that the contract is not hard-wired to one grid, only to a
*fixed* grid. The plate geometry motivates the shape: 16 x 16 in the
in-plane directions (where the spreading structure lives) and only 4
through the thin thickness.

## Columns

The first eight columns are the inputs (one per design / operating
parameter). The next 1024 columns are the temperature field. One optional
notes column may follow.

### Input columns (1 - 8)

| #  | Column name              | Role     | Quantity                                              | Units    | Typical range |
|----|--------------------------|----------|-------------------------------------------------------|----------|---------------|
| 1  | `length_mm`              | input    | Plate length (in-plane, the longer face direction)    | mm       | 40 - 200      |
| 2  | `width_mm`               | input    | Plate width (in-plane, the other face direction)      | mm       | 40 - 200      |
| 3  | `thickness_mm`           | input    | Plate thickness (the short, through-thickness dim)    | mm       | 2 - 20        |
| 4  | `conductivity_W_mK`      | input    | Thermal conductivity k of the plate material          | W/(m K)  | 10 - 400      |
| 5  | `h_W_m2K`                | input    | Convective heat-transfer coefficient on cooled faces  | W/(m^2 K)| 5 - 250       |
| 6  | `T_ambient_C`            | input    | Ambient / coolant temperature T_inf                   | deg C    | -20 - +80     |
| 7  | `src_size_mm`            | input    | Heat-source footprint side (square source on top face)| mm       | 5 - 40        |
| 8  | `q_W`                    | input    | Total heat-source power deposited on the plate         | W        | 1 - ~300      |

The seventh input -- `src_size_mm`, the heat-source footprint -- is the
**new geometry knob** this plate geometry introduces. The fin example had
no localised source, so it had no such column; here the size of the hot
patch is a first-class design variable that materially shapes the field.

### Field columns (9 - 1032): the temperature field

| #         | Column name          | Role       | Quantity                                            | Units | Typical range |
|-----------|----------------------|------------|-----------------------------------------------------|-------|---------------|
| 9 .. 1032 | `T_0000` .. `T_1023` | **target** | Temperature at each voxel of the (16, 16, 4) grid   | deg C | -40 - 400     |

### Optional column (1033)

| #    | Column name | Role       | Quantity                            | Units | Typical range |
|------|-------------|------------|-------------------------------------|-------|---------------|
| 1033 | `notes`     | *optional* | Free-form notes (run ID, DOE label) | text  | --            |

## The grid and the flattening convention

The 1024 field columns are the temperature field flattened into a single
row of numbers. The grid is indexed:

- `i = 0 .. 15` along the **length** (an in-plane direction),
- `j = 0 .. 15` across the **width** (the other in-plane direction),
- `k = 0 .. 3` through the **thickness** (`k = 0` is the **cooled bottom
  face**, `k = 3` is the **heated top face** that carries the source).

The flat column index for voxel `(i, j, k)` is

```
flat = (i * 16 + j) * 4 + k          (voxel-major: i outer, then j, then k)
```

so `T_0000` is voxel `(0, 0, 0)`, `T_0001` is `(0, 0, 1)`, `T_0004` is
`(0, 1, 0)`, `T_0064` is `(1, 0, 0)`, and `T_1023` is `(15, 15, 3)`. To
re-fold the 1024 numbers back into a `(16, 16, 4)` array for plotting,
reshape in C / row-major order with that same `(i, j, k)` nesting. The
trainer and predictor use this exact convention; honour it when you
export your FE field so column `T_<flat>` always means the same physical
voxel across every row.

**You must resample your FE field onto this fixed grid.** Real
steady-state thermal FE produces a field on your solver's mesh, which is
generally unstructured and run-specific. Before filling the template,
interpolate (sample) that field onto the normalised `(16, 16, 4)` grid
spanning the plate's bounding box. Use the **same** bounding-box
convention and the **same** interpolation policy across all runs --
mixing conventions gives the surrogate a hidden variable it cannot see.
This resampling step is the field-example equivalent of the scalar
examples' "use the same mesh-refinement policy across all rows" rule.

## Rules

1. **Eight inputs, 1024 field targets.** Columns 1-8 are the parameters
   you vary across your DOE (3 geometry + 1 material + 1
   boundary-condition + 1 operating-point + 1 source-geometry +
   1 source-power). Columns 9-1032 are the temperature field your
   steady-state run produced, resampled onto the fixed grid. Column 1033
   is optional and ignored by the trainer. The analysis is steady-state
   thermal FEA, the canonical conduction-with-convection workflow;
   [Bergman2017] is the textbook anchor for the conduction-equation
   derivations and the Biot / Fourier dimensionless framework,
   [Patankar1980] for the FV/FE discretisation family, and [Bathe2014]
   for the Galerkin-FE machinery shared with structural FEA.
2. **One row per FE run.** Each row is one completed steady-state thermal
   solve: the 8 input parameters and the 1024 field values the run
   produced (after resampling onto the fixed grid). Use the *same* mesh-
   refinement policy and the *same* resampling grid across all rows.
3. **Targets are linear-scale, not logarithmic.** Temperature spans at
   most ~1 order of magnitude across the ranges above, so the surrogate
   is trained on raw values. Enter `T_0123 = 87.4`, not `log10(87.4)`.
4. **Steady-state regime only.** The contract assumes steady-state
   thermal FE: the temperature field has reached equilibrium under the
   prescribed boundary conditions -- no transient warm-up / cool-down, no
   phase change. A transient or phase-change problem is a different
   bucket (a time-resolved field variant). The
   trainer does NOT detect transient inputs automatically; honour this
   constraint upstream.
5. **Constant-property regime.** The contract treats `conductivity_W_mK`
   as a single scalar per run. If your FE uses temperature-dependent
   `k(T)`, either report the *effective* k at the run's mean temperature
   and accept the constant-k simplification, or treat the strongly
   k(T)-dependent regime as out of scope (material-property temperature
   dependence is the dominant thermal-surrogate-failure mode).
6. **Single-class boundary conditions per dataset.** The contract assumes
   a uniform boundary-condition class across runs: a localised heat
   source on the top face and Robin (convective) cooling on the plate
   faces. If some runs use radiation, a prescribed-flux Neumann source,
   or a base-cooled cold-plate (heat extracted through the bottom face to
   a liquid loop) instead of face convection, train a separate surrogate
   per class (boundary-condition class inheritance).
7. **The same fixed grid for every row.** Because the output is a field,
   the contract's load-bearing rule is that every row reports the field
   on the SAME `(16, 16, 4)` grid in the SAME flatten order. A row with a
   different number of field columns, or a field exported in a different
   voxel order, silently corrupts the surrogate -- the trainer checks the
   column count and names but cannot see a mis-ordered field.
8. **The source position is a fixed modelling assumption of the sample
   data.** The shipped `sample-dataset.csv` places the heat source at the
   **centre** of the top face for every run (so the synthetic field is a
   deterministic function of the eight input columns alone). If in your
   real data the source position varies run-to-run, that position is an
   *additional input* the surrogate needs: add `src_x_frac` and
   `src_y_frac` columns and extend the contract, or hold the source
   centred as the sample data does. Do not let source position vary
   silently while leaving it out of the inputs -- that is a hidden
   variable the model cannot see.
9. **No blanks in the numeric columns; all numeric.** Columns 1-1032 must
   contain numbers in every row. The optional `notes` column may be
   blank. The trainer rejects a dataset with any missing or non-numeric
   value in columns 1-1032.
10. **At least 80 rows; more is better, and a field rewards more.** A
    field surrogate has many output numbers per row; with this plate's
    in-plane spreading structure, the field *shape* varies more across the
    design space than the fin's did, so a larger sample helps the
    dense decoder more than it did for `temperature-field`. The minimum is still
    80 (the input design space is an 8-parameter space), but a healthy
    dataset is 400-600 well-spread runs; the sample shipped here has 500.
11. **Spread your runs across the ranges.** The model can only be trusted
    inside the range of data it has seen. Vary each input independently
    and span its realistic range. The field response is strongly governed
    by the spreading group (conductivity vs convection) and by the source
    size relative to the plate; bias your sample density toward the
    corners that matter for your design (small plate + large source, or
    low-k + high-h, where the field is most peaked).

## Sign conventions

- **`T_ambient_C`** and every **`T_<flat>`** field value are in degrees
  Celsius on the same reference scale. The trainer does not
  non-dimensionalise -- if you train on Celsius and predict in Kelvin,
  predictions will be wrong by 273.15 every time. Pick one scale and
  apply it across all rows.
- **`q_W`** is the *total* heat-source power in watts deposited on the
  plate, not a flux density. The source flux `q'' [W/m^2] = q_W /
  (src_size * src_size)` is recoverable from the source-size column;
  surrogates trained on total-W inputs decouple the source-scaling axis
  from the footprint axis more cleanly.
- **The grid orientation is fixed**: `k = 0` is the cooled bottom face,
  `k = NZ-1 = 3` is the heated top face carrying the source; `i` and `j`
  are the two in-plane directions. The field is hottest directly under the
  source on the top face and cools both outward in-plane and downward
  through the thickness. Keep this orientation identical across all rows.

## What "field accuracy" means here

A scalar surrogate reports one error number per target. A field
surrogate reports an error over the whole grid, so the trainer prints
two field-level figures:

- **Mean relative L2 error** -- the size of the prediction error vector
  divided by the size of the true field vector, averaged over the
  held-out runs. It answers "what fraction of the field's magnitude does
  the typical prediction miss by?" Lower is better; below ~0.10 (10 %) is
  a tight field, 0.10-0.20 is usable for design screening.
- **Per-voxel mean absolute error (deg C)** -- the average temperature
  miss at a single voxel, in degrees, averaged over all voxels and all
  held-out runs. It is the field-wide analogue of the scalar examples'
  MAE and is the easiest number to reason about physically.

Both figures are illustrative on the sample data (see below).

## How this maps to the taxonomy

This example sits in the same cell as `temperature-field`, one step to
the **right** of the top-left B1 cell on the input/output grid: *scalar /
vector (parametric) input -> field on a regular grid output* (cell
`n=1, m=2`). That cell is **Bucket B2 -- the regular-grid field
surrogate**. It is the second field-output worked cell and the second
instance of this cell, demonstrating the cell across a different
geometry / boundary-condition family in the same steady-state thermal
domain.

Anchors:

- Steady-state thermal FEA governing equations and fidelity tiers.
  Textbook anchors: [Bergman2017] (conduction-equation framing, Biot /
  Fourier dimensionless-number framework), [Patankar1980] (FV
  discretisation), [Bathe2014] (Galerkin-FE machinery), [Hughes2000] (FE
  machinery).
- A volumetric temperature field on a regular voxel grid (electronics
  cooling, packed-bed reactors, regular-domain heat-exchanger studies)
  is the canonical B2 case; a flat heat-spreader plate with a discrete
  source is a textbook electronics-cooling instance of it. The B2
  defining test -- the output is a field on a regular Cartesian grid and
  its spatial structure is exploitable -- fires.
- The scalar B1 version of the same analysis is the
  parameter-to-peak-temperature regression; this example, like
  `temperature-field`, is the field variant of the same analysis.

**A note on bucket routing.** The canonical production architecture for
this case is a 3-D U-Net / dense 3-D CNN. This worked example ships a
simpler **dense-decoder** surrogate (a fully-connected network that maps
the eight inputs to the 1024-voxel field) so the example trains on a CPU
in seconds-to-minutes -- exactly the same architecture choice
`temperature-field` made. The U-Net / CNN with spatial convolutions is
the heavier production variant; it is named in WALKTHROUGH.md section 7
as the upgrade. The bucket is B2 either way -- the classifier attribute
is the regular-grid field *output*, not the specific decoder internals.

**Companion examples.** `temperature-field` (fin temperature field) is
the closest sibling: the same Bucket-B2 field-output data contract on a
*different* geometry and boundary-condition family. Reading the two
together is the cleanest way to see that the field-output template
generalises across geometry families, not just across domains.
`peak-temperature` is the scalar B1 ancestor of the thermal field
line.

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../../../docs/REFERENCES.md).*
