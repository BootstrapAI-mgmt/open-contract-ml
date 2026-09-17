# TASK-8-1104 — Data Contract

> This is the exact specification of the dataset the trainer expects.
> Fill `template.csv` so that every column below is present, **in this
> order**, with one row per steady-state thermal FE run. If your file
> matches this contract, the trainer will accept it; if it does not,
> the trainer will tell you exactly which column is wrong and stop.
>
> All numeric values are *illustrative* in `sample-dataset.csv` — that
> file exists only so you can run the workflow once before supplying
> your own real FE results.

## Columns

| #  | Column name              | Role     | Quantity                                              | Units   | Typical range |
|----|--------------------------|----------|-------------------------------------------------------|---------|---------------|
| 1  | `length_mm`              | input    | Component length (along the cooling-axis direction)   | mm      | 30 – 200      |
| 2  | `width_mm`               | input    | Cross-section width                                   | mm      | 10 – 60       |
| 3  | `thickness_mm`           | input    | Cross-section thickness                               | mm      | 2 – 20        |
| 4  | `conductivity_W_mK`      | input    | Thermal conductivity `k` of the component material    | W/(m·K) | 10 – 400      |
| 5  | `h_W_m2K`                | input    | Convective heat-transfer coefficient on cooled surface| W/(m²·K)| 5 – 250       |
| 6  | `T_ambient_C`            | input    | Ambient / coolant temperature `T_∞`                   | °C      | -20 – +80     |
| 7  | `q_W`                    | input    | Total internal heat-generation rate                   | W       | 1 – 200       |
| 8  | `peak_temp_C`            | **target** | Peak steady-state temperature over the component    | °C      | 30 – 350      |
| 9  | `hot_spot_x_mm`          | **target** | Position along the length where the peak occurs     | mm      | 0 – 200       |
| 10 | `notes`                  | *optional* | Free-form notes (run ID, DOE label)                 | text    | —             |

## Rules

1. **Seven inputs, two targets.** Columns 1–7 are the parameters you
   vary across your DOE (3 geometry + 2 boundary-condition + 1
   operating-point + 1 material). Columns 8–9 are the two headline
   thermal-FE responses your steady-state run produced. Column 10 is
   optional and ignored by the trainer; it exists so you can carry your
   own run labels through. Catalog anchor: TASK-1 entry A.3.1 (FEA:
   Thermal Steady — the canonical steady-state conduction-with-convection
   workflow; [Bergman2017] is the textbook anchor for the
   conduction-equation derivations and the Biot / Fourier dimensionless
   framework, [Patankar1980] for the FV/FE discretisation family, and
   [Bathe2014] for the Galerkin-FE machinery shared with
   structural FEA).
2. **One row per FE run.** Each row is one completed steady-state
   thermal solve: the 7 input parameters and the 2 response numbers
   the run produced. Use the *same* mesh-refinement policy across all
   rows — mixing fine and coarse meshes within one dataset gives the
   surrogate an extra hidden variable it cannot see.
3. **Targets are linear-scale, not logarithmic.** Peak temperature
   spans at most ~1 order of magnitude across the ranges above, and
   hot-spot position is a length scale, so the surrogate is trained on
   the raw values. Enter `peak_temp_C = 187.4`, not `log10(187.4)`.
4. **Steady-state regime only.** The contract assumes steady-state
   thermal FE: temperature field has reached equilibrium under the
   prescribed boundary conditions, no transient warm-up / cool-down,
   no phase change. If your FE problem is transient or includes phase
   change, this surrogate will misrepresent the physics — that is a
   different bucket (TASK-1 entry A.3.2). The trainer does NOT detect
   transient inputs automatically; honour this constraint upstream.
5. **Constant-property regime (one-row-per-(material, geometry)
   pair).** The contract treats `conductivity_W_mK` as a single scalar
   per run. If your high-fidelity FE uses temperature-dependent
   `k(T)`, you have two options: (a) report the *effective* k at the
   run's mean temperature and accept the constant-k simplification, or
   (b) treat the strongly k(T)-dependent regime as out of scope for
   this surrogate (TASK-1 A.3.1 Pitfall (i) — material-property
   temperature dependence is the dominant thermal-surrogate-failure
   mode). The trainer cannot tell which choice you made; honour the
   simplification upstream.
6. **Single-class boundary conditions per dataset.** The contract
   assumes a uniform boundary-condition class across runs: Dirichlet
   on the heat-source-attachment face and Robin (convective) on the
   cooled surfaces. If some of your runs use radiation boundaries or
   prescribed-flux Neumann boundaries, train a separate surrogate per
   class — surrogates trained across classes lose the architectural
   guarantee the bucket relies on (TASK-1 A.3.1 Pitfall (ii) —
   boundary-condition class inheritance).
7. **No blanks in the numeric columns; all numeric.** Columns 1–9
   must contain numbers in every row. The optional `notes` column may
   be blank. The trainer rejects a dataset with any missing or
   non-numeric value in columns 1–9.
8. **At least 80 rows; more is better.** The 7-input geometry +
   material + boundary + operating-point space is comparable to the
   pump-pair design + operating-point space, so the minimum is the
   same as the pump pair and the structural example (80 rows).
   200–400 well-spread runs is a healthy dataset; the sample shipped
   here has 250.
9. **Spread your runs across the ranges.** The model can only be
   trusted inside the range of data it has seen. If every run uses
   `conductivity_W_mK = 200` (aluminium), the model learns nothing
   about how peak temperature scales with material conductivity.
   Vary each input independently and span its realistic range. The
   peak-temperature response is *highly* nonlinear in the Biot
   number `Bi = h·L_c / k` — bias your sample density toward the
   high-Bi corner (small k, large h, large L_c) if your design space
   includes thermally-thick regimes.

## Sign conventions

- **`T_ambient_C`** and **`peak_temp_C`** are both in degrees Celsius
  on the same reference scale. The trainer does not non-dimensionalise
  — if you train on Celsius and predict in Kelvin, predictions will be
  wrong by 273.15 every time. Pick one scale and apply it across all
  rows.
- **`q_W`** is the *total* internal heat-generation rate in watts
  integrated over the component volume, not a volumetric density.
  Volumetric density `q̇ [W/m³] = q_W / (length·width·thickness)` is
  recoverable from the geometry columns; surrogates trained on total-W
  inputs decouple the geometry-scaling axis from the per-unit-volume
  axis more cleanly.
- **`hot_spot_x_mm`** is the position along the `length_mm` axis where
  the peak temperature occurs, measured from the heat-source-attachment
  face (`x = 0`) toward the cooled tip (`x = length_mm`). The hot spot
  is typically near `x = 0` for components dominated by source-side
  heating, and shifts toward the interior for components with strong
  internal heat generation.

## How this maps to the taxonomy

TASK-8-1104 sits in the **top-left cell** of the BRIDGE-A slide-9
grid: *scalar/vector (parametric) input → scalar/short-vector QoI
output*. That cell is **Bucket B1 — the tabular surrogate**. This is
the **fourth B1 example** in the iteration-0 inventory (after
TASK-8-1101 fatigue-life, TASK-8-1102 drag/lift, and TASK-8-1103
peak-stress), and the first that lives in the thermal-FE domain.

Catalog anchors:

- TASK-1 §6 A.3.1 — FEA Thermal Steady governing equations / fidelity
  tiers. Textbook anchors: [Bergman2017] (foundational
  conduction-equation framing, Biot / Fourier dimensionless-number
  framework), [Patankar1980] (FV discretisation), [Bathe2014]
  (Galerkin-FE machinery shared with structural FEA),
  [Hughes2000] (FE machinery).
- TASK-3 §6 A.3.1 → Bucket B1 mapping — GBM and GP both listed as
  tabular surrogates for parameter-vector → peak-temperature
  regression. GP is unusually attractive for thermal because the
  Gaussian-process predictive variance gives free uncertainty
  quantification that feeds thermal-margin sizing decisions directly;
  this iteration ships the GBM baseline and a future iteration adds
  the GP variant.
- TASK-4 §5 Bucket B1 roster row.
- `EXAMPLES-ARC-SCOPING.md` §4 inventory (fourth B1 entry).

**Companion examples.** TASK-8-1103 (bracket peak-stress) is the
arc's structural-FE B1 and the closest sibling architecturally —
same 2-target multi-output regressor, same recipe; reading the two
together shows how the same B1 pattern transfers across physics
families. TASK-8-1101 (bracket fatigue-life) is the arc's first B1
and demonstrates a log-scale target. TASK-8-1107 / TASK-8-1401 (pump
operating-point / performance-curve) demonstrate the B1 / B7 split
for a downstream-question shift. All four are worth reading
alongside this example.

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../../../docs/REFERENCES.md).*
