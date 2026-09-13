"""
TASK-9 H-T WORKED INSTANCE -- SAMPLE-DATA SYNTHESIZER
=====================================================
Generates the 720-row full-factorial thermal DOE that the head-to-head
(`run_ht_instance.py`) fits three surrogate families to. This is the
instance the TASK-9 taxonomy walks rule-by-rule in section 8, made
runnable: "a 720-row full-factorial thermal DOE; 5 scalar targets;
physics-engineered features (dT terms and a T^4 radiation term); the
product is a bisection inverse ('what clearance keeps this under
120 C')".

THE PHYSICAL SETUP
------------------
A heat-dissipating module sits inside an enclosure, separated from a
liquid-cooled wall by an air CLEARANCE gap. Heat leaves the module by
three paths, in parallel:

    conduction across the clearance gap    U_gap  = k_air * A_gap / g
    radiation across the clearance gap     sigma * eps_eff * A_gap * (Ts^4 - Tw^4)
    conduction through the mounting feet   C_mount * (Ts - T_coolant)

and the wall itself rejects what the gap delivers to the coolant
through a finite wall conductance C_WALL.

Two steady-state energy balances close the system:

    node 1 (module surface, Ts):
        q_W = U_gap*(Ts - Tw) + sigma*eps_eff*A*(Ts^4 - Tw^4) + C_mount*(Ts - Tc)

    node 2 (enclosure wall, Tw):
        U_gap*(Ts - Tw) + sigma*eps_eff*A*(Ts^4 - Tw^4) = C_WALL*(Tw - Tc)

Node 2 gives Tw explicitly in terms of Ts, so the pair collapses to ONE
scalar equation in Ts that is strictly monotone -- solved here by
bisection to a tight tolerance. See `_solve_surface_temperature`.

WHY THE GAP IS PURE CONDUCTION (a modelling statement, not an oversight)
------------------------------------------------------------------------
For a horizontal air layer the onset of Rayleigh-Benard convection is at
Ra_g ~ 1708. Across this DOE's clearance range (0.50-2.00 mm) and its
gap temperature differences, Ra_g stays well below that threshold -- the
layer is conduction-dominated and Nu = 1 exactly. `main()` prints the
worst-case Ra_g over the whole design so the claim is checked, not
asserted. If you widen the clearance levels past ~4 mm you leave that
regime and this synthesizer's gap model stops being defensible.

DETERMINISM (project memory: the synthesizer must be deterministic)
--------------------------------------------------------------------
This generator contains NO randomness of any kind. The design is a full
factorial over declared level lists, and every response is a closed-form
function of the design row resolved by a deterministic bisection. There
is deliberately no --seed flag: an inert flag would teach the reader that
some of this script's controls do not matter. Re-running regenerates
`sample-dataset.csv` byte-for-byte.

The numerical constants are CHOSEN so the responses land in the
data-contract.md ranges and so the 120 C inverse target sits inside the
achievable band. They are not calibrated against any specific hardware
or FE benchmark. See data-contract.md and WALKTHROUGH.md.

Run:
    python synthesize_sample.py
    python synthesize_sample.py --out my-doe.csv
"""

import argparse
import csv
import itertools
import os

# ---------------------------------------------------------------------------
# Fixed hardware constants (not varied by the DOE)
# ---------------------------------------------------------------------------
A_GAP = 0.12          # m^2      module face area presented to the cooled wall
K_AIR = 0.030         # W/(m K)  air conductivity at ~350 K
SIGMA = 5.670374419e-8  # W/(m^2 K^4)  Stefan-Boltzmann
EPS_WALL = 0.90       # -        emissivity of the cooled wall
C_WALL = 8.0          # W/K      wall-to-coolant conductance
NU_AIR = 2.0e-5       # m^2/s    air kinematic viscosity at ~350 K
ALPHA_AIR = 2.9e-5    # m^2/s    air thermal diffusivity at ~350 K
G_ACCEL = 9.81        # m/s^2
KELVIN = 273.15

# ---------------------------------------------------------------------------
# The design: a full factorial, 6 x 5 x 4 x 3 x 2 = 720 rows
# ---------------------------------------------------------------------------
LEVELS_CLEARANCE_MM = [0.50, 0.80, 1.10, 1.40, 1.70, 2.00]
LEVELS_Q_W = [120.0, 150.0, 180.0, 210.0, 240.0]
LEVELS_T_COOLANT_C = [30.0, 45.0, 60.0, 75.0]
LEVELS_EMISSIVITY = [0.20, 0.50, 0.80]
LEVELS_C_MOUNT = [0.50, 1.10]

INPUT_COLUMNS = [
    "clearance_mm",
    "q_W",
    "T_coolant_C",
    "emissivity",
    "mount_conductance_W_K",
]
TARGET_COLUMNS = [
    "T_peak_C",
    "T_wall_C",
    "q_gap_W",
    "q_rad_W",
    "q_mount_W",
]


def effective_emissivity(eps_surface):
    """Two-parallel-grey-surface effective emissivity."""
    return 1.0 / (1.0 / eps_surface + 1.0 / EPS_WALL - 1.0)


def _wall_temperature(T_s_K, q_W, T_c_K, c_mount):
    """Node-2 balance solved for the wall temperature, given the surface one.

    Everything the module does not send through its feet must cross the
    gap, and the wall passes exactly that to the coolant through C_WALL.
    """
    q_mount = c_mount * (T_s_K - T_c_K)
    return T_c_K + (q_W - q_mount) / C_WALL


def _node1_residual(T_s_K, row_K):
    """Node-1 energy balance residual: (heat out) - (heat in). Increasing in T_s."""
    g_m, q_W, T_c_K, eps_surface, c_mount = row_K
    T_w_K = _wall_temperature(T_s_K, q_W, T_c_K, c_mount)
    u_gap = K_AIR * A_GAP / g_m
    eps_eff = effective_emissivity(eps_surface)
    q_cond = u_gap * (T_s_K - T_w_K)
    q_rad = SIGMA * eps_eff * A_GAP * (T_s_K ** 4 - T_w_K ** 4)
    q_mount = c_mount * (T_s_K - T_c_K)
    return q_cond + q_rad + q_mount - q_W


def _solve_surface_temperature(row_K, tol=1e-10, max_iter=200):
    """Bisect the node-1 residual for the module surface temperature.

    The residual is strictly increasing in T_s (raising T_s raises every
    outbound path AND lowers the wall temperature, widening the gap
    difference), so a bracketed bisection converges to the unique root.
    Bisection rather than Newton: no derivative, no step control, and the
    iterate count is a fixed function of the bracket, which keeps the
    whole generator reproducible to the last bit.
    """
    T_c_K = row_K[2]
    lo = T_c_K
    hi = T_c_K + 1.0
    guard = 0
    while _node1_residual(hi, row_K) < 0.0:
        hi = T_c_K + (hi - T_c_K) * 2.0
        guard += 1
        if guard > 60:
            raise RuntimeError("failed to bracket the surface temperature")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if _node1_residual(mid, row_K) < 0.0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


def evaluate_row(clearance_mm, q_W, T_coolant_C, emissivity, c_mount):
    """Map one design row to the five scalar targets. Deterministic."""
    g_m = clearance_mm / 1000.0
    T_c_K = T_coolant_C + KELVIN
    row_K = (g_m, q_W, T_c_K, emissivity, c_mount)

    T_s_K = _solve_surface_temperature(row_K)
    T_w_K = _wall_temperature(T_s_K, q_W, T_c_K, c_mount)

    u_gap = K_AIR * A_GAP / g_m
    eps_eff = effective_emissivity(emissivity)
    q_gap = u_gap * (T_s_K - T_w_K)
    q_rad = SIGMA * eps_eff * A_GAP * (T_s_K ** 4 - T_w_K ** 4)
    q_mount = c_mount * (T_s_K - T_c_K)

    return (T_s_K - KELVIN, T_w_K - KELVIN, q_gap, q_rad, q_mount)


def rayleigh_gap(clearance_mm, dT_gap_K, T_mean_K):
    """Rayleigh number of the air layer, for the Nu = 1 regime check."""
    g_m = clearance_mm / 1000.0
    beta = 1.0 / T_mean_K
    return G_ACCEL * beta * dT_gap_K * g_m ** 3 / (NU_AIR * ALPHA_AIR)


def build_design():
    """The full factorial, first column varying slowest."""
    return list(itertools.product(
        LEVELS_CLEARANCE_MM,
        LEVELS_Q_W,
        LEVELS_T_COOLANT_C,
        LEVELS_EMISSIVITY,
        LEVELS_C_MOUNT,
    ))


def synthesize():
    rows = []
    for design in build_design():
        targets = evaluate_row(*design)
        rows.append(list(design) + list(targets))
    return rows


def write_csv(rows, path):
    """Write the DOE, pinning LF line endings on every platform.

    csv.writer defaults to the excel dialect, whose line terminator is
    CRLF. The repo's .gitattributes declares `* text=auto eol=lf`, so a
    CRLF file on disk is normalized by git on read and looks clean --
    but after a fresh checkout the CSV arrives LF and the first
    regeneration silently flips it to CRLF. That would make this
    example's "regenerates byte-identically" acceptance criterion pass
    on the machine that wrote the file and fail on every other one.
    Pinning the terminator makes the criterion mean what it says.
    """
    header = INPUT_COLUMNS + TARGET_COLUMNS
    with open(path, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            out = [
                "%.2f" % r[0],
                "%.1f" % r[1],
                "%.1f" % r[2],
                "%.2f" % r[3],
                "%.2f" % r[4],
                "%.4f" % r[5],
                "%.4f" % r[6],
                "%.4f" % r[7],
                "%.4f" % r[8],
                "%.4f" % r[9],
            ]
            w.writerow(out)


def main():
    ap = argparse.ArgumentParser(
        description="Generate the 720-row full-factorial thermal DOE "
                    "(deterministic; no seed, because nothing here is random)."
    )
    ap.add_argument("--out", type=str, default=None,
                    help="output CSV path (default: sample-dataset.csv beside this file)")
    args = ap.parse_args()

    out_path = args.out
    if out_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        out_path = os.path.join(here, "sample-dataset.csv")

    rows = synthesize()
    write_csv(rows, out_path)

    T_peak = [r[5] for r in rows]
    T_wall = [r[6] for r in rows]
    q_gap = [r[7] for r in rows]
    q_rad = [r[8] for r in rows]
    q_mount = [r[9] for r in rows]

    # energy-balance closure: the three heat paths must sum to q_W
    worst_closure = max(abs(r[7] + r[8] + r[9] - r[1]) for r in rows)

    # regime check: worst-case gap Rayleigh number against the Ra ~ 1708 onset
    worst_ra = 0.0
    for r in rows:
        dT_gap = r[5] - r[6]
        T_mean = 0.5 * (r[5] + r[6]) + KELVIN
        worst_ra = max(worst_ra, rayleigh_gap(r[0], dT_gap, T_mean))

    # how many DOE rows sit each side of the 120 C inverse target
    under = sum(1 for v in T_peak if v < 120.0)

    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  design      : %d x %d x %d x %d x %d full factorial over %s"
          % (len(LEVELS_CLEARANCE_MM), len(LEVELS_Q_W), len(LEVELS_T_COOLANT_C),
             len(LEVELS_EMISSIVITY), len(LEVELS_C_MOUNT), ", ".join(INPUT_COLUMNS)))
    print("  T_peak_C    : min %7.2f  max %7.2f  mean %7.2f"
          % (min(T_peak), max(T_peak), sum(T_peak) / len(T_peak)))
    print("  T_wall_C    : min %7.2f  max %7.2f  mean %7.2f"
          % (min(T_wall), max(T_wall), sum(T_wall) / len(T_wall)))
    print("  q_gap_W     : min %7.2f  max %7.2f" % (min(q_gap), max(q_gap)))
    print("  q_rad_W     : min %7.2f  max %7.2f" % (min(q_rad), max(q_rad)))
    print("  q_mount_W   : min %7.2f  max %7.2f" % (min(q_mount), max(q_mount)))
    print("  rows below the 120 C inverse target : %d / %d (%.0f %%)"
          % (under, len(rows), 100.0 * under / len(rows)))
    print("  energy-balance closure (max |q_gap+q_rad+q_mount - q_W|) : %.3e W"
          % worst_closure)
    print("  worst-case gap Rayleigh number : %.1f  (conduction regime needs < 1708)"
          % worst_ra)


if __name__ == "__main__":
    main()
