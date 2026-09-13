# TASK-8-1106 — Data Contract

> This is the exact specification of the dataset the trainer expects.
> Fill `template.csv` so that every column below is present, **in this
> order**, with one row per injection-molding process-simulation run. If
> your file matches this contract, the trainer will accept it; if it does
> not, the trainer will tell you exactly which column is wrong and stop.
>
> All numeric values are *illustrative* in `sample-dataset.csv` — that
> file exists only so you can run the workflow once before supplying
> your own real warpage / shrinkage results.

## Columns

| #  | Column name                  | Role       | Quantity                                                       | Units  | Typical range |
|----|------------------------------|------------|----------------------------------------------------------------|--------|---------------|
| 1  | `melt_temp_c`                | input      | Polymer-melt (barrel) temperature at injection                 | °C     | 200 – 300     |
| 2  | `mold_temp_c`                | input      | Mold-coolant / cavity-wall temperature                         | °C     | 20 – 100      |
| 3  | `pack_pressure_mpa`          | input      | Packing (hold) pressure                                        | MPa    | 30 – 120      |
| 4  | `cooling_time_s`             | input      | Packing + cooling time in the mold                             | s      | 8 – 40        |
| 5  | `injection_rate_ccs`         | input      | Injection (fill) volumetric flow rate                          | cm³/s  | 10 – 120      |
| 6  | `wall_thickness_mm`          | input      | Nominal part wall thickness                                    | mm     | 1 – 4         |
| 7  | `part_size_mm`               | input      | Projected part size / characteristic flow length              | mm     | 50 – 400      |
| 8  | `glass_fibre_pct`            | input      | Glass-fibre weight content of the polymer grade               | %      | 0 – 40        |
| 9  | `warpage_mm`                 | **target** | Peak out-of-plane warpage (deflection magnitude)              | mm     | 0 – 10        |
| 10 | `springback_mm`              | **target** | Elastic spring-back recovered on ejection                     | mm     | 0 – 5         |
| 11 | `peak_residual_stress_mpa`   | **target** | Peak frozen-in residual stress in the as-molded part          | MPa    | 0 – 130       |
| 12 | `notes`                      | *optional* | Free-form notes (run ID, DOE label, polymer grade)            | text   | —             |

## Rules

1. **Eight inputs, three targets.** Columns 1–8 are the parameters you
   vary across your DOE (5 process + 2 part-design + 1 material).
   Columns 9–11 are the three headline as-molded-quality responses your
   run produced. Column 12 is optional and ignored by the trainer; it
   exists so you can carry your own run labels (and, importantly, your
   polymer grade — see Rule 5) through. Like TASK-8-1105 this is a
   **three-value output bundle** example; the recipe is identical to the
   structural / thermal / motor examples and simply carries three
   targets. Catalog anchor: TASK-1 §6 A.10.2 (Manufacturing: Injection
   molding; [Kennedy2013] is the foundational textbook anchor for the
   numerical-modelling treatment of injection-molding flow analysis — the
   Hele-Shaw / 2.5-D fill formulation, the packing and cooling phases
   that drive residual stress and warpage, and the fibre-orientation
   evolution that drives anisotropic shrinkage).
2. **One row per simulation run.** Each row is one completed
   fill→pack→cool→warp solve at one process setting for one part design:
   the 8 input parameters and the 3 response numbers the run produced.
   The three targets are *integral / headline* part-level scalars
   (peak warpage, spring-back, peak residual stress) — the deployed
   tabular-surrogate target flavor per TASK-1 §6 A.10.2 (the deployed
   industrial pattern at injection-molded-component design organisations
   regresses process-and-design parameters → headline as-molded-quality
   metric). Use the *same* solver, mesh policy, and analysis settings
   across all rows.
3. **Targets are linear-scale, not logarithmic.** Warpage, spring-back,
   and residual stress each span at most ~2–3 orders of magnitude across
   the ranges above, and the surrogate handles that natively here, so
   train on the raw values. Enter `warpage_mm = 1.8`, not
   `log10(1.8)`. (Contrast TASK-8-1101 fatigue-life, where the target
   spanned many decades and a log transform was warranted.)
4. **Process-and-design sweep is part of the DOE.** Warpage is a coupled
   consequence of *both* the process window (melt / mold temperature,
   packing pressure, cooling time, injection rate) *and* the part design
   (wall thickness, size, fibre loading). A complete dataset sweeps both
   families. If every run is at one fixed process setting, the surrogate
   learns nothing about the process-window sensitivity — and the
   process-window sensitivity is exactly what a molding engineer tunes
   to pull warpage into tolerance.
5. **Single polymer-class per dataset (the load-bearing discipline).**
   The contract assumes one polymer base-resin class across all runs
   (e.g. one PP-GF family, or one PA6-GF family — not a mix). Per
   TASK-1 §6 A.10.2 Pitfall (ii), a surrogate trained on one polymer
   class cannot be silently used on a different class: different
   rheology, different pvT (pressure-volume-temperature) behaviour,
   different fibre-orientation-evolution kinetics, and (for
   semi-crystalline grades) different crystallisation behaviour all
   change the warpage response. `glass_fibre_pct` is carried as a
   *continuous* input here because fibre loading varies *within* a resin
   family and is on the critical path for warpage; the *base-resin class*
   itself is the categorical you must hold fixed per dataset (record it
   in `notes`). The trainer cannot tell which resin class your runs are;
   honour this constraint upstream.
6. **One flow-formulation class per dataset.** Per TASK-1 §6 A.10.2
   Pitfall (iii), a surrogate trained on Hele-Shaw / 2.5-D fill data
   inherits the thin-walled-cavity assumption and cannot be silently
   used on thick-walled parts where the 3-D flow physics matters. Keep
   the formulation class uniform across the dataset (all 2.5-D *or* all
   3-D). The `wall_thickness_mm` input lets the surrogate learn the
   thickness sensitivity *within* a formulation class, but it does not
   make the surrogate valid across the 2.5-D / 3-D boundary.
7. **No blanks in the numeric columns; all numeric.** Columns 1–11 must
   contain numbers in every row. The optional `notes` column may be
   blank. The trainer rejects a dataset with any missing or non-numeric
   value in columns 1–11.
8. **At least 80 rows; more is better.** The 8-input process + design
   space is comparable to the motor example's 8-input space, so the
   minimum is the same as the structural / thermal / motor examples
   (80 rows). 200–400 well-spread runs is a healthy dataset; the sample
   shipped here has 250.
9. **Spread your runs across the ranges, and cover the process-window
   corners.** The model can only be trusted inside the range of data it
   has seen. The warpage response is *highly* nonlinear near the
   short-shot (under-pack) and over-pack boundaries and near the
   thin-wall / large-part corner — bias your sample density so it spans
   the full process window, not just the nominal recipe (TASK-1 §6
   A.10.2 Pitfall (iv), the dominant *deployed-pattern* surrogate-failure
   mode: a surrogate trained on one narrow process-parameter envelope
   mispredicts qualitatively outside it). A surrogate that only sees the
   nominal-recipe corner will mispredict warpage at the aggressive-cycle
   and thin-wall settings that matter most for tolerance.

## Sign conventions

- **`melt_temp_c`** is the polymer-melt temperature as it enters the
  cavity (barrel / nozzle melt temperature), on the Celsius scale. It
  sets the upper end of the thermal-contraction span that drives
  shrinkage; apply the same definition (melt vs. nozzle-set) across all
  rows.
- **`mold_temp_c`** is the mold-coolant / cavity-wall temperature, not
  the part temperature. The difference between melt and mold temperature
  is the contraction span that locks in shrinkage and the residual-stress
  gradient; a hotter mold reduces the gradient but lengthens cycle time.
- **`pack_pressure_mpa`** is the packing (hold) pressure applied after
  fill, in MPa. Packing feeds additional melt into the cavity to
  compensate volumetric shrinkage during cooling; too little under-packs
  (sink and high shrink), too much over-packs (residual stress and
  ejection difficulty). Use the same gauge convention (hydraulic vs.
  cavity / melt pressure) across all rows.
- **`warpage_mm`** is the *peak out-of-plane deflection magnitude* of the
  as-molded part relative to the nominal CAD surface (the headline
  warpage number a Moldflow / Moldex3D warp result reports), not a signed
  per-node displacement. Pick one warpage metric (e.g. peak total
  deflection) and apply it across all rows.
- **`springback_mm`** is the elastic-recovery component of the deflection
  released when the part is ejected and the mold constraint is removed —
  the part of the warpage that "springs back" rather than staying locked
  in. If your post-processing reports total warpage only, derive a
  consistent spring-back metric and apply it uniformly.
- **`peak_residual_stress_mpa`** is the peak frozen-in residual stress in
  the as-molded part in MPa, the locked-in thermal-and-packing stress
  that remains after cooling. It is the upstream-input field for any
  downstream A.2.x structural analysis of the part; per TASK-1 §6 A.10.2
  Pitfall (vi) the architecturally-correct treatment chains this
  manufacturing output into the downstream structural model rather than
  discarding it.

## How this maps to the taxonomy

TASK-8-1106 sits in the **top-left cell** of the BRIDGE-A slide-9
grid: *scalar/vector (parametric) input → scalar/short-vector QoI
output*. That cell is **Bucket B1 — the tabular surrogate**. This is
the **sixth B1 example** in the iteration-0 inventory (after
TASK-8-1101 fatigue-life, TASK-8-1102 drag/lift, TASK-8-1103
peak-stress, TASK-8-1104 peak-temperature, and TASK-8-1105 motor
torque/efficiency), and the first that lives in the manufacturing-
process (injection-molding) domain — closing the iteration-0 domain
spread.

Catalog anchors:

- TASK-1 §6 A.10.2 — Manufacturing: Injection molding governing
  equations / fidelity tiers. Textbook anchor: [Kennedy2013]
  (the canonical numerical-modelling reference for injection-molding
  flow analysis — the Hele-Shaw / 2.5-D fill formulation, packing and
  cooling phases, Folgar-Tucker fibre-orientation evolution, warpage
  and shrinkage prediction; the foundational methodology Moldflow's
  commercial implementation is built on). The headline tabular-
  regression flavor (warpage / shrinkage / peak-stress / weld-line-
  strength scalars) is named in TASK-1 §6 A.10.2 Trainable-ML-
  architectures as the deployed industrial pattern; GBM / MLP are the
  listed tabular architectures ([Chen2016] / [Ke2017] / [Goodfellow2016];
  Q-ml-tab-02 / Q-ml-tab-02b / Q-ml-tab-03 / Q-ml-tab-01). The fibre-
  orientation-tensor *field* prediction flavor is a different bucket and
  a different architecture (3-D CNN / GNN — research-active, not this
  tabular surrogate).
- TASK-3 §6 A.10.2 → Bucket B1 mapping — headline as-molded-quality
  scalar regression as the deployed, production-mature surrogate target;
  full-field fibre-orientation-tensor regression is the research-active
  flavor in a different bucket.
- TASK-4 §5 Bucket B1 roster row.
- `EXAMPLES-ARC-SCOPING.md` §4 inventory (sixth B1 entry).

**Companion examples.** TASK-8-1105 (motor torque/efficiency) is the
closest sibling architecturally — the arc's other **three-target**
multi-output gradient-boosted-tree example, same recipe; this example
applies that identical three-target pattern in the manufacturing-process
domain. TASK-8-1104 (peak-temperature) and TASK-8-1103 (peak-stress) are
the two-target siblings. Reading the manufacturing example after the
motor example shows the same three-target B1 pattern transferring across
yet another physics family (low-frequency EM → injection-molding
process). TASK-8-1101 (bracket fatigue-life) is the arc's first B1 and
demonstrates a log-scale target. TASK-8-1107 / TASK-8-1401 (pump
operating-point / performance-curve) demonstrate the B1 / B7 split for a
downstream-question shift. All are worth reading alongside this example.
