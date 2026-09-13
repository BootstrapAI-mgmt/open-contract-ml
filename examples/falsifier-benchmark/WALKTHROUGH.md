# TASK-9 — The Falsifier: Checking the Selection Rules Against Measurement

### A step-by-step guide for CAE engineers — no ML background needed

> Part of the CAE-ML worked-example arc (`EXAMPLES-ARC-SCOPING.md`). Unlike
> the `TASK-8-nm##` examples, this one does not train a surrogate for you,
> and unlike its sibling `examples/TASK-9-surrogate-selector/` it does not
> answer questions about *your* problem. It answers a question about the
> **taxonomy itself**: when the selection rules claim that some model
> families cannot be solved backwards, differentiated, or swept smoothly —
> **is that measurably true, and by how much?**
>
> You will run a ninety-second check and read two result surfaces. You will
> **not** write code or make any machine-learning decisions. Everything runs
> by double-clicking a file.

---

## 1. What this folder is

The TASK-9 taxonomy (`TASK-9-TAXONOMY-scalar-surrogate-selection.md` at the
repository root) tells you which family of surrogate model fits a problem's
requirements, and its sibling tool in `examples/TASK-9-surrogate-selector/`
applies those rules to your answers. Both rest on published literature —
every rule carries citations. But some of the matrix cells the rules fill in
had **no published number behind them**: the literature says a random
forest's surface is a staircase, and says a staircase breaks root-finding,
without ever saying *how often* the root-finder fails, at what sample size,
by how much. The taxonomy's Appendix B logs those cells as `[OPEN]`.

This folder is the **falsifier benchmark** — the experiment built to put
numbers on exactly those cells, designed so that it *could have refuted* the
rules it tests. A *falsifier* is an experiment whose job is to give a claim
a fair chance to fail: if the partition families had localized roots as well
as the smooth families, or the exact interpolant had shrugged off noise, the
taxonomy's rules would have been in trouble, and this experiment would have
said so in print.

What it does, in one paragraph: it manufactures six synthetic response
surfaces whose true answer is known exactly (a plane, a quadratic, a smooth
wave, a kinked surface, a hard step, and a five-input smooth extension),
lays out training designs of 49 to 1,024 runs on them, fits **nine
surrogate families to every cell under the same declared budget**, and then
measures each fitted model on the axes the selection rules actually branch
on — accuracy, root-finding, gradients, extrapolation, sweep smoothness,
noise response, and fit cost. Because the true surface is analytic, every
measurement is scored against truth, not against another model.

Two artifacts live here beside this guide:

- **`falsifier_benchmark.py`** — the instrument. Seeded (seed 0), pinned to
  numpy + scipy + scikit-learn, single-threaded, ~12 CPU-minutes in full.
- **`falsifier_results.txt`** — the verbatim output of a real full run,
  committed as the quotable record. Its 51 cell tables end in twelve
  **verdict blocks** (`[V1]`–`[V12]`) that name the matrix cell or
  indifference tolerance each result settles or supports.

**This is the evidence lane, not the reader lane.** If you want to know
which family *your* problem should use, close this and open
`examples/TASK-9-surrogate-selector/WALKTHROUGH.md` — fifteen questions,
under a second, a forwardable verdict sheet. Come back here when somebody
looks at a verdict sheet's rule trace and asks *"says who, and by how
much?"* — this folder is where those magnitudes come from, and it is the
instrument behind the taxonomy's Appendix B `[OPEN]`-cell log.

```
   Step 1                      Step 2                    Step 3
  Run the check   ──▶   Read the cell tables   ──▶   Read the verdicts
  (~90 s, writes        (what was measured)          [V1]–[V12] (what it
  nothing)                                           settles, and how much)
```

---

## 2. What you'll need before you start

**Nothing of your own.** This is the other place this guide differs from
every `TASK-8` example: there is no template CSV to fill, because the
experiment ships its own problems. The surfaces are synthetic *on purpose* —
only a surface with a known analytic answer lets you score a model's root,
gradient, or extrapolation against **truth** rather than against a
second model whose own error is unknown.

So the checklist is short:

- **Python 3.12** installed once (see *One-time setup* at the end).
- **Three libraries** — numpy, scipy, scikit-learn. Nothing else: no GPU,
  no internet connection during the run, no ML toolchain.
- **About 90 seconds** for the wiring check, or **about 12 minutes** if you
  choose to regenerate the full grid (most readers never need to).

You also do not need to have read the 1,482-line taxonomy document. You do
need one sentence of context from it: the selection rules prune model
families based on *what you will do with the model* — solve it backwards,
differentiate it, sweep it, trust it near the edge of the data — and this
experiment measures each family doing exactly those things.

---

## 3. Step 1 — Check the instrument runs

Double-click **`Run-Falsifier.bat`**. It runs the benchmark's *smoke check*:
a reduced grid (fewer cells, fewer test points) that exercises every family,
every metric, and every code path in **60–90 seconds**, prints its tables to
the console, and **writes nothing to disk** — the committed
`falsifier_results.txt` is never touched by the check. The same thing from a
terminal, run from inside this folder (the shared convention across both
TASK-9 example folders):

```
cd examples/TASK-9-falsifier-benchmark
py -3.12 falsifier_benchmark.py --smoke
```

If the window fills with cell tables and ends without a traceback, the
instrument works on your machine, and everything in the committed results
file was produced by code you have just run.

### 3.1 The full run — optional, and read the warning first

```
py -3.12 falsifier_benchmark.py
```

This regenerates the entire pinned grid — 51 cells, 9 families per cell,
seed 0 — and **overwrites `falsifier_results.txt` in this folder**. That
file is a verbatim record of a real dated run, and other documents quote it;
do not regenerate it casually, and if you do, expect version-control to show
the file as modified.

Two facts about the full run, both measured rather than estimated:

- **Wall time.** 10.5 min (627 s) for the original 37-cell grid on the
  Windows build host; the committed 51-cell file stamps **700.1 s
  (11.7 min)** on its own last line, on the Linux venue that produced it.
  Single-threaded on purpose (`OMP_NUM_THREADS=1` is pinned in-script) —
  measured faster than threaded at these small N, and reproducible on a
  loaded machine.
- **Determinism, stated honestly.** Everything is seeded (seed 0): designs,
  noise, test points, slices, gradient points, sweeps, rays. On one machine,
  re-running reproduces the file. Across *different* library versions the
  cell values drift at the last printed digit (measured when the run venue
  moved: 32 of 37 cells moved, median relative drift 1.4%, concentrated in
  the neural-network family) — while the headline verdict blocks `[V2]` and
  `[V3]` were **byte-identical across the two venues**. The file's first
  line always stamps the Python/numpy/scipy/sklearn versions and OS it ran
  on, so any number you re-derive can carry its venue with it.

---

## 4. Step 2 — Read the cell tables

Open **`falsifier_results.txt`**. The first ~800 lines are cell tables, one
block per *surface × design × N × noise* combination, one row per family.
The block you will get the most out of first is `sin-exp` (the smooth
nonlinear wave) at `N=200, noise=0` — a well-sampled, noise-free, smooth
problem, i.e. the friendliest possible conditions, which is what makes the
failures in it meaningful.

Every column operationalizes one axis the selection rules branch on. In
engineering terms:

- **`nrmse`** — *accuracy*: prediction error against the true function on
  2,000 in-range points, as a fraction of the response range. The axis
  everybody argues about, and — this experiment's recurring finding — the
  axis on which the families genuinely are close.
- **`bis`, `ns/wr`** — *can you solve it backwards?* Twenty fixed 1-D
  slices; on each, a standard root-finder (bisection-style, `brentq`) hunts
  the input that produces a target output, using the fitted model in place
  of the solver. Success = the found input lands within 2% of the axis
  range of the true one. `ns` counts slices where the model's curve never
  crossed the target at all (no sign change — nothing to bracket); `wr`
  counts roots found in the wrong place. This is the "what clearance keeps
  this part under 120 °C" question, asked of the surrogate.
- **`gcos`, `grel`** — *can you differentiate it?* The model's finite-
  difference gradient against the true analytic gradient at 100 interior
  points: direction agreement (cosine — 1.0 is perfect, 0 means the model's
  slopes point nowhere in particular) and relative magnitude error. This is
  the sensitivity-study axis.
- **`xnrmse`** — *what happens just outside the data?* Error on a shell of
  points 1.0–1.2× the training hull — mild extrapolation, the kind a design
  study commits daily. A separate probe table (further down the file) sends
  rays out to 2× the hull and classifies the *shape* of each family's
  far-field behavior: frozen flat, diverging, or flattening.
- **`rough`** — *can you sweep it and read a trend?* Mean second-difference
  along fine axis sweeps (×1e3): near zero for a curve you would show a
  reviewer, large for a staircase.
- **`sec`** — fit cost in seconds, *including* the model-selection pass
  (below) — the retrain-cost axis at these small N, not a deployment
  benchmark.
- **`fold-std`** — the yardstick the indifference tolerance IC-1 is defined
  in: the spread of a family's own cross-validation folds. "Two families
  are indifferent" is operationalized as "within one fold-std of the best."

The file's own `HOW TO READ THIS` block (just above the verdicts) says the
same things more tersely and adds the fine print — noise is added to
training data only, every family in a cell sees identical designs and test
points, and the step surface's true gradient is undefined so its gradient
column is `--`.

### 4.1 One row, read aloud

From `surface=sin-exp DOE=lhs d=2 N=200 noise=0`: the Gaussian-process row
reads `nrmse 0.000101, bis 20/20, gcos 1.000, rough 0.121`; the
random-forest row reads `nrmse 0.0202, bis 1/20 (0 ns / 19 wr), gcos 0.390,
rough 4.99`. Both models are usably *accurate* — about 0.01% versus 2%
error as a fraction of range. But on this smooth, noise-free, well-sampled
problem, the forest's fitted surface let the root-finder localize the
target on only **1 of 20 slices** (the other 19 all found a root in the
wrong place), its gradients point ~67° away from truth on average
(cosine 0.390), and its sweeps are ~40× rougher. Accuracy did not separate
these families; **what you can do with the fitted surface did.** That
asymmetry — stated as measurement, not opinion — is the taxonomy's whole
argument, and it is the sibling selector's opening line.

---

## 5. Step 3 — Read the verdicts

The last ~350 lines are the point of the file: twelve blocks, `[V1]` to
`[V12]`, each opening with the matrix cell, rule id, or indifference
tolerance it bears on, then the numbers, then a `Reading:` paragraph. Two
words carry defined meanings throughout: **settles** = this experiment
decided the cell (it had no published number before); **supports** = the
result is consistent with a claim the cited literature already carries.

What each block says, transcribed from the committed file:

- **`[V1 IC-1]`** — the *indifference tolerance* among the four smooth
  families (polynomial, spline, Gaussian process, RBF) on smooth
  noise-free problems. The strict form ("all four within one fold-std of
  the best") holds in **0 of 24** eligible cells, the core three-family
  form in **1 of 24** — but the best-to-worst accuracy gap is tiny
  (**median 0.0019, max 0.0681** of range). The reading: where the best
  family sits at machine precision the one-fold-std tolerance collapses to
  ~1e-16 and the binary check fails on practically-indifferent gaps, so
  the honest IC-1 statement is the **measured gap boundary**, not the
  binary. The experiment published a result *against* its own taxonomy's
  strict operationalization and refined the claim — that is the falsifier
  doing its job. (Supports the large-sample near-equivalence the
  literature reports: Q-surr-15, Q-surr-19.)
- **`[V2 R1-bisection]`** — *settles the magnitude* of rule R1's
  backwards-solving cell. Smooth-family success averages **85% → 94%**
  (N=50 → N=800) while the partition families (forest, boosted trees,
  nearest-neighbours) sit at **10% / 5% / 23%** at N=50, closing to
  **57% / 68% / 83%** at N=800. Failure anatomy at N=50 (60 slices):
  wrong-root dominates for the forest (54) and kNN (46); no-sign-change
  appears for boosted trees (15). Reading: the localization gap *closes*
  as plateaus narrow, so at high N the rule's load-bearing content is the
  **precondition** — a continuous function is what bisection's theorem
  asks for (Q-surr-46), and a staircase's plateau holds an interval of
  roots — plus the gradient and sweep rows, not a gross localization
  failure at every N.
- **`[V3 R1-gradients]`** — *settles* the gradient leg. On the smooth wave
  at N=200: direction agreement **0.999–1.000** for the spline / GP / RBF /
  SVR families versus **0.390 / 0.116 / 0.755** for forest / boosted trees
  / kNN (the quadratic reads 0.183 there — degree inadequacy on that wave,
  a different failure than partitioning); relative magnitude error
  **0.00119** (GP) versus **1.13** (forest).
  Finite differences on a piecewise-constant surface return zero inside a
  plateau and a spike across a split — both are counted (Q-surr-39).
- **`[V4 sweeps]`** — *settles* the sweep-smoothness cell. Roughness
  (×1e3) on the same cell: smooth families **0.007–0.13** versus
  **4.99 / 7.02 / 5.22** for the partition families — a **~40×**
  separation, with the neural network sitting smooth at 0.209.
- **`[V5 R4-extrapolation]`** — the shape of each family just outside the
  data, in four findings: **(a)** tree families are *exactly* frozen
  (0.0000 change) outside the hull along the axes, kNN nearly so
  (0.0285), while smooth families keep moving — on diagonal directions
  the trees only flatten (0.038–0.057), because splits on the other
  coordinate keep firing; the taxonomy's "constant outside the hull" cell
  is settled in its axis-aligned form and should name kNN alongside the
  trees. **(b)** The quadratic's curvature holds constant as you leave
  the data (1.14 → 1.14 — the divergence signature), while the network
  and the GP both flatten (~5 → ~2.8): at ≤2× hull, curvature alone
  cannot yet separate the network's asymptotic linearity (Q-surr-34) from
  the GP's flattening. **(c)** The GP's *mean* has **not** reverted to
  the training mean by 2× hull (0.580 — the largest among the smooth
  families): the textbook reversion is asymptotic, so at practical ranges
  the GP honesty story lives on the *variance* side, which a mean-only
  harness does not measure — a correction to folklore, recorded against
  the experiment's own preferred family. **(d)** At the mild 1.2× shell
  the GP still has the best magnitude: 0.0085 versus the quadratic's
  0.37 on the smooth wave.
- **`[V6 R9-noise]`** — *settles* the exact-interpolation noise penalty.
  Same design, 0 → 5% noise on the smooth wave at N=800: the exact RBF
  interpolant goes **0.0005 → 0.0498** (it reproduces the noise — the 5%
  floor is 0.05, and it lands on it; Q-surr-17), the GP-with-nugget goes
  to 0.0133, and the quadratic barely moves (0.1430 → 0.1429 —
  noise-insensitive because it is bias-limited). Same pattern on the
  kinked surface (0.0017 → 0.0474 vs 0.0028 → 0.0161).
- **`[V7 IC-2]`** — the boosted-trees-versus-network indifference claim on
  irregular noisy problems, graded **supports, does not settle**: the gap
  is **0.0147** on the kinked surface (inside the "few percent" reading of
  Q-surr-04) but **0.0905** on the step — whose jump boundary is oblique,
  exactly the shape axis-aligned partitions must staircase — and N=800
  sits below the claim's 1k–10k window, with one of its families (B10)
  not runnable in the pinned dependency set.
- **`[V8 DOE-lattice]`** — full-factorial grid versus space-filling design
  at matched N=196: largest accuracy delta anywhere in the 5×9 sweep is
  **+0.107** (the network on the step surface); **no family collapses on
  the grid** at these low polynomial orders (the equispaced pathology the
  literature pins to high-degree interpolation does not bite here,
  Q-surr-57), and the grid even *helps* the trees on the step (−0.031).
- **`[V9 d5-check]`** — five inputs instead of two, smooth surface: the
  GP-first ordering sharpens (N=800: GP **0.0004**, spline 0.0013, exact
  RBF **0.0254**, quadratic 0.1256) — the exact interpolant falls visibly
  behind the GP as dimension grows at fixed N, which is where IC-1's
  blanket interchangeability genuinely starts to break. Also visible: the
  GP's declared budget cap in action (fit seconds 0.3 → 2.5).
- **`[V10 design-structure]`** + **`[V10-A1]`** — does *how the runs were
  laid out* (grid versus space-filling) move the partition families as
  much as *how many* runs? On gradients, decisively yes for the forest:
  the structure leg (**−0.525**, taking its gradient cosine 0.647 →
  0.122 on the matched-N grid) *exceeds* its entire N leg (+0.492). On
  root-finding, the block's original pooled "N dominates" reading is
  **annotated as defective by `[V10-A1]`** — the pool hid a sign split
  (families and surfaces move in *both* directions, up to +0.217 /
  −0.150), so no pooled direction is claimed. The annotation sits *beside*
  the block, dated, with the original unedited — the file's convention
  for correcting itself without rewriting its history.
- **`[V11 d5-readout]`** — a read-out of cells the file had carried since
  Session B, answering the worked instance's open question: partition-
  family root-finding falls **0.483 → 0.150** from two inputs to five at
  matched N=800 (**−0.333**, with the instance's measured 0.075 *bracketed*
  by the two d=5 cells at 0.067 and 0.150), and **−0.241** of it survives
  on the one slice-axis both cells share — so **dimensionality is the
  dominant measured effect**, and it survives the block's own confound
  decomposition. One root-finding slice is worth 0.050; every leg is
  quoted against that resolution.
- **`[V12 d5-design]`** — the falsification verdict on the arc's standing
  hypothesis, with its pass/fail conditions fixed *before* the run: the
  worked instance's own anisotropic 6×5×4×3×2 grid layout scores **0.317**
  against its matched-N space-filling control's **0.050** — condition C2,
  **anisotropy points the other way**, refuted rather than merely
  insufficient. The control lands within one slice of the instance's
  0.075, so at matched N and dimension, plain dimensionality reproduces
  the instance's number and the design axis moves *away* from it. Left
  open, and said so: the surface itself and the instance's physical axis
  ranges, neither measured here.

The pattern worth noticing across all twelve: three of them (`[V1]`,
`[V5c]`, `[V12]`) record results *against* the taxonomy's or the arc's own
expectations, published rather than absorbed. An experiment that can only
confirm is not a falsifier.

---

## 6. Reading the results responsibly

This section is the one to read twice — these numbers are quotable, and the
envelope travels with them or the quote is wrong.

**1. Synthetic surfaces, closed world.** Every surface is an analytic
function chosen so truth is known exactly. That is what buys clean
measurement of the discriminating axes, and it is also the boundary: none
of these numbers is a benchmark of what any family achieves on real CAE
data. The point is *controlled separation* — which axes discriminate
between families and by how much — not absolute performance. (The
walkthrough discipline of `EXAMPLES-ARC-SCOPING.md` §6.1 applies: every
figure here is illustrative of the mechanism, not predictive of your data.)

**2. The declared envelope.** Dimensions **d ≤ 5**; sample sizes
**N ≤ 1,024** (the bound moved from 800 when the k=4 lattice cell landed —
the file's own history section records it); **one seeded realization**
(seed 0, no seed sweep); noise at 0 and 5% only, and **the lattice-design
leg is noise-free only** — nothing here says whether the design-structure
effect survives noise, a named gap rather than an oversight. Quote a number
outside this envelope and you are extrapolating the falsifier itself.

**3. Two families are absent, and one is approximated.** Symbolic
regression (B9) and the prior-fitted transformer (B10) are outside the
pinned numpy/scipy/scikit-learn dependency set, so their rows do not exist
here — their matrix cells rest on the cited literature alone. MARS has no
maintained library in the pinned set; the spline family stands in as its
nearest relative. The IC-2 check therefore runs over two families instead
of three, and is graded *supports*, never *settles*.

**4. Venue-dependence, stated precisely.** The committed file was produced
on Linux / Python 3.11.15 / numpy 2.4.4 / scipy 1.17.1 / sklearn 1.8.0
(the header line stamps this). An unmodified re-run on a different
toolchain moved 32 of 37 original cells at a median 1.4% relative drift —
concentrated in the neural-network family (124 of 218 moved values) —
while the band-bearing verdict blocks `[V2]` and `[V3]` were byte-identical
and no moved root-finding count feeds a published band. The narrow caution:
**attach the venue to anything you re-derive from the cell tables,
especially anything involving the network family**; the published verdict
bands themselves reproduced exactly.

**5. The tuning budget is matched and declared, not optimal.** Every family
gets **at most 3 configurations**, picked by 5-fold cross-validation on the
training data only, then refit. This is a fairness device — no family gets
a tuning advantage — and a floor, not a ceiling: a tuned-to-death entry of
any family would score differently. The declared runtime reductions (all
recorded in the README and the file header, none silent): the GP trains on
a seeded 400-point subsample when N > 400; forest capped at 80 trees;
boosted trees at 2 configs / 64 bins; network at 150 optimizer iterations;
root-finder tolerance 2e-4 (still 100× below the success threshold);
single-threaded execution.

**6. Root localization is not exact inversion.** The bisection metric
measures whether a standard root-finder *localizes* a target through the
fitted surface under a fair bracket protocol. The deeper statement — that
exact inversion on a plateau is ill-posed because a plateau is an
*interval* of roots — remains the definitional argument (Q-surr-46,
Q-surr-38), which `[V2]`'s reading defers to at high N. The measurement
quantifies the practical failure; it does not replace the theorem.

---

## 7. What's happening inside (optional, one page)

*Strictly optional. Skip it if you just wanted the verdicts.*

One full run is a triple loop: for each of **51 cells** (surface × design ×
N × noise), for each of **9 families**, fit under the declared budget, then
score every metric against the analytic truth.

**The surfaces** are chosen as minimal representatives of response
behaviors an engineer recognizes: exactly-linear (`3·x0 − 2·x1 + 1`),
low-order curved (quadratic + interaction), smooth-but-genuinely-nonlinear
(`sin(2πx0)·exp(x1)`), kinked (absolute values — contact engaging, regime
change), discontinuous (a hard step across an oblique boundary), and the
five-input `smooth5`, which is *the smooth wave plus two gentle terms* —
deliberately its own strict extension, so the d=2 → d=5 comparison in
`[V11]` is one function against itself, not two unrelated problems.

**The designs** cross two structures at the same sizes — space-filling
(Latin hypercube) and full-factorial lattice at matched N (49↔50, 196↔200,
784↔800), so design *structure* is never confounded with sample *size* —
plus, at d=5, the worked instance's own anisotropic 6×5×4×3×2 layout,
its isotropic cousins, and a matched-N space-filling control (`[V12]`).

**The families** are the taxonomy's buckets B1–B8 (with the tree bucket
split into random forest and gradient boosting, its two live sub-families):
quadratic polynomial, penalized splines, Gaussian process, exact
thin-plate RBF, support-vector regression, forest, boosted trees, a 2×64
neural network, and 5-nearest-neighbours. The exact interpolant is kept
*exact* on purpose — that is its bucket's estimation principle, and the
noise verdict `[V6]` needs it.

**The referee protocol**: every family in a cell sees the identical design,
identical noise draw, identical test points, slices, gradient points,
sweeps and rays (all seeded); each gets its ≤3-config CV pick; every score
is against the true function. The how-to-read block in the results file is
the same referee explaining the columns.

**Why you can trust the file you did not generate**: the committed
`falsifier_results.txt` opens by stamping its venue and grid
(`seed=0 | python 3.11.15 | ... | cells=51`) and closes with its wall
clock (`total wall: 700.1 s`). The smoke check you ran in Step 1 exercises
the same code paths at reduced size. And the file's history — three dated
extensions (`TASK-9-C1`, `-C2`, `-E`) — is recorded in the README beside
it, including the two defects a later session found in `[V10]` and
annotated *beside* the block rather than editing it. The record accretes;
it is never rewritten.

---

## 8. Where to go next

- **The tool these rules power.**
  `examples/TASK-9-surrogate-selector/WALKTHROUGH.md` — answer fifteen
  questions about your problem, get a cited verdict sheet. Its rule trace
  is where these magnitudes get used on a real decision.
- **The taxonomy itself.**
  `TASK-9-TAXONOMY-scalar-surrogate-selection.md` at the repository root —
  §4 is the decision procedure, Appendix B is the `[OPEN]`-cell log this
  experiment feeds, §9 is the honest-boundaries section that carries this
  folder's envelope into the document's own claims.
- **The instrument turned on one real case.**
  `examples/TASK-9-HT-worked-instance/` — the same exclusion argument run
  on a 720-row thermal DOE: accuracy ties, the inverse does not (quadratic
  40/40, forest 3/40). Its two out-of-band cross-checks are what `[V11]`
  and `[V12]` chased down: dimensionality explains its root-finding
  number; its grid layout does not.
- **The room version.**
  `presentations/Presentation-TASK-9-Surrogate-Selection.pptx` (13 slides)
  and the one-page decision map
  `presentations/Presentation-TASK-9-Decision-Tree-1pager.pdf`.
- **The contributor door.** `README.md` in this folder — the grid, budget,
  and change history in full detail, including the measured venue-drift
  study and every declared reduction.

---

## One-time setup

The standalone `.exe` form of the arc's tools is queued behind the packaging
sub-task (`TASK-8-PKG`) and is not built yet. In the meantime this is the
arc's interim click-to-run form: a `.bat` file you double-click, which needs
Python installed once.

1. Install Python 3.12 for Windows from python.org. Tick **"Add python.exe
   to PATH"** in the installer.
2. Open Command Prompt and run:

   ```
   pip install numpy scipy scikit-learn
   ```

   These three are the only dependencies — one more (scipy) than the
   sibling selector needs, because the root-finder and the space-filling
   designs live there.
3. Double-click `Run-Falsifier.bat`.

If the batch file reports that Python was not found, step 1's PATH tick box
was missed; re-run the installer and choose *Modify*.

---

*Artifact A of the `EXAMPLES-ARC-SCOPING.md` §5 set, on the §6 eight-section
contract, adapted for an evidence-lane instrument under the 2026-08-15
binding-by-neighbourhood ruling (`AUDIT-TASK-9-deliverable-conformance.md`;
sibling template `examples/TASK-9-surrogate-selector/WALKTHROUGH.md`,
SESSION-9B §4.1). Authored 2026-09-03. Every number in this document is
transcribed from `falsifier_results.txt` (seed 0, committed) or `README.md`
in this folder; quote ids cited are VERIFIED entries in `QUOTES.md`; no new
measurements and no new quotations were introduced by this document.*
