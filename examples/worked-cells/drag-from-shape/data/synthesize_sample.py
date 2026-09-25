"""
Drag-From-Shape-Image Surrogate example -- SAMPLE-DATA SYNTHESIZER
======================================================================
Generates an *illustrative* sample dataset for the first
IMAGE-INPUT worked cell (grid cell n=2, m=1, Bucket B2 by input shape).
It bridges from the drag-lift example (a B1 scalar example) by stepping
the INPUT from a parameter vector to a regular-grid geometry image: the
model is handed a picture of the body cross-section (a signed-distance
field on a fixed grid) instead of a row of numbers, and predicts the
drag coefficient CD (and lift CL) at a fixed operating point.

ASCII-only source by discipline.

------------------------------------------------------------------
What goes in the CSV
------------------------------------------------------------------
The geometry is a 2-D bluff-body cross-section (think the side profile
of a vehicle / fairing) defined by a handful of latent shape parameters.
Each body is rasterised to a signed-distance field (SDF) on a fixed

    (NX, NY) = (24, 16)  ->  384 pixels per body

grid spanning a fixed physical window. SDF convention: negative INSIDE
the body, positive OUTSIDE, zero on the surface, in grid-cell units.
Each dataset row is:

    384 SDF columns  (S_000 ... S_383, row-major: iy outer, ix inner)
  + 2 target columns (CD, CL)
  + 1 optional notes column

The SDF columns ARE the model input (the "image"); the latent shape
parameters are NOT in the CSV -- the whole point of this example is that
the model reads the geometry picture directly. (We keep the latent
params only inside the synthesizer to generate shapes + the deterministic
drag; a real user would export the SDF of their actual CAD geometry.)

------------------------------------------------------------------
The shape family
------------------------------------------------------------------
A body is a superellipse-ish profile, tapered front-to-back, optionally
with a roof bump and a blunt tail. Latent parameters (sampled per body):

    length_frac    fraction of the window length the body spans (fineness)
    height_frac    fraction of the window height (frontal bluffness)
    nose_sharp     superellipse exponent at the nose (round->sharp)
    tail_taper     how much the rear contracts (0 = blunt, 1 = pointed)
    roof_bump      height of a smooth roof bump (adds frontal area + wake)
    ground_gap     gap below the body to the ground plane (ride height)

------------------------------------------------------------------
The deterministic drag/lift (an analytical pastiche, NOT real CFD)
------------------------------------------------------------------
CD is built from SHAPE DESCRIPTORS that the SDF image encodes (so a CNN /
image regressor can recover them) but that a short parameter vector would
NOT cleanly capture -- that is the pedagogical point of the image input:

    frontal_area    the body's max vertical extent (projected frontal height)
    fineness        length / frontal_height (slender bodies have lower CD)
    base_blunt      how blunt the tail is (blunt base -> big wake -> high CD)
    roof_curv       roof-bump prominence (a bump trips the wake -> +CD, +CL)
    ground_effect   ride-height term (small gap -> +CL magnitude, mild +CD)

    CD = CD0 + k_front*frontal_area + k_base*base_blunt + k_roof*roof_curv
             - k_fine*(fineness - fineness_ref) + k_gap_d/(ground_gap+g0)
    CL = k_camber*roof_curv - k_gap_l/(ground_gap+g0) + k_taillift*base_blunt

All coefficients are CHOSEN to land CD/CL in plausible bluff-body ranges
(CD ~ 0.2 .. 1.1, CL ~ -0.4 .. +0.6); they are NOT from real CFD. CD/CL
are DETERMINISTIC functions of the shape descriptors (hence of the SDF),
with only a small post-response multiplicative scatter random. See
data-contract.md and WALKTHROUGH.md section 4 for the illustrative-
numerics framing.

Run:
    python synthesize_sample.py
    python synthesize_sample.py --rows 400 --seed 7 --out my-data.csv
"""

import argparse
import csv
import math
import os
import random


# --- fixed grid: same for every body (the regular-grid B2 convention) ---
NX = 24   # pixels along the length (flow direction, +x downstream)
NY = 16   # pixels in the vertical
N_PIX = NX * NY   # 384

# physical window the grid spans (arbitrary consistent units)
WIN_X = 6.0   # length of the window
WIN_Y = 4.0   # height of the window
GROUND_Y = 0.5  # y-coordinate of the ground plane within the window

# --- drag/lift coefficients (tuned for plausible bluff-body ranges) ---
CD0 = 0.12
K_FRONT = 0.70
K_BASE = 0.45
K_ROOF = 0.35
K_FINE = 0.055
FINENESS_REF = 2.5
K_GAP_D = 0.045
G0 = 0.35
K_CAMBER = 0.55
K_GAP_L = 0.22
K_TAILLIFT = 0.18
_NOISE_FRAC = 0.02


def flat_index(iy, ix):
    """Row-major: iy outer (vertical), ix inner (length)."""
    return iy * NX + ix


def _sample_shape(rng):
    """Sample one body's latent shape parameters."""
    length_frac = rng.uniform(0.55, 0.95)
    height_frac = rng.uniform(0.20, 0.62)
    nose_sharp = rng.uniform(1.6, 4.5)     # superellipse exponent (2=ellipse)
    tail_taper = rng.uniform(0.0, 1.0)     # 0 = blunt base, 1 = pointed tail
    roof_bump = rng.uniform(0.0, 0.45)     # roof-bump height fraction
    ground_gap = rng.uniform(0.10, 1.10)   # ride height (window units)
    return {
        "length_frac": length_frac, "height_frac": height_frac,
        "nose_sharp": nose_sharp, "tail_taper": tail_taper,
        "roof_bump": roof_bump, "ground_gap": ground_gap,
    }


def _body_halfheight(xc, p, x0, x1, h):
    """Upper surface half-height of the body at physical x (0 if outside).

    The body spans [x0, x1] in x. Cross-section uses a superellipse-style
    upper profile, tapered toward the tail, with an optional roof bump.
    Lower surface is the ground-gap line (flat underbody).
    """
    if xc < x0 or xc > x1:
        return None
    L = x1 - x0
    t = (xc - x0) / L          # 0 at nose, 1 at tail
    # superellipse longitudinal envelope: full height in the middle, tapering
    # at the nose (sharpness via exponent) and the tail (via tail_taper).
    nose_env = (1.0 - (1.0 - t) ** p["nose_sharp"]) if t < 1.0 else 1.0
    nose_env = max(0.0, min(1.0, nose_env))
    # tail contraction: blunt (tail_taper~0) keeps height to the base;
    # pointed (tail_taper~1) contracts the rear.
    tail_env = 1.0 - p["tail_taper"] * (t ** 2.2)
    env = nose_env * tail_env
    half = 0.5 * h * env
    # roof bump: a smooth Gaussian-ish lump near t=0.45
    bump = p["roof_bump"] * h * math.exp(-((t - 0.45) ** 2) / (2 * 0.12 ** 2))
    return half + bump


def _rasterize_sdf(p):
    """Rasterise the body to an SDF on the fixed (NY, NX) grid.

    Returns (sdf_flat, descriptors). SDF is signed distance in grid-cell
    units (negative inside). Descriptors are the shape features the drag
    model uses (all recoverable from the silhouette the SDF encodes).
    """
    dx = WIN_X / NX
    dy = WIN_Y / NY
    L = p["length_frac"] * WIN_X
    x0 = (WIN_X - L) * 0.5
    x1 = x0 + L
    h = p["height_frac"] * WIN_Y
    base_y = GROUND_Y + p["ground_gap"]   # underbody line

    # build an inside-mask + track frontal height and tail height
    inside = [[False] * NX for _ in range(NY)]
    max_top = 0.0
    frontal_height = 0.0
    # sample the body's upper surface on a fine x-grid for descriptors
    tail_top = None
    for ix in range(NX):
        xc = (ix + 0.5) * dx
        half = _body_halfheight(xc, p, x0, x1, h)
        if half is None:
            continue
        top = base_y + 2.0 * half        # body sits on the underbody line
        # frontal (projected) height = the body's vertical extent at its tallest
        ext = top - base_y
        if ext > frontal_height:
            frontal_height = ext
        if top > max_top:
            max_top = top
        for iy in range(NY):
            yc = (iy + 0.5) * dy
            if base_y <= yc <= top:
                inside[iy][ix] = True
        # remember the tail (last spanned column) height
        if x0 <= xc <= x1:
            tail_top = top - base_y

    # signed distance via a brute-force nearest-boundary estimate.
    # cheap + deterministic: distance to nearest cell of opposite class.
    sdf = [0.0] * N_PIX
    inside_cells = [(iy, ix) for iy in range(NY) for ix in range(NX) if inside[iy][ix]]
    out_cells = [(iy, ix) for iy in range(NY) for ix in range(NX) if not inside[iy][ix]]
    # guard: empty body (shouldn't happen with the sampling ranges)
    if not inside_cells:
        for iy in range(NY):
            for ix in range(NX):
                sdf[flat_index(iy, ix)] = float(NX)
        descr = {"frontal_area": 0.0, "fineness": 5.0, "base_blunt": 0.0,
                 "roof_curv": 0.0, "ground_gap": p["ground_gap"]}
        return sdf, descr

    for iy in range(NY):
        for ix in range(NX):
            here_inside = inside[iy][ix]
            opp = out_cells if here_inside else inside_cells
            best = 1e9
            for (jy, jx) in opp:
                d = math.hypot(iy - jy, ix - jx)
                if d < best:
                    best = d
            sdf[flat_index(iy, ix)] = -best if here_inside else best

    # --- shape descriptors (all derivable from the silhouette) ---
    frontal_area = frontal_height / WIN_Y                  # normalised frontal height
    body_len_norm = (x1 - x0) / WIN_X
    fineness = body_len_norm / max(frontal_area, 1e-3)     # length / frontal height
    base_blunt = (tail_top / max(frontal_height, 1e-6)) if tail_top else 0.0
    base_blunt = max(0.0, min(1.0, base_blunt))            # 1 = base as tall as frontal (blunt)
    roof_curv = p["roof_bump"]                             # bump prominence
    descr = {
        "frontal_area": frontal_area, "fineness": fineness,
        "base_blunt": base_blunt, "roof_curv": roof_curv,
        "ground_gap": p["ground_gap"],
    }
    return sdf, descr


def _drag_lift(descr):
    """Deterministic CD, CL from the shape descriptors."""
    fa = descr["frontal_area"]
    fine = descr["fineness"]
    base = descr["base_blunt"]
    roof = descr["roof_curv"]
    gap = descr["ground_gap"]
    CD = (CD0 + K_FRONT * fa + K_BASE * base + K_ROOF * roof
          - K_FINE * (fine - FINENESS_REF) + K_GAP_D / (gap + G0))
    CL = (K_CAMBER * roof - K_GAP_L / (gap + G0) + K_TAILLIFT * base)
    # keep in plausible bands
    CD = max(0.12, min(CD, 1.30))
    CL = max(-0.60, min(CL, 0.80))
    return CD, CL


def synthesize(rows, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(rows):
        p = _sample_shape(rng)
        sdf, descr = _rasterize_sdf(p)
        CD, CL = _drag_lift(descr)
        # small multiplicative scatter (the only random part of the output)
        CD *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        CL += rng.gauss(0.0, _NOISE_FRAC * 0.5)
        out.append((sdf, CD, CL))
    return out


def sdf_columns():
    return ["S_%03d" % f for f in range(N_PIX)]


def write_csv(rows, path):
    header = sdf_columns() + ["CD", "CL"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for sdf, CD, CL in rows:
            line = ["%.3f" % v for v in sdf]
            line.append("%.4f" % CD)
            line.append("%.4f" % CL)
            w.writerow(line)


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
    CD = [r[1] for r in rows]
    CL = [r[2] for r in rows]
    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  grid           : (%d, %d) = %d SDF pixels per body" % (NY, NX, N_PIX))
    print("  CD : min %.3f  max %.3f  mean %.3f" % (min(CD), max(CD), sum(CD) / len(CD)))
    print("  CL : min %.3f  max %.3f  mean %.3f" % (min(CL), max(CL), sum(CL) / len(CL)))


if __name__ == "__main__":
    main()