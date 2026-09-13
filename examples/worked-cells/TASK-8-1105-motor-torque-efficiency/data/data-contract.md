# TASK-8-1105 — Data Contract

> This is the exact specification of the dataset the trainer expects.
> Fill `template.csv` so that every column below is present, **in this
> order**, with one row per low-frequency electromagnetic FE run. If your
> file matches this contract, the trainer will accept it; if it does not,
> the trainer will tell you exactly which column is wrong and stop.
>
> All numeric values are *illustrative* in `sample-dataset.csv` — that
> file exists only so you can run the workflow once before supplying
> your own real FE results.

## Columns

| #  | Column name             | Role       | Quantity                                                  | Units  | Typical range |
|----|-------------------------|------------|-----------------------------------------------------------|--------|---------------|
| 1  | `stator_od_mm`          | input      | Stator outer diameter                                     | mm     | 80 – 260      |
| 2  | `stack_length_mm`       | input      | Active axial (stack) length                               | mm     | 40 – 180      |
| 3  | `airgap_mm`             | input      | Mechanical air-gap (rotor-to-stator radial clearance)     | mm     | 0.5 – 2.5     |
| 4  | `magnet_thickness_mm`   | input      | Permanent-magnet radial thickness                         | mm     | 3 – 12        |
| 5  | `turns_per_coil`        | input      | Number of conductor turns per stator coil                 | turns  | 6 – 30        |
| 6  | `current_a`             | input      | Stator phase-current amplitude at the operating point     | A      | 20 – 160      |
| 7  | `speed_rpm`             | input      | Rotor mechanical speed                                    | rpm    | 500 – 12000   |
| 8  | `temperature_c`         | input      | Magnet / winding operating temperature                    | °C     | 20 – 140      |
| 9  | `torque_nm`             | **target** | Mean electromagnetic torque at the operating point        | N·m    | 0 – 90        |
| 10 | `efficiency_pct`        | **target** | Electromagnetic-to-mechanical efficiency at the op. point | %      | 40 – 99       |
| 11 | `total_loss_w`          | **target** | Total electromagnetic + mechanical loss at the op. point  | W      | 0 – 1800      |
| 12 | `notes`                 | *optional* | Free-form notes (run ID, DOE label)                       | text   | —             |

## Rules

1. **Eight inputs, three targets.** Columns 1–8 are the parameters you
   vary across your DOE (4 geometry + 1 winding + 3 operating-point).
   Columns 9–11 are the three headline low-frequency-EM responses your
   run produced. Column 12 is optional and ignored by the trainer; it
   exists so you can carry your own run labels through. This is the
   first example in the arc with a **three-value output bundle** — the
   only structural change from the two-target structural and thermal
   examples (TASK-8-1103 / TASK-8-1104) is the slightly longer output
   vector. Catalog anchor: TASK-1 entry A.5.1 (Electromagnetics:
   Low-frequency — motors, induction; [Jackson1998] is the textbook
   anchor for the Maxwell-equation derivations and the magneto-
   quasi-static reduction, and [Bathe2014] / Q-cae-05 / [Hughes2000]
   for the Galerkin-FE machinery shared with structural FE).
2. **One row per FE run.** Each row is one completed low-frequency-EM
   solve at one operating point: the 8 input parameters and the 3
   response numbers the run produced. The three targets are the
   *integral* outputs (torque, efficiency, loss) — the production-mature
   surrogate-target flavor per TASK-1 A.5.1 (integral outputs average
   out local-field errors that would dominate a full-B-field
   regression; see Rule 6 and Pitfall (iii) below). Use the *same*
   mesh-refinement and solver-settings policy across all rows — mixing
   2-D-cross-section and 3-D runs, or fundamental-frequency and
   transient-time-stepping runs, gives the surrogate hidden variables
   it cannot see (TASK-1 A.5.1 Pitfalls (iv) and (v)).
3. **Targets are linear-scale, not logarithmic.** Torque, efficiency,
   and loss each span at most ~2–3 orders of magnitude across the
   ranges above, but the surrogate handles that natively here, so
   train on the raw values. Enter `torque_nm = 42.7`, not
   `log10(42.7)`. (Contrast TASK-8-1101 fatigue-life, where the target
   spanned many decades and a log transform was warranted.)
4. **Operating-point sweep is part of the DOE.** Unlike a pure
   geometry-only design study, two of the three response columns
   (efficiency, loss) depend strongly on `current_a` and `speed_rpm`.
   A complete dataset sweeps both the *design* axes (geometry, magnet,
   turns) and the *operating-point* axes (current, speed, temperature).
   If every run is at one fixed speed and current, the surrogate learns
   nothing about the efficiency map across the operating envelope — and
   the efficiency map is the headline motor-design deliverable.
5. **Single analysis-class per dataset (the load-bearing discipline).**
   The contract assumes a uniform analysis class across runs:
   2-D-cross-section *or* 3-D, and periodic-steady-state *or* transient
   — not a mix. Per TASK-1 A.5.1 Pitfall (iv), surrogates trained on
   2-D-cross-section data are blind to end-region and axial-skew
   effects; per Pitfall (v), surrogates trained on periodic-steady-state
   data cannot be used for fault-transient analyses (start-up,
   short-circuit, demagnetisation event). If your DOE mixes classes,
   train a separate surrogate per class. The trainer cannot tell which
   class your runs are; honour this constraint upstream.
6. **Integral outputs only — do not mix with full-field targets.** Per
   TASK-1 A.5.1 Pitfall (iii), the integral outputs in this contract
   (torque, efficiency, loss) are a fundamentally *easier* surrogate
   target than the full B / H / J vector fields, because the integration
   averages out the local-field errors that would dominate a full-field
   regression. This example is the integral-output flavor. If you need
   per-region local Joule heating for a downstream thermal-coupling
   analysis, that is the full-field flavor — a different bucket (and a
   different architecture: 3-D CNN / sparse-CNN / FNO per TASK-1 A.5.1
   Trainable-ML-architectures), not this tabular surrogate.
7. **No blanks in the numeric columns; all numeric.** Columns 1–11 must
   contain numbers in every row. The optional `notes` column may be
   blank. The trainer rejects a dataset with any missing or
   non-numeric value in columns 1–11.
8. **At least 80 rows; more is better.** The 8-input geometry + winding
   + operating-point space is comparable to the structural example's
   9-input space, so the minimum is the same as the structural and
   thermal examples (80 rows). 200–400 well-spread runs is a healthy
   dataset; the sample shipped here has 250.
9. **Spread your runs across the ranges, and cover the saturation
   knee.** The model can only be trusted inside the range of data it
   has seen. The torque response is *highly* nonlinear in stator
   current near magnetic saturation — bias your sample density so it
   spans below-saturation, knee-of-the-curve, and deep-saturation
   regimes (TASK-1 A.5.1 Pitfall (i), the dominant low-frequency-EM
   surrogate-failure mode). Likewise cover the operating-temperature
   range, including the hot end where permanent-magnet remanence
   degrades materially (Pitfall (ii)). A surrogate that only sees the
   below-saturation, nominal-temperature corner will over-predict
   torque at high current and hot temperature.

## Sign conventions

- **`current_a`** is the stator phase-current *amplitude* at the
  operating point (peak of the sinusoid), q-axis-dominant for the
  torque-producing component. If your control parameterisation is in
  RMS, convert to amplitude (`amplitude = √2 · RMS`) and apply the
  same convention across all rows — the trainer does not know which
  convention you used.
- **`torque_nm`** is the *mean* electromagnetic torque over a
  fundamental electrical period at the operating point, not the peak or
  the cogging-ripple amplitude. Torque ripple and cogging are a
  separate NVH-input deliverable (TASK-1 A.5.1 → A.4 cross-reference)
  and are not modelled by this surrogate.
- **`efficiency_pct`** is the electromagnetic-to-mechanical efficiency
  `100 · P_out / (P_out + P_loss)` at the operating point, on a 0–100
  *percent* scale (enter `94.2`, not `0.942`). Pick the percent scale
  and apply it across all rows.
- **`total_loss_w`** is the *total* loss in watts at the operating
  point — copper + iron + mechanical + stray, summed. If your FE export
  separates the loss components, sum them into this single column;
  per-component loss breakdown is a richer output the tabular surrogate
  could carry as extra targets in a future variant, but this contract
  rolls them to a single total.
- **`temperature_c`** is the magnet / winding operating temperature, on
  the Celsius scale. The permanent-magnet remanence and the winding
  resistance both depend on it; train across the realistic operating
  range so the surrogate learns the derate.

## How this maps to the taxonomy

TASK-8-1105 sits in the **top-left cell** of the BRIDGE-A slide-9
grid: *scalar/vector (parametric) input → scalar/short-vector QoI
output*. That cell is **Bucket B1 — the tabular surrogate**. This is
the **fifth B1 example** in the iteration-0 inventory (after
TASK-8-1101 fatigue-life, TASK-8-1102 drag/lift, TASK-8-1103
peak-stress, and TASK-8-1104 peak-temperature), and the first that
lives in the low-frequency-electromagnetics domain.

Catalog anchors:

- TASK-1 §6 A.5.1 — Electromagnetics: Low-frequency (motors,
  induction) governing equations / fidelity tiers. Textbook anchors:
  [Jackson1998] (Maxwell-equation derivations and the magneto-
  quasi-static reduction `∇×H = J`), [Bathe2014] / Q-cae-05 (Galerkin-FE
  machinery shared with structural FE), [Hughes2000] (FE machinery).
  The integral-output regression flavor (torque / efficiency / loss)
  is named in TASK-1 A.5.1 Trainable-ML-architectures as the
  production-mature target with deep deployment in motor-design
  optimisation; GBM / MLP / GP are the listed tabular architectures
  ([Chen2016] / [Ke2017] / [Goodfellow2016] / [Rasmussen2006];
  Q-ml-tab-02 / Q-ml-tab-02b / Q-ml-tab-03 / Q-ml-tab-04).
- TASK-3 §6 A.5.1 → Bucket B1 mapping — integral-output regression
  (forces, torques, efficiency, flux-linkage maps) as the easier,
  production-mature surrogate target; full-field B/H/J regression is
  the research-active flavor in a different bucket.
- TASK-4 §5 Bucket B1 roster row.
- `EXAMPLES-ARC-SCOPING.md` §4 inventory (fifth B1 entry).

**Companion examples.** TASK-8-1104 (peak-temperature) and TASK-8-1103
(peak-stress) are the closest siblings architecturally — same
multi-output gradient-boosted-tree regressor, same recipe; this example
extends the output vector from two targets to **three** (torque,
efficiency, loss), which is the only structural change. Reading the
three together shows how the same B1 pattern transfers across physics
families (structural FE → thermal FE → low-frequency EM) and scales
cleanly to a slightly longer output vector. TASK-8-1101 (bracket
fatigue-life) is the arc's first B1 and demonstrates a log-scale
target. TASK-8-1107 / TASK-8-1401 (pump operating-point /
performance-curve) demonstrate the B1 / B7 split for a downstream-
question shift. All are worth reading alongside this example.
