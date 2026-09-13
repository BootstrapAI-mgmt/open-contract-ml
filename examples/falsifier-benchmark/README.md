# TASK-9 falsifier benchmark — Session B

The small CPU experiment behind the TASK-9 scalar-surrogate selection
taxonomy (task card `tasks/TASK-9-scalar-surrogate-selection-taxonomy.md`
§5 Session B; shepherd spec §7 is the binding contract). It measures, on
five synthetic response surfaces with known analytic truth, the axes the
taxonomy's decision rules claim discriminate between surrogate families —
so the matrix cells the literature leaves `[OPEN]` get numbers, and the
indifference-class tolerances (IC-1, IC-2) get an empirical check instead
of an adjective.

Style anchor: `substructuring_experiment.py` (seeded, minutes, printed
table with a how-to-read block). `falsifier_results.txt` in this directory
is the verbatim output of a real run of this script (seed=0).

> **Reader?** Start with **`WALKTHROUGH.md`** in this folder, not here. It is
> written for a CAE engineer with no ML background and takes you from "what
> is a falsifier?" to reading the verdicts responsibly. This README is the
> contributor-facing document.

> **Sibling folder.** `examples/TASK-9-surrogate-selector/` holds the
> decision procedure this benchmark tests, and — since SESSION-9B-2 — a
> reader-facing front door (`Select-Surrogate.bat` / `select_surrogate.py`)
> and `WALKTHROUGH.md`. The division of labour: the selector *applies* the
> rules and cites them; this benchmark *measures* the axes the rules claim
> discriminate. Numbers from here are only quotable with the envelope stated
> under **Caveats** below (synthetic surfaces, d ≤ 5, N ≤ 1024, seed 0).

## What TASK-9-E changed (2026-08-21)

Recorded here for the same reason the C1 section below exists: this folder's
`falsifier_results.txt` has been regenerated again and no longer matches the
C1 file.

**1. A read-out, costing no new runtime.** The `d = 5` cells have been in this
file since Session B, and nothing had ever reported their *bisection* rows —
`[V9 d5-check]` prints NRMSE for B1-B4 only, and is silent on both bisection
and the partition families, which is exactly where the H-T worked instance's
open disagreement sat. Reading them out is verdict block **[V11 d5-readout]**,
and it moves most of that gap: `smooth5` is `sin-exp` *plus two smooth
low-order terms*, so d = 2 → d = 5 is a function against its own strict
extension, and across it the partition families fall **0.483 → 0.150** at
matched N = 800 (0.067 at N = 200). `[V11]` also decomposes that leg by the
axis each slice runs along, because the two cells turn out not to share a
slice set at all — `make_slices` admits no slice on an axis whose endpoints
agree, so `sin-exp` is scored entirely on its `exp(x1)` axis. On the one axis
both cells do share, the leg is still **−0.241**.

**2. Two defects in `[V10]`, annotated rather than edited.** `[V10]` prints
`mean |dSTRUCT|` over a number its emitter computes as
`abs(mean(lattice) − mean(lhs))` — the absolute value of a mean, not the mean
of absolute values (0.017 against a mean magnitude of 0.106) — and its
sign-split guard runs on gradient cosine only. Asked of bisection, that guard
fires twice: by family, and by surface (quad-int **+0.217**, sin-exp
**−0.150**). Both are recorded in **[V10-A1]**, a dated annotation beside
`[V10]`; `[V10]` itself is unedited, per the conformance audit's convention.
A `b_split` guard now runs in `[V11]` and `[V12]`.

**3. The design axis crossed with dimensionality, and anisotropy made
expressible.** Every lattice cell in this file was `d = 2` before this run,
and `make_design` built one level count for every axis, so the H-T instance's
**6x5x4x3x2 = 720** could not be written down. A `lat-aniso` DOE mode carries
an explicit level tuple; the isotropic branch is byte-unchanged and every
`d > 2` lattice cell now prints its level pattern in the cell header. Four new
cells and verdict block **[V12 d5-design]**. The result refutes the arc's
standing hypothesis: the anisotropic lattice scores **0.317** against its
matched-N space-filling control's **0.050** — anisotropy moves bisection
*away* from the instance's 0.075, not toward it. The control itself lands
within one slice of that number.

*Two consequences worth stating plainly.* The N envelope moved: the k = 4
isotropic lattice is **N = 1024**, so the declared bound is now `N ≤ 1024`,
not `N ≤ 800`. And `ic1_cells` selects on surface and noise — never on design,
never on dimension — so all four new cells entered the IC-1 check and moved
`[V1]`'s denominators from 20 to 24 cells, exactly as C1's lattice cells moved
them from 14 to 20. Predicted before the run, reported after; no IC-1
definition changed.

## What TASK-9-C1 changed (2026-08-17)

Two things, both recorded here because `falsifier_results.txt` in this folder
has been regenerated and no longer matches the Session-B file byte-for-byte.

**1. The design-structure axis got an N leg.** The lattice design *structure*
was present from Session B, but at exactly one point: a single 14x14 = 196
full-factorial cell compared against LHS-200. One point has no N leg, so it
could not answer the question the H-T worked instance
(`examples/TASK-9-HT-worked-instance/`) raised at SESSION-9B-3 — whether
**design structure at fixed N** moves the partition families' inverse and
gradient metrics by more than **N at fixed design structure** does. That
instance is a 6-level full factorial; it reproduced taxonomy §8's *direction*
on every axis and missed §8's *magnitude* bands on 6 of 7 cross-checks, and
the hypothesis on the table was that the unmodelled variable is design
structure.

C1 therefore runs the lattice structure across the same N grid the
space-filling designs already use — 50 → 49 (7x7), 200 → 196 (14x14),
800 → 784 (28x28), each requested N adjusted down to the nearest achievable
lattice size with the adjustment printed at run time rather than inferred.
`make_design` is **unchanged**: `k = round(N**(1/d))` was already the rule it
implemented. No family, no metric, no metric definition and no tolerance
changed. The new readings are the two `DESIGN STRUCTURE vs N` tables and
verdict block **[V10]**. **[V8]** is left exactly as it was, still reporting
the original single-point cell against LHS-200.

**2. The run venue moved, and it is not neutral.** The Session-B file was
produced on **Windows / Python 3.12.3 / numpy 2.2.6 / scipy 1.15.3 /
sklearn 1.6.1**. The regenerated file was produced on **Linux / Python
3.11.15 / numpy 2.4.4 / scipy 1.17.1 / sklearn 1.8.0**, because the Windows
host has no scikit-learn installed. This was *measured*, not assumed: an
unmodified re-run in the new venue reproduces 5 of the 37 Session-B cells
exactly and differs in 32, with a median relative drift of **1.4%** across
the 218 of 1,665 printed values that move. Nearly all of that is last-ulp
noise on quantities already at 1e-16. What is **not** cosmetic: **6 bisection
counts and 1 CV config pick differ**, and the drift is concentrated rather
than diffuse — **B7 (MLP) accounts for 124 of the 218 moved values**, while
**B2, B6b and B8 are byte-identical throughout**.

*Narrowed at TASK-9-C2.* This block originally concluded that "bands quoted
from this experiment to two significant figures are not venue-stable".
Re-deriving the same diff from `d6f3103` shows that is broader than the
measurement supports. **Verdict blocks `[V2]` and `[V3]` — the blocks the
taxonomy's bands are read from — are byte-identical across the two venues.**
`[V4]` moves only in the third significant figure (B6a 4.98 → 4.99,
B7 0.205 → 0.209), which does not touch the ~40x separation. And not one of
the six moved bisection counts is a cell that feeds a quoted band: four are
B7, the other two are B6a at 5% noise and at d=5. The true caution is
narrower and sharper — **attach the venue to anything you re-derive from this
file, especially anything involving B7** — while the bands themselves
reproduced exactly. Design structure remains the independent qualifier, and
it is the one that actually moves a band (item 8b).

**Numbers elsewhere in this README — swept at TASK-9-C2.** Item 1 of the
headline list (the IC-1 strict-form cell count) was corrected at C1 as a
direct readout of a count that grew when the lattice cells were added. The
falsifier *band* quotes were deliberately left alone at C1 so SESSION-9C-2's
`grep` completeness check stayed meaningful; **C2 has now swept them**, along
with every other number this regeneration made stale — the `[V4]`/`[V5]`/
`[V7]` readouts that moved with the venue, and the IC-1 d=2 small-N gap bound
(<= 0.016 -> <= 0.018, broken by the new quad-int lattice cell at N=49).
Every band quote below now carries its design class.

## Run it

Run from *inside this folder* — the shared convention across both TASK-9
example folders (`examples/TASK-9-surrogate-selector/` uses the same form;
unified at SESSION-9B-2, audit minor row 14):

```
cd examples/TASK-9-falsifier-benchmark
py -3.12 falsifier_benchmark.py            # full pinned grid, writes falsifier_results.txt
py -3.12 falsifier_benchmark.py --smoke    # ~90 s wiring check (writes nothing)
```

Dependencies: numpy + scipy + sklearn only (no matplotlib, no networkx).
Originally verified on Python 3.12.3 / numpy 2.2.6 / scipy 1.15.3 /
sklearn 1.6.1 (Windows). The committed `falsifier_results.txt` has since
been regenerated on Python 3.11.15 / numpy 2.4.4 / scipy 1.17.1 /
sklearn 1.8.0 (Linux) — see **What TASK-9-C1 changed** above for the
measured drift between the two venues, and the header line of
`falsifier_results.txt` itself, which always stamps the venue it ran on.
Measured full-run wall time: **10.5 min** (627 s) for the 37-cell Session-B
grid on the Windows build host, and **8.1 min** (484.7 s) for the 47-cell C1
grid on the Linux venue; the C1 grid adds 10 lattice cells. Single-threaded either
way — `OMP_NUM_THREADS=1` is pinned in-script — on a loaded shared machine;
the ~5-min spec target was not reachable at the pinned grid even after the
declared reductions below, and nothing was dropped.
Everything is seeded (seed=0): designs, noise, test points, slices,
gradient points, sweeps, rays.

## The grid

- **Surfaces** (domain `[0,1]^d`, analytic gradients where they exist):
  `linear`, `quad-int` (quadratic + interaction), `sin-exp` (smooth
  nonlinear, `sin(2*pi*x0)*exp(x1)`), `kinked` (`|x0-.45| + .5|x1-.6|`),
  `step` (`1[x0+x1>1]`) at d=2; `smooth5` (sin-exp + quadratic + product
  terms) as the d=5 smooth check.
- **Designs**: two design *structures*, crossed with the same N grid at d=2.
  **Space-filling** — N in {50, 200, 800} Latin hypercube (`scipy.stats.qmc`,
  seeded). **Lattice** — full-factorial, k = `round(N**(1/d))` levels per
  axis, so the requested N is adjusted down to the nearest achievable size:
  50 → 49 (7x7), 200 → 196 (14x14), 800 → 784 (28x28). Noise 0 on the
  lattice leg only, matching the convention of the axis's original cell.
  Each lattice cell is keyed by the N it actually has, never by the N that
  was requested, and the adjustment is printed at run time. *(Extended from
  a single 196-point cell to the full N grid at TASK-9-C1; see above.)*
- **Noise**: {0, 5% of the surface's reference range}, added to TRAIN y
  only; every metric is scored against the true function.
- **Families**: B1 poly-2 · B2 spline (SplineTransformer+Ridge) · B3 GP
  (Matern 5/2 ARD, nugget when noisy) · B4 RBF (scipy `RBFInterpolator`,
  thin-plate, smoothing=0 — the exact interpolant, kept exact on purpose:
  that is the bucket's estimation principle and the R9 cell needs it) ·
  B5 SVR-RBF · B6a RF · B6b HistGradientBoosting · B7 MLP 2x64 · B8 kNN-5.
  **MARS is omitted — no maintained library exists inside the pinned
  numpy/scipy/sklearn dependency set.** B9 (symbolic regression) and B10
  (TabPFN) are likewise outside the pinned set; the IC-2 check therefore
  runs over {B6b, B7} only (see caveats).

## Declared matched tuning budget

At most 3 configurations per family, chosen by 5-fold CV on the training
set only (`KFold(5, shuffle=True, random_state=0)`, MSE score). The winner
is refit on the full train set. The per-family fold-std of NRMSE (the IC-1
tolerance unit) is computed for every family from the selected config's CV
folds.

| Family | Configs (CV picks one) |
|---|---|
| B1 poly2 | `PolynomialFeatures(2) + LinearRegression` (1 config) |
| B2 spline | additive k10 alpha 1e-4 / pairwise tensor-product k6 alpha 1e-4 / tensor k6 alpha 1e-2 (structure AND stiffness on the CV axis, mirroring how smoothing splines pick their penalty) |
| B3 GP | Matern 5/2 ARD (+WhiteKernel nugget iff noisy); hyperparameters by MLE — the family's native selection; fold-std at the fixed MLE kernel (1 config) |
| B4 RBF | thin-plate, smoothing=0 (1 config; a smoothing-RBF escape exists but its estimation principle is ridge-like, i.e. B5's) |
| B5 SVR | C in {1, 10, 100}, eps {.05, .05, .01} in standardized-y units, gamma='scale' |
| B6a RF | 80 trees, min_samples_leaf in {1, 3} |
| B6b HGB | max_bins=64, (lr .1, 200 iter) / (lr .05, 250 iter) |
| B7 MLP | (64,64), lbfgs 150 iter, alpha in {1e-4, 1e-2}, standardized X and y |
| B8 kNN | k=5, weights in {uniform, distance} |

**Declared runtime-budget reductions** (spec §7: "subsample or declare the
reduction ... rather than silently dropping"; measured full grid would
otherwise run ~20+ min on the build host):

- **B3 GP trains on a seeded 400-point subsample of the same design when
  N > 400** (config label `mle-sub400`) — the spec's named GP-at-N=800
  risk, remediated exactly as the escape clause directs. MLE restarts 1→0.
- RF 80 trees; HGB 2 configs, 64 bins; MLP lbfgs capped at 150 iterations;
  `brentq` xtol 2e-4 (still 100x below the 2%-of-range success threshold);
  `OMP_NUM_THREADS=1` (measured faster than threaded at these N — per-fit
  thread-spawn overhead dominates — and reproducible on a loaded host).

## What each measured axis operationalizes

| Column | Taxonomy axis / rule it operationalizes |
|---|---|
| `nrmse` | The accuracy axis (A x B): RMSE vs the TRUE function on 2000 in-hull points / range. Under 5% train noise an exact interpolant floors near 0.05; a regularized family can go below it. |
| `bis`, `ns/wr` | C-axis "continuous inverse / root-finding" (rule R1). 20 fixed random 1-D slices; y_target = midpoint of the slice's endpoint values (guarantees a bracketed true root); `brentq` on (surrogate − y_target) in the grid bracket nearest the true root; success = within 2% of range. Failures split: `ns` = surrogate never changes sign on the slice, `wr` = root found but > 2% off. (Machine-precision guard: when the 513-point batch predict sees a sign change that the scalar path loses to last-ulp float dust, the bracket midpoint — within 1/1024 — is scored instead; a far-off bracket still fails the 2% test.) |
| `gcos`, `grel` | C-axis "analytic gradients / sensitivities" (R1). Central differences (h=1e-3) vs the analytic gradient at 100 interior points: mean cosine similarity + mean relative L2. Partition surrogates give 0-or-spike finite differences; both are counted. |
| `xnrmse` | C-axis "extrapolation behavior" magnitude (R4): NRMSE on a 400-point shell between the hull and the 1.2x-scaled hull. |
| probe table (`dEdgeAx`, `dEdgeDg`, `curvN`, `curvF`, `farVsMu`) | R4's SHAPE leg on 4 axis-aligned + 24 random rays out to 2x hull: hull-constancy in its clean axis-aligned form vs generic directions (B6/B8), near-vs-far curvature bands (constant = polynomial divergence, decaying = flattening, persistent = plateau kinks), and distance from the train mean at 2x hull (mean-reversion check for B3). |
| `rough` | C-axis "smoothness of sweeps" (R1): mean second difference along axis sweeps / range x 1e3. |
| `sec` | Retrain-cost axis at these tiny N (fit incl. CV + fold-std + interp predict; not a deployment benchmark). |
| fold-std | The IC-1 tolerance unit: std of the chosen config's 5 CV-fold NRMSEs. |

## What the results say (headline numbers from `falsifier_results.txt`)

1. **IC-1 tolerance** ({B1,B2,B3,B4} interchangeable on smooth
   deterministic DOEs, within 1 CV-fold std of the best): the strict form
   holds in **0/24** smooth noise-free cells, and the {B2,B3,B4} core form
   in **1/24** — but the best→worst NRMSE gap is **median 0.0019,
   max 0.0681** (the max is B4 on the d=5 surface; every d=2 gap is
   ≤ 0.018 at the small-N end (N=50/49) and ≤ 0.0009 at the top (N=800/784)). Where the best family sits at
   machine precision (linear/quad-int for B1/B4) the 1-fold-std tolerance
   collapses to ~1e-16 and the strict criterion fails on gaps of 1e-4 —
   so the honest IC-1 statement is the measured gap boundary
   (sub-0.1%-NRMSE practical indifference at d=2, real B4/B1 gaps at
   d=5), NOT the binary the strict operationalization yields.
   *(Was 0/14 and 0/14 in the Session-B file. `ic1_cells` selects on
   surface and noise, never on design, so TASK-9-C1's six added smooth
   lattice cells entered this check. One of them — `sin-exp/lattice/N=49`
   — is the only cell in the whole experiment where the core form holds,
   and it holds the weak way: the 7x7 lattice's CV-fold std is **0.0241**
   against a best→worst gap of **0.0102**, so the tolerance is loose at
   small N rather than the families being closer. That is the same
   criticism item 1 already makes of the strict form, appearing now from
   the other end of the scale. The IC-1 definition did not change; the
   cell set grew. Flagged in `[V10]` and queued for SESSION-9C-2. The set
   grew again at TASK-9-E2, 20 → 24, when four d = 5 design cells landed;
   the median gap moved 0.0010 → 0.0019 for the same reason and the max
   did not move.)*
   Anchors:
   Q-surr-15 — "When large sample sizes are used (assuming designers have
   enough computational resource), MARS, RBF, and KG perform equally well
   in both average accuracy and robustness." (Jin2001) — and Q-surr-19
   (WangShan2007's no-conclusion sentence).
2. **Bisection-inverse (R1)** — *space-filling designs*: on smooth
   noise-free cells the smooth families average **85% → 94%** success
   (N=50 → N=800; the min, 67-68%, is degree-inadequate B1 on sin-exp —
   adequacy failure, not a family trait) while B6a/B6b/B8 sit at
   **10% / 5% / 23%** at N=50, closing to **57% / 68% / 83%** at N=800.
   *Design structure does not move this axis:* on the matched-N 28x28
   lattice the same three sit at a mean of **0.711**, inside the band
   (item 8b). So R1's load-bearing content at high N
   is the bisection PRECONDITION (Q-surr-46: "An equation f(x) = 0, where
   f(x) is a real continuous function, has at least one root between x_l
   and x_u if f(x_l) f(x_u) < 0 (See Figure 1)." — Kaw2012, the legal
   stand-in anchor for Burden §2.1) plus the gradient/sweep rows, not a
   gross localization failure. Failure anatomy at N=50 (60 slices):
   wrong-root dominates (B6a 54, B8 46), no-sign-change appears for B6b
   (15).
3. **Gradient fidelity (R1)** — *space-filling designs; this is the axis
   design structure DOES move (item 8b)*: sin-exp N=200 — gcos
   **0.999–1.000** for B2/B3/B4/B5 vs **0.390 / 0.116 / 0.755** for
   B6a/B6b/B8; grel
   **0.0012** (B3) vs **1.13** (B6a). Finite-difference gradients on
   partition surrogates are 0-or-spike (Q-surr-39).
4. **Sweep roughness (R1)** — *space-filling designs; not crossed with the
   C1 design axis*: sin-exp N=200 — smooth families **0.007–0.13** (x1e3
   units) vs **4.99 / 7.02 / 5.22** for B6a/B6b/B8 (a ~40x separation;
   B7 sits smooth at 0.21).
5. **Extrapolation shape (R4)** — three findings, one of them a
   correction to the folklore reading:
   - Hull-constancy is EXACT on axis-aligned extension for the trees:
     B6a and B6b read dEdgeAx = **0.0000**; B8 with CV-picked distance
     weights reads **0.0285** (near-constant — the neighbor set freezes
     but the distance weights keep renormalizing; uniform-weight kNN
     would freeze exactly). Smooth families move: B3 0.320, B4 0.212,
     B1 0.127. On random (diagonal) rays the same partition models read
     **0.057 / 0.045 / 0.038** — flattening but NOT yet constant at
     <=2x hull, because splits on the other coordinate keep firing. The
     R4 "constant outside the hull" cell is settled in its axis-aligned
     form, and it should name B8 alongside B6.
   - Curvature bands (near s 1.1–1.4 vs far s 1.6–1.9): B1 is constant
     (**1.14 → 1.14** — the fitted quadratic's divergence signature);
     B7 and B3 both DECAY (**5.11 → 2.72**; **4.97 → 2.83**) — at this
     range curvature alone cannot yet separate B7's asymptotic
     linearity (Q-surr-34: "First, we quantify the observation that ReLU
     MLPs quickly converge to linear functions along any direction from
     the origin, which implies that ReLU MLPs do not extrapolate most
     nonlinear functions." — Xu2021) from B3's flattening; B6a stays
     kinky (**8.66 → 5.51**).
   - The MLE'd Matern MEAN has NOT reverted to the train mean by 2x hull
     (farVsMu B3 = **0.580**, the LARGEST of the smooth families, vs
     B4 0.272, B7 0.354, B1 0.427): mean-side reversion (Q-surr-31,
     "for large |t|") is asymptotic in lengthscale units, not operative
     at 1.2–2x hull — at this range the R4 honesty story lives on the
     VARIANCE side (Q-surr-26), which a mean-only harness does not
     measure. The taxonomy's R4 cell should say exactly that. (At the
     pinned 1.2x shell B3 still has the best MAGNITUDE: xnrmse 0.0085
     vs B1 0.37, B4 0.044, B7 0.040 on sin-exp N=200.)
6. **Noise / R9**: on the identical N=800 design, 0 → 5% noise moves the
   exact interpolant B4 from **0.0005 to 0.0498** NRMSE (it interpolates
   the noise; the 5%-sigma floor is 0.05) while nugget-B3 goes
   **2.8e-5 → 0.0133** and B1 stays bias-floored (**0.1430 → 0.1429** —
   noise-insensitive, adequacy-limited). Same pattern on kinked: B4
   0.0017 → 0.0474 vs B3 0.0028 → 0.0161. Anchors Q-surr-17 ("KG is very
   sensitive to the noise because it interpolates the sample data") and
   Q-surr-22.
7. **IC-2 (approximate)**: at N=800 + 5% noise — B6b vs B7 NRMSE gap
   **0.0147 on kinked (within the 0.03 "few percent" reading)** but
   **0.0905 on step (outside it)** — and B6a reads 0.1372 next to B6b's
   0.1411, so the step gap is a tree-family result, not an HGB artifact:
   the step boundary here is OBLIQUE (x0+x1=1), which axis-aligned
   partitions must staircase while the MLP (0.0506) fits it directly.
   Read against Q-surr-04 (McElfresh2023): **supports-with-a-caveat,
   does not settle** — N=800 sits below IC-2's 1k–10k window, B10 is not
   runnable here, and one oblique-boundary surface is exactly the shape
   tabular benchmarks under-represent.
8. **DOE geometry (B-axis), accuracy leg**: 14x14 lattice vs LHS-200 at
   matched N — largest |delta NRMSE| across 5 surfaces x 9 families is
   **+0.107 (B7 on step)**; the lattice even helps the axis-aligned
   partition families on the step surface (B6a delta **-0.031**). No
   family collapses on the lattice at these low orders, consistent with
   Q-surr-57 pinning the equispaced pathology to HIGH-degree
   interpolation (poly-2 least squares escapes it). *(This is `[V8]`,
   unchanged by C1 — the extended axis was scoped so it stays exactly as
   Session B measured it.)*
8b. **DOE geometry crossed with N (`[V10]`, added TASK-9-C1)**: with the
   lattice now run at 49 / 196 / 784 against LHS-50 / 200 / 800, the two
   legs — **dN** (N at fixed structure) and **dSTRUCT** (structure at
   fixed N) — can finally be compared, and **they answer differently.**
   - *Bisection success*, partition families (B6a/B6b/B8) over the smooth
     d=2 surfaces: **dN +0.567, dSTRUCT +0.017**. N dominates by a factor
     of thirty. A matched-N lattice does **not** reproduce the H-T
     instance's 0.075 — the lattice partition families sit at **0.711**,
     inside the band §8 quotes.
   - *Gradient cosine*, same families: the 3-family mean is **dN +0.199,
     dSTRUCT −0.131** — but **the mean cancels a sign split and
     understates both sides.** The two tree families move *down* on the
     lattice and the neighbour family moves *up*:

     | family | LHS-50 | LHS-800 | LAT-784 | dN | dSTRUCT |
     |---|---|---|---|---|---|
     | B6a RF | 0.155 | 0.647 | **0.122** | +0.492 | **−0.525** |
     | B6b HGB | 0.014 | 0.136 | 0.077 | +0.122 | −0.059 |
     | B8 kNN-5 | 0.749 | 0.732 | 0.924 | −0.017 | **+0.192** |

     **On B6a RF alone the structure leg exceeds the whole N grid's leg
     (0.525 vs 0.492)**, taking the forest's gradient cosine
     **0.647 → 0.122** — the direction of the instance's measured
     **0.000**, and past the low end of the quoted 0.116–0.755 band.

   So the design-structure hypothesis SESSION-9B-3 raised **bears on the
   gradient miss — decisively for the tree family that produced it — and
   does not explain the bisection miss at all.** One of the two headline
   disagreements, accounted for, and only for part of the family set.
   What remains unmodelled, and differs between this experiment and that
   instance: dimensionality (2 here, 5 there) and level **anisotropy**
   (k-per-axis here, 6x5x4x3x2 there). A lattice is not one thing, and
   neither is "the partition families". Reported, not resolved.
9. **d=5 smooth check**: the kriging-first ordering sharpens at d=5
   (N=800: B3 **0.0004**, B2 0.0013, B4 **0.0254**, B1 0.1256) — the
   exact thin-plate interpolant falls visibly behind the MLE'd GP as d
   grows at fixed N, which is where IC-1's blanket {B2,B3,B4}
   interchangeability genuinely starts to break (max gap 0.068 at
   N=200).

10. **d=5 bisection, and the design axis at d=5** (`[V11]`, `[V12]`, added
   TASK-9-E): the partition families' bisection success falls
   **0.483 → 0.150** from `sin-exp` at d=2, N=800 to its own strict
   extension `smooth5` at d=5, N=800 (**0.067** at N=200) — and **−0.241**
   of that survives when the leg is restricted to the one axis both cells
   admit slices on. At d=5 the design axis then splits three ways at
   matched N=720: a **6x5x4x3x2** anisotropic lattice scores **0.317**, an
   isotropic 3x3x3x3x3 (N=243) scores **0.000**, and the space-filling
   control scores **0.050**. Anisotropy is not a small effect in the
   expected direction — it is a large one in the opposite direction.
   One bisection slice is 0.05; every leg here is quoted against that.

## Which matrix cells / IC tolerances this speaks to

- **Settles (numbers where the ledgers had none)**: the R1 cells' measured
  magnitudes (bisection success/failure anatomy, gradient cosine collapse,
  sweep roughness) for B6a/B6b/B8 vs B1–B5; the R4 shape leg — exact
  axis-aligned hull-constancy for B6 (and near-constancy for
  distance-weighted B8), B1's constant-curvature divergence, and the
  honesty refinement that B7's asymptotic linearity and B3's mean-side
  reversion are NOT yet separable/operative at ≤2x hull (the R4 cell
  should carry the variance-side citation for honesty at practical
  ranges); the R9 exact-interpolation noise penalty for B4 with the
  paired-design delta; the IC-1 tolerance boundary as measured gaps; the
  matched-N lattice-vs-LHS deltas.
- **Supports (literature already carries the claim)**: IC-1's
  large-sample near-equivalence (Q-surr-15, Q-surr-19); IC-2's
  B6b-vs-B7 gap (Q-surr-04) — approximate here, below the class's N
  window and without B10; the GP O(n^3) cost ceiling (Q-surr-27) — this
  experiment caps GP at sub-400 rather than re-measuring it.
- **Out of scope**: B9/B10 rows; monotonicity cells (IC-4 — no shape
  constraint is exercised here); UQ cells (IC-3 — no interval metrics);
  the d 11–20 column; real (non-synthetic) responses.

## Caveats

- Closed-world synthetic surfaces at d=2/d=5 with known truth; the point
  is controlled measurement of the DISCRIMINATING axes, not a tabular
  benchmark. Cell values are one seeded realization (no seed sweep).
- B2 here = additive/pairwise-tensor penalized splines built from
  `SplineTransformer` — GAM-adjacent; a full tensor-product smoother or
  MARS could shift B2's smooth-surface numbers.
- The bisection metric measures ROOT LOCALIZATION through a deterministic
  bracket protocol; it does not measure the well-posedness of exact
  inversion on a plateau (an interval of roots) — that remains the
  definitional R1 argument (Q-surr-46, Q-surr-38, Q-surr-42, Q-surr-44).
- The lattice leg is 7x7 / 14x14 / 28x28 vs the spec sketch's "6x6x..." —
  the level counts are chosen so every lattice cell has a matched-N
  space-filling partner (49↔50, 196↔200, 784↔800) instead of confounding
  geometry with sample size (deviation noted in the lane report). The
  original single 14x14 cell is unchanged and still drives `[V8]`.
- **The lattice leg is noise-free only.** Design structure has not been
  crossed with the 5% noise axis, so nothing here says whether the
  structure effect survives noise. That is a named gap, not an oversight.
- **Cell values are venue-dependent at the second significant figure — but
  the published bands are not.** See **What TASK-9-C1 changed** above: across
  an unmodified re-run in a different Python/numpy/scipy/sklearn/OS venue,
  32 of 37 cells moved, 6 bisection counts among them, with B7 contributing
  124 of the 218 moved values. Re-measured at C2: `[V2]` and `[V3]` are
  byte-identical across the two venues and no moved bisection count feeds a
  published band, so quote **re-derived** numbers with the venue attached —
  especially anything involving B7 — rather than distrusting the bands.

## Cited quote ids (all status VERIFIED in `QUOTES.md`)

Q-surr-03, Q-surr-04, Q-surr-15, Q-surr-17, Q-surr-19, Q-surr-22,
Q-surr-26, Q-surr-27, Q-surr-31, Q-surr-34, Q-surr-38, Q-surr-39,
Q-surr-42, Q-surr-44, Q-surr-46, Q-surr-57.
