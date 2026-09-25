# Drag-lift example — Assembly Catalog (catalog → physical attributes)

> This file is the **lookup table** that converts each assembly-slot
> option code (CHS-A1, ENG-A2, …) into the physical-attribute values
> the surrogate actually uses. The surrogate is trained on the
> *physical attributes*, not on the option codes; the codes are a
> reader-friendly naming layer the trainer resolves on the reader's
> behalf.
>
> Two consequences of this design that matter to a reader:
>
> 1. **Dual-channel input.** When you predict with the trained model
>    you can supply either the option codes (the model looks up the
>    attributes for you), the physical attributes directly (skip the
>    catalog), or a mix (codes for some slots, attributes for others).
> 2. **New assemblies are predictable within reason.** If you design
>    a new ROPS that has `rops_lateral_projected_area_m2 = 1.40` —
>    a value between catalog options ROPS-A1 (0.00) and ROPS-A2
>    (1.85) — the surrogate predicts on that attribute value
>    directly. The prediction is honest *within the training
>    envelope* and flagged as extrapolation outside it.
>
> The catalog values below are *illustrative* in this synthetic
> example. In a real CAE program, the catalog would be authored by
> the CAE / vehicle-architecture team from CAD measurements or
> wind-tunnel runs of each option's geometry. The catalog itself is
> not learned; it is *measured* once per option and reused across
> CFD studies.

## Slot → physical-attribute schema

Each slot maps to one or more named physical attributes. All
attribute values are floats; units are documented.

| Slot | Physical attribute(s) | Units | Notes |
|------|------------------------|-------|-------|
| `chassis_option` | `chassis_envelope_height_mm`, `chassis_envelope_width_mm` | mm, mm | Frame outer envelope; drives effective frontal area and side-view shape. |
| `engine_option` | `hood_clearance_mm`, `grille_area_m2` | mm, m² | Hood-bulge height above stock; front grille area for mass-flow demand. |
| `transmission_option` | `tunnel_belly_clearance_mm` | mm | Underbody tunnel depth; small underbody flow effect. |
| `clutch_option` | `clutch_protrusion_mm` | mm | Belly-pan disturbance; minor underbody effect. |
| `cooling_option` | `radiator_frontal_area_m2`, `radiator_pressure_drop_pa` | m², Pa | Front-face mass-flow demand. Higher pressure drop → more drag-as-cooling-tax. |
| `intake_option` | `intake_height_above_hood_mm`, `intake_diameter_mm` | mm, mm | The classic snorkel: a vertical drag tower. Both height and diameter scale the effect. |
| `exhaust_option` | `exhaust_protrusion_height_mm`, `exhaust_protrusion_width_mm` | mm, mm | Externally-routed exhaust surface area; affects surface drag + side-flow under yaw. |
| `fuel_option` | `tank_underbody_drop_mm` | mm | Long-range tank drops below baseline underbody. |
| `brakes_option` | `brake_duct_inlet_area_m2` | m² | Brake-cooling duct mass-flow; affects underhood pressure recovery. |
| `cabin_option` | `cabin_frontal_area_m2`, `cabin_length_m`, `cabin_height_mm` | m², m, mm | Cabin envelope. **NONE = all zeros** (open-frame ATV / dune-buggy). |
| `electrical_option` | `battery_underbody_height_mm` | mm | Battery pack underbody protrusion (dual-battery / winch-rated). |
| `oil_option` | `oil_cooler_frontal_area_m2` | m² | External oil-cooler frontal area (when present). |
| `rops_option` | `rops_lateral_projected_area_m2`, `rops_height_above_roof_mm` | m², mm | Roll-over cage geometry. **NONE = all zeros** (sealed-cab vehicles). |
| `steering_option` | `steering_column_diameter_mm` | mm | Hydraulic-assist columns have a thicker external profile; minor. |
| `suspension_front_option` | `front_ride_height_mm`, `front_track_width_mm` | mm, mm | Front ride-height + track width; drives stance + crosswind exposure. |
| `suspension_rear_option` | `rear_ride_height_mm`, `rear_track_width_mm` | mm, mm | Same as front, rear-axle. |

**Total physical attributes:** 26 across the 16 slots.

**Plus the operating-point continuous inputs** (not slot-resolved):
`speed_kmh`, `yaw_deg`.

**Total model inputs:** 26 attributes + 2 operating-point = **28 inputs.**

## Slot → option → attribute-value lookup

Each row below is one catalog option. The Right-hand columns are the
attribute values the surrogate sees when that option code is used.
The lookup is loaded at training time and persisted into
`model-info.json` so the predictor can apply it consistently.

### chassis_option

| Option | chassis_envelope_height_mm | chassis_envelope_width_mm |
|--------|----------------------------|---------------------------|
| `CHS-A1` ladder-frame | 1850 | 1980 |
| `CHS-A2` monocoque | 1720 | 1920 |
| `CHS-A3` tube-frame | 1920 | 2040 |

### engine_option

| Option | hood_clearance_mm | grille_area_m2 |
|--------|-------------------|----------------|
| `ENG-A1` small I4 | 0 | 0.42 |
| `ENG-A2` mid V6 | 20 | 0.52 |
| `ENG-A3` large V8 | 45 | 0.62 |

### transmission_option

| Option | tunnel_belly_clearance_mm |
|--------|---------------------------|
| `TRN-A1` manual | 110 |
| `TRN-A2` automatic | 130 |
| `TRN-A3` dual-clutch | 105 |

### clutch_option

| Option | clutch_protrusion_mm |
|--------|----------------------|
| `CLT-A1` hydraulic | 25 |
| `CLT-A2` dry | 22 |
| `CLT-A3` dual | 32 |

### cooling_option

| Option | radiator_frontal_area_m2 | radiator_pressure_drop_pa |
|--------|--------------------------|---------------------------|
| `COL-A1` stock | 0.32 | 180 |
| `COL-A2` oversized | 0.42 | 240 |
| `COL-A3` trans-cooler-add | 0.48 | 280 |

### intake_option

| Option | intake_height_above_hood_mm | intake_diameter_mm |
|--------|------------------------------|---------------------|
| `INT-A1` stock | 0 | 0 |
| `INT-A2` snorkel | 380 | 140 |
| `INT-A3` high-mount | 180 | 180 |

### exhaust_option

| Option | exhaust_protrusion_height_mm | exhaust_protrusion_width_mm |
|--------|-------------------------------|------------------------------|
| `EXH-A1` stock-routing | 0 | 0 |
| `EXH-A2` high-mount | 220 | 80 |
| `EXH-A3` side-exit | 80 | 120 |

### fuel_option

| Option | tank_underbody_drop_mm |
|--------|------------------------|
| `FUL-A1` stock | 0 |
| `FUL-A2` dual-tank | 35 |
| `FUL-A3` long-range | 55 |

### brakes_option

| Option | brake_duct_inlet_area_m2 |
|--------|---------------------------|
| `BRK-A1` stock-disc | 0.06 |
| `BRK-A2` large-disc | 0.09 |
| `BRK-A3` heavy-duty | 0.12 |

### cabin_option

| Option | cabin_frontal_area_m2 | cabin_length_m | cabin_height_mm |
|--------|------------------------|----------------|-----------------|
| `CAB-A1` single-cab | 2.10 | 1.40 | 1280 |
| `CAB-A2` double-cab | 2.45 | 2.10 | 1380 |
| `CAB-A3` crew-cab | 2.70 | 2.60 | 1420 |
| `NONE` (open-frame ATV) | 0.00 | 0.00 | 0 |

### electrical_option

| Option | battery_underbody_height_mm |
|--------|------------------------------|
| `ELE-A1` stock-12V | 0 |
| `ELE-A2` dual-battery | 28 |
| `ELE-A3` winch-rated | 48 |

### oil_option

| Option | oil_cooler_frontal_area_m2 |
|--------|-----------------------------|
| `OIL-A1` stock | 0.00 |
| `OIL-A2` extra-cooler | 0.08 |
| `OIL-A3` dry-sump | 0.05 |

### rops_option

| Option | rops_lateral_projected_area_m2 | rops_height_above_roof_mm |
|--------|----------------------------------|----------------------------|
| `ROPS-A1` internal | 0.00 | 0 |
| `ROPS-A2` exposed-cage | 1.85 | 220 |
| `ROPS-A3` hi-rise-cage | 2.45 | 380 |
| `NONE` (sealed-cab) | 0.00 | 0 |

### steering_option

| Option | steering_column_diameter_mm |
|--------|------------------------------|
| `STR-A1` rack-pinion | 24 |
| `STR-A2` recirc-ball | 28 |
| `STR-A3` hydraulic-assist | 36 |

### suspension_front_option

| Option | front_ride_height_mm | front_track_width_mm |
|--------|----------------------|----------------------|
| `SFR-A1` independent | 220 | 1620 |
| `SFR-A2` solid-axle | 280 | 1680 |
| `SFR-A3` long-travel | 360 | 1740 |

### suspension_rear_option

| Option | rear_ride_height_mm | rear_track_width_mm |
|--------|---------------------|---------------------|
| `SRR-A1` independent | 220 | 1620 |
| `SRR-A2` solid-axle | 290 | 1690 |
| `SRR-A3` long-travel | 360 | 1740 |

## Using the catalog at predict-time

When you make predictions, you can address each slot in one of two ways:

1. **Catalog mode** (default). Supply the option code (`INT-A2`); the
   predictor resolves it to `(intake_height_above_hood_mm=380,
   intake_diameter_mm=140)` via this catalog. This is the simplest
   mode and is what the single-point and batch-mode UIs default to.

2. **Direct-attributes mode**. Supply the physical-attribute values
   directly for a slot (`intake_height_above_hood_mm=420,
   intake_diameter_mm=180`) — useful when you are exploring a *new*
   assembly design that does not match any catalog option, or when
   you want to interpolate between two catalog options at a custom
   value (e.g., `intake_height_above_hood_mm=280` is halfway between
   stock-zero and high-mount-180, with diameter 180).

In batch-mode CSVs, every slot you want to address by direct
attributes contributes its attribute column(s) to the CSV instead of
its `<slot>_option` column. Mixing is allowed per row — different
rows can use different mixes — but within a single row each slot is
either catalog (its `<slot>_option` column is set) or direct
(its attribute columns are set).

**Extrapolation flag.** The trainer records the observed (min, max)
of each *physical attribute* across the training rows. The predictor
flags any input that falls outside its training envelope, whether
the input came from a catalog code or was supplied directly. New
catalog options whose attributes happen to fall outside the training
envelope will also be flagged.

## Pedagogical note

A core surrogate-modelling lesson this example teaches is:

> *The surrogate's input vocabulary should be the physical attributes
> that drive the physics, not the engineering nomenclature.* The
> catalog layer is a usability translation, not a physics one. The
> reader's CSV stays reader-friendly (option codes); the model sees
> physics (resolved attributes).

This is why the trainer separates "what the reader provides" from
"what the model regresses on" — the same separation a chained-surrogate
design makes between its links (predicted coefficients as the hand-off),
but at the input side rather than the output side.
