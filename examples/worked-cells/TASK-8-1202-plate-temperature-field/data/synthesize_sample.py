"""
TASK-8-1202 Plate Temperature-Field Surrogate -- SAMPLE-DATA SYNTHESIZER
=======================================================================
Generates an *illustrative* sample dataset that the reader can use to
run the trainer end-to-end before supplying real steady-state thermal-FE
field results.

This is the arc's SECOND field-output example (slide-9 cell n=1, m=2,
bucket B2) and the second instance of that cell in the SAME thermal
domain (A.3.1) as TASK-8-1201 -- but on a DIFFERENT component geometry
and boundary-condition family. Where TASK-8-1201 modelled an extruded
cooling fin (base-temperature + adiabatic-tip BCs, a 1-D fin profile
extruded across the section), this example models a FLAT COOLED PLATE
(a heat-spreader / cold-plate) carrying a DISCRETE EMBEDDED HEAT SOURCE,
cooled by convection over its faces. The geometry, the boundary
conditions, and the dominant physics (in-plane heat spreading away from
a localised source, rather than 1-D conduction along a fin) are all
different; only the domain (A.3.1 steady thermal) and the B2 field-output
data-contract SHAPE are shared. That is the pedagogical point of this
example: the field-output template generalises across geometry / BC
FAMILIES within a domain, not only across physics domains.

Source-of-truth note (ASCII-only by discipline). This file deliberately
uses ASCII-only source (words like "sigma", "->", "deg" rather than the
Unicode glyphs) per the project's synthesizer-source rule: a non-ASCII
run that crosses an internal write boundary can deterministically
truncate the written file. See LESSONS L15 and the project memory.

------------------------------------------------------------------
The field model (an analytical pastiche, NOT a real thermal-FE solve)
------------------------------------------------------------------
The plate is modelled as a thin rectangular conductor of size
length x width x thickness. A localised heat source of total power q_W
is deposited over a square footprint of side src_size_mm centred on the
plate's top face. The plate rejects heat by convection (coefficient h)
over its faces to an ambient at T_amb. We want the steady temperature
rise everywhere.

The closed-form pastiche superposes two physically-motivated, smooth,
deterministic terms:

  1. A SPREADING term -- the in-plane temperature rise around the source.
     A real plate's steady rise around a localised source decays roughly
     like a smoothed spreading profile modulated by the plate's ability
     to carry heat away. We use a Gaussian-blurred disc centred at the
     source:

         spread(x,y) = dT_src * exp( -d2 / (2 * w_spread^2) )

     where d2 is the squared in-plane distance from the source centre
     (in metres), w_spread is a spreading length that GROWS with
     conductivity k and the source footprint and SHRINKS with stronger
     convection (a well-cooled or low-k plate keeps heat local), and
     dT_src is the peak rise at the source, set by the source power and
     the plate's convective rejection over an effective area.

  2. A THROUGH-THICKNESS term -- a small parabolic gradient from the
     heated top face toward the cooled bottom face. The thickness is the
     short dimension, so this gradient is modest; it is scaled by the
     local in-plane rise so the through-thickness drop is largest
     directly under the source.

The whole field is

    T(x,y,z) = T_amb + spread(x,y) * (1 - through_drop(z))

which is a DETERMINISTIC function of the eight inputs and the (i,j,k)
voxel coordinates -- the determinism discipline holds across the entire
grid, which is what a field surrogate needs to be learnable.

The numerical coefficients are CHOSEN to make the synthetic field land
in the data-contract typical ranges; they are NOT derived from any
specific FE benchmark and do NOT reproduce the absolute magnitudes of any
specific real cold-plate. See data-contract.md and WALKTHROUGH.md section
4 for the illustrative-numerics framing.

------------------------------------------------------------------
The grid and the CSV layout
------------------------------------------------------------------
The field is sampled on a fixed regular grid of shape

    (NX, NY, NZ) = (16, 16, 4)   -> 1024 voxels per run

indexed i = 0..NX-1 along the length, j = 0..NY-1 across the width,
k = 0..NZ-1 through the thickness (k = 0 is the cooled bottom face,
k = NZ-1 is the heated top face). The voxel grid is NORMALISED: it
always has the same shape regardless of the plate's physical dimensions,
so every row of the dataset has the same 1024 output columns. (This is
the standard regular-grid B2 convention; note the grid shape here is
DIFFERENT from TASK-8-1201's (12,8,8) -- a deliberate demonstration that
the contract is not hard-wired to one grid, only to a FIXED grid.)

Each dataset row is:

    8 input columns
  + 1024 field columns (T_0000 ... T_1023, voxel-major in i, then j, then k)
  + 1 optional notes column

The field columns are named T_<iiii> with a zero-padded flat index
flat = (i * NY + j) * NZ + k. The trainer and the data-contract both
document this flattening so a reader can re-fold the 1024 numbers back
into a (16, 16, 4) grid for plotting.

Run:
    python synthesize_sample.py
    python synthesize_sample.py --rows 400 --seed 7 --out my-data.csv
"""

import argparse
import csv
import math
import os
import random


# --- fixed grid shape: same for every run (the regular-grid B2 convention) ---
NX = 16   # voxels along the length
NY = 16   # voxels across the width
NZ = 4    # voxels through the thickness (k=0 cooled face, k=NZ-1 heated face)
N_VOXELS = NX * NY * NZ   # 1024

# --- coefficients tuned so the synthetic field covers the contract ranges ---
THROUGH_DROP_FRAC = 0.12   # max fractional through-thickness drop under source
_NOISE_FRAC = 0.015        # small multiplicative scatter mimicking mesh noise
_W_SPREAD_FLOOR = 0.004    # m, minimum spreading length (numerical guard)

# --- fixed (deterministic) source position: the source sits at plate centre. ---
# Keeping the source centred makes the field a deterministic function of the
# eight sampled inputs alone (no hidden random position), which is the
# determinism discipline the surrogate needs. The position is documented in
# the data-contract as a fixed modelling assumption of this sample generator.
SRC_X_FRAC = 0.5
SRC_Y_FRAC = 0.5


def flat_index(i, j, k):
    """Voxel-major flat index: i outer (length), then j (width), then k (thickness)."""
    return (i * NY + j) * NZ + k


def _sample_design(rng):
    """Sample one (geometry + material + boundary + operating-point) input vector.

    Eight inputs. The first six mirror the thermal vocabulary the arc has
    used since TASK-8-1104 (geometry + material + convection + ambient);
    the seventh is the heat-source footprint size -- the NEW geometry knob
    this plate geometry introduces (the fin example had no localised
    source); the eighth is the source power q_W.

    q_W is kept PROPORTIONAL to the plate's convective capacity (no hard
    absolute wattage cap): a hard cap pins small plates at a power far
    above their capacity and makes the peak temperature run away, so the
    source power tracks capacity and the resulting peak rise stays bounded
    by construction across the whole parameter cube.
    """
    length_mm = rng.uniform(40.0, 200.0)        # mm  (plate length)
    width_mm = rng.uniform(40.0, 200.0)         # mm  (plate width)
    thickness_mm = rng.uniform(2.0, 20.0)       # mm  (plate thickness)
    conductivity = rng.uniform(10.0, 400.0)     # W/(m K)  -- polymer through copper
    h = rng.uniform(5.0, 250.0)                 # W/(m^2 K) -- natural through forced
    T_amb = rng.uniform(-20.0, 80.0)            # deg C
    src_size_mm = rng.uniform(5.0, 40.0)        # mm  (square source footprint side)

    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    area_top = length_m * width_m                  # m^2 (the rejection surface)
    q_capacity = h * area_top * 130.0              # W at delta-T ~ 130 K
    q_target_frac = rng.uniform(0.15, 1.05)
    q_W = max(q_target_frac * q_capacity, 1.0)
    return [length_mm, width_mm, thickness_mm, conductivity, h, T_amb, src_size_mm, q_W]


def _profile_constants(x):
    """Return the deterministic plate-field constants for input vector x.

    Computed once per run, then reused at every voxel.
    """
    length_mm, width_mm, thickness_mm, conductivity, h, T_amb, src_size_mm, q_W = x
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    src_size_m = src_size_mm / 1000.0
    area_top = length_m * width_m                  # m^2 (the rejection surface)

    # spreading length: grows with the conductance ratio (k vs convection)
    # and the source footprint, so high-k / low-h plates spread heat farther.
    # We use a fourth-root of the conductance group to keep the dynamic range
    # of the field SHAPE moderate across the parameter cube (a raw sqrt swung
    # the Gaussian width by an order of magnitude, which makes the field shape
    # hard to learn); the result is still monotonic in k and h. Bounded below
    # by the source half-size and above by the plate half-extent.
    cond_group = conductivity / (h + 20.0)
    w_spread = (cond_group ** 0.25) * 0.018 + 0.6 * src_size_m
    w_spread = min(w_spread, 0.5 * min(length_m, width_m))
    w_spread = max(w_spread, 0.5 * src_size_m, _W_SPREAD_FLOOR)

    # peak rise at the source centre. Heat is rejected over an effective
    # convective area that SMOOTHLY blends the local spreading footprint with a
    # share of the broader plate face (a soft sum, not a hard max, so the peak
    # depends continuously on BOTH the local spreading -- hence on k and the
    # source size -- and the plate area). The plate-area share keeps the peak
    # physical and clamp-free when the spreading patch is tiny.
    area_local = (math.pi * (2.0 * w_spread) ** 2) + (src_size_m * src_size_m)
    eff_area = area_local + 0.85 * area_top
    dT_src = q_W / (h * eff_area + 1e-9)

    # source centre in physical coordinates (m), at cell-centre resolution.
    src_x_m = SRC_X_FRAC * length_m
    src_y_m = SRC_Y_FRAC * width_m

    return {
        "length_m": length_m, "width_m": width_m,
        "w_spread": w_spread, "dT_src": dT_src,
        "src_x_m": src_x_m, "src_y_m": src_y_m,
        "T_amb": T_amb,
    }


def _field(x):
    """Map an input vector to the full (NX, NY, NZ) temperature field, flattened.

    T(i,j,k) = T_amb
             + spread(x_i, y_j)              (Gaussian-blurred disc around source)
             * (1 - through_drop(k))         (cooler toward the bottom cooled face)

    The value at every voxel is a DETERMINISTIC function of the eight inputs
    and the voxel coordinates.
    """
    c = _profile_constants(x)
    length_m = c["length_m"]
    width_m = c["width_m"]
    w_spread = c["w_spread"]
    dT_src = c["dT_src"]
    src_x_m = c["src_x_m"]
    src_y_m = c["src_y_m"]
    T_amb = c["T_amb"]

    two_w2 = 2.0 * w_spread * w_spread

    field = [0.0] * N_VOXELS
    for i in range(NX):
        x_m = ((i + 0.5) / NX) * length_m
        dx = x_m - src_x_m
        for j in range(NY):
            y_m = ((j + 0.5) / NY) * width_m
            dy = y_m - src_y_m
            d2 = dx * dx + dy * dy
            spread = dT_src * math.exp(-d2 / two_w2)
            for k in range(NZ):
                # k = NZ-1 is the heated top face (no drop), k = 0 is the cooled
                # bottom face (max drop). Drop is parabolic in the normalised
                # depth below the top face.
                depth_frac = (NZ - 1 - k) / float(NZ - 1) if NZ > 1 else 0.0
                through_drop = THROUGH_DROP_FRAC * (depth_frac * depth_frac)
                field[flat_index(i, j, k)] = T_amb + spread * (1.0 - through_drop)
    return field


def synthesize(rows, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(rows):
        x = _sample_design(rng)
        field = _field(x)
        T_amb = x[5]
        # small multiplicative scatter on the EXCESS temperature, per voxel,
        # mimicking mesh / post-processing noise. The scatter is random (it is
        # the only random part of the output); the underlying field is fully
        # deterministic in the inputs + coordinates.
        noisy = []
        for v in field:
            excess = v - T_amb
            excess *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
            t = T_amb + excess
            # defensive clamp to the data-contract field range
            t = max(min(t, 400.0), -40.0)
            noisy.append(t)
        out.append(x + noisy)
    return out


def field_columns():
    return ["T_%04d" % f for f in range(N_VOXELS)]


def write_csv(rows, path):
    header = [
        "length_mm", "width_mm", "thickness_mm",
        "conductivity_W_mK", "h_W_m2K", "T_ambient_C",
        "src_size_mm", "q_W",
    ] + field_columns()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            out = []
            for v in r[:8]:
                out.append("%.4f" % v)
            for v in r[8:]:
                out.append("%.3f" % v)
            w.writerow(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    out_path = args.out
    if out_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        out_path = os.path.join(here, "sample-dataset.csv")
    rows = synthesize(args.rows, args.seed)
    write_csv(rows, out_path)
    # quick summary so the reader (or a session) can sanity-check ranges
    field_max = []
    field_min = []
    field_mean = []
    for r in rows:
        f = r[8:]
        field_max.append(max(f))
        field_min.append(min(f))
        field_mean.append(sum(f) / len(f))
    overall_peak = max(field_max)
    overall_floor = min(field_min)
    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  grid shape         : (%d, %d, %d) = %d voxels per run"
          % (NX, NY, NZ, N_VOXELS))
    print("  per-run peak temp  : min %.1f  max %.1f  (deg C)"
          % (min(field_max), max(field_max)))
    print("  per-run mean temp  : min %.1f  max %.1f  (deg C)"
          % (min(field_mean), max(field_mean)))
    print("  overall field range: %.1f .. %.1f  (deg C)"
          % (overall_floor, overall_peak))


if __name__ == "__main__":
    main()
