"""
Motor Torque & Efficiency Surrogate example — SAMPLE-DATA SYNTHESIZER
========================================================================
Generates an *illustrative* sample dataset that the reader can use to
run the trainer end-to-end before supplying real low-frequency-EM FE
results (ANSYS Maxwell / JMAG / Altair Flux torque-and-efficiency-map
exports).

The functional form here is an analytical *pastiche* of an interior-
permanent-magnet (IPM) synchronous machine operating point — it is NOT
a substitute for a real magnetostatic / eddy-current FE solve. The
purpose is to give the surrogate something smoothly variable and
qualitatively plausible to learn from, so the reader can verify the
workflow shape:

    rotor flux linkage   λ   ∝ turns · D² · L · [m/(m+g)] · B_r(T)
    magnetic saturation  s   = tanh(I / I_sat),  I_sat ∝ iron area (D·L)
    electromagnetic torque   T_em = k_T · λ · I · s · (turns/12)
    mechanical output    P_out = T_em · ω,   ω = rpm·2π/60
    copper loss          P_cu  = 3 · (I/√2)² · R_phase,  R_phase ∝ turns²/(D·L)
    iron loss            P_fe  ∝ rpm^1.5 · λ² · (D·L)          (Steinmetz-ish)
    mechanical loss      P_mech ∝ rpm² · D^1.5                  (windage+friction)
    efficiency           η = 100 · P_out / (P_out + P_loss)

The two load-bearing physical mechanisms that dominate low-frequency-EM
surrogate failures are baked into the response surface so the example
is honest about them:

  * Magnetic saturation (the DOMINANT low-frequency-EM
    surrogate-failure mode): the tanh(I/I_sat) rolloff makes torque
    grow less-than-linearly with current once the iron approaches
    saturation, and the saturation knee scales with iron cross-section
    so bigger machines saturate at higher current. A surrogate that
    never sees the high-current corner will over-predict torque there.

  * Permanent-magnet temperature dependence: B_r(T)
    derates linearly with operating temperature (the NdFeB remanence
    temperature coefficient is ≈ -0.11 %/°C), so the same machine at a
    hot operating point makes less torque. A surrogate trained only at
    nominal temperature cannot be silently used at hot-fault
    temperatures.

Both mechanisms make the response a *deterministic* function of the
input vector — there is no per-row hidden random knob. (Per the
project's synthesizer-determinism discipline: every per-row stochastic
term in the generator becomes irreducible noise the surrogate cannot
learn and shows up as low held-out R². The only randomness here is the
small multiplicative scatter added at the end to mimic mesh /
post-processing noise, applied AFTER the deterministic response.)

The numerical coefficients are CHOSEN to make the synthetic responses
land in the data-contract.md typical ranges (torque to ~80 N·m,
efficiency mostly 80–99 %, total loss to ~1.6 kW); they are NOT derived
from any specific motor design or FE benchmark and they do NOT
reproduce the absolute magnitudes of any specific real electric machine.
See data-contract.md for the illustrative-numerics framing.

Run:
    python synthesize_sample.py
    python synthesize_sample.py --rows 400 --seed 7 --out my-data.csv
"""

import argparse
import csv
import math
import os
import random


# --- coefficients tuned so the synthetic responses cover the contract ranges ---
# (calibrated empirically against the contract's typical-range columns; see the
#  module docstring for the physical role of each)
KE_BASE      = 0.0034    # flux-linkage scale per (turn · D² · L) unit
KT_FRAC      = 0.92      # torque-constant coupling fraction (q-axis-dominant drive)
I_SAT_BASE   = 110.0     # A: saturation-knee current scale (scaled by iron area below)
TEMP_REF_C   = 40.0      # °C: reference temperature at which B_r is nominal
BR_TEMPCO    = 0.0011    # per-°C fractional remanence loss (NdFeB ≈ -0.11 %/°C)
R_PHASE_BASE = 0.00055   # Ω scale: copper resistance per (turns² / iron-area) unit
IRON_K       = 2.2e-6    # iron-loss coefficient (rpm^1.5 · flux² · iron-area)
MECH_K       = 5.0e-7    # windage + friction coefficient (rpm² · D^1.5)
STRAY_FRAC   = 0.010     # stray load loss as a fraction of output power
_NOISE_FRAC  = 0.020     # multiplicative scatter mimicking mesh / post-processing noise


def _sample_design(rng):
    """Sample one (geometry + winding + operating-point) input vector.

    The eight inputs parameterise an IPM-style synchronous machine and
    its operating point, drawn from the usual low-frequency-EM input set:
      - 4 geometry  : stator outer diameter, stack (axial) length,
                      mechanical air-gap, magnet thickness
      - 1 winding   : turns per coil
      - 3 operating : stator current amplitude, rotor speed, operating
                      temperature
    Ranges are chosen to span a small-EV / e-mobility traction-motor
    design space without straying into the deep-fault corners the
    contract excludes (see data-contract.md Rule 5 and Pitfall (ii)).
    """
    stator_od_mm    = rng.uniform(80.0, 260.0)    # mm
    stack_length_mm = rng.uniform(40.0, 180.0)    # mm
    airgap_mm       = rng.uniform(0.5, 2.5)       # mm
    magnet_thk_mm   = rng.uniform(3.0, 12.0)      # mm
    turns_per_coil  = rng.uniform(6.0, 30.0)      # turns
    current_a       = rng.uniform(20.0, 160.0)    # A (amplitude)
    speed_rpm       = rng.uniform(500.0, 12000.0) # rpm
    temperature_c   = rng.uniform(20.0, 140.0)    # °C
    return [stator_od_mm, stack_length_mm, airgap_mm, magnet_thk_mm,
            turns_per_coil, current_a, speed_rpm, temperature_c]


def _eval_response(x):
    """Map an input vector to (torque_nm, efficiency_pct, total_loss_w).

    Closed-form IPM-operating-point pastiche; deterministic in the input
    vector (no hidden random knob). See the module docstring for the
    governing relations and the two embedded failure-mode mechanisms.
    """
    (od, L, airgap, mthk, turns, current, rpm, temp) = x
    od_m = od / 1000.0
    L_m = L / 1000.0
    ag_m = airgap / 1000.0
    mthk_m = mthk / 1000.0

    # --- rotor flux linkage (deterministic in geometry, magnet, temperature) ---
    # remanence derate with temperature (Pitfall (ii) — PM demagnetisation);
    # clamped at 0.45 so a hot magnet never goes unphysically negative.
    br_factor = max(0.45, 1.0 - BR_TEMPCO * (temp - TEMP_REF_C))
    # air-gap flux concentration: thicker magnet and smaller gap -> more flux
    gap_term = mthk_m / (mthk_m + ag_m)                  # 0..1, dimensionless
    # rotor flux scales with bore area (~D²) · stack length · gap_term · B_r(T)
    flux = KE_BASE * turns * (od_m ** 2) * L_m * gap_term * br_factor * 1.0e3

    # --- electromagnetic torque with magnetic-saturation rolloff ---
    # (Pitfall (i) — the DOMINANT low-frequency-EM surrogate-failure mode)
    # The saturation knee I_sat scales with iron cross-section (D·L): bigger
    # iron carries more flux before saturating, so it saturates at higher
    # current. tanh() gives the soft below-knee / knee / deep-saturation
    # rolloff that flattens torque-per-amp at high current.
    i_sat = I_SAT_BASE * (0.4 + 1.6 * (od_m * L_m) / (0.20 * 0.12))
    sat = math.tanh(current / i_sat)                     # 0..~1
    torque = KT_FRAC * flux * current * sat * (turns / 12.0)

    # --- losses ---
    omega = rpm * 2.0 * math.pi / 60.0                   # rad/s
    p_out = torque * omega                               # W (mechanical output)
    # copper loss: 3-phase I²R with R from turns² / conductor cross-section (~D·L)
    r_phase = R_PHASE_BASE * (turns ** 2) / (od_m * L_m * 1.0e3)
    p_cu = 3.0 * (current / math.sqrt(2.0)) ** 2 * r_phase
    # iron loss: ~ f^1.5 · flux² (Steinmetz-ish), f proportional to rpm
    p_fe = IRON_K * (rpm ** 1.5) * (flux ** 2) * (od_m * L_m * 1.0e3)
    # mechanical (windage + friction): ~ rpm²
    p_mech = MECH_K * (rpm ** 2) * (od_m ** 1.5)
    # stray load loss
    p_stray = STRAY_FRAC * max(p_out, 0.0)
    p_loss = p_cu + p_fe + p_mech + p_stray

    p_in = p_out + p_loss
    efficiency = 100.0 * p_out / p_in if p_in > 1e-6 else 0.0
    return torque, efficiency, p_loss


def synthesize(rows, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(rows):
        x = _sample_design(rng)
        torque, eff, loss = _eval_response(x)
        # modest multiplicative scatter to mimic mesh / post-processing noise,
        # applied AFTER the deterministic response so it does not contaminate
        # the learnable surface (it is the only randomness on the targets).
        torque *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        loss *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        eff += rng.gauss(0.0, 0.4)            # additive scatter on % points
        # clamp to data-contract ranges as a defensive guard
        torque = max(torque, 0.0)
        loss = max(loss, 0.0)
        eff = max(min(eff, 99.0), 40.0)
        out.append(x + [torque, eff, loss])
    return out


def write_csv(rows, path):
    header = [
        "stator_od_mm", "stack_length_mm", "airgap_mm", "magnet_thickness_mm",
        "turns_per_coil", "current_a", "speed_rpm", "temperature_c",
        "torque_nm", "efficiency_pct", "total_loss_w",
    ]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            out = []
            for v in r[:8]:
                out.append("%.4f" % v)
            out.append("%.4f" % r[8])     # torque
            out.append("%.3f" % r[9])     # efficiency
            out.append("%.3f" % r[10])    # total loss
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
    # quick summary so the reader (or a reviewer) can sanity-check ranges
    tq = [r[8] for r in rows]
    eff = [r[9] for r in rows]
    loss = [r[10] for r in rows]
    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  torque_nm      : min %.2f  max %.2f  mean %.2f"
          % (min(tq), max(tq), sum(tq) / len(tq)))
    print("  efficiency_pct : min %.2f  max %.2f  mean %.2f"
          % (min(eff), max(eff), sum(eff) / len(eff)))
    print("  total_loss_w   : min %.2f  max %.2f  mean %.2f"
          % (min(loss), max(loss), sum(loss) / len(loss)))
    # how many designs are high-efficiency (>= 90 %) vs poor (< 80 %)
    hi = sum(1 for e in eff if e >= 90.0)
    lo = sum(1 for e in eff if e < 80.0)
    print("  efficiency >= 90%%: %d / %d (%.0f %%);  < 80%%: %d (%.0f %%)"
          % (hi, len(rows), 100.0 * hi / len(rows),
             lo, 100.0 * lo / len(rows)))


if __name__ == "__main__":
    main()
