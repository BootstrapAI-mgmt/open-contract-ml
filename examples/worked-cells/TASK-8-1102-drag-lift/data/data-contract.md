# TASK-8-1102 — Data Contract

> This is the exact specification of the dataset the trainer expects.
> Fill `template.csv` so that every column below is present, **in this
> order**, with one row per CAE run. If your file matches this contract,
> the trainer will accept it; if it does not, the trainer will tell you
> exactly which column is wrong and stop.
>
> All numeric values in `sample-dataset.csv` are *illustrative* — that
> file exists only so you can run the workflow once before supplying
> your own real CFD aero results. The synthetic data is generated from
> an internal geometric-delta lookup, **not** from real CFD; the
> sample-data accuracy figures the trainer reports tell you about the
> workflow, not about what you will get on your own runs.

## What this example predicts

An external-aero CAE engineer working on an **off-road / overland
utility vehicle** wants to screen the aerodynamic effects of swapping
one *assembly* for another — e.g., does swapping intake option INT-A1
(stock) for INT-A2 (snorkel) noticeably hurt drag at highway cruise?
Across a 16-slot assembly catalog and two operating conditions
(highway speed and crosswind yaw), the surrogate predicts the four
force / moment coefficients **CD, CL, CY, CM** at the program's
canonical reference area / length, given the assembly-ID vector + the
operating point.

The honest framing is *on-road aero for an off-road-styled vehicle.*
Pure off-road operation is mostly low-speed where aero effects are
negligible; the engineering question that justifies aero CFD on an
off-road platform is sustained highway cruise and crosswind stability
(fuel economy, lane-keeping in side winds).

## Dual-channel input vocabulary (catalog codes OR physical attributes)

This example uses a **dual-channel** input design that is unusual for
a B1 example and worth understanding before you start.

- **What you put in your training CSV: option codes.** The 16
  assembly columns in your CSV are filled with reader-friendly
  *catalog option codes* (`INT-A2`, `CAB-A1`, etc.). This is the
  format below.
- **What the surrogate actually trains on: physical attributes.**
  Each option code is resolved to a small vector of *physical
  attributes* (e.g. `INT-A2 → intake_height_above_hood_mm=380,
  intake_diameter_mm=140`) via the catalog at
  `data/assembly-catalog.md`. The trainer does this resolution
  automatically; you never see it in your CSV.
- **At predict-time you can address each slot either way.** Supply
  the option code (the predictor resolves it for you) or supply the
  underlying physical attributes directly (skip the catalog —
  useful when you're exploring a new design that doesn't match any
  catalog option, or you want a "between" interpolation).

This separation buys two things:

1. **The training CSV stays simple.** Your DOE table contains the
   option codes you actually ran in CFD. No need to redundantly
   record the geometric details.
2. **The surrogate generalizes within the physical-attribute
   envelope.** A new `intake_height_above_hood_mm=280` that doesn't
   match any catalog option still gets a real prediction grounded in
   the trained continuous-attribute manifold, with the standard
   extrapolation flag if the value falls outside the training range.

See `data/assembly-catalog.md` for the full per-slot
catalog → attribute schema. The schema is documented there because
the model card metadata (in `trained-model/model-info.json`) also
carries the lookup so the predictor is fully self-contained.

## Columns — the 18 inputs + 4 targets + 1 optional notes

| #  | Column name | Role | Type | Quantity / option set | Notes |
|----|-------------|------|------|------------------------|-------|
| 1  | `chassis_option` | input | categorical | `CHS-A1` ladder-frame · `CHS-A2` monocoque · `CHS-A3` tube-frame | The frame architecture; strongly affects envelope shape, ride height, and frontal area. |
| 2  | `engine_option` | input | categorical | `ENG-A1` small-displacement I4 · `ENG-A2` mid-displacement V6 · `ENG-A3` large-displacement V8 | Larger engines tend to require taller hood / wider grille → modest CD effects. |
| 3  | `transmission_option` | input | categorical | `TRN-A1` manual · `TRN-A2` automatic · `TRN-A3` dual-clutch | Mostly internal — small effect on tunnel routing, minimal external aero impact. |
| 4  | `clutch_option` | input | categorical | `CLT-A1` hydraulic · `CLT-A2` dry · `CLT-A3` dual | Internal — negligible direct aero impact. |
| 5  | `cooling_option` | input | categorical | `COL-A1` stock · `COL-A2` oversized · `COL-A3` trans-cooler-add | Front face mass-flow + grille area; meaningful effect on CD. |
| 6  | `intake_option` | input | categorical | `INT-A1` stock · `INT-A2` snorkel · `INT-A3` high-mount | Snorkel adds a vertical drag tower; strong CD + CY effect. |
| 7  | `exhaust_option` | input | categorical | `EXH-A1` stock-routing · `EXH-A2` high-mount · `EXH-A3` side-exit | External exhaust paths can create surface-mounted drag features. |
| 8  | `fuel_option` | input | categorical | `FUL-A1` stock · `FUL-A2` dual-tank · `FUL-A3` long-range | Mostly internal — small effect via underbody profile. |
| 9  | `brakes_option` | input | categorical | `BRK-A1` stock-disc · `BRK-A2` large-disc · `BRK-A3` heavy-duty | Front-wheel-well mass-flow demand for brake cooling. |
| 10 | `cabin_option` | input | categorical | `CAB-A1` single-cab · `CAB-A2` double-cab · `CAB-A3` crew-cab · **`NONE`** (open-frame ATV / dune-buggy) | Major frontal-area driver. `NONE` is a valid choice for open-frame vehicles. |
| 11 | `electrical_option` | input | categorical | `ELE-A1` stock-12V · `ELE-A2` dual-battery · `ELE-A3` winch-rated | Mostly internal — negligible direct aero impact. |
| 12 | `oil_option` | input | categorical | `OIL-A1` stock · `OIL-A2` extra-cooler · `OIL-A3` dry-sump | Mostly internal — small effect via cooler air-routing. |
| 13 | `rops_option` | input | categorical | `ROPS-A1` internal · `ROPS-A2` exposed-cage · `ROPS-A3` hi-rise-cage · **`NONE`** (sealed-cab vehicles) | Exposed cages are surface-mounted trip-wire drag generators with strong yaw-dependent CY effect. `NONE` is a valid choice for sealed-cab passenger vehicles. |
| 14 | `steering_option` | input | categorical | `STR-A1` rack-pinion · `STR-A2` recirc-ball · `STR-A3` hydraulic-assist | Internal — negligible direct aero impact. |
| 15 | `suspension_front_option` | input | categorical | `SFR-A1` independent · `SFR-A2` solid-axle · `SFR-A3` long-travel | Ride height + fender bulge; meaningful effect on CD and CL. |
| 16 | `suspension_rear_option` | input | categorical | `SRR-A1` independent · `SRR-A2` solid-axle · `SRR-A3` long-travel | Same as front; rear-axle effect on CL trim balance. |
| 17 | `speed_kmh` | input | continuous | 60 – 130 km/h | Highway cruise envelope; outside this range the surrogate flags extrapolation. |
| 18 | `yaw_deg` | input | continuous | −15 – +15 degrees | Crosswind / overtaking-turbulence envelope. Sign convention: positive = wind from driver's right. |
| 19 | `CD` | **target** | continuous | dimensionless | Drag coefficient at the program's reference area. |
| 20 | `CL` | **target** | continuous | dimensionless | Lift coefficient at the program's reference area. Positive = upward (lifting); off-road utility vehicles are typically slightly positive. |
| 21 | `CY` | **target** | continuous | dimensionless | Side-force coefficient. Sign follows the same right-hand convention as yaw. |
| 22 | `CM` | **target** | continuous | dimensionless | Yawing-moment coefficient about the vehicle's vertical centerline at the program's reference length. Positive = nose-out-of-wind. |
| 23 | `notes` | input (optional) | text | freeform | Optional — the trainer ignores it. Useful for recording the DOE row's CFD case ID or comments. |

## Rules

1. **Sixteen categorical inputs + two continuous inputs + four
   continuous targets.** Columns 1–16 are the assembly-ID vector that
   defines the vehicle build. Columns 17–18 are the operating point.
   Columns 19–22 are what the surrogate learns to predict. Column 23
   is optional and ignored by the trainer.
2. **One row per CFD run.** Each row is one completed external-aero
   CFD case at one specific assembly build and one specific
   (speed, yaw) operating point.
3. **Assembly codes must match the option set above** — the trainer
   rejects any value not in the documented set (except `NONE` for
   `cabin_option` and `rops_option`, which is valid for those two
   slots only). An unknown code at predict-time triggers an
   extrapolation flag.
4. **`NONE` is a valid choice for `cabin_option` and `rops_option`
   only.** Treat absence-of-feature as itself a design choice — for
   example, an open-frame ATV legitimately has `cabin_option=NONE` and
   `rops_option=ROPS-A2`. For all other slots, one of the three
   catalog codes must be supplied.
5. **No blanks in input columns, all categorical values must be exact
   string matches; numeric inputs must be parseable as floats.** The
   trainer rejects a dataset with any missing or non-conformant cell.
6. **At least 80 rows; 150 – 300 well-spread rows is healthy.** A
   16-categorical-input GBM needs enough rows to see each option at
   least a few times under varied operating conditions before its
   per-assembly effect estimates are trustworthy. The trainer enforces
   the 80-row floor.
7. **Spread your runs across the assembly options and operating
   range.** If every run uses `intake_option=INT-A1`, the model
   learns nothing about the snorkel option. Aim for each slot's
   options to appear at varied speeds and yaws.

## Sign conventions

- **CD positive** is drag in the +X direction (rearward on the
  vehicle, opposing forward motion).
- **CL positive** is lift in the +Z direction (upward).
- **CY positive** is side-force toward the driver's left (right-hand
  rule with X forward, Z up).
- **CM positive** is yawing moment that turns the vehicle's nose
  *out of the wind* (positive yaw produces a positive CM that
  stabilises lateral motion; negative CM indicates a yaw-divergent
  vehicle).
- All coefficients are non-dimensionalised at the program's reference
  area / length / dynamic pressure — the trainer does not need these
  values; it learns the dimensionless mapping directly.

## How this maps to the taxonomy

TASK-8-1102 sits in the **top-left cell** of the BRIDGE-A slide-9 grid:
*scalar / vector (parametric) input → scalar QoI output* (a 4-target
output is still in the scalar-QoI column — each target is its own
scalar). That cell is **Bucket B1 — the tabular surrogate**. The
dual-channel input handling is via the catalog-resolution layer at
load time: option codes (categorical) are resolved into physical
attributes (continuous) by lookup before the GBM sees them, so the
model itself regresses on the continuous physical-attribute vector
(26 attributes from the 16 slots + 2 operating-point continuous = 28
inputs). No one-hot encoding is needed. Catalog anchor:
`tasks/TASK-1-cae-analysis-catalog.md` entry **A.1.1
CFD.External-Aero**; bucket roster:
`tasks/TASK-4-architecture-buckets.md` §5, Bucket B1.

## Illustrative-numerics caveat (per `EXAMPLES-ARC-SCOPING.md` §6.1)

`sample-dataset.csv` is generated by a synthetic geometric-delta
lookup that composes per-assembly aero contributions and adds modest
Gaussian noise to mimic CFD-vs-test scatter. **The accuracy figures
the trainer prints on the sample data are properties of the
synthesizer, not of CFD.** When you train on your own real CFD runs
the figures will be different — better or worse depending on how
well-conditioned your DOE is. The sample-data figures tell you the
workflow runs end-to-end; they tell you nothing about the surrogate's
accuracy on real aero CFD.
