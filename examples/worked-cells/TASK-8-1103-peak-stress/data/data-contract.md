# TASK-8-1103 — Data Contract

> This is the exact specification of the dataset the trainer expects.
> Fill `template.csv` so that every column below is present, **in this
> order**, with one row per linear-static FE run. If your file matches
> this contract, the trainer will accept it; if it does not, the trainer
> will tell you exactly which column is wrong and stop.
>
> All numeric values are *illustrative* in `sample-dataset.csv` — that
> file exists only so you can run the workflow once before supplying
> your own real FE results.

## Columns

| #  | Column name        | Role     | Quantity                                | Units | Typical range |
|----|--------------------|----------|-----------------------------------------|-------|---------------|
| 1  | `length_mm`        | input    | Bracket length (load arm)               | mm    | 80 – 200      |
| 2  | `width_mm`         | input    | Bracket cross-section width             | mm    | 20 – 60       |
| 3  | `thickness_mm`     | input    | Bracket cross-section thickness         | mm    | 4 – 16        |
| 4  | `fillet_mm`        | input    | Root-fillet radius at the constraint    | mm    | 2 – 12        |
| 5  | `hole_dia_mm`      | input    | Through-hole diameter on the load arm   | mm    | 0 – 14        |
| 6  | `force_N`          | input    | Applied load magnitude                  | N     | 200 – 4000    |
| 7  | `force_angle_deg`  | input    | Load direction (0° = pure bending)      | °     | -30 – +30     |
| 8  | `youngs_modulus_GPa` | input  | Material Young's modulus                | GPa   | 70 – 210      |
| 9  | `yield_strength_MPa` | input  | Material 0.2 % proof / yield strength   | MPa   | 200 – 900     |
| 10 | `peak_vm_stress_MPa` | **target** | Peak von Mises stress over the part | MPa   | 30 – 1200     |
| 11 | `peak_disp_mm`       | **target** | Peak displacement magnitude         | mm    | 0.02 – 20     |
| 12 | `notes`            | *optional* | Free-form notes (run ID, DOE label)   | text  | —             |

## Rules

1. **Nine inputs, two targets.** Columns 1–9 are the parameters you
   vary across your DOE (5 geometry + 2 load + 2 material). Columns
   10–11 are the two headline structural-FE responses your linear-
   static run produced. Column 12 is optional and ignored by the
   trainer; it exists so you can carry your own run labels through.
   Catalog anchor: TASK-1 entry A.2.1 (FEA: Linear Static — the
   foundational structural-FE workflow; [Bathe2014] / [Hughes2000] /
   [Zienkiewicz2013] are the textbook anchors and [Yuksel2026] is the
   peer-reviewed precedent for GBM-on-bracket-peak-stress surrogacy).
2. **One row per FE run.** Each row is one completed linear-static
   solve: the 9 input parameters and the 2 response numbers the run
   produced. Use the *same* mesh-refinement policy across all rows —
   mixing fine and coarse meshes within one dataset gives the
   surrogate an extra hidden variable it cannot see.
3. **Targets are linear-scale, not logarithmic.** Peak stress and
   peak displacement span at most ~2 orders of magnitude across the
   ranges above, so the surrogate is trained on the raw values.
   Enter `peak_vm_stress_MPa = 387.4`, not `log10(387.4)`. Stress is
   in MPa (= N/mm²); displacement is in mm.
4. **Linear-static regime only.** The contract assumes elastic
   linear-static FE: stress is linear in load, displacement is linear
   in load, no contact, no plasticity, no buckling. If your FE
   includes nonlinearity, this surrogate will misrepresent the
   physics — that is a different bucket (TASK-1 entry A.2.2). The
   trainer does NOT detect nonlinearity automatically; it is the
   reader's responsibility to honour this constraint upstream.
5. **No blanks in the numeric columns; all numeric.** Columns 1–11
   must contain numbers in every row. The optional `notes` column may
   be blank. The trainer rejects a dataset with any missing or
   non-numeric value in columns 1–11.
6. **At least 80 rows; more is better.** The 9-input geometry +
   load + material space is wider than the fatigue-life example, so
   the minimum is the same as the pump pair (80 rows). 200–400
   well-spread runs is a healthy dataset; the sample shipped here
   has 250.
7. **Spread your runs across the ranges.** The model can only be
   trusted inside the range of data it has seen. If every run uses
   `youngs_modulus_GPa = 200`, the model learns nothing about how
   peak stress scales with material stiffness. Vary each input
   independently and span its realistic range. Stress concentration
   at the fillet is *highly* nonlinear in `fillet_mm` near the lower
   end of the range — bias your sample density toward small fillets
   if your design space includes them.

## Sign conventions

- **`force_angle_deg`** is measured at the load-application point.
  `0°` means the load acts perpendicular to the bracket axis (pure
  bending). Positive angles tilt the load toward the constraint;
  negative angles tilt it away.
- **`peak_vm_stress_MPa`** is the maximum scalar von Mises stress
  over the entire FE mesh (post-processed at integration points or
  averaged to nodes — pick one convention and apply it across all
  rows).
- **`peak_disp_mm`** is the maximum nodal displacement magnitude
  `‖u‖ = sqrt(ux² + uy² + uz²)` over the mesh, in mm.

## How this maps to the taxonomy

TASK-8-1103 sits in the **top-left cell** of the BRIDGE-A slide-9
grid: *scalar/vector (parametric) input → scalar/short-vector QoI
output*. That cell is **Bucket B1 — the tabular surrogate**. This is
the **third B1 example** in the iteration-0 inventory (after
TASK-8-1101 fatigue-life and TASK-8-1102 drag-lift), and the first
that lives in the structural-FE domain.

Catalog anchors:

- TASK-1 §6 A.2.1 — FEA Linear Static governing equations / fidelity
  tiers. Textbook anchors: [Bathe2014] (foundational framing per
  Q-cae-05), [Hughes2000] (linear-static-and-dynamic monograph),
  [Zienkiewicz2013] (variational methods and error estimation),
  [Roark2020] (handbook-tier analytical stress formulas — the
  low-fidelity benchmark).
- TASK-3 §6 A.2.1 → Bucket B1 mapping — peer-reviewed peak-stress
  GBM precedent is [Yuksel2026] (aircraft landing-gear bracket
  parametric study: XGBoost / Random Forest / Kriging / SVR / MLP
  comparison across dataset sizes 500–5000, with XGBoost and Random
  Forest reported as the most balanced / stable across dataset
  sizes).
- TASK-4 §5 Bucket B1 roster row.
- `EXAMPLES-ARC-SCOPING.md` §4 inventory (third B1 entry).

**Companion examples.** TASK-8-1101 (bracket fatigue-life) is the
arc's first B1 and the same domain shape as this example but
focused on fatigue life rather than peak stress; TASK-8-1102
(drag/lift) is the same B1 bucket on an external-aero CFD case;
TASK-8-1107 / TASK-8-1401 (pump operating-point / performance-curve)
demonstrate the B1 / B7 split for a downstream-question shift. All
four are worth reading alongside this example.
