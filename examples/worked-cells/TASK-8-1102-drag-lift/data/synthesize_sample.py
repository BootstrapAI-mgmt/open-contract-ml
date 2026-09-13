#!/usr/bin/env python3
"""
synthesize_sample.py — Generate `sample-dataset.csv` for TASK-8-1102.

This is a *synthetic* data generator. It computes 4 aerodynamic
coefficients (CD, CL, CY, CM) as smooth, physics-flavoured functions
of the underlying *physical attributes* (per slot) plus the operating
point. Per-assembly catalog options are then labels for specific
attribute-value sets per the catalog at data/assembly-catalog.md.

The reader-facing CSV that this script writes contains the catalog
option codes (not the attribute values) so the reader can interpret
each row as a vehicle build. The trainer resolves codes → attributes
via the catalog at load time and trains on the attribute vector.

This is NOT a CFD solver. It is NOT real aero data. Its purpose is
to let a reader run the workflow once before producing real CFD runs.
The illustrative-numerics discipline (EXAMPLES-ARC-SCOPING.md §6.1)
applies: figures derived from this data tell you about the
synthesizer, not about CFD.

Usage:
    python synthesize_sample.py [--n-rows 200] [--out sample-dataset.csv]
                                [--seed 42]

The default invocation reproduces the shipped sample-dataset.csv
byte-for-byte at seed=42, n-rows=200.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Catalog: slot → list of (option_code, attribute_dict)
# Mirrors data/assembly-catalog.md exactly. Update both together.
# ---------------------------------------------------------------------------

CATALOG: dict[str, list[tuple[str, dict[str, float]]]] = {
    "chassis_option": [
        ("CHS-A1", {"chassis_envelope_height_mm": 1850.0, "chassis_envelope_width_mm": 1980.0}),
        ("CHS-A2", {"chassis_envelope_height_mm": 1720.0, "chassis_envelope_width_mm": 1920.0}),
        ("CHS-A3", {"chassis_envelope_height_mm": 1920.0, "chassis_envelope_width_mm": 2040.0}),
    ],
    "engine_option": [
        ("ENG-A1", {"hood_clearance_mm": 0.0,  "grille_area_m2": 0.42}),
        ("ENG-A2", {"hood_clearance_mm": 20.0, "grille_area_m2": 0.52}),
        ("ENG-A3", {"hood_clearance_mm": 45.0, "grille_area_m2": 0.62}),
    ],
    "transmission_option": [
        ("TRN-A1", {"tunnel_belly_clearance_mm": 110.0}),
        ("TRN-A2", {"tunnel_belly_clearance_mm": 130.0}),
        ("TRN-A3", {"tunnel_belly_clearance_mm": 105.0}),
    ],
    "clutch_option": [
        ("CLT-A1", {"clutch_protrusion_mm": 25.0}),
        ("CLT-A2", {"clutch_protrusion_mm": 22.0}),
        ("CLT-A3", {"clutch_protrusion_mm": 32.0}),
    ],
    "cooling_option": [
        ("COL-A1", {"radiator_frontal_area_m2": 0.32, "radiator_pressure_drop_pa": 180.0}),
        ("COL-A2", {"radiator_frontal_area_m2": 0.42, "radiator_pressure_drop_pa": 240.0}),
        ("COL-A3", {"radiator_frontal_area_m2": 0.48, "radiator_pressure_drop_pa": 280.0}),
    ],
    "intake_option": [
        ("INT-A1", {"intake_height_above_hood_mm":   0.0, "intake_diameter_mm":   0.0}),
        ("INT-A2", {"intake_height_above_hood_mm": 380.0, "intake_diameter_mm": 140.0}),
        ("INT-A3", {"intake_height_above_hood_mm": 180.0, "intake_diameter_mm": 180.0}),
    ],
    "exhaust_option": [
        ("EXH-A1", {"exhaust_protrusion_height_mm":   0.0, "exhaust_protrusion_width_mm":   0.0}),
        ("EXH-A2", {"exhaust_protrusion_height_mm": 220.0, "exhaust_protrusion_width_mm":  80.0}),
        ("EXH-A3", {"exhaust_protrusion_height_mm":  80.0, "exhaust_protrusion_width_mm": 120.0}),
    ],
    "fuel_option": [
        ("FUL-A1", {"tank_underbody_drop_mm":  0.0}),
        ("FUL-A2", {"tank_underbody_drop_mm": 35.0}),
        ("FUL-A3", {"tank_underbody_drop_mm": 55.0}),
    ],
    "brakes_option": [
        ("BRK-A1", {"brake_duct_inlet_area_m2": 0.06}),
        ("BRK-A2", {"brake_duct_inlet_area_m2": 0.09}),
        ("BRK-A3", {"brake_duct_inlet_area_m2": 0.12}),
    ],
    "cabin_option": [
        ("CAB-A1", {"cabin_frontal_area_m2": 2.10, "cabin_length_m": 1.40, "cabin_height_mm": 1280.0}),
        ("CAB-A2", {"cabin_frontal_area_m2": 2.45, "cabin_length_m": 2.10, "cabin_height_mm": 1380.0}),
        ("CAB-A3", {"cabin_frontal_area_m2": 2.70, "cabin_length_m": 2.60, "cabin_height_mm": 1420.0}),
        ("NONE",   {"cabin_frontal_area_m2": 0.00, "cabin_length_m": 0.00, "cabin_height_mm":    0.0}),
    ],
    "electrical_option": [
        ("ELE-A1", {"battery_underbody_height_mm":  0.0}),
        ("ELE-A2", {"battery_underbody_height_mm": 28.0}),
        ("ELE-A3", {"battery_underbody_height_mm": 48.0}),
    ],
    "oil_option": [
        ("OIL-A1", {"oil_cooler_frontal_area_m2": 0.00}),
        ("OIL-A2", {"oil_cooler_frontal_area_m2": 0.08}),
        ("OIL-A3", {"oil_cooler_frontal_area_m2": 0.05}),
    ],
    "rops_option": [
        ("ROPS-A1", {"rops_lateral_projected_area_m2": 0.00, "rops_height_above_roof_mm":   0.0}),
        ("ROPS-A2", {"rops_lateral_projected_area_m2": 1.85, "rops_height_above_roof_mm": 220.0}),
        ("ROPS-A3", {"rops_lateral_projected_area_m2": 2.45, "rops_height_above_roof_mm": 380.0}),
        ("NONE",    {"rops_lateral_projected_area_m2": 0.00, "rops_height_above_roof_mm":   0.0}),
    ],
    "steering_option": [
        ("STR-A1", {"steering_column_diameter_mm": 24.0}),
        ("STR-A2", {"steering_column_diameter_mm": 28.0}),
        ("STR-A3", {"steering_column_diameter_mm": 36.0}),
    ],
    "suspension_front_option": [
        ("SFR-A1", {"front_ride_height_mm": 220.0, "front_track_width_mm": 1620.0}),
        ("SFR-A2", {"front_ride_height_mm": 280.0, "front_track_width_mm": 1680.0}),
        ("SFR-A3", {"front_ride_height_mm": 360.0, "front_track_width_mm": 1740.0}),
    ],
    "suspension_rear_option": [
        ("SRR-A1", {"rear_ride_height_mm": 220.0, "rear_track_width_mm": 1620.0}),
        ("SRR-A2", {"rear_ride_height_mm": 290.0, "rear_track_width_mm": 1690.0}),
        ("SRR-A3", {"rear_ride_height_mm": 360.0, "rear_track_width_mm": 1740.0}),
    ],
}

# Slots where NONE is a valid option
NONE_VALID_SLOTS = {"cabin_option", "rops_option"}

# The ordered list of slots (matches CSV column order)
ASSEMBLY_SLOTS = list(CATALOG.keys())

# Derived: full ordered list of physical-attribute names (one model-input vector)
def _all_attribute_names() -> list[str]:
    names = []
    for slot in ASSEMBLY_SLOTS:
        # the first option's attribute keys define the schema for that slot
        attrs = CATALOG[slot][0][1]
        names.extend(sorted(attrs.keys()))
    return names

ATTRIBUTE_NAMES = _all_attribute_names()

# Lookup helper: option_code → attribute dict (per slot)
def resolve_to_attributes(slot: str, code: str) -> dict[str, float]:
    for opt_code, attrs in CATALOG[slot]:
        if opt_code == code:
            return dict(attrs)
    raise ValueError(f"Unknown option code {code!r} for slot {slot!r}")


# ---------------------------------------------------------------------------
# Aero model — driven by physical attributes
# ---------------------------------------------------------------------------
# The aero model below computes (CD, CL, CY, CM) as smooth functions of the
# 27 physical attributes + (speed_kmh, yaw_deg). The intent is for the
# response surface to be (a) reasonable for an off-road utility vehicle
# at highway cruise, (b) smooth enough that the GBM can learn it well
# with ~200 training rows, and (c) physics-flavoured enough that
# attribute-based generalization is meaningful (e.g., predicting a new
# snorkel height between two catalog values gives a sensible CD delta).
#
# The numbers below are illustrative — not derived from a specific
# wind-tunnel or CFD study. The synthesizer is a hand-built physics
# pastiche, not a substitute for real CFD.

BASELINE = {"CD": 0.34, "CL": 0.05, "CY": 0.00, "CM": 0.00}

def _aero_from_attributes(attrs: dict[str, float], speed_kmh: float,
                          yaw_deg: float, rng: random.Random
                          ) -> tuple[float, float, float, float]:
    """Compute (CD, CL, CY, CM) from the attribute dict + operating point."""
    cd = BASELINE["CD"]
    cl = BASELINE["CL"]
    cy = BASELINE["CY"]
    cm = BASELINE["CM"]

    # --- chassis envelope: drives baseline frontal-area and side-area effects ---
    # nominal heights/widths centered around mid-catalog options
    cd += 0.00012 * (attrs["chassis_envelope_height_mm"] - 1850.0)  # ~ +/-0.012 per +/-100 mm
    cd += 0.00015 * (attrs["chassis_envelope_width_mm"]  - 1980.0)
    cl += 0.00004 * (attrs["chassis_envelope_height_mm"] - 1850.0)

    # --- engine: hood clearance is a bulge; grille is mass-flow demand ---
    cd += 0.00040 * attrs["hood_clearance_mm"]                     # +0.018 at +45 mm
    cd += 0.080  * (attrs["grille_area_m2"] - 0.42)                # +0.016 at +0.20 m^2

    # --- transmission/clutch/electrical/oil/steering/fuel: small/weak ---
    cd += 0.00005 * (attrs["tunnel_belly_clearance_mm"] - 110.0)   # very small
    cd += 0.00010 * (attrs["clutch_protrusion_mm"]      - 22.0)
    cd += 0.00010 * attrs["battery_underbody_height_mm"]
    cd += 0.00006 * attrs["steering_column_diameter_mm"]
    cd += 0.00020 * attrs["tank_underbody_drop_mm"]
    cd += 0.060  * attrs["oil_cooler_frontal_area_m2"]

    # --- cooling: front-face mass-flow penalty ---
    cd += 0.090 * (attrs["radiator_frontal_area_m2"] - 0.32)        # +0.015 at +0.16 m^2
    cd += 4.5e-5 * (attrs["radiator_pressure_drop_pa"] - 180.0)     # +0.005 at +110 Pa

    # --- intake: snorkel / vertical drag tower ---
    intake_h = attrs["intake_height_above_hood_mm"]
    intake_d = attrs["intake_diameter_mm"]
    # frontal-area product is roughly h * d (mm^2). Effect on CD is linear-ish in
    # that product, scaled to give +0.040 for a 380x140 snorkel (53200 mm^2).
    intake_frontal_mm2 = intake_h * intake_d
    cd += 0.040 * intake_frontal_mm2 / 53200.0
    cl += 0.004 * intake_h / 380.0

    # --- exhaust: external protrusion drag (surface bulge) ---
    exh_h = attrs["exhaust_protrusion_height_mm"]
    exh_w = attrs["exhaust_protrusion_width_mm"]
    exh_frontal_mm2 = exh_h * exh_w
    cd += 0.012 * exh_frontal_mm2 / 17600.0  # +0.012 at 220x80 high-mount
    cl += 0.0001 * exh_h / 220.0

    # --- brakes: cooling ducts add to underhood pressure-recovery loss ---
    cd += 0.18 * (attrs["brake_duct_inlet_area_m2"] - 0.06)  # +0.011 at +0.06 m^2

    # --- cabin: dominant frontal-area driver (could be zero for open-frame) ---
    cd += 0.015 * (attrs["cabin_frontal_area_m2"] - 2.10)  # negative for NONE
    cd += -0.005 * (attrs["cabin_length_m"] - 1.40)         # longer cabin smooths flow slightly
    cd += 0.00010 * (attrs["cabin_height_mm"] - 1280.0)
    cl += 0.007 * (attrs["cabin_frontal_area_m2"] - 2.10)
    cl += 0.00006 * (attrs["cabin_height_mm"] - 1280.0)

    # When cabin is absent (NONE → all zeros) the deltas push CD/CL DOWN, which is
    # physically right: an open-frame ATV has dramatically lower frontal area.
    # The numeric drop from a CAB-A1 build to a NONE build is ~ -0.032 in CD.

    # --- rops: exposed cage is a trip-wire drag generator + lateral surface ---
    rops_area = attrs["rops_lateral_projected_area_m2"]
    rops_h    = attrs["rops_height_above_roof_mm"]
    cd += 0.030 * rops_area / 1.85           # +0.030 at ROPS-A2
    cd += 0.000060 * rops_h                  # mild additional at hi-rise
    cl += 0.010 * rops_area / 1.85
    cl += 0.000020 * rops_h

    # --- suspension: ride height + track width drive stance + crosswind exposure ---
    sfr_h = attrs["front_ride_height_mm"]
    srr_h = attrs["rear_ride_height_mm"]
    sfr_w = attrs["front_track_width_mm"]
    srr_w = attrs["rear_track_width_mm"]
    cd += 0.00012 * (sfr_h - 220.0)         # +0.017 at long-travel front
    cd += 0.00010 * (srr_h - 220.0)
    cl += 0.00006 * (sfr_h - 220.0)
    cl += 0.00005 * (srr_h - 220.0)
    cd += 0.00005 * ((sfr_w - 1620.0) + (srr_w - 1620.0))

    # --- speed effects (mild) ---
    speed_norm = (speed_kmh - 95.0) / 35.0
    cd += -0.005 * speed_norm   # slight Re reduction
    cl += +0.008 * speed_norm   # mild ground-effect interaction

    # --- yaw effects: dominant non-trivial physics ---
    yaw_rad = math.radians(yaw_deg)
    sin_yaw = math.sin(yaw_rad)
    abs_sin = abs(sin_yaw)

    # Per-attribute lateral-exposure amplitudes for CY and CM. Each attribute that
    # contributes lateral surface area at exposed positions amplifies the
    # yaw-response of CY (side force) and CM (yawing moment).
    cy_amp = 0.05  # baseline lateral surface of the vehicle
    cm_amp = 0.02

    # intake snorkel: tall and exposed
    cy_amp += 0.18 * intake_frontal_mm2 / 53200.0
    cm_amp += 0.05 * intake_frontal_mm2 / 53200.0
    # exhaust side-exit: lateral surface
    cy_amp += 0.08 * exh_w / 120.0
    cm_amp += 0.02 * exh_w / 120.0
    # rops cage: huge lateral surface when exposed
    cy_amp += 0.28 * rops_area / 1.85
    cm_amp += 0.08 * rops_area / 1.85
    # tall suspension: more body exposed to crosswind
    cy_amp += 0.05 * (sfr_h - 220.0) / 140.0
    cm_amp += 0.01 * (sfr_h - 220.0) / 140.0
    # cabin: big lateral surface
    cy_amp += 0.12 * (attrs["cabin_frontal_area_m2"] / 2.10)
    cm_amp += 0.04 * (attrs["cabin_frontal_area_m2"] / 2.10)

    cy += cy_amp * sin_yaw
    cm += cm_amp * sin_yaw

    # CD increases under yaw (effective frontal area grows)
    cd += 0.15 * abs_sin * (1.0 + 0.4 * (cy_amp - 0.05))
    # CL responds modestly to yaw via roof / fender flow
    cl += 0.06 * abs_sin

    # --- noise (CFD-vs-test scatter / numerical noise) ---
    cd += rng.gauss(0, 0.008)
    cl += rng.gauss(0, 0.008)
    cy += rng.gauss(0, 0.006)
    cm += rng.gauss(0, 0.004)

    return cd, cl, cy, cm


# ---------------------------------------------------------------------------
# Plausibility filter (same as before)
# ---------------------------------------------------------------------------

def _is_plausible_build(build: dict[str, str]) -> bool:
    cab = build.get("cabin_option")
    rops = build.get("rops_option")
    # Open-frame cab can't have an internal cage
    if cab == "NONE" and rops == "ROPS-A1":
        return False
    return True


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def _sample_build(rng: random.Random) -> dict[str, str]:
    while True:
        build = {}
        for slot in ASSEMBLY_SLOTS:
            codes = [opt for opt, _ in CATALOG[slot]]
            if slot in NONE_VALID_SLOTS:
                # weight: regular options each 2x, NONE 1x
                weights = [1 if c == "NONE" else 2 for c in codes]
                code = rng.choices(codes, weights=weights, k=1)[0]
            else:
                # regular options only (NONE shouldn't be in the catalog list for these slots anyway)
                regular = [c for c in codes if c != "NONE"]
                code = rng.choice(regular)
            build[slot] = code
        if _is_plausible_build(build):
            return build


def _sample_operating_point(rng: random.Random) -> tuple[float, float]:
    speed = round(rng.uniform(60.0, 130.0), 1)
    if rng.random() < 0.6:
        yaw = round(rng.gauss(0.0, 3.0), 1)
    else:
        yaw = round(rng.uniform(-15.0, 15.0), 1)
    yaw = max(-15.0, min(15.0, yaw))
    return speed, yaw


def _build_attributes(build: dict[str, str]) -> dict[str, float]:
    """Resolve a (slot → code) build into the full physical-attribute dict."""
    attrs = {}
    for slot, code in build.items():
        attrs.update(resolve_to_attributes(slot, code))
    return attrs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# Column order must match data-contract.md exactly
COLUMNS = ASSEMBLY_SLOTS + ["speed_kmh", "yaw_deg",
                            "CD", "CL", "CY", "CM",
                            "notes"]


def synthesize(n_rows: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    rows = []
    for i in range(n_rows):
        build = _sample_build(rng)
        speed, yaw = _sample_operating_point(rng)
        attrs = _build_attributes(build)
        cd, cl, cy, cm = _aero_from_attributes(attrs, speed, yaw, rng)
        row = {slot: build[slot] for slot in ASSEMBLY_SLOTS}
        row["speed_kmh"] = speed
        row["yaw_deg"] = yaw
        row["CD"] = round(cd, 4)
        row["CL"] = round(cl, 4)
        row["CY"] = round(cy, 4)
        row["CM"] = round(cm, 4)
        row["notes"] = ""
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-rows", type=int, default=200,
                        help="Number of synthetic rows to generate (default: 200)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility (default: 42)")
    parser.add_argument("--out", type=Path, default=Path("sample-dataset.csv"),
                        help="Output CSV path (default: sample-dataset.csv)")
    args = parser.parse_args(argv)

    rows = synthesize(args.n_rows, args.seed)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {args.out}")
    print(f"  seed = {args.seed}")
    print(f"  CD range: {min(r['CD'] for r in rows):.3f} – {max(r['CD'] for r in rows):.3f}")
    print(f"  CL range: {min(r['CL'] for r in rows):.3f} – {max(r['CL'] for r in rows):.3f}")
    print(f"  CY range: {min(r['CY'] for r in rows):.3f} – {max(r['CY'] for r in rows):.3f}")
    print(f"  CM range: {min(r['CM'] for r in rows):.3f} – {max(r['CM'] for r in rows):.3f}")
    print(f"  cabin=NONE rows: {sum(1 for r in rows if r['cabin_option'] == 'NONE')}")
    print(f"  rops=NONE rows:  {sum(1 for r in rows if r['rops_option'] == 'NONE')}")
    print(f"  catalog → attribute physical-attribute count: {len(ATTRIBUTE_NAMES)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
