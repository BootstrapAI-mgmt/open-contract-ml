# TASK-8-1201 -- Data Contract

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

This is the arc's first **field-output** example. The six tabular
examples before it (TASK-8-1101 through 1106) predicted one or a few
scalar numbers per run. This one predicts a whole **temperature field**:
the temperature at every voxel of a fixed regular grid, laid out across
the component. The input side is unchanged from the scalar
peak-temperature example (TASK-8-1104) -- the same seven thermal
parameters. Only the output grows from a number to a field.

Because the output is now a field, the data contract carries one new
idea: a **fixed grid**. Every run reports its temperature field on the
same grid shape, so every row of the dataset has the same number of
output columns. The grid is `(NX, NY, NZ) = (12, 8, 8) = 768 voxels`.
The physical size of the component varies run to run; the grid topology
does not. (This is the standard regular-grid convention -- it is what
lets one model read every row regardless of the part's dimensions.)

## Columns

The first seven columns are the inputs (one per design / operating
parameter). The next 768 columns are the temperature field. One optional
notes column may follow.

### Input columns (1 - 7)

| #  | Column name              | Role     | Quantity                                              | Units    | Typical range |
|----|--------------------------|----------|-------------------------------------------------------|----------|---------------|
| 1  | `length_mm`              | input    | Component length (along the cooling-axis direction)   | mm       | 30 - 200      |
| 2  | `width_mm`               | input    | Cross-section width                                   | mm       | 10 - 60       |
| 3  | `thickness_mm`           | input    | Cross-section thickness                               | mm       | 2 - 20        |
| 4  | `conductivity_W_mK`      | input    | Thermal conductivity k of the component material      | W/(m K)  | 10 - 400      |
| 5  | `h_W_m2K`                | input    | Convective heat-transfer coefficient on cooled surface| W/(m^2 K)| 5 - 250       |
| 6  | `T_ambient_C`            | input    | Ambient / coolant temperature T_inf                   | deg C    | -20 - +80     |
| 7  | `q_W`                    | input    | Total internal heat-generation rate                   | W        | 1 - 200       |

### Field columns (8 - 775): the temperature field

| #        | Column name        | Role       | Quantity                                          | Units | Typical range |
|----------|--------------------|------------|---------------------------------------------------|-------|---------------|
| 8 .. 775 | `T_000` .. `T_767` | **target** | Temperature at each voxel of the (12, 8, 8) grid  | deg C | -40 - 400     |

### Optional column (776)

| #   | Column name | Role       | Quantity                            | Units | Typical range |
|-----|-------------|------------|-------------------------------------|-------|---------------|
| 776 | `notes`     | *optional* | Free-form notes (run ID, DOE label) | text  | --            |

## The grid and the flattening convention

The 768 field columns are the temperature field flattened into a single
row of numbers. The grid is indexed:

- `i = 0 .. 11` along the **length** (the cooling axis; `i = 0` is the
  heat-source-attachment / base face, `i = 11` is the cooled tip),
- `j = 0 .. 7` across the **width**,
- `k = 0 .. 7` through the **thickness**.

The flat column index for voxel `(i, j, k)` is

```
flat = (i * 8 + j) * 8 + k          (voxel-major: i outer, then j, then k)
```

so `T_000` is voxel `(0, 0, 0)`, `T_001` is `(0, 0, 1)`, `T_008` is
`(0, 1, 0)`, `T_064` is `(1, 0, 0)`, and `T_767` is `(11, 7, 7)`. To
re-fold the 768 numbers back into a `(12, 8, 8)` array for plotting,
reshape in C / row-major order with that same `(i, j, k)` nesting. The
trainer and predictor use this exact convention; honour it when you
export your FE field so column `T_<flat>` always means the same physical
voxel across every row.

**You must resample your FE field onto this fixed grid.** Real
steady-state thermal FE produces a field on your solver's mesh, which is
generally unstructured and run-specific. Before filling the template,
interpolate (sample) that field onto the normalised `(12, 8, 8)` grid
spanning your component's bounding box. Use the **same** bounding-box
convention and the **same** interpolation policy across all runs --
mixing conventions gives the surrogate a hidden variable it cannot see.
This resampling step is the field-example equivalent of the scalar
examples' "use the same mesh-refinement policy across all rows" rule.

## Rules

1. **Seven inputs, 768 field targets.** Columns 1-7 are the parameters
   you vary across your DOE (3 geometry + 2 boundary-condition + 1
   operating-point + 1 material -- the same vocabulary as TASK-8-1104).
   Columns 8-775 are the temperature field your steady-state run
   produced, resampled onto the fixed grid. Column 776 is optional and
   ignored by the trainer. Catalog anchor: TASK-1 entry A.3.1 (FEA:
   Thermal Steady -- the canonical steady-state conduction-with-convection
   workflow; [Bergman2017] is the textbook anchor for the
   conduction-equation derivations and the Biot / Fourier dimensionless
   framework, [Patankar1980] for the FV/FE discretisation family, and
   [Bathe2014] for the Galerkin-FE machinery shared with
   structural FEA).
2. **One row per FE run.** Each row is one completed steady-state thermal
   solve: the 7 input parameters and the 768 field values the run
   produced (after resampling onto the fixed grid). Use the *same* mesh-
   refinement policy and the *same* resampling grid across all rows.
3. **Targets are linear-scale, not logarithmic.** Temperature spans at
   most ~1 order of magnitude across the ranges above, so the surrogate
   is trained on raw values. Enter `T_123 = 187.4`, not `log10(187.4)`.
4. **Steady-state regime only.** The contract assumes steady-state
   thermal FE: the temperature field has reached equilibrium under the
   prescribed boundary conditions -- no transient warm-up / cool-down, no
   phase change. A transient or phase-change problem is a different
   bucket (TASK-1 entry A.3.2 / a time-resolved field variant). The
   trainer does NOT detect transient inputs automatically; honour this
   constraint upstream.
5. **Constant-property regime.** The contract treats `conductivity_W_mK`
   as a single scalar per run. If your FE uses temperature-dependent
   `k(T)`, either report the *effective* k at the run's mean temperature
   and accept the constant-k simplification, or treat the strongly
   k(T)-dependent regime as out of scope (TASK-1 A.3.1 Pitfall (i) --
   material-property temperature dependence is the dominant
   thermal-surrogate-failure mode).
6. **Single-class boundary conditions per dataset.** The contract assumes
   a uniform boundary-condition class across runs: Dirichlet on the
   heat-source-attachment face and Robin (convective) on the cooled
   surfaces. If some runs use radiation or prescribed-flux Neumann
   boundaries, train a separate surrogate per class (TASK-1 A.3.1 Pitfall
   (ii) -- boundary-condition class inheritance).
7. **The same fixed grid for every row.** Because the output is a field,
   the contract's load-bearing new rule is that every row reports the
   field on the SAME `(12, 8, 8)` grid in the SAME flatten order. A row
   with a different number of field columns, or a field exported in a
   different voxel order, silently corrupts the surrogate -- the trainer
   checks the column count and names but cannot see a mis-ordered field.
8. **No blanks in the numeric columns; all numeric.** Columns 1-775 must
   contain numbers in every row. The optional `notes` column may be
   blank. The trainer rejects a dataset with any missing or non-numeric
   value in columns 1-775.
9. **At least 80 rows; more is better.** A field surrogate has many more
   output numbers per row than a scalar surrogate, but the *input* design
   space is the same seven-parameter space as TASK-8-1104, so the minimum
   row count is the same (80). 200-400 well-spread runs is a healthy
   dataset; the sample shipped here has 250. (The field output does not
   reduce the number of runs you need -- if anything a richer output
   rewards more runs -- but it does not raise the floor either, because
   the thing being sampled is still the seven-input design space.)
10. **Spread your runs across the ranges.** The model can only be trusted
    inside the range of data it has seen. Vary each input independently
    and span its realistic range. The field response is *highly*
    nonlinear in the Biot number `Bi = h * L_c / k`; bias your sample
    density toward the high-Bi corner (small k, large h, large L_c) if
    your design space includes thermally-thick regimes.

## Sign conventions

- **`T_ambient_C`** and every **`T_<flat>`** field value are in degrees
  Celsius on the same reference scale. The trainer does not
  non-dimensionalise -- if you train on Celsius and predict in Kelvin,
  predictions will be wrong by 273.15 every time. Pick one scale and
  apply it across all rows.
- **`q_W`** is the *total* internal heat-generation rate in watts
  integrated over the component volume, not a volumetric density. The
  volumetric density `q_dot [W/m^3] = q_W / (length * width * thickness)`
  is recoverable from the geometry columns; surrogates trained on total-W
  inputs decouple the geometry-scaling axis from the per-unit-volume axis
  more cleanly.
- **The grid orientation is fixed**: `i = 0` is the
  heat-source-attachment (base) face, `i = NX-1` is the cooled tip;
  `j` runs across the width and `k` through the thickness, both centred
  on the component. The field is typically hottest near the base or in
  the interior (depending on whether source-side heating or internal
  self-heating dominates) and cooler toward the lateral faces. Keep this
  orientation identical across all rows.

## What "field accuracy" means here

A scalar surrogate reports one error number per target. A field
surrogate reports an error over the whole grid, so the trainer prints
two field-level figures:

- **Mean relative L2 error** -- the size of the prediction error vector
  divided by the size of the true field vector, averaged over the
  held-out runs. It answers "what fraction of the field's magnitude does
  the typical prediction miss by?" Lower is better; below ~0.10 (10 %) is
  a usable design-screening field.
- **Per-voxel mean absolute error (deg C)** -- the average temperature
  miss at a single voxel, in degrees, averaged over all voxels and all
  held-out runs. It is the field-wide analogue of the scalar examples'
  MAE and is the easiest number to reason about physically.

Both figures are illustrative on the sample data (see below).

## How this maps to the taxonomy

TASK-8-1201 sits one cell to the **right** of the top-left B1 cell on the
BRIDGE-A slide-9 grid: *scalar / vector (parametric) input -> field on a
regular grid output* (cell `n=1, m=2`). That cell is **Bucket B2 -- the
regular-grid field surrogate**. It is the **first non-B1 example** in the
arc and the first to live in the field-output column.

Catalog anchors:

- TASK-1 section 6 A.3.1 -- FEA Thermal Steady governing equations /
  fidelity tiers. Textbook anchors: [Bergman2017] (conduction-equation
  framing, Biot / Fourier dimensionless-number framework), [Patankar1980]
  (FV discretisation), [Bathe2014] (Galerkin-FE machinery),
  [Hughes2000] (FE machinery).
- TASK-4 section 5 Bucket B2 roster, the **A.3.1 row**: "volumetric
  temperature scalar field T(x) on regular voxel grids
  (electronics-cooling, packed-bed reactors, regular-domain
  heat-exchanger studies) -> 3-D U-Net / dense 3-D CNN for regular-grid
  thermal fields." This is the exact catalog row this example
  instantiates. The B2 defining test ("output is a field on a regular
  Cartesian grid; spatial structure is exploitable") fires.
- TASK-3 section 6 A.3.1 -> Bucket mapping (the scalar B1 row is the
  parameter-to-peak-temperature regression; this example is the field
  variant of the same analysis).
- `EXAMPLES-ARC-SCOPING.md` section 11.2 (the rightward-cell lead
  candidate) and section 4 inventory.

**A note on bucket routing.** TASK-4's B2 roster names the canonical
production architecture for this row as a 3-D U-Net / dense 3-D CNN. This
worked example ships a simpler **dense-decoder** surrogate (a
fully-connected network that maps the seven inputs to the 768-voxel
field) so the example trains on a CPU in seconds-to-minutes and keeps the
arc's click-to-run promise. The U-Net / CNN with spatial convolutions is
the heavier production variant; it is named in WALKTHROUGH.md section 7
as the planned-but-deferred upgrade, exactly as the scalar examples name
their GP variant. The bucket is B2 either way -- the classifier attribute
is the regular-grid field *output*, not the specific decoder internals.

**Companion examples.** TASK-8-1104 (peak-temperature) is the closest
sibling: the same seven thermal inputs, with the output stepped from the
single peak number to the whole field. Reading the two together is the
cleanest way to see what "stepping one cell right on the grid" means in
practice. TASK-8-1101 (fatigue-life) is the arc's first B1 and the
template proof. The BRIDGE-A deck (slide 9) is the conceptual home of the
input-vs-output grid this example's cell comes from.

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../../../docs/REFERENCES.md).*
