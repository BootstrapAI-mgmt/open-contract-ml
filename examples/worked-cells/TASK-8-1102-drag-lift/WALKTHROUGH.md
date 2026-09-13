# TASK-8-1102 — Predicting Drag & Lift of an Off-Road Utility Vehicle

### A step-by-step worked example for CAE engineers — no ML background needed

> Part of the CAE-ML step-by-step examples arc — project task 8
> (`EXAMPLES-ARC-SCOPING.md`). This is example **`TASK-8-1102`**: the
> ID encodes its slide-9 grid cell — `n=1` (parametric-input row),
> `m=1` (scalar-output column), example `02` — i.e. Bucket B1, the
> tabular surrogate. It is the **eighth B1 example** in the arc and
> the first external-aerodynamics example (the canonical CFD B1 — see
> `EXAMPLES-ARC-SCOPING.md` §4 row TASK-8-1102).
>
> You will train a model and use it. You will **not** write code or make
> any machine-learning decisions. Everything runs by double-clicking a
> file.

---

## 1. What this example does

Running a full 3-D external-aero CFD analysis of a vehicle to get a
single set of force / moment coefficients — drag, lift, side force,
yawing moment at one (speed, yaw) operating point — typically takes
many CPU-hours per run on a properly-refined surface mesh with a
resolved wake. When you are screening *assembly choices* across an
off-road / overland utility vehicle program — does swapping the stock
intake (`INT-A1`) for a snorkel (`INT-A2`) noticeably hurt drag at
highway cruise? does the crew-cab option (`CAB-A3`) cost you crosswind
stability? — you cannot afford to run the full CFD for every candidate
× operating-point combination.

This example builds a **surrogate**: a fast model that has learned,
from a batch of vehicle aero CFD runs you have *already* done, the
relationship between an assembly's choice-vector (sixteen catalog
slots) + the operating point (highway speed + crosswind yaw) and the
four aero-coefficient targets `CD`, `CL`, `CY`, `CM` at the program's
canonical reference area / length. Once trained, it returns all four
numbers in a fraction of a second, so you can screen hundreds of
assembly × operating-point combinations before committing solver time
to the few that matter.

**Where this sits in the taxonomy.** The model takes a *row of inputs*
(sixteen catalog option codes plus speed and yaw) and returns a
*short vector of numbers* (four aero-coefficient scalars). On the
BRIDGE-A slide-9 grid that is the top-left cell — *parametric input →
scalar(s) output* — which is **Bucket B1, the tabular surrogate**. B1
is the simplest and most production-proven corner of the grid, which
is why this example uses it. Catalog reference: analysis **A.1.1**
(CFD family, external-aerodynamics sub-variant) in
`tasks/TASK-1-cae-analysis-catalog.md`. Arc admission record:
`EXAMPLES-ARC-SCOPING.md` §4 row TASK-8-1102 (canonical-CFD-B1
admission, the second B1 example for the CFD-trained reader after the
pump pair).

**The honest framing.** This is *on-road aero for an off-road-styled
vehicle.* Pure off-road operation is mostly low-speed where aero
effects are negligible; the engineering question that justifies aero
CFD on an off-road platform is sustained highway cruise (fuel economy)
and crosswind stability (lane-keeping in side winds during overtaking
or sustained gusts). The `speed_kmh` range (60 – 130 km/h) and
`yaw_deg` range (-15 – +15 deg) are calibrated to that envelope.

The four steps ahead:

```
   Step 1                  Step 2                              Step 3
  Format    ──▶   Train-Drag-Lift.exe   ──▶   Predict-Drag-Lift.exe
  your data       (makes the                  (use the trained
  (a CSV)          trained model)              model on new assemblies)
```

---

## 2. What you'll need before you start

- **A batch of vehicle aero CFD runs you have already completed.**
  Each run is one assembly at one (speed, yaw) operating point,
  analysed through your normal 3-D external-aero CFD process (Fluent
  / STAR-CCM+ / OpenFOAM with any standard RANS or DDES closure on a
  properly-refined surface mesh with a resolved wake). For each run
  you must know the sixteen assembly option codes you used, the two
  operating-point values, and the four aero coefficients the run
  produced at the program's canonical reference area / length.
- **At least 150 runs**; 250 – 500 is healthy. The minimum is higher
  than for the fatigue-life example (TASK-8-1101) because drag-lift
  spans both an *assembly* space (sixteen categorical slots, each
  with three or four options — a combinatorially large catalog) and
  an *operating-point* space (two continuous parameters). A practical
  DOE shape: ~50 assemblies × ~4 operating-point combinations each ≈
  200 rows. Use a fractional-factorial or Latin-hypercube design over
  the catalog to keep the slot-coverage balanced.
- The eighteen inputs and four targets are listed in
  `data/data-contract.md`; the per-slot catalog of option codes and
  what physical attributes each one resolves to is in
  `data/assembly-catalog.md`. The sixteen catalog slots are:
  chassis, engine, transmission, clutch, cooling, intake, exhaust,
  fuel, brakes, cabin, electrical, oil, ROPS, steering, suspension-
  front, suspension-rear. The two operating-point inputs are speed
  and yaw. The four targets are `CD`, `CL`, `CY`, `CM`.
- A Windows PC. See *Setup* at the end of this document — there is
  no install step.

You do **not** need a GPU, an internet connection while training,
Python, or any ML software. Everything the example needs is inside
the executables.

> **If you just want to see it work first:** this example ships with
> a synthetic `data/sample-dataset.csv` (200 rows). You can run Steps
> 2 and 3 on that immediately, before you have prepared any real
> data. The sample data is illustrative only — it is *not* real
> vehicle-aero CFD data and its accuracy tells you nothing about what
> you will get on your own runs.

---

## 3. Step 1 — Format your data

The trainer reads one CSV file. It must have the twenty-two required
columns in `data/data-contract.md` (plus an optional `notes` column),
in that order, with one row per CFD run.

1. Open `data/template.csv`. It has the correct header row and three
   blank guide rows.
2. For each vehicle aero CFD run you have done, add one row: the
   sixteen assembly option codes you used, then the two operating-
   point values, then the four aero coefficients it produced. The
   23rd column (`notes`) is optional — leave it blank or use it for
   your own DOE / run-ID labels.
3. **Use catalog option codes in the assembly columns.** The trainer
   resolves each code (e.g. `INT-A2`) to its physical-attribute
   vector (e.g. `intake_height_above_hood_mm = 380`,
   `intake_diameter_mm = 140`) via `data/assembly-catalog.md`. You
   never see this resolution in your CSV. (Two slots — `cabin_option`
   and `rops_option` — accept the special value `NONE` for open-frame
   ATVs and sealed-cab passenger vehicles respectively. Both are
   valid choices.)
4. **The targets are signed dimensionless coefficients.** `CD` is
   always positive (drag is in the direction of motion). `CL` is
   positive for net upward lift (off-road utility vehicles are
   typically slightly positive in clean cruise). `CY` and `CM`
   follow the same right-hand convention as `yaw_deg` — positive
   yaw and positive `CY` both correspond to wind from the driver's
   right. Use the program's canonical reference area and reference
   length consistently across every row — the surrogate cannot
   un-do an inconsistent reference convention.
5. Fill every cell in columns 1–22 — option codes for slots 1–16,
   numbers for columns 17–22. Column 23 (`notes`) may be blank.
6. Save it as a `.csv` file. Anywhere is fine; you will point the
   trainer at it in Step 2.

When you are done, your file should look like
`data/sample-dataset.csv` — same columns, same shape, just with your
real catalog choices and CFD numbers.

> This is the only step where you do real work. The trainer checks
> your file against the contract before it does anything, and if a
> column is missing, a cell is not a recognised option code, or a
> number cell is non-numeric, it tells you exactly what to fix.

**One subtlety vs. the fatigue example (TASK-8-1101).** The drag-lift
data contract has a **dual-channel input vocabulary**. Your training
CSV uses reader-friendly catalog option codes; the surrogate
internally trains on the physical-attribute vectors those codes
resolve to. At predict-time you can address each slot either way —
supply the option code (the predictor resolves it for you) or supply
the underlying physical attributes directly (useful when you are
exploring a new design that doesn't match any catalog option, or you
want a "between" interpolation). Both channels feed the same trained
model. See `data/assembly-catalog.md` for the full per-slot schema.

---

## 4. Step 2 — Train the model

1. Open the `Train-Drag-Lift` folder.
2. Double-click **`Train-Drag-Lift.exe`**. A black window opens.
3. When it asks for the dataset path, paste the full path to the CSV
   you saved in Step 1 and press Enter. (To try the sample, type
   `data\sample-dataset.csv`.)

The trainer now does three things, with no further input from you:

- **It checks your data** against the contract and the catalog
  (every option code in slots 1–16 must be one of the catalog's
  enumerated codes for that slot, or `NONE` where allowed) and tells
  you how many runs it found.
- **It learns the relationship** between your eighteen inputs and
  the four aero coefficients, by looking at all of your runs
  together. This is the sealed part — you do not configure it.
- **It checks itself honestly.** Before learning, it sets aside one
  in five of your runs at random and does *not* look at them while
  learning. Afterwards it predicts those held-back runs and
  compares to the real answers, **per target separately**. This is
  the only honest way to estimate how the model will do on
  assemblies it has never seen.

It then prints a short **per-target accuracy report**:

```
    Target        Avg error (MAE)   R-squared
    CD               0.011          0.943
    CL               0.007          0.913
    CY               0.015          0.891
    CM               0.007          0.823

  Average R-squared across targets : 0.893
```

- **Average error (MAE)** is how far off a typical prediction is, in
  the target's own units (dimensionless for these). A `CD` MAE of
  0.011 means a typical drag-coefficient prediction lands within
  about 0.01 of the real number — good enough to *rank* assemblies
  whose true `CD` separation is bigger than that.
- **R-squared** is how much of the variation in each target the
  model explains. Closer to 1.00 is better; below about 0.6 for any
  target the trainer warns you that target is weak and you probably
  need more or better-spread runs.
- **Average R-squared across targets** is a quick health signal for
  the model overall.

Finally the trainer creates a **`trained-model`** folder next to
your dataset. That folder is your finished model. You are done with
training.

> The numbers above come from the shipped synthetic sample data and
> are illustrative. Your accuracy depends entirely on your own runs.

---

## 5. Step 3 — Use the trained model

1. Open the **`trained-model`** folder the trainer just created,
   then the **`Predict-Drag-Lift`** folder inside it.
2. Double-click **`Predict-Drag-Lift.exe`**.
3. Choose how you want to use it:

   **Option 1 — one assembly at a time.** It asks for each of the
   sixteen catalog slots in turn — type the option code (e.g.
   `INT-A2`) or press Enter to accept the stock option. It then asks
   for `speed_kmh` and `yaw_deg`. Finally it prints the predicted
   **four-value bundle**:

   ```
     Drag coefficient    CD : 0.382
                              range: 0.371 to 0.393
     Lift coefficient    CL : 0.034
                              range: 0.027 to 0.041
     Side-force coef.    CY : 0.012
                              range: -0.003 to 0.027
     Yawing-moment coef. CM : 0.008
                              range: -0.000 to 0.016
   ```

   **Option 2 — many assemblies at once.** Point it at a CSV
   containing the eighteen input columns (no target columns needed —
   those are what you are predicting). It writes a new file ending
   `-predictions.csv` with the four predicted values (and per-target
   ranges) plus a single extrapolation flag per row.

Every prediction comes with a **per-target likely range**, not just a
single number. A wide range means "treat this as a rough screen"; a
narrow range means "this is a confident estimate." The four ranges
can be wider or narrower for different targets — `CD` is often the
narrowest (drag is dominated by frontal-area choices that the
catalog captures cleanly), `CM` is often the widest (yawing moment
involves a longer lever arm and is more sensitive to subtle
asymmetries that the sample size may not have spanned).

**What the four numbers mean together.** A useful diagnostic: at
zero yaw an aero-symmetric vehicle should give predicted `CY` and
`CM` near zero. If the predictor returns a strongly non-zero `CY`
at `yaw_deg = 0`, either the assembly is genuinely asymmetric
(off-side exhaust, single-side snorkel, etc.) or your training data
did not span enough zero-yaw runs to anchor that target. At nonzero
yaw, `CY` and `CM` should change sign with the yaw sign — a model
that does not honour that sign-flip on its hold-out predictions has
been trained on data with insufficient yaw-sign coverage.

---

## 6. Reading the results responsibly

A surrogate is a screening tool, not a replacement for your solver.
Three rules keep you out of trouble for the external-aero case
specifically:

1. **Watch for the extrapolation warning.** The model has only seen
   the range of assemblies and operating points in your training
   data. If you ask it about an operating point outside that range —
   say a `speed_kmh` value above the highest you trained on, or a
   `yaw_deg` outside the trained envelope — it prints:

   ```
     *** EXTRAPOLATION WARNING ***
     These inputs are outside the range of your training runs:
       speed_kmh
   ```

   A flagged prediction is a guess outside the model's experience.
   Treat it as a prompt to run a real CFD simulation, not as an
   answer. The same warning fires if you supply a physical-attribute
   value (rather than an option code) that falls outside the
   training envelope for that attribute — useful when you are
   exploring "between" designs not in the catalog.

2. **The surrogate predicts your CFD, not the physical vehicle.**
   This is load-bearing for external aero specifically. CFD of an
   industrial-scale vehicle at highway Reynolds numbers is not a
   solved problem — the NASA CFD Vision 2030 study (Slotnick et al.
   2014) frames the broader gap directly:

   > "the 'Vision 2030' CFD study is to provide a knowledge-based
   > forecast of the future computational capabilities required for
   > turbulent, transitional, and reacting flow simulations across
   > a broad Mach number regime, and to lay the foundation for the
   > development of a future framework and/or environment where
   > physics-based, accurate predictions of complex turbulent flows,
   > including flow separation, can be accomplished routinely and
   > efficiently in cooperation with other physics-based simulations
   > to enable multi-physics analysis and design."
   > — Slotnick, Khodadoust, Alonso, Darmofal, Gropp, Lurie &
   > Mavriplis (2014), *CFD Vision 2030 Study: A Path to Revolutionary
   > Computational Aerosciences*, NASA/CR–2014-218178, abstract
   > (NTRS: [20140003093](https://ntrs.nasa.gov/citations/20140003093);
   > quote block `Q-cae-03` in `QUOTES.md`).

   The headline is that "physics-based, accurate predictions of
   complex turbulent flows, including flow separation" is a 2030
   *target*, not a 2014/2026 default. Off-road utility vehicles are
   blunt bodies with substantial flow separation behind the cabin,
   around exposed cages, and over wheel arches — exactly the regime
   the Vision 2030 study flags as gap-bearing. **Your CFD has a
   systematic error band relative to wind-tunnel test** — typically
   ~5–15% in `CD`, larger in `CY` and `CM` at high yaw — and
   **your surrogate inherits this gap.** It learns your CFD's
   behaviour, not the vehicle's wind-tunnel behaviour. Expect a
   systematic bias when you compare predictions to wind-tunnel
   results, and use your own CFD-vs-tunnel calibration (if you have
   one) to debias the surrogate's output post-hoc rather than trying
   to bake the correction into the training set.

3. **Use it to rank, then verify.** The honest use of a B1 vehicle-
   aero surrogate is to screen many assembly × operating-point
   combinations quickly, pick the few best, and then run your full
   CFD on those few to confirm. The surrogate narrows the search;
   the solver still makes the final call. For final claims that
   leave the engineering group — published fuel-economy figures,
   stability certifications, marketing copy — anchor them on real
   CFD plus, where the program budget supports it, wind-tunnel test.

**This example predicts coefficients at a query operating point,
not the shape of the polar curve as a whole.** If you need the
`CD(yaw)` / `CY(yaw)` polar curves themselves — the side-force
build-up rate, the destabilising-moment crossover point — you
would need a curve-prediction example analogous to the pump pair's
PCC half (`TASK-8-1401`). No such curve-prediction aero example
exists yet in the arc; that is a deliberate iteration-0 scoping
decision (see `EXAMPLES-ARC-SCOPING.md` §4 and §3.3).

If the accuracy report in Step 2 was weak for any target (low
R-squared on that row), that target's predictions are not
trustworthy yet — add more runs, spread them more widely across the
assembly catalog (cover every option code in every slot at least a
few times) and the (speed, yaw) envelope, and train again. `CM` is
the most common weak target because its smaller magnitude and
greater sensitivity to subtle geometric asymmetries demand more
samples than the other three.

---

## 7. What's happening inside (optional — you can skip this)

You do not need this section to use the example. It is here for
the curious.

The sealed model is a **multi-output gradient-boosted-tree
ensemble**. Under the hood the trainer fits *one independent
boosted-tree regressor per target* (`CD`, `CL`, `CY`, `CM`),
wrapped in scikit-learn's `MultiOutputRegressor`. Each individual
regressor is the same family used in the fatigue-life example
(TASK-8-1101) and the pump pair (TASK-8-1107 / TASK-8-1401) — a
large set of simple yes/no flowcharts ("is the
`intake_height_above_hood_mm` above 200? is the `speed_kmh` below
100?") each making a small correction to that target's estimate.

The sixteen catalog slots are not used as ML inputs directly.
Instead the trainer resolves each option code to its physical-
attribute vector (twenty-six attributes total across the catalog —
see `data/assembly-catalog.md`), then concatenates the twenty-six
attributes with the two operating-point inputs to form the
twenty-eight-dimensional feature vector the boosted trees actually
see. This is what makes the *dual-channel* predict-time input
possible: catalog codes route through the resolution table;
attribute values bypass it. Both arrive at the same twenty-eight-
dimensional feature space.

Picture the four target heads as four parallel B1 surrogates that
happen to share the same twenty-eight input columns. Doing them
all at once is operationally convenient; it does *not* mean the
model learns relationships *between* the four outputs (a multi-
output GBM has no such cross-target structure). That is a
deliberate choice for this example — the four outputs are
physically related (a CD increase from a frontal-area choice will
usually correlate with a CY change at non-zero yaw), but the
surrogate respects that relation only insofar as the underlying
CFD data already encodes it.

This family of model is the industrial workhorse for *parametric
input → short scalar vector output* problems (Bucket B1). It needs
no GPU, trains in seconds to minutes, handles the eighteen inputs
without you having to scale or transform them, and copes
gracefully with parameters that matter a lot (intake snorkel
height) and parameters that barely matter (transmission option).

**Why not learn the whole polar curve?** A B1 surrogate is the
right answer when you need coefficients at a *specific* operating
point. When you need the *whole `CD(yaw)` polar curve* — the
shape itself, including the side-force build-up rate and the
moment crossover — the right architecture is different, for the
same reason a B7 polynomial-basis surrogate beats a B1 sampled-
points surrogate for the pump-curve case (TASK-8-1401). No B7
external-aero example exists yet in the arc; the pump pair is the
arc's authoritative B1-vs-B7 worked-instance.

---

## 8. Where to go next

- **The other B1 examples in the arc** apply these exact four
  steps to other physics: fatigue life (`TASK-8-1101`), pump
  operating-point performance (`TASK-8-1107`), peak structural
  stress (`TASK-8-1103`), peak temperature (`TASK-8-1104`), motor
  torque (`TASK-8-1105`), and molding warpage (`TASK-8-1106`).
  Same four steps, same data-contract shape, different domain. See
  `EXAMPLES-ARC-SCOPING.md` §4 for the inventory.
- **The B1-vs-B7 worked-instance — the pump pair.** TASK-8-1107
  (Pump Operating-Point Performance, PCS — Bucket B1, scalars at
  a query operating point) and TASK-8-1401 (Pump Performance
  Curve, PCC — Bucket B7, full H(Q) / η(Q) / NPSHr(Q) curves at a
  query RPM via a polynomial basis) are the same CFD case with
  the same design vector, but differ in which bucket their
  downstream question routes them to. **Choose B1 when you need
  values at a specific operating point; choose B7 when you need
  the whole curve.** See `examples/TASK-8-1107-pump-operating-point/`
  and `examples/TASK-8-1401-pump-performance-curve/` for the pair.
  The pair teaches the same lesson from two angles: *the right ML
  bucket depends on the downstream question, not the underlying
  CFD case.*
- **For the concepts behind this**, see the BRIDGE-A framework
  deck (`presentations/Presentation-BRIDGE-A-Framework.pptx`) —
  slide 9 is the input/output shape grid this example is built
  around.
- **The Slotnick (2014) anchor** is in `SOURCES.md` (key
  `Slotnick2014`); the verbatim Vision 2030 framing sentence
  cited in §6 above is in `QUOTES.md` (`Q-cae-03`).

---

## Setup

**There is no install step.** This example ships as standalone
Windows programs. You do not need Python, you do not need to install
anything, and you do not need an internet connection to run it.

1. Download the example folder onto your Windows PC.
2. Open it. Inside you will find the `Train-Drag-Lift` folder (your
   trainer), a `data` folder (the sample dataset, the assembly
   catalog, and the templates), and this walkthrough.
3. That is all. Go to Step 1 above to format your data, or jump
   straight to Step 2 and train on the sample dataset to see it work.

### If Windows shows a blue "SmartScreen" box

These programs are **not code-signed**, so the first time you run
`Train-Drag-Lift.exe` (or `Predict-Drag-Lift.exe`) Windows may show
*"Windows protected your PC"*. This is expected for an unsigned in-
house engineering tool — it is not a warning that anything is wrong.
Click **More info**, then **Run anyway**. You will only see this
once per program.

> **How these programs were made.** The `.exe` files are produced by
> the project's packaging recipe (`examples/packaging/`, sub-task
> `TASK-8-PKG` — see `EXAMPLES-ARC-SCOPING.md` §5A). The recipe
> bundles a sealed Python machine-learning runtime *inside* each
> executable, so the program is fully self-contained. You never see
> Python; it is an implementation detail of the build, not something
> you install.
