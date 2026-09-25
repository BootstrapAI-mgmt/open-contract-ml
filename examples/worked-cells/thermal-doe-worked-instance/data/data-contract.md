# Thermal DOE worked instance — Data Contract

> This is the exact specification of the dataset the head-to-head
> comparison (`run_ht_instance.py`, not included in this repository)
> expects. Unlike the other worked cells, this folder is not asking you
> to supply your own CAE results — the whole point of the instance is
> that everyone runs the *same* 720 rows, so that the numbers can be
> reproduced rather than believed. `synthesize_sample.py` regenerates
> the file byte-for-byte on demand.
>
> All numeric values are *illustrative*. The functional form is a
> two-node steady-state energy balance, not a substitute for a
> conjugate thermal-FE solve. It exists so that a requirements-driven
> selection argument can be watched happening on a surface whose
> exact answer is known at every point — which is what makes the
> gradient and inverse comparisons gradeable at all.

## The physical case

A heat-dissipating module sits inside an enclosure, separated from a
liquid-cooled wall by an air **clearance** gap. Heat leaves the module
by three parallel paths — conduction across the gap, radiation across
the gap, and conduction through the mounting feet — and the wall passes
what it receives to the coolant through a finite wall conductance.

The design question the DOE exists to answer is an **inverse** one, and
it is the sentence this instance is built around:

> *what clearance keeps this under 120 °C?*

That is not a prediction. Nobody wants a number for a clearance they
already chose; they want the clearance that lands the temperature on a
limit. Which surrogate families can answer that question, and which
cannot, is the entire subject of this instance.

## Columns

| #  | Column name               | Role       | Quantity                                                  | Units   | Levels / range           |
|----|---------------------------|------------|-----------------------------------------------------------|---------|--------------------------|
| 1  | `clearance_mm`            | input      | Air gap between the module face and the cooled wall        | mm      | 0.50 / 0.80 / 1.10 / 1.40 / 1.70 / 2.00 |
| 2  | `q_W`                     | input      | Total heat dissipated by the module                        | W       | 120 / 150 / 180 / 210 / 240 |
| 3  | `T_coolant_C`             | input      | Coolant temperature behind the cooled wall                 | °C      | 30 / 45 / 60 / 75        |
| 4  | `emissivity`              | input      | Emissivity of the module's gap-facing surface              | —       | 0.20 / 0.50 / 0.80       |
| 5  | `mount_conductance_W_K`   | input      | Conductance of the mounting-foot path to the coolant       | W/K     | 0.50 / 1.10              |
| 6  | `T_peak_C`                | **target** | Peak module surface temperature — **the 120 °C limit applies here** | °C      | 53.7 – 183.4             |
| 7  | `T_wall_C`                | **target** | Enclosure-wall temperature on the gap side                 | °C      | 38.9 – 101.7             |
| 8  | `q_gap_W`                 | **target** | Heat crossing the gap by conduction                        | W       | 50.0 – 206.2             |
| 9  | `q_rad_W`                 | **target** | Heat crossing the gap by radiation                         | W       | 2.2 – 83.3               |
| 10 | `q_mount_W`               | **target** | Heat leaving through the mounting feet                     | W       | 13.2 – 96.8              |

**Five inputs, five targets, 6 × 5 × 4 × 3 × 2 = 720 rows.** The file is
a complete full factorial: every combination of the levels above appears
exactly once, with the first column varying slowest.

## Rules

1. **The design is a full factorial, and that matters.** Most CAE
   surrogate datasets in this repo are space-filling — Latin hypercube
   or Sobol. This one is a grid, because the instance it reproduces was
   a grid, and because one of the practitioner's own points was about
   grids: a partition model fitted to full-factorial levels interpolates
   as a staircase, and engineers query between the nodes. A
   partition-based model fitted to a 6-level grid has **five** places it
   can put a split on
   `clearance_mm` and nothing in between. That is not a defect in the
   model; it is the interaction between an estimation principle and a
   design, and §7 of the head-to-head output measures what it costs.
2. **Six clearance levels is few, on purpose.** It is enough to see the
   response curve and far too few to interpolate a root to 2% of range
   by recall. Widening the grid would soften the effect; the DOE this
   instance reproduces had this shape and the instance keeps it.
3. **The three heat-path targets sum to `q_W` by construction.**
   `q_gap_W + q_rad_W + q_mount_W = q_W` to within 3 × 10⁻¹⁰ W across all
   720 rows (`synthesize_sample.py` prints the worst case on every run).
   No surrogate here is told about that constraint. Whether a fitted
   model happens to respect it is a legitimate diagnostic, and it is
   deliberately **not** one of the head-to-head's metrics. It is noted so
   a reader does not mistake the redundancy for a mistake.
4. **Deterministic, noise-free, no seed.** There is no measurement
   scatter in this file and no random number is drawn anywhere in its
   generation. The response is a closed-form energy balance resolved by
   bisection to 10⁻¹⁰ K. This matches the problem spec for the case
   (`deterministic: yes`, `noise: none`; the format is in
   `examples/problem-spec/`) — if you change one, change the other, or a
   selector will be answering about a different problem than the one in
   this folder. The response surface must be a deterministic function of
   the inputs: a per-row `rng.uniform()` inside the response evaluation
   becomes irreducible noise and destroys the fit (an earlier synthesizer
   that did this held the average R² at 0.025; removing it gave
   0.890).
5. **Temperatures are Celsius; the physics is Kelvin.** Columns 3, 6 and
   7 are °C. The radiation term is a fourth power and is therefore
   *only* meaningful in absolute temperature — the synthesizer converts
   internally and converts back. If you extend this dataset, do not feed
   Celsius into a T⁴ term.
6. **Conduction-regime gap only.** The gap model is pure conduction,
   `U_gap = k_air · A / g`, with Nu = 1. That is defensible here because
   the worst-case gap Rayleigh number across the whole design is **32**,
   two orders of magnitude below the Ra ≈ 1708 onset of Rayleigh–Bénard
   convection in a horizontal air layer (`synthesize_sample.py` prints
   it every run — the claim is checked, not asserted). Widen the
   clearance levels past roughly 4 mm and you leave that regime; the gap
   model stops being defensible and this contract stops applying.
7. **Constant air properties.** `k_air`, ν and α are fixed at their
   ~350 K values. Across the temperature span in this file the true
   conductivity of air moves by roughly 15%, which is absorbed into the
   illustrative-numerics framing. A real study would evaluate properties
   at each film temperature.
8. **One row per operating point; no repeats.** The file is a factorial,
   not a sample. There is no replication and there is nothing to average.

## The engineered feature basis

This instance carries physics-engineered features (ΔT terms and a
linearized T⁴ radiation term). Those features are **not** in this CSV —
they are built from these columns at fit time by the head-to-head script
(`run_ht_instance.py`, not included in this repository) and handed
identically to all three families:

| Feature | Expression | What it is |
|---|---|---|
| `u_gap_W_K` | `k_air · A / g` | the gap conductance — the 1/clearance term |
| `h_rad_W_K` | `4 σ ε_eff A T_c³` | the **linearized T⁴ radiation term**, evaluated at the known coolant temperature |
| `dT_cond_K` | `q / (u_gap + C_mount)` | a **ΔT term**: the conduction-only temperature rise |
| `dT_full_K` | `q / (u_gap + C_mount + h_rad)` | a **ΔT term** with radiation folded in |

Every one is computable from the five inputs alone — none of them needs
the answer. Section 3b of the head-to-head ablates them, and the result
is the sharpest single number in the folder: taking the basis away costs
the quadratic a factor of **36**, the forest a factor of 1.1, and the
network nothing at all. The features are available to all three
families; only one of them has an estimation principle that can convert
them into accuracy. That is the reason to group surrogate families by
estimation principle rather than by function class.

## How this maps to the taxonomy

A surrogate-family selector that reads the problem-spec format in
`examples/problem-spec/` returns, for this instance, top-1 **B1**,
admissible **{B1, B2, B4, B3}**, with **B6 / B8 / B10 excluded by R1**
— the rule that reads `needs_inverse`, `needs_gradients` and
`needs_smooth_sweeps`. (The selector and its filled spec for this case
are not included in this repository.)

The three requirements R1 reads are all true of this dataset by
construction, and all three are properties of the *question*, not of the
data:

- **inverse** — the 120 °C clearance solve, §4 of the head-to-head;
- **gradients** — sensitivities of `T_peak_C` to all five design
  variables, §5;
- **smooth sweeps** — a clearance sweep an engineer will read off a
  chart, §6.

The analysis is steady-state thermal, a Bucket B1 tabular case.
Textbook anchor for the conduction and radiation framing and for the
Ra ≈ 1708 enclosure criterion: [Bergman2017].

**Companion material.** The contrast case worth reading next to this one
is a problem described as a measured NVH rig — kinked and noisy, with
no smoothness requirement — for which the same selection returns
**B6**. The pair is the argument that the selection prefers whichever
families survive the declared requirements, not whichever families are
smooth.
