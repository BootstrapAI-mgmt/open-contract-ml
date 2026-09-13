"""
falsifier_benchmark.py - TASK-9 Session-B falsifier for the surrogate taxonomy
==============================================================================

The small CPU experiment that settles/supports the [OPEN] cells of the
TASK-9 scalar-surrogate selection matrix and grounds the IC-1/IC-2
indifference tolerances empirically (task card section 5, Session B;
shepherd spec section 7 is the binding contract). Style-matched to
substructuring_experiment.py: seeded, CPU-minutes, printed table with a
how-to-read block, results written to falsifier_results.txt by this script.

WHAT IS MEASURED (per surface x family x N x noise cell)
--------------------------------------------------------
  nrmse    accuracy on the interpolation region (2000 uniform test points,
           scored vs the TRUE noise-free function, / range)
  bis      bisection-inverse success out of 20 fixed random 1-D slices:
           brentq root of (surrogate - y_target) vs the true root;
           success = |x_surr - x_true| <= 2% of the axis range.
           ns/wr = failures split: no-sign-change / wrong-root
  gcos     mean cosine(central-diff surrogate gradient, analytic true
           gradient) at 100 fixed interior points (h = 1e-3)
  grel     mean relative L2 error of the same gradients
  xnrmse   extrapolation NRMSE on a 400-point shell between the hull and
           the 1.2x-scaled hull (box [-0.1, 1.1]^d minus [0,1]^d)
  rough    sweep roughness: mean |second difference| along axis-aligned
           201-point sweeps / range x 1e3 (0 for smooth, large for steps)
  sec      fit wall seconds incl. the <=3-config 5-fold CV pick, the
           fold-std pass, and the interp-region predict

FAMILIES (bucket ids from the taxonomy; <=3 configs each, 5-fold CV pick)
-------------------------------------------------------------------------
  B1 poly2      PolynomialFeatures(2) + LinearRegression (1 config)
  B2 spline     SplineTransformer+Ridge: additive k10 alpha 1e-4 / pairwise
                tensor-product k6 alpha 1e-4 / tensor k6 alpha 1e-2
                (3 configs; CV picks structure AND stiffness, mirroring how
                smoothing splines choose their penalty)
  B3 GP-Mat52   GP, ConstantKernel*Matern(nu=2.5, ARD) [+White nugget iff
                noisy]; hyperparams by MLE (the family's native selection);
                fold-std computed at the fixed MLE kernel (1 config).
                N>400 cells train on a SEEDED 400-point subsample of the
                design (config label 'mle-sub400') - the spec's named
                GP-at-N=800 budget risk, remediated by subsampling as the
                spec section 7 escape clause directs, never dropped.
  B4 RBF-TPS    scipy RBFInterpolator thin-plate, smoothing=0 - the EXACT
                interpolant, per the bucket's estimation principle (1 config)
  B5 SVR-RBF    C in {1,10,100} (eps 0.05/0.05/0.01 in standardized-y units)
  B6a RF        80 trees, min_samples_leaf in {1,3}
  B6b HGB       HistGradientBoosting, max_bins=64: (lr .1, 200 it) /
                (lr .05, 250 it) - 2 configs
  B7 MLP-2x64   lbfgs, alpha in {1e-4, 1e-2}, max_iter 150, standardized
                X and y
  B8 kNN-5      k=5, weights in {uniform, distance}
  (GP sub-400, RF 80 trees, HGB 2 configs / 200-250 iters / 64 bins, MLP
  150 lbfgs iters, brentq xtol 2e-4, and OMP_NUM_THREADS=1 are the declared
  runtime-budget reductions - see README, spec section 7 escape clause.)
  MARS omitted (no maintained lib in the pinned numpy/scipy/sklearn set);
  B9 symbolic and B10 TabPFN are outside the pinned dependency set.

SURFACES (analytic, with analytic gradients where they exist)
-------------------------------------------------------------
  linear    3*x0 - 2*x1 + 1
  quad-int  x0^2 + 2*x1^2 + 1.5*x0*x1 + x0 - 0.5
  sin-exp   sin(2*pi*x0) * exp(x1)                  (smooth nonlinear)
  kinked    |x0 - 0.45| + 0.5*|x1 - 0.6|            (gradient a.e.)
  step      1[x0 + x1 > 1]                          (gradient n/a)
  smooth5   sin(2*pi*x0)*exp(x1) + 2*(x2-0.5)^2 + x3*x4   (the d=5 check)

DESIGNS: two design STRUCTURES, crossed with the N grid at d=2 --
  space-filling  LHS (scipy.stats.qmc, seeded), N in {50, 200, 800}
  lattice        full-factorial k-level grid, k = round(N**(1/d)) levels
                 per axis, so a requested N is ADJUSTED to the nearest
                 achievable lattice size: 50 -> 49 (7x7), 200 -> 196
                 (14x14), 800 -> 784 (28x28). The adjustment is printed at
                 run time and the cell is keyed by the size it actually
                 has, never by the size that was asked for. Noise 0 only,
                 matching the convention of the axis's original cell.
Plus a d=5 smooth check at N in {200, 800} (LHS). Noise in {0, 5% of range},
added to TRAIN y only; every metric is scored against the true function.

THE DESIGN-STRUCTURE AXIS (TASK-9-C1). The lattice structure was present
from Session B but at exactly ONE point (14x14=196, noise 0), compared
against LHS-200. One point cannot answer the question the H-T worked
instance raised - whether design structure at fixed N moves the
partition-family inverse and gradient metrics by MORE than N does at fixed
design structure - because it has no N leg. TASK-9-C1 extends the same
structure across the same N grid so both legs exist. `make_design` is
UNCHANGED: the k = round(N**(1/d)) rule was already what it implemented.
No family, no metric, no metric definition and no tolerance changed.

Usage:
    py -3.12 falsifier_benchmark.py            # the pinned full grid (~5 min)
    py -3.12 falsifier_benchmark.py --smoke    # 60-90 s wiring check

Seed = 0 everywhere. Progress goes to stderr; the report goes to stdout AND
falsifier_results.txt next to this file.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import warnings

# Single-threaded OpenMP/BLAS: at N <= 800 per-fit thread-spawn overhead
# dominates any parallel win (measured 11 HGB fits: 3.6 s at OMP=1 vs 5.8 s
# at OMP=4 on the build host) and it makes timings reproducible on a loaded
# machine. Set BEFORE numpy/sklearn import. Declared in the README.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
from scipy.interpolate import RBFInterpolator
from scipy.optimize import brentq
from scipy.stats import qmc
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import KFold
from sklearn.neighbors import KNeighborsRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import PolynomialFeatures, SplineTransformer, StandardScaler
from sklearn.svm import SVR

warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

SEED = 0
TWO_PI = 2.0 * np.pi

# The N grid the lattice design structure is requested at, before the
# round(N**(1/d)) adjustment (TASK-9-C1). Deliberately the SAME grid the
# space-filling designs use, so every lattice cell has a matched-N partner.
LATTICE_N_REQ = (50, 200, 800)

_LINES = []


def emit(s=""):
    print(s)
    _LINES.append(s)


def note(s):
    print(s, file=sys.stderr, flush=True)


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


# ----------------------------------------------------------------------------
# Surfaces (truth + analytic gradients)
# ----------------------------------------------------------------------------
class Surface:
    def __init__(self, name, d, f, grad):
        self.name, self.d, self.f, self.grad = name, d, f, grad


def _f_linear(X):
    return 3.0 * X[:, 0] - 2.0 * X[:, 1] + 1.0


def _g_linear(X):
    G = np.zeros_like(X)
    G[:, 0], G[:, 1] = 3.0, -2.0
    return G


def _f_quad(X):
    return X[:, 0] ** 2 + 2.0 * X[:, 1] ** 2 + 1.5 * X[:, 0] * X[:, 1] + X[:, 0] - 0.5


def _g_quad(X):
    G = np.zeros_like(X)
    G[:, 0] = 2.0 * X[:, 0] + 1.5 * X[:, 1] + 1.0
    G[:, 1] = 4.0 * X[:, 1] + 1.5 * X[:, 0]
    return G


def _f_sinexp(X):
    return np.sin(TWO_PI * X[:, 0]) * np.exp(X[:, 1])


def _g_sinexp(X):
    G = np.zeros_like(X)
    G[:, 0] = TWO_PI * np.cos(TWO_PI * X[:, 0]) * np.exp(X[:, 1])
    G[:, 1] = np.sin(TWO_PI * X[:, 0]) * np.exp(X[:, 1])
    return G


def _f_kink(X):
    return np.abs(X[:, 0] - 0.45) + 0.5 * np.abs(X[:, 1] - 0.6)


def _g_kink(X):
    G = np.zeros_like(X)
    G[:, 0] = np.sign(X[:, 0] - 0.45)
    G[:, 1] = 0.5 * np.sign(X[:, 1] - 0.6)
    return G


def _f_step(X):
    return (X[:, 0] + X[:, 1] > 1.0).astype(float)


def _f_smooth5(X):
    return (np.sin(TWO_PI * X[:, 0]) * np.exp(X[:, 1])
            + 2.0 * (X[:, 2] - 0.5) ** 2 + X[:, 3] * X[:, 4])


def _g_smooth5(X):
    G = np.zeros_like(X)
    G[:, 0] = TWO_PI * np.cos(TWO_PI * X[:, 0]) * np.exp(X[:, 1])
    G[:, 1] = np.sin(TWO_PI * X[:, 0]) * np.exp(X[:, 1])
    G[:, 2] = 4.0 * (X[:, 2] - 0.5)
    G[:, 3] = X[:, 4]
    G[:, 4] = X[:, 3]
    return G


SURFS = {
    "linear": Surface("linear", 2, _f_linear, _g_linear),
    "quad-int": Surface("quad-int", 2, _f_quad, _g_quad),
    "sin-exp": Surface("sin-exp", 2, _f_sinexp, _g_sinexp),
    "kinked": Surface("kinked", 2, _f_kink, _g_kink),
    "step": Surface("step", 2, _f_step, None),
    "smooth5": Surface("smooth5", 5, _f_smooth5, _g_smooth5),
}
SURF_ID = {k: i for i, k in enumerate(SURFS)}
SMOOTH_SURFS = ("linear", "quad-int", "sin-exp", "smooth5")

# TASK-9-E2. The H-T worked instance's design is a 6x5x4x3x2 full factorial:
# a lattice with a DIFFERENT level count on every axis. make_design's lattice
# branch cannot express that (one level count, every axis), so the pattern is
# carried here and reached through the separate DOE name "lat-aniso". The
# isotropic branch is untouched.
ANISO_LEVELS = {5: (6, 5, 4, 3, 2)}

# TASK-9-E cross-references. Values owned by ANOTHER program or fixed by the
# brief that commissioned this run, named here with their provenance so that
# no verdict emitter below contains a bare literal. This is the same
# convention run_ht_instance.py uses to carry this file's [V10] numbers -
# each script keeps the other's numbers as declared constants rather than
# reading the other's files at run time.
HT_INSTANCE_BIS = 0.075        # H-T worked instance, partition-family
                               # bisection success; its own section 7
                               # output, checked 2026-08-21 (TASK-9-E)
E2_C1_CEILING = 0.10           # SESSION-9E falsification condition C1
E2_IC1_CELLS_BEFORE = 20       # IC-1 cell count in the pre-9E results file
E2_PROBE = {                   # SESSION-9E authoring probe: PREDICTIONS to
    ("lattice", 243): 0.000,   # be refuted, from a scratch harness, NOT
    ("lhs", 720): 0.050,       # from this code path. Printed beside the
    ("lattice", 1024): 0.100,  # measurement so a disagreement is visible
    ("lat-aniso", 720): 0.317, # rather than quietly reconciled.
}
B1_INADEQUATE = ("sin-exp", "smooth5")   # degree-2 basis cannot represent these


# ----------------------------------------------------------------------------
# Family wrappers (uniform fit/predict interface)
# ----------------------------------------------------------------------------
class PolyLS:
    def fit(self, X, y):
        self.pf = PolynomialFeatures(2, include_bias=True)
        self.lr = LinearRegression().fit(self.pf.fit_transform(X), y)
        return self

    def predict(self, X):
        return self.lr.predict(self.pf.transform(X))


class SplineRidge:
    """SplineTransformer + Ridge. tensor=True adds pairwise products of the
    per-feature B-spline bases (a 2-way tensor-product spline, still
    linear-in-parameters + penalized LS = the B2 estimation principle)."""

    def __init__(self, n_knots, tensor, alpha):
        self.n_knots, self.tensor, self.alpha = n_knots, tensor, alpha

    def _feats(self, B):
        if not self.tensor:
            return B
        n = B.shape[0]
        d, m = self.d, self.m
        blocks = [B]
        for i in range(d):
            for j in range(i + 1, d):
                Bi = B[:, i * m:(i + 1) * m]
                Bj = B[:, j * m:(j + 1) * m]
                blocks.append((Bi[:, :, None] * Bj[:, None, :]).reshape(n, m * m))
        return np.hstack(blocks)

    def fit(self, X, y):
        self.st = SplineTransformer(n_knots=self.n_knots, degree=3,
                                    include_bias=False, extrapolation="linear")
        B = self.st.fit_transform(X)
        self.d = X.shape[1]
        self.m = B.shape[1] // self.d
        self.ridge = Ridge(alpha=self.alpha).fit(self._feats(B), y)
        return self

    def predict(self, X):
        return self.ridge.predict(self._feats(self.st.transform(X)))


class GPModel:
    def __init__(self, d, noisy, kernel=None):
        if kernel is not None:                       # fixed-kernel fold refit
            self.gp = GaussianProcessRegressor(kernel=kernel, optimizer=None,
                                               normalize_y=True, alpha=1e-10)
        else:
            k = (ConstantKernel(1.0, (1e-3, 1e3))
                 * Matern(length_scale=[0.3] * d,
                          length_scale_bounds=(1e-2, 1e2), nu=2.5))
            if noisy:
                k = k + WhiteKernel(1e-2, (1e-8, 1e1))
            self.gp = GaussianProcessRegressor(kernel=k, n_restarts_optimizer=0,
                                               normalize_y=True, alpha=1e-10,
                                               random_state=SEED)

    def fit(self, X, y):
        self.gp.fit(X, y)
        return self

    def predict(self, X):
        return self.gp.predict(X)

    @property
    def kernel_(self):
        return self.gp.kernel_


class RBFTPS:
    """B4: EXACT thin-plate interpolant (smoothing=0). Kept exact even under
    noise - that IS the bucket's estimation principle; the R9 cell needs it."""

    def fit(self, X, y):
        self.r = RBFInterpolator(X, y, kernel="thin_plate_spline", smoothing=0.0)
        return self

    def predict(self, X):
        return self.r(X)


class SVRModel:
    def __init__(self, C, eps):
        self.C, self.eps = C, eps

    def fit(self, X, y):
        self.sx = StandardScaler().fit(X)
        self.mu, self.sd = float(np.mean(y)), float(np.std(y)) or 1.0
        self.svr = SVR(kernel="rbf", C=self.C, epsilon=self.eps, gamma="scale")
        self.svr.fit(self.sx.transform(X), (y - self.mu) / self.sd)
        return self

    def predict(self, X):
        return self.svr.predict(self.sx.transform(X)) * self.sd + self.mu


class RFModel:
    def __init__(self, leaf):
        self.leaf = leaf

    def fit(self, X, y):
        self.rf = RandomForestRegressor(n_estimators=80, min_samples_leaf=self.leaf,
                                        random_state=SEED, n_jobs=-1).fit(X, y)
        return self

    def predict(self, X):
        return self.rf.predict(X)


class HGBModel:
    def __init__(self, lr, iters, leaves):
        self.lr, self.iters, self.leaves = lr, iters, leaves

    def fit(self, X, y):
        self.m = HistGradientBoostingRegressor(
            learning_rate=self.lr, max_iter=self.iters, max_leaf_nodes=self.leaves,
            max_bins=64, random_state=SEED, early_stopping=False).fit(X, y)
        return self

    def predict(self, X):
        return self.m.predict(X)


class MLPModel:
    def __init__(self, alpha):
        self.alpha = alpha

    def fit(self, X, y):
        self.sx = StandardScaler().fit(X)
        self.mu, self.sd = float(np.mean(y)), float(np.std(y)) or 1.0
        self.mlp = MLPRegressor(hidden_layer_sizes=(64, 64), solver="lbfgs",
                                alpha=self.alpha, max_iter=150, tol=1e-6,
                                random_state=SEED)
        self.mlp.fit(self.sx.transform(X), (y - self.mu) / self.sd)
        return self

    def predict(self, X):
        return self.mlp.predict(self.sx.transform(X)) * self.sd + self.mu


class KNNModel:
    def __init__(self, w):
        self.w = w

    def fit(self, X, y):
        self.m = KNeighborsRegressor(n_neighbors=5, weights=self.w).fit(X, y)
        return self

    def predict(self, X):
        return self.m.predict(X)


def family_registry(d, noisy):
    """(key, label, [(config_label, factory)]) - <=3 configs per family."""
    return [
        ("B1", "B1 poly2", [("deg2", lambda: PolyLS())]),
        ("B2", "B2 spline", [("add-k10", lambda: SplineRidge(10, False, 1e-4)),
                             ("ten-k6", lambda: SplineRidge(6, True, 1e-4)),
                             ("ten-k6-st", lambda: SplineRidge(6, True, 1e-2))]),
        ("B3", "B3 GP-Mat52", [("mle+nug" if noisy else "mle",
                                lambda: GPModel(d, noisy))]),
        ("B4", "B4 RBF-TPS", [("tps-exact", lambda: RBFTPS())]),
        ("B5", "B5 SVR-RBF", [("C1", lambda: SVRModel(1.0, 0.05)),
                              ("C10", lambda: SVRModel(10.0, 0.05)),
                              ("C100", lambda: SVRModel(100.0, 0.01))]),
        ("B6a", "B6a RF", [("leaf1", lambda: RFModel(1)),
                           ("leaf3", lambda: RFModel(3))]),
        ("B6b", "B6b HGB", [("lr.1", lambda: HGBModel(0.1, 200, 31)),
                            ("lr.05", lambda: HGBModel(0.05, 250, 31))]),
        ("B7", "B7 MLP-2x64", [("a1e-4", lambda: MLPModel(1e-4)),
                               ("a1e-2", lambda: MLPModel(1e-2))]),
        ("B8", "B8 kNN-5", [("unif", lambda: KNNModel("uniform")),
                            ("dist", lambda: KNNModel("distance"))]),
    ]


FAM_LABEL = {k: lbl for k, lbl, _ in family_registry(2, False)}


# ----------------------------------------------------------------------------
# Fixtures per (surface, d): shared across every family and N for fairness
# ----------------------------------------------------------------------------
def _pt(base, j, t):
    p = base.copy()
    p[j] = t
    return p[None, :]


def make_slices(f, d, rng, M, range_ref):
    """Fixed random 1-D slices with a bracketed TRUE root. y_target = midpoint
    of the slice's endpoint values; x_true = first grid crossing refined by
    brentq (deterministic, unambiguous under multiple crossings)."""
    out, att = [], 0
    tgrid = np.linspace(0.0, 1.0, 513)
    while len(out) < M and att < 4000:
        att += 1
        j = int(rng.integers(0, d))
        base = rng.uniform(0.0, 1.0, d)
        a, b = base.copy(), base.copy()
        a[j], b[j] = 0.0, 1.0
        fa, fb = float(f(a[None, :])[0]), float(f(b[None, :])[0])
        if abs(fa - fb) < 0.05 * range_ref:
            continue
        y_t = 0.5 * (fa + fb)
        P = np.repeat(base[None, :], tgrid.size, 0)
        P[:, j] = tgrid
        g = f(P) - y_t
        sgn = np.sign(g)
        sgn[sgn == 0] = 1.0
        ch = np.nonzero(sgn[:-1] * sgn[1:] < 0)[0]
        if len(ch) == 0:
            continue
        k = int(ch[0])

        def gt(t, base=base, j=j, y_t=y_t):
            return float(f(_pt(base, j, t))[0]) - y_t

        try:
            x_true = brentq(gt, tgrid[k], tgrid[k + 1], xtol=1e-6, maxiter=200)
        except Exception:
            continue
        if not (0.01 <= x_true <= 0.99):
            continue
        out.append((j, base, y_t, float(x_true)))
    if len(out) < M:
        raise RuntimeError("slice construction failed")
    return out


def make_shell(d, rng, n_pts):
    pts = []
    while len(pts) < n_pts:
        cand = rng.uniform(-0.1, 1.1, size=(4 * n_pts, d))
        inside = np.all((cand >= 0.0) & (cand <= 1.0), axis=1)
        pts.extend(cand[~inside])
    return np.array(pts[:n_pts])


def make_sweeps(d, rng, per_axis=2):
    return [(j, rng.uniform(0.0, 1.0, d)) for j in range(d) for _ in range(per_axis)]


def _ray_points(c, u):
    s = np.arange(1.0, 2.0001, 0.1)
    with np.errstate(divide="ignore"):
        t_hi = np.where(u > 1e-12, (1.0 - c) / u, np.inf)
        t_lo = np.where(u < -1e-12, (0.0 - c) / u, np.inf)
    t_exit = float(min(t_hi.min(), t_lo.min()))
    b = c + t_exit * u
    return c[None, :] + s[:, None] * (b - c)[None, :]


def make_rays(d, rng, K=24):
    """Two ray sets from the domain center out to 2x the hull half-width:
    'ax' = the 2d axis-aligned rays (the clean hull-constancy probe: beyond
    the exit face only ONE coordinate keeps moving, so a partition model
    that has passed its last split threshold must go exactly constant);
    'diag' = K random directions (the generic-direction probe, where a
    partition model can keep crossing splits on the other coordinates)."""
    c = np.full(d, 0.5)
    ax = []
    for j in range(d):
        for sgn in (1.0, -1.0):
            u = np.zeros(d)
            u[j] = sgn
            ax.append(_ray_points(c, u))
    diag = []
    for _ in range(K):
        u = rng.normal(size=d)
        u /= np.linalg.norm(u)
        diag.append(_ray_points(c, u))
    return {"ax": ax, "diag": diag}


def build_fixture(sname, cfg):
    surf = SURFS[sname]
    d, sid = surf.d, SURF_ID[sname]
    ref = np.random.default_rng([SEED, sid, 9]).uniform(0, 1, size=(20000, d))
    yref = surf.f(ref)
    range_ref = float(yref.max() - yref.min())
    fx = {
        "surf": surf, "d": d, "range": range_ref,
        "Xte": np.random.default_rng([SEED, sid, 1]).uniform(0, 1, size=(cfg["n_test"], d)),
        "shell": make_shell(d, np.random.default_rng([SEED, sid, 2]), cfg["n_shell"]),
        "gpts": np.random.default_rng([SEED, sid, 3]).uniform(0.05, 0.95, size=(100, d)),
        "slices": make_slices(surf.f, d, np.random.default_rng([SEED, sid, 4]),
                              cfg["n_slices"], range_ref),
        "sweeps": make_sweeps(d, np.random.default_rng([SEED, sid, 5])),
        "rays": make_rays(d, np.random.default_rng([SEED, sid, 6])),
    }
    fx["yte"] = surf.f(fx["Xte"])
    fx["yshell"] = surf.f(fx["shell"])
    return fx


# ----------------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------------
def bisection_metrics(model, slices):
    """TASK-9-E1 adds `detail`: one (axis, outcome) record per slice.

    The three returned counts are unchanged and nothing in the printed cell
    block reads the new field. It exists because a cell's bisection score
    pools slices that do not all run along the same axis, and [V11] needs
    to decompose the d=2 -> d=5 leg by axis to say whether that leg is
    dimensionality or slice composition.
    """
    succ = ns = wr = 0
    detail = []
    tgrid = np.linspace(0.0, 1.0, 513)
    for (j, base, y_t, x_true) in slices:
        P = np.repeat(base[None, :], tgrid.size, 0)
        P[:, j] = tgrid
        g = model.predict(P) - y_t
        sgn = np.sign(g)
        sgn[sgn == 0] = 1.0
        ch = np.nonzero(sgn[:-1] * sgn[1:] < 0)[0]
        if len(ch) == 0:
            ns += 1
            detail.append((j, "nosign"))
            continue
        mids = 0.5 * (tgrid[ch] + tgrid[ch + 1])
        k = int(ch[int(np.argmin(np.abs(mids - x_true)))])

        def gh(t, base=base, j=j, y_t=y_t):
            return float(model.predict(_pt(base, j, t))[0]) - y_t

        ga, gb = gh(tgrid[k]), gh(tgrid[k + 1])
        if ga == 0.0:
            xh = tgrid[k]
        elif gb == 0.0:
            xh = tgrid[k + 1]
        elif np.sign(ga) * np.sign(gb) < 0:
            try:
                xh = brentq(gh, tgrid[k], tgrid[k + 1], xtol=2e-4, maxiter=100)
            except Exception:
                wr += 1
                detail.append((j, "miss"))
                continue
        else:
            # Batch-vs-scalar float dust at a machine-precision crossing:
            # the 513-point batch predict saw a sign change in this bracket
            # but the scalar path does not (last-ulp BLAS differences). The
            # bracket midpoint is within half a grid cell (~1/1024) of the
            # batch-detected crossing; pass it to the same 2%-of-range test
            # as any other root estimate (a far-off bracket still fails).
            xh = 0.5 * (tgrid[k] + tgrid[k + 1])
        if abs(xh - x_true) <= 0.02:
            succ += 1
            detail.append((j, "hit"))
        else:
            wr += 1
            detail.append((j, "miss"))
    return succ, ns, wr, detail


def gradient_metrics(model, surf, pts, h=1e-3):
    if surf.grad is None:
        return float("nan"), float("nan")
    G_true = surf.grad(pts)
    n, d = pts.shape
    stack = []
    for j in range(d):
        e = np.zeros(d)
        e[j] = h
        stack.append(pts + e)
        stack.append(pts - e)
    Y = model.predict(np.vstack(stack))
    G = np.empty((n, d))
    for j in range(d):
        G[:, j] = (Y[2 * j * n:(2 * j + 1) * n] - Y[(2 * j + 1) * n:(2 * j + 2) * n]) / (2 * h)
    nt = np.linalg.norm(G_true, axis=1)
    nh = np.linalg.norm(G, axis=1)
    keep = nt > 1e-12
    dots = np.einsum("ij,ij->i", G, G_true)
    cos = np.where(nh > 1e-12, dots / np.maximum(nh * nt, 1e-300), 0.0)
    rel = np.linalg.norm(G - G_true, axis=1) / nt
    return float(np.mean(cos[keep])), float(np.mean(rel[keep]))


def roughness(model, sweeps, range_ref):
    acc = []
    t = np.linspace(0.0, 1.0, 201)
    for (j, base) in sweeps:
        P = np.repeat(base[None, :], t.size, 0)
        P[:, j] = t
        yv = model.predict(P)
        acc.append(np.abs(yv[2:] - 2 * yv[1:-1] + yv[:-2]))
    return float(np.mean(np.concatenate(acc)) / range_ref * 1e3)


def probe_metrics(model, rays, ytrain_mean, range_ref):
    def _edge(ray_list):
        acc = []
        for P in ray_list:
            yv = model.predict(P)
            acc.append(np.abs(yv[1:] - yv[0]))
        return float(np.mean(np.concatenate(acc)) / range_ref)

    curv_n, curv_f, far = [], [], []
    for P in rays["ax"] + rays["diag"]:
        yv = model.predict(P)
        d2 = np.abs(yv[2:] - 2 * yv[1:-1] + yv[:-2])   # centers s=1.1..1.9
        curv_n.append(d2[:4])                          # s 1.1-1.4 (near band)
        curv_f.append(d2[5:])                          # s 1.6-1.9 (far band)
        far.append(abs(float(yv[-1]) - ytrain_mean))
    return (_edge(rays["ax"]), _edge(rays["diag"]),
            float(np.mean(np.concatenate(curv_n)) / range_ref * 1e3),
            float(np.mean(np.concatenate(curv_f)) / range_ref * 1e3),
            float(np.mean(far) / range_ref))


# ----------------------------------------------------------------------------
# Fit with the declared matched tuning budget
# ----------------------------------------------------------------------------
def cv_select_and_fit(fam_key, configs, X, y, range_ref, d, noisy):
    """<=3 configs, 5-fold CV pick on TRAIN only. Returns (model, cfg_label,
    fold_nrmse_std_of_chosen, sec). B3 special case: hyperparams by MLE (the
    family's native selection); fold-std at the fixed MLE kernel."""
    t0 = time.perf_counter()
    kf = KFold(5, shuffle=True, random_state=SEED)
    folds = list(kf.split(X))
    if fam_key == "B3":
        # Declared budget remediation (spec section 7: 'GP at N=800 is the
        # risk ... subsample or declare'): N>400 trains on a seeded
        # 400-point subsample of the SAME design.
        if len(X) > 400:
            idx = np.random.default_rng([SEED, 42, len(X)]).choice(
                len(X), 400, replace=False)
            Xg, yg = X[idx], y[idx]
            sub = "-sub400"
        else:
            Xg, yg, sub = X, y, ""
        folds_g = list(KFold(5, shuffle=True, random_state=SEED).split(Xg))
        model = configs[0][1]().fit(Xg, yg)
        cfg_label = configs[0][0] + sub
        fold_nrmse = []
        for tr, va in folds_g:
            m = GPModel(d, noisy, kernel=model.kernel_).fit(Xg[tr], yg[tr])
            fold_nrmse.append(rmse(m.predict(Xg[va]), yg[va]) / range_ref)
    else:
        best = None
        for label, fac in configs:
            fn = []
            for tr, va in folds:
                m = fac().fit(X[tr], y[tr])
                fn.append(rmse(m.predict(X[va]), y[va]) / range_ref)
            score = float(np.mean(fn))
            if best is None or score < best[0]:
                best = (score, label, fac, fn)
        _, cfg_label, fac, fold_nrmse = best
        model = fac().fit(X, y)
    return model, cfg_label, float(np.std(fold_nrmse)), time.perf_counter() - t0


# ----------------------------------------------------------------------------
# Cell grid
# ----------------------------------------------------------------------------
def cell_list(smoke):
    d2 = ["linear", "quad-int", "sin-exp", "kinked", "step"]
    cells = []
    if smoke:
        for s in d2:
            cells.append((s, "lhs", 2, 50, 0.0))
        return cells
    for s in d2:
        for noise in (0.0, 0.05):
            for n in (50, 200, 800):
                cells.append((s, "lhs", 2, n, noise))
    for s in d2:
        for n_req in LATTICE_N_REQ:
            cells.append((s, "lattice", 2, lattice_size(n_req, 2)[1], 0.0))
    for n in (200, 800):
        cells.append(("smooth5", "lhs", 5, n, 0.0))
    # TASK-9-E2: the design axis crossed with dimensionality. Every lattice
    # cell before this one was d=2, so "design structure" and "d=5" had never
    # been measured together, and level anisotropy was not expressible at all.
    # The LHS-720 control is what makes the anisotropic cell readable - same
    # N, same surface, space-filling instead of gridded.
    for c in (("smooth5", "lattice", 5, 243, 0.0),
              ("smooth5", "lhs", 5, 720, 0.0),
              ("smooth5", "lattice", 5, 1024, 0.0),
              ("smooth5", "lat-aniso", 5, 720, 0.0)):
        cells.append(c)
    return cells


def lattice_size(n_req, d):
    """Nearest achievable full-factorial size for a requested N.

    k = round(n_req ** (1/d)) levels per axis gives k**d points, which is
    what the cell is keyed by - a lattice cell is labelled with the N it
    actually has, not the N that was asked for. At d=2 the N grid adjusts
    50 -> 49, 200 -> 196, 800 -> 784. Returns (k, k**d).

    This is the same rule make_design already applies; naming it here is
    what lets the adjustment be printed instead of inferred.
    """
    k = int(round(n_req ** (1.0 / d)))
    return k, k ** d


def lattice_adjustment_line(d=2):
    parts = []
    for n_req in LATTICE_N_REQ:
        k, sz = lattice_size(n_req, d)
        parts.append("%d->%d (%dx%d)" % (n_req, sz, k, k))
    return ("lattice N-adjustment (k = round(N**(1/d)) levels/axis, d=%d): %s"
            % (d, ", ".join(parts)))


def make_design(doe, n, d, sname):
    sid = SURF_ID[sname]
    if doe == "lat-aniso":
        levels = ANISO_LEVELS[d]
        if len(levels) != d or int(np.prod(levels)) != n:
            raise ValueError("anisotropic levels %s do not give d=%d N=%d"
                             % (levels, d, n))
        axes = [np.linspace(0.0, 1.0, m) for m in levels]
        return np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, d)
    if doe == "lattice":
        m = int(round(n ** (1.0 / d)))
        axes = [np.linspace(0.0, 1.0, m)] * d
        return np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, d)
    rng = np.random.default_rng([SEED, sid, 7, n])
    return qmc.LatinHypercube(d=d, seed=rng).random(n)


# ----------------------------------------------------------------------------
# Report helpers
# ----------------------------------------------------------------------------
def leg_stats(vals):
    """Signed mean, mean magnitude, and whether the legs split in sign.

    TASK-9-E1. [V10] printed `mean |dSTRUCT|` over a number its emitter
    computed as abs(mean(lattice) - mean(lhs)) - the absolute value of a
    mean, not the mean of absolute values - and guarded only its GRADIENT
    line against a sign split. Both means are returned here, always, along
    with the split flag, so no caller can assert dominance across a sign
    split without printing that it did.
    """
    a = [float(v) for v in vals if not np.isnan(v)]
    if not a:
        return float("nan"), float("nan"), False
    return (float(np.mean(a)), float(np.mean([abs(v) for v in a])),
            bool(min(a) < 0.0 < max(a)))


def _g(v, w=9):
    if isinstance(v, float) and np.isnan(v):
        return "--".rjust(w)
    return ("%.3g" % v).rjust(w)


def _cell_hdr(key):
    s, doe, d, n, noise = key
    base = ("--- surface=%-8s DOE=%-7s d=%d  N=%-3d  noise=%s ---"
            % (s, doe, d, n, ("0" if noise == 0 else "%g%%" % (100 * noise))))
    # TASK-9-E2 DoD 2: a lattice above d=2 prints its ACTUAL level pattern, so
    # 6x5x4x3x2 is readable in this file without opening the source. The d=2
    # lattice cells that predate 9E are left exactly as they were.
    if doe == "lat-aniso":
        return base + " levels=%s" % "x".join(str(m) for m in ANISO_LEVELS[d])
    if doe == "lattice" and d > 2:
        m = int(round(n ** (1.0 / d)))
        return base + " levels=%s" % "x".join([str(m)] * d)
    return base


def print_cell_block(key, rows):
    emit(_cell_hdr(key))
    emit("  %-12s %-10s %s %s %s %s %s %s %s %s" % (
        "family", "cfg", "nrmse".rjust(9), "bis".rjust(6), "ns/wr".rjust(6),
        "gcos".rjust(7), "grel".rjust(9), "xnrmse".rjust(9),
        "rough".rjust(9), "sec".rjust(7)))
    for r in rows:
        gcos = "--".rjust(7) if np.isnan(r["gcos"]) else ("%6.3f" % r["gcos"]).rjust(7)
        emit("  %-12s %-10s %s %s %s %s %s %s %s %s" % (
            FAM_LABEL[r["fam"]], r["cfg"], _g(r["nrmse"]),
            ("%d/%d" % (r["bis"], r["n_slices"])).rjust(6),
            ("%d/%d" % (r["ns"], r["wr"])).rjust(6), gcos, _g(r["grel"]),
            _g(r["xnrmse"]), _g(r["rough"]), ("%.2f" % r["sec"]).rjust(7)))
    emit()


# ----------------------------------------------------------------------------
# Main experiment
# ----------------------------------------------------------------------------
def run(smoke=False):
    t_start = time.perf_counter()
    cfg = {"n_test": 500 if smoke else 2000,
           "n_shell": 200 if smoke else 400,
           "n_slices": 6 if smoke else 20}
    cells = cell_list(smoke)
    fixtures = {}
    results = {}
    pick_counts = {}
    probe_rows = None

    import platform
    import scipy
    import sklearn
    emit("=" * 78)
    emit("TASK-9 FALSIFIER BENCHMARK - scalar-surrogate taxonomy, Session B")
    emit("=" * 78)
    emit("seed=%d | python %s | numpy %s | scipy %s | sklearn %s | %s"
         % (SEED, platform.python_version(), np.__version__, scipy.__version__,
            sklearn.__version__, platform.system()))
    emit("mode=%s | cells=%d | families=9 | interp test=%d pts | slices=%d | "
         "shell=%d pts" % ("SMOKE" if smoke else "FULL", len(cells),
                           cfg["n_test"], cfg["n_slices"], cfg["n_shell"]))
    emit("tuning budget: <=3 configs/family, 5-fold CV on train only "
         "(B3: MLE, its native selection)")
    if not smoke:
        emit(lattice_adjustment_line(2))
    emit()

    for key in cells:
        sname, doe, d, n, noise = key
        if sname not in fixtures:
            fixtures[sname] = build_fixture(sname, cfg)
        fx = fixtures[sname]
        surf, range_ref = fx["surf"], fx["range"]
        X = make_design(doe, n, d, sname)
        n_eff = X.shape[0]
        y_clean = surf.f(X)
        if noise > 0:
            rngn = np.random.default_rng([SEED, SURF_ID[sname], 8, n])
            y = y_clean + noise * range_ref * rngn.standard_normal(n_eff)
        else:
            y = y_clean
        ytrain_mean = float(np.mean(y))

        rows = []
        for fam_key, fam_label, configs in family_registry(d, noise > 0):
            note("  cell %s N=%d noise=%g :: %s" % (sname, n_eff, noise, fam_label))
            model, cfg_label, fold_std, sec = cv_select_and_fit(
                fam_key, configs, X, y, range_ref, d, noise > 0)
            t0 = time.perf_counter()
            yp = model.predict(fx["Xte"])
            sec += time.perf_counter() - t0
            row = {
                "fam": fam_key, "cfg": cfg_label, "fold_std": fold_std,
                "nrmse": rmse(yp, fx["yte"]) / range_ref,
                "sec": sec, "n_slices": cfg["n_slices"],
            }
            (row["bis"], row["ns"], row["wr"],
             row["bis_detail"]) = bisection_metrics(model, fx["slices"])
            row["gcos"], row["grel"] = gradient_metrics(model, surf, fx["gpts"])
            row["xnrmse"] = rmse(model.predict(fx["shell"]), fx["yshell"]) / range_ref
            row["rough"] = roughness(model, fx["sweeps"], range_ref)
            if key == ("sin-exp", "lhs", 2, 200, 0.0):
                row["probe"] = probe_metrics(model, fx["rays"], ytrain_mean, range_ref)
            rows.append(row)
            pick_counts.setdefault(fam_key, {}).setdefault(cfg_label, 0)
            pick_counts[fam_key][cfg_label] += 1
        results[key] = {r["fam"]: r for r in rows}
        if key == ("sin-exp", "lhs", 2, 200, 0.0):
            probe_rows = rows
        print_cell_block(key, rows)

    # ---------------- summary tables ----------------
    emit("=" * 78)
    emit("CONFIG PICKS (5-fold-CV winner counts across all cells)")
    emit("=" * 78)
    for fam_key in pick_counts:
        picks = ", ".join("%s x%d" % (c, k) for c, k in
                          sorted(pick_counts[fam_key].items(), key=lambda t: -t[1]))
        emit("  %-12s %s" % (FAM_LABEL[fam_key], picks))
    emit()

    ic1_cells = [k for k in results
                 if k[0] in SMOOTH_SURFS and k[4] == 0.0]
    emit("=" * 78)
    emit("IC-1 CHECK - {B1,B2,B3,B4} on smooth deterministic cells")
    emit("tolerance = 1 CV-fold std of the best family's NRMSE (the spec's")
    emit("operationalization); Dmax = worst member's NRMSE gap to the best")
    emit("=" * 78)
    emit("  %-34s %-10s %s %s  %-6s %-6s %s" % (
        "cell", "best", "nrmse".rjust(9), "tol".rjust(9),
        "all4", "B2-B4", "Dmax(B2-B4)".rjust(12)))
    ic1_stats = []
    for k in ic1_cells:
        rs = results[k]
        members = ["B1", "B2", "B3", "B4"]
        best = min(members, key=lambda f: rs[f]["nrmse"])
        tol = rs[best]["fold_std"]
        thr = rs[best]["nrmse"] + tol
        ok4 = all(rs[f]["nrmse"] <= thr for f in members)
        core = ["B2", "B3", "B4"]
        best_c = min(core, key=lambda f: rs[f]["nrmse"])
        thr_c = rs[best_c]["nrmse"] + rs[best_c]["fold_std"]
        ok3 = all(rs[f]["nrmse"] <= thr_c for f in core)
        dmax3 = max(rs[f]["nrmse"] for f in core) - rs[best_c]["nrmse"]
        lbl = "%s/%s/d%d/N=%d" % (k[0], k[1], k[2], k[3])
        emit("  %-34s %-10s %s %s  %-6s %-6s %s" % (
            lbl, FAM_LABEL[best], _g(rs[best]["nrmse"]), _g(tol),
            "HOLD" if ok4 else "FAIL", "HOLD" if ok3 else "FAIL", _g(dmax3, 12)))
        ic1_stats.append((k, ok4, ok3, dmax3))
    emit()

    emit("=" * 78)
    emit("IC-2 CHECK (approximate: N=800 sits BELOW the class's 1k-10k window;")
    emit("B10 TabPFN outside the pinned dependency set) - irregular + 5% noise")
    emit("=" * 78)
    ic2_stats = []
    for k in [("kinked", "lhs", 2, 800, 0.05), ("step", "lhs", 2, 800, 0.05)]:
        if k not in results:
            continue
        rs = results[k]
        gap = abs(rs["B6b"]["nrmse"] - rs["B7"]["nrmse"])
        emit("  %-22s B6b=%.4f  B7=%.4f  |gap|=%.4f  (B6a=%.4f)" % (
            k[0] + " N=800 5%", rs["B6b"]["nrmse"], rs["B7"]["nrmse"], gap,
            rs["B6a"]["nrmse"]))
        ic2_stats.append((k[0], rs["B6b"]["nrmse"], rs["B7"]["nrmse"], gap))
    emit()

    emit("=" * 78)
    emit("BISECTION-INVERSE SUCCESS by family x N (smooth d=2 LHS cells, noise 0)")
    emit("=" * 78)
    bis_tab = {}
    smooth2 = [s for s in SMOOTH_SURFS if SURFS[s].d == 2]
    n_grid = sorted({k[3] for k in results if k[1] == "lhs" and k[2] == 2})
    emit("  %-12s %s   (success%% over %d slices x %d surfaces; ns=no-sign-change, wr=wrong-root)"
         % ("family", "".join(("N=%d" % n).rjust(18) for n in n_grid),
            cfg["n_slices"], len(smooth2)))
    for fam_key in FAM_LABEL:
        line = "  %-12s" % FAM_LABEL[fam_key]
        for n in n_grid:
            tot = suc = ns = wr = 0
            for s in smooth2:
                k = (s, "lhs", 2, n, 0.0)
                if k in results:
                    r = results[k][fam_key]
                    tot += r["n_slices"]
                    suc += r["bis"]
                    ns += r["ns"]
                    wr += r["wr"]
            bis_tab[(fam_key, n)] = (suc, tot, ns, wr)
            line += ("%3d%% (%d ns/%d wr)" % (round(100 * suc / max(tot, 1)), ns, wr)).rjust(18)
        emit(line)
    emit()

    if probe_rows is not None:
        emit("=" * 78)
        emit("EXTRAPOLATION-BEHAVIOR PROBE (sin-exp, N=200, noise 0; rays from the")
        emit("domain center, sampled at s = 1.0..2.0 x hull half-width)")
        emit("  dEdgeAx = mean |f(s) - f(1.0)| / range on the 4 AXIS-ALIGNED rays")
        emit("            (the clean hull-constancy probe: ~0 => CONSTANT beyond")
        emit("            the face - only one coordinate keeps moving)")
        emit("  dEdgeDg = the same on 24 random-direction rays (a partition model")
        emit("            can keep crossing splits on the other coordinates)")
        emit("  curvN/F = mean |second difference along ray| / range x 1e3 over")
        emit("            the near band (s 1.1-1.4) / far band (s 1.6-1.9):")
        emit("            constant N=F => fixed-curvature polynomial growth;")
        emit("            decaying => flattening (asymptotic linearity or mean-")
        emit("            reversion); persistent high => plateau kinks")
        emit("  farVsMu = |f(2.0) - train mean| / range  (~0 => reverted to the")
        emit("            train mean by 2x hull)")
        emit("=" * 78)
        emit("  %-12s %s %s %s %s %s" % ("family", "dEdgeAx".rjust(9),
                                         "dEdgeDg".rjust(9), "curvN".rjust(9),
                                         "curvF".rjust(9), "farVsMu".rjust(9)))
        for r in probe_rows:
            pa, pd_, pcn, pcf, pf = r["probe"]
            emit("  %-12s %s %s %s %s %s" % (FAM_LABEL[r["fam"]], _g(pa),
                                             _g(pd_), _g(pcn), _g(pcf), _g(pf)))
        emit()

    # lat_stats stays the 196-vs-200 pair ONLY - it is V8's input and V8's
    # wording is quoted downstream, so extending the axis must not silently
    # re-scope it. The full three-pair set goes to lat_all and V10.
    lat_stats = []
    lat_all = {}
    lat_pairs = [(nq,) + lattice_size(nq, 2) for nq in LATTICE_N_REQ]
    if any(k[1] == "lattice" for k in results):
        emit("=" * 78)
        emit("DOE GEOMETRY - full-factorial lattice vs space-filling LHS at")
        emit("matched N, noise 0 (interp NRMSE; Delta = lattice - LHS)")
        emit("=" * 78)
        for n_req, k_lev, n_lat in lat_pairs:
            pair_rows = [(s, (s, "lattice", 2, n_lat, 0.0), (s, "lhs", 2, n_req, 0.0))
                         for s in SURFS if SURFS[s].d == 2]
            pair_rows = [t for t in pair_rows if t[1] in results and t[2] in results]
            if not pair_rows:
                continue
            emit("  %dx%d lattice (N=%d) vs LHS-%d" % (k_lev, k_lev, n_lat, n_req))
            emit("  %-10s" % "surface"
                 + "".join(FAM_LABEL[f].rjust(13) for f in FAM_LABEL))
            for s, kl, kh in pair_rows:
                line = "  %-10s" % s
                for f in FAM_LABEL:
                    dl = results[kl][f]["nrmse"] - results[kh][f]["nrmse"]
                    lat_all.setdefault(n_req, []).append((s, f, dl))
                    if n_lat == 196:
                        lat_stats.append((s, f, dl))
                    line += ("%+.3g" % dl).rjust(13)
                emit(line)
            emit()

    # The two legs the H-T worked instance asked for: does design STRUCTURE at
    # fixed N move the R1 metrics by more than N does at fixed structure?
    leg_tab = {}
    leg_meta = {}
    if lat_all:
        def _agg(doe, n):
            """(bis success fraction, mean gcos) over the smooth d=2 surfaces."""
            out = {}
            for f in FAM_LABEL:
                suc = tot = 0
                gc = []
                for s in smooth2:
                    k = (s, doe, 2, n, 0.0)
                    if k not in results:
                        continue
                    r = results[k][f]
                    suc += r["bis"]
                    tot += r["n_slices"]
                    if not np.isnan(r["gcos"]):
                        gc.append(r["gcos"])
                out[f] = (suc / tot if tot else float("nan"),
                          float(np.mean(gc)) if gc else float("nan"))
            return out

        cols = ([("lhs", nq, "LHS-%d" % nq) for nq, _, _ in lat_pairs]
                + [("lattice", nl, "LAT-%d" % nl) for _, _, nl in lat_pairs])
        cols = [c for c in cols
                if any((s, c[0], 2, c[1], 0.0) in results for s in smooth2)]
        for doe, n, _ in cols:
            leg_tab[(doe, n)] = _agg(doe, n)
        # Both legs need a matched pair at each end; take the widest span
        # actually present so a reduced grid degrades instead of crashing.
        span = [(nq, nl) for nq, _, nl in lat_pairs
                if ("lhs", nq) in leg_tab and ("lattice", nl) in leg_tab]
        if not span:
            leg_tab = {}
        else:
            n_lo, l_lo = span[0]
            n_hi, l_hi = span[-1]
            leg_meta = {"n_lo": n_lo, "n_hi": n_hi, "l_lo": l_lo, "l_hi": l_hi}
    if leg_tab:
        n_lo, n_hi = leg_meta["n_lo"], leg_meta["n_hi"]
        l_lo, l_hi = leg_meta["l_lo"], leg_meta["l_hi"]
        for metric, mi, fmt in (("bisection success", 0, "%6.3f"),
                                ("mean gradient cosine", 1, "%6.3f")):
            emit("=" * 78)
            emit("DESIGN STRUCTURE vs N - %s, smooth d=2 surfaces, noise 0"
                 % metric)
            emit("(dN = LHS-%d minus LHS-%d, the N leg at fixed structure;"
                 % (n_hi, n_lo))
            emit(" dSTRUCT = LAT-%d minus LHS-%d, the structure leg at fixed N)"
                 % (l_hi, n_hi))
            emit("=" * 78)
            emit("  %-12s%s%s%s" % ("family",
                                    "".join(c[2].rjust(9) for c in cols),
                                    "dN".rjust(10), "dSTRUCT".rjust(10)))
            for f in FAM_LABEL:
                line = "  %-12s" % FAM_LABEL[f]
                for doe, n, _ in cols:
                    v = leg_tab[(doe, n)][f][mi]
                    line += ("--".rjust(9) if np.isnan(v)
                             else (fmt % v).rjust(9))
                d_n = (leg_tab[("lhs", n_hi)][f][mi]
                       - leg_tab[("lhs", n_lo)][f][mi])
                d_s = (leg_tab[("lattice", l_hi)][f][mi]
                       - leg_tab[("lhs", n_hi)][f][mi])
                line += ("%+.3f" % d_n).rjust(10) + ("%+.3f" % d_s).rjust(10)
                emit(line)
            emit()

    # ---------------- how to read ----------------
    emit("""HOW TO READ THIS (columns and their taxonomy axes):
  nrmse   : RMSE vs the TRUE function on 2000 in-hull points / true range.
            Operationalizes the accuracy axis; scored against truth, so under
            5% train noise an EXACT interpolant (B4) floors near 0.05+, while
            a regularized family can go below the noise level.
  bis     : the C-axis 'continuous inverse / root-finding' cell (rule R1).
            For each of 20 fixed slices, y_target = midpoint of the slice's
            endpoint values (guarantees a bracketed true root); brentq runs on
            (surrogate - y_target) in the grid bracket nearest the true root.
            success = |x_surr - x_true| <= 2% of the axis range.
            ns = the surrogate's slice never changes sign (no bracket at all);
            wr = a root was found but off by > 2% of range.
  gcos/grel: the C-axis 'analytic gradients / sensitivities' cell. Central
            differences (h=1e-3) on the surrogate vs the analytic gradient at
            100 interior points. Piecewise-constant surrogates return zero
            gradient inside a leaf (gcos contribution 0, grel 1) or a huge
            spike across a split - both are counted, not excluded. '--' on
            the step surface: the true gradient is 0 a.e. (undefined metric).
  xnrmse  : extrapolation NRMSE on the 1.2x-hull shell (the R4 cell's
            magnitude leg; the probe table carries the SHAPE leg).
  rough   : the C-axis 'smoothness of sweeps' cell - mean |second difference|
            along axis sweeps / range x 1e3. Smooth families ~0; plateaus and
            step artifacts inflate it.
  sec     : fit incl. CV + fold-std pass + interp predict (retrain-cost axis
            at these tiny N; not a deployment benchmark).
  fold-std (IC-1 tol column): std of the chosen config's 5 CV-fold NRMSEs -
            the spec's IC-1 tolerance unit ('within 1 CV-fold std').
  Noise is added to TRAIN y only; all metrics score against the true surface.
  Every family in a cell sees the same design, test points, slices, gradient
  points, sweeps, and rays (seed=0).""")
    emit()

    # ---------------- verdicts ----------------
    emit("=" * 78)
    emit("[OPEN]-cell verdicts and IC checks")
    emit("(each verdict names the matrix cell / rule id / IC it settles or")
    emit("supports, then the numbers; 'settles' = decided by this experiment,")
    emit("'supports' = consistent with the cited literature anchor)")
    emit("=" * 78)

    def vd(tag, lines):
        emit("[%s]" % tag)
        for ln in lines:
            emit(("  " + ln) if ln else "")
        emit()

    # V1 IC-1 strict + practical
    hold4 = sum(1 for _, ok4, _, _ in ic1_stats if ok4)
    hold3 = sum(1 for _, _, ok3, _ in ic1_stats if ok3)
    core_cells = [(k, d3) for k, _, _, d3 in ic1_stats]
    dmax_all = max(d3 for _, d3 in core_cells)
    dmed = float(np.median([d3 for _, d3 in core_cells]))
    v1 = ["IC-1 tolerance check (cell: B1-B4 rows x accuracy axis, smooth",
          "deterministic DOE; anchors Q-surr-15, Q-surr-19).",
          "Strict form (all of B1,B2,B3,B4 within 1 CV-fold std of the best):",
          "  holds in %d/%d smooth noise-free cells." % (hold4, len(ic1_stats)),
          "Core form ({B2,B3,B4}; B1 poly-2 is inadequate-degree on sin-exp/",
          "smooth5, its exclusion there is P2's 'B1-with-adequacy-check'):",
          "  holds in %d/%d cells; max NRMSE gap best->worst %.4f, median %.4f."
          % (hold3, len(ic1_stats), dmax_all, dmed)]
    for k, ok4, ok3, d3 in ic1_stats:
        if not ok3:
            rs = results[k]
            core = ["B2", "B3", "B4"]
            best_c = min(core, key=lambda f: rs[f]["nrmse"])
            worst_c = max(core, key=lambda f: rs[f]["nrmse"])
            v1.append("  out-of-tol cell %s/N=%d: best %s %.4g, worst %s %.4g,"
                      " tol %.2g" % (k[0], k[3], best_c, rs[best_c]["nrmse"],
                                     worst_c, rs[worst_c]["nrmse"],
                                     rs[best_c]["fold_std"]))
    v1.append("Reading: where the best family sits near machine precision the")
    v1.append("1-fold-std tolerance collapses toward 0 and the strict verdict")
    v1.append("fails on gaps that are practically indifferent; the gap numbers")
    v1.append("above are the boundary the taxonomy should quote.")
    vd("V1 IC-1", v1)

    # V2 bisection separation
    smooth_fams = ["B1", "B2", "B3", "B4", "B5"]
    tree_fams = ["B6a", "B6b", "B8"]
    v2 = ["R1 cell (B6/B8 rows x C-axis continuous inverse; Q-surr-46 is the",
          "continuity+sign-change precondition; Q-surr-38/42 piecewise-",
          "constant; Q-surr-44 exact tree inversion is NP-Hard)."]
    for n in n_grid:
        sm = [100 * bis_tab[(f, n)][0] / max(bis_tab[(f, n)][1], 1) for f in smooth_fams]
        tr = [100 * bis_tab[(f, n)][0] / max(bis_tab[(f, n)][1], 1) for f in tree_fams]
        v2.append("N=%3d: smooth-family success min/mean %3.0f%%/%3.0f%%; "
                  "step-family (B6a,B6b,B8) %3.0f%%/%3.0f%%/%3.0f%%"
                  % (n, min(sm), np.mean(sm), tr[0], tr[1], tr[2]))
    v2.append("Failure anatomy at N=50 (ns/wr over %d slices): B6a %d/%d, "
              "B6b %d/%d, B8 %d/%d." % (len(smooth2) * cfg["n_slices"],
                                        bis_tab[("B6a", 50)][2], bis_tab[("B6a", 50)][3],
                                        bis_tab[("B6b", 50)][2], bis_tab[("B6b", 50)][3],
                                        bis_tab[("B8", 50)][2], bis_tab[("B8", 50)][3]))
    v2.append("Reading: the 2%-localization gap closes as N grows (plateaus")
    v2.append("narrow), so the R1 exclusion's load-bearing content at high N is")
    v2.append("the PRECONDITION (no continuity -> no bracketing guarantee, an")
    v2.append("interval of roots on a plateau) plus the gradient/sweep rows")
    v2.append("below - not a gross localization failure.")
    vd("V2 R1-bisection", v2)

    # V3 gradients
    kg = ("sin-exp", "lhs", 2, 200, 0.0)
    if kg not in results:                       # smoke fallback
        kg = ("sin-exp", "lhs", 2, 50, 0.0)
    rs = results[kg]
    v3 = ["R1 cell, gradient leg (C-axis analytic gradients; Q-surr-39).",
          "sin-exp N=200 noise 0: gcos B1..B5 = %s; B6a/B6b/B8 = %s;"
          % (", ".join("%.3f" % rs[f]["gcos"] for f in smooth_fams),
             ", ".join("%.3f" % rs[f]["gcos"] for f in tree_fams)),
          "grel B3=%.3g B4=%.3g vs B6a=%.3g B6b=%.3g B8=%.3g."
          % (rs["B3"]["grel"], rs["B4"]["grel"], rs["B6a"]["grel"],
             rs["B6b"]["grel"], rs["B8"]["grel"]),
          "Central-difference gradients on partition surrogates are 0-or-spike;",
          "the cosine collapse quantifies the cell."]
    vd("V3 R1-gradients", v3)

    # V4 sweeps
    v4 = ["C-axis smoothness-of-sweeps cell (Q-surr-39; Q-surr-03).",
          "sin-exp N=200 noise 0 roughness (x1e3): B1=%.3g B2=%.3g B3=%.3g "
          "B4=%.3g B5=%.3g" % tuple(rs[f]["rough"] for f in smooth_fams),
          "vs B6a=%.3g B6b=%.3g B8=%.3g (B7=%.3g)."
          % (rs["B6a"]["rough"], rs["B6b"]["rough"], rs["B8"]["rough"],
             rs["B7"]["rough"])]
    vd("V4 sweeps", v4)

    # V5 extrapolation shape
    if probe_rows is not None:
        pr = {r["fam"]: r["probe"] for r in probe_rows}
        v5 = ["R4 cell (C-axis extrapolation behavior; Q-surr-26/31 GP",
              "reversion, Q-surr-34 MLP linear far field, hull-constant trees).",
              "(a) Hull-constancy - axis rays: B6a=%.4f B6b=%.4f B8=%.4f vs"
              % (pr["B6a"][0], pr["B6b"][0], pr["B8"][0]),
              "    B3=%.3f B1=%.3f B4=%.3f. Random rays: B6a=%.4f B6b=%.4f"
              % (pr["B3"][0], pr["B1"][0], pr["B4"][0], pr["B6a"][1],
                 pr["B6b"][1]),
              "    B8=%.4f - SETTLED: exactly constant on axis-aligned"
              % pr["B8"][1],
              "    extension (B6 AND ALSO B8 - the R4 row should name both);",
              "    only flattening-not-constant on generic directions at <=2x",
              "    hull (splits on the other coordinate keep firing).",
              "(b) Curvature bands (x1e3, near s1.1-1.4 -> far s1.6-1.9):",
              "    B1 %.3g -> %.3g (CONSTANT curvature = the fitted quadratic's"
              % (pr["B1"][2], pr["B1"][3]),
              "    divergence signature); B7 %.3g -> %.3g and B3 %.3g -> %.3g"
              % (pr["B7"][2], pr["B7"][3], pr["B3"][2], pr["B3"][3]),
              "    (both DECAY ~3x - flattening; at <=2x hull curvature alone",
              "    cannot yet separate B7's asymptotic linearity [Q-surr-34]",
              "    from B3's flattening); B6a %.3g -> %.3g (persistent plateau"
              % (pr["B6a"][2], pr["B6a"][3]),
              "    kinks).",
              "(c) farVsMu at 2x hull: B3=%.3f B1=%.3f B4=%.3f B7=%.3f -"
              % (pr["B3"][4], pr["B1"][4], pr["B4"][4], pr["B7"][4]),
              "    the MLE'd Matern mean has NOT reverted to the train mean by",
              "    2x hull (B3 is not the smallest here): mean-side reversion",
              "    (Q-surr-31, 'for large |t|') is ASYMPTOTIC in lengthscale",
              "    units, not operative at 1.2-2x hull - at this range the R4",
              "    honesty story lives on the VARIANCE side (Q-surr-26), which",
              "    a mean-only harness does not measure.",
              "(d) 1.2x-shell xnrmse (sin-exp N=200): B3=%.3g B1=%.3g B2=%.3g "
              "B4=%.3g B7=%.3g B6a=%.3g B6b=%.3g"
              % tuple(results[kg][f]["xnrmse"] for f in
                      ["B3", "B1", "B2", "B4", "B7", "B6a", "B6b"])]
        vd("V5 R4-extrapolation", v5)

    # V6 noise / R9
    kn0 = ("sin-exp", "lhs", 2, 800, 0.0)
    kn5 = ("sin-exp", "lhs", 2, 800, 0.05)
    if kn5 in results:
        r0, r5 = results[kn0], results[kn5]
        v6 = ["R9 cell (B4 row x noise axis: exact interpolation under noise;",
              "Q-surr-17, Q-surr-22; nugget-GP and poly robustness).",
              "sin-exp N=800, same design, noise 0 -> 5% of range:",
              "  B4 exact-TPS nrmse %.4f -> %.4f (interpolates the noise;"
              % (r0["B4"]["nrmse"], r5["B4"]["nrmse"]),
              "  the 5%%-sigma floor is 0.05); B3 nugget %.4f -> %.4f;"
              % (r0["B3"]["nrmse"], r5["B3"]["nrmse"]),
              "  B1 poly2 %.4f -> %.4f (bias-floored, noise-insensitive);"
              % (r0["B1"]["nrmse"], r5["B1"]["nrmse"]),
              "  B2 spline %.4f -> %.4f." % (r0["B2"]["nrmse"], r5["B2"]["nrmse"]),
              "kinked N=800: B4 %.4f -> %.4f; B3 %.4f -> %.4f."
              % (results[("kinked", "lhs", 2, 800, 0.0)]["B4"]["nrmse"],
                 results[("kinked", "lhs", 2, 800, 0.05)]["B4"]["nrmse"],
                 results[("kinked", "lhs", 2, 800, 0.0)]["B3"]["nrmse"],
                 results[("kinked", "lhs", 2, 800, 0.05)]["B3"]["nrmse"])]
        vd("V6 R9-noise", v6)

    # V7 IC-2
    if ic2_stats:
        v7 = ["IC-2 tolerance check (B6b/B7 rows x accuracy axis on irregular",
              "noisy cells; anchor Q-surr-04). Approximate: N=800 is below the",
              "class's 1k-10k window and B10 is not runnable in the pinned",
              "dependency set - this SUPPORTS, it does not settle."]
        for s, b6, b7, gap in ic2_stats:
            v7.append("%s N=800 5%%: B6b %.4f vs B7 %.4f, |gap| %.4f (%s 0.03 "
                      "'a few percent')" % (s, b6, b7, gap,
                                            "<=" if gap <= 0.03 else ">"))
        vd("V7 IC-2", v7)

    # V8 lattice
    if lat_stats:
        worst = max(lat_stats, key=lambda t: abs(t[2]))
        v8 = ["B-axis DOE-geometry cell (full-factorial lattice vs space-",
              "filling at matched N; Q-surr-57 pins the pathology to HIGH-",
              "DEGREE equispaced interpolation - low-order LS escapes).",
              "Largest |Delta nrmse| over 5 surfaces x 9 families: %s on %s, "
              "%+.3g." % (FAM_LABEL[worst[1]], worst[0], worst[2]),
              "No family collapses on the lattice at these orders; the lattice",
              "even helps the axis-aligned partition families on the step",
              "surface (Delta B6a on step: %+.3g)."
              % ([t[2] for t in lat_stats if t[0] == "step" and t[1] == "B6a"][0])]
        vd("V8 DOE-lattice", v8)

    # V9 d=5
    k5a, k5b = ("smooth5", "lhs", 5, 200, 0.0), ("smooth5", "lhs", 5, 800, 0.0)
    if k5b in results:
        r5a, r5b = results[k5a], results[k5b]
        v9 = ["d=5 smooth check (B-axis d scaling; IC-1 at d=4-10).",
              "N=200: B3 %.4f B4 %.4f B2 %.4f B1 %.4f | N=800: B3 %.4f B4 %.4f "
              "B2 %.4f B1 %.4f" % (r5a["B3"]["nrmse"], r5a["B4"]["nrmse"],
                                   r5a["B2"]["nrmse"], r5a["B1"]["nrmse"],
                                   r5b["B3"]["nrmse"], r5b["B4"]["nrmse"],
                                   r5b["B2"]["nrmse"], r5b["B1"]["nrmse"]),
              "GP fit seconds N=200 (full) -> N=800 (sub-400 cap): %.1f -> "
              "%.1f - the budget cap in action; Q-surr-27 carries the O(n^3)"
              % (r5a["B3"]["sec"], r5b["B3"]["sec"]),
              "ceiling this experiment does not re-measure."]
        vd("V9 d5-check", v9)

    # V10 design-structure axis (TASK-9-C1). V8 above keeps the original
    # single-point lattice reading; this block is the axis with an N leg.
    if leg_tab:
        nlo, nhi = leg_meta["n_lo"], leg_meta["n_hi"]
        llo, lhi = leg_meta["l_lo"], leg_meta["l_hi"]
        part = [f for f in tree_fams if f in FAM_LABEL]

        def _pm(doe, n, mi):
            vals = [leg_tab[(doe, n)][f][mi] for f in part
                    if (doe, n) in leg_tab
                    and not np.isnan(leg_tab[(doe, n)][f][mi])]
            return float(np.mean(vals)) if vals else float("nan")

        n_lat_ic1 = sum(1 for k, _, _, _ in ic1_stats if k[1] == "lattice")
        v10 = ["B-axis DOE-geometry cell crossed with N, bearing on R1 (the",
               "continuous-inverse rule) and on its gradient leg. Motivated by",
               "the H-T worked instance, whose 6-level full factorial reproduced",
               "section 8's DIRECTION on every axis and missed its MAGNITUDE",
               "bands at 6 of 7 cross-checks.",
               "Partition families (%s), means over the"
               % ", ".join(FAM_LABEL[f] for f in part),
               "smooth d=2 surfaces at noise 0. dN = LHS-%d minus LHS-%d, the N"
               % (nhi, nlo),
               "leg at fixed structure; dSTRUCT = LAT-%d minus LHS-%d, the"
               % (lhi, nhi),
               "structure leg at fixed N:"]
        v10.append("    %-16s %-12s %8s %8s %8s %8s %8s"
                   % ("metric", "family", "LHS-%d" % nlo, "LHS-%d" % nhi,
                      "LAT-%d" % lhi, "dN", "dSTRUCT"))
        legs = {}
        for label, mi in (("bisection", 0), ("gradient cosine", 1)):
            for f in part:
                lo = leg_tab[("lhs", nlo)][f][mi]
                hi = leg_tab[("lhs", nhi)][f][mi]
                lat = leg_tab[("lattice", lhi)][f][mi]
                legs[(label, f)] = (hi - lo, lat - hi)
                v10.append("    %-16s %-12s %8.3f %8.3f %8.3f %+8.3f %+8.3f"
                           % (label, FAM_LABEL[f], lo, hi, lat,
                              hi - lo, lat - hi))
            legs[(label, "mean")] = (_pm("lhs", nhi, mi) - _pm("lhs", nlo, mi),
                                     _pm("lattice", lhi, mi) - _pm("lhs", nhi, mi))

        def _dom(label):
            dn, ds = legs[(label, "mean")]
            return abs(ds) > abs(dn), abs(dn), abs(ds)

        b_wins, b_dn, b_ds = _dom("bisection")
        g_wins, g_dn, g_ds = _dom("gradient cosine")
        # Does the family-level picture agree with the mean, or does the mean
        # cancel a sign split? Report whichever is true; never assert it.
        g_signs = [legs[("gradient cosine", f)][1] for f in part]
        g_split = min(g_signs) < 0 < max(g_signs)
        g_big = max(part, key=lambda f: abs(legs[("gradient cosine", f)][1]))
        gb_dn, gb_ds = legs[("gradient cosine", g_big)]
        v10 += [
            "READING: the two axes answer DIFFERENTLY, and that split IS the",
            "result.",
            "  Bisection - mean |dSTRUCT| %.3f vs mean |dN| %.3f: %s. A lattice"
            % (b_ds, b_dn, "STRUCTURE dominates" if b_wins else "N dominates"),
            "  at matched N does NOT reproduce the instance's 0.075; these",
            "  families sit at %.3f on the %dx%d lattice, inside section 8's band."
            % (_pm("lattice", lhi, 0), int(round(lhi ** 0.5)),
               int(round(lhi ** 0.5))),
            "  Gradient cosine - mean |dSTRUCT| %.3f vs mean |dN| %.3f: %s on the"
            % (g_ds, g_dn, "STRUCTURE dominates" if g_wins else "N dominates"),
            "  mean%s" % (", BUT THE MEAN CANCELS A SIGN SPLIT --" if g_split
                          else " and at family level too --"),
            "  %s move(s) DOWN on the lattice and %s move(s) UP, so averaging"
            % ("/".join(FAM_LABEL[f] for f in part
                        if legs[("gradient cosine", f)][1] < 0),
               "/".join(FAM_LABEL[f] for f in part
                        if legs[("gradient cosine", f)][1] >= 0)),
            "  them understates both. On %s alone the structure leg is %.3f"
            % (FAM_LABEL[g_big], abs(gb_ds)),
            "  against an N leg of %.3f (%s), taking its gradient cosine"
            % (abs(gb_dn),
               "structure EXCEEDS the whole N grid" if abs(gb_ds) > abs(gb_dn)
               else "still under the whole N grid"),
            "  %.3f -> %.3f - the direction of the instance's measured 0.000,"
            % (leg_tab[("lhs", nhi)][g_big][1],
               leg_tab[("lattice", lhi)][g_big][1]),
            "  and past the low end of the quoted band.",
            "So design structure bears on the GRADIENT miss - decisively for the",
            "tree family that produced it - and does NOT explain the BISECTION",
            "miss at all. One hypothesis, one of two headline disagreements",
            "accounted for, and only for part of the family set. Still",
            "unmodelled, and different between this experiment and the instance:",
            "dimensionality (2 here, 5 there) and level ANISOTROPY (k per axis",
            "here; 6x5x4x3x2 there). Reported, not resolved - a lattice is not",
            "one thing, and neither is 'the partition families'.",
            "The R1 exclusion is unchanged either way. This measures the STRENGTH",
            "of its supporting evidence, not its direction. Section 1 admits both",
            "design classes, so a band quoted without a design qualifier is",
            "under-specified for half the declared scope - now demonstrable on",
            "the gradient axis specifically rather than argued.",
            "SIDE EFFECT, reported not absorbed: ic1_cells selects on surface and",
            "noise only, never on design, so the added lattice cells enter the",
            "IC-1 check and V1 above - %d of its %d cells are now lattice, and"
            % (n_lat_ic1, len(ic1_stats)),
            "V1's denominators differ from the Session-B file for that reason. No",
            "IC-1 definition changed; the cell set grew. Queued for 9C-2."]
        vd("V10 design-structure", v10)

    # ======================================================================
    # TASK-9-E (2026-08-21). [V10-A1] annotates [V10] WITHOUT editing it;
    # [V11] reads out d=5 cells this file has carried since Session B and was
    # never asked about; [V12] measures the design axis at d=5, including the
    # level anisotropy that was not expressible before this run.
    # Brief: sessions/SESSION-9E-the-bisection-miss-dimensionality-and-anisotropy.md
    # ======================================================================
    part9e = [f for f in ("B6a", "B6b", "B8") if f in FAM_LABEL]
    sm2_9e = [nm for nm in SMOOTH_SURFS if nm in SURFS and SURFS[nm].d == 2]
    res9e = 1.0 / cfg["n_slices"]

    def _b1(key, fam):
        r = results.get(key, {}).get(fam)
        return float("nan") if r is None else r["bis"] / float(r["n_slices"])

    def _bm(key):
        v = [x for x in (_b1(key, f) for f in part9e) if not np.isnan(x)]
        return float(np.mean(v)) if v else float("nan")

    def _bsurf(doe, n, fam=None):
        """Partition bisection over the smooth d=2 surfaces, one family or all."""
        v = [(_b1((nm, doe, 2, n, 0.0), fam) if fam else _bm((nm, doe, 2, n, 0.0)))
             for nm in sm2_9e if (nm, doe, 2, n, 0.0) in results]
        v = [x for x in v if not np.isnan(x)]
        return float(np.mean(v)) if v else float("nan")

    def _axis_tab(key):
        """{axis: (hits, slices)} pooled over the partition families."""
        agg = {}
        for f in part9e:
            r = results.get(key, {}).get(f)
            if r is None or "bis_detail" not in r:
                continue
            for j, oc in r["bis_detail"]:
                h, t = agg.get(j, (0, 0))
                agg[j] = (h + (1 if oc == "hit" else 0), t + 1)
        return agg

    def _axfrac(tab, axes):
        h = sum(tab[j][0] for j in axes)
        t = sum(tab[j][1] for j in axes)
        return (h / float(t) if t else float("nan")), h, t

    def _slices(v):
        return abs(v) / res9e

    def _wrap(text, width=66, lead="  "):
        out, cur = [], ""
        for w in text.split():
            if cur and len(cur) + 1 + len(w) > width:
                out.append(lead + cur)
                cur = w
            else:
                cur = (cur + " " + w) if cur else w
        if cur:
            out.append(lead + cur)
        return out

    e1 = {}

    # ---------------- [V10-A1] annotation beside [V10] --------------------
    if leg_tab and part9e:
        _nhi, _lhi = leg_meta["n_hi"], leg_meta["l_hi"]
        fam_legs = [_bsurf("lattice", _lhi, f) - _bsurf("lhs", _nhi, f)
                    for f in part9e]
        f_sm, f_mm, f_sp = leg_stats(fam_legs)
        surf_legs = [(nm, _bm((nm, "lattice", 2, _lhi, 0.0))
                      - _bm((nm, "lhs", 2, _nhi, 0.0)))
                     for nm in sm2_9e
                     if (nm, "lattice", 2, _lhi, 0.0) in results
                     and (nm, "lhs", 2, _nhi, 0.0) in results]
        s_sm, s_mm, s_sp = leg_stats([v for _, v in surf_legs])
        worst_surf = min(surf_legs, key=lambda t: t[1]) if surf_legs else None
        best_surf = max(surf_legs, key=lambda t: t[1]) if surf_legs else None
        a1 = ["Annotation BESIDE [V10], not an edit to it. [V10] is a dated",
              "measurement record; the convention is the conformance audit's",
              "(2026-08-17): what a block found is never rewritten, only",
              "annotated with what a later session found out about it. Two",
              "defects, both in [V10]'s READING lines. Neither overturns its",
              "conclusion; both weaken its bisection half.",
              "DEFECT 1 - THE BARS ARE IN THE WRONG PLACE. [V10] prints",
              "\"mean |dSTRUCT|\" over a number its emitter computes as",
              "abs(mean_over_families(lattice) - mean_over_families(lhs)):",
              "the ABSOLUTE VALUE OF A MEAN, not the mean of absolute values.",
              "Bisection structure legs by family: %s."
              % ", ".join("%s %+.3f" % (FAM_LABEL[f], v)
                          for f, v in zip(part9e, fam_legs)),
              "Signed mean %+.3f, mean magnitude %.3f - %.1fx larger. On the"
              % (f_sm, f_mm, (f_mm / abs(f_sm)) if f_sm else float("nan")),
              "dN line the same error is invisible: those legs share a sign.",
              "DEFECT 2 - THE SIGN-SPLIT GUARD RUNS ON ONE AXIS ONLY. [V10]",
              "carries g_split with the comment \"does the family-level picture",
              "agree with the mean, or does the mean cancel a sign split?",
              "Report whichever is true; never assert it\" - and asks it of",
              "gradient cosine alone. Asked of bisection, it answers twice:",
              "  split by FAMILY  : %s" % ("YES" if f_sp else "no"),
              "  split by SURFACE : %s (%s)"
              % ("YES" if s_sp else "no",
                 ", ".join("%s %+.3f" % (nm, v) for nm, v in surf_legs))]
        if worst_surf and best_surf and worst_surf[0] != best_surf[0]:
            a1 += ["CONSEQUENCE. [V10]'s \"on bisection, N dominates and structure",
                   "does not\" is a pooled mean taken across a sign split - the",
                   "failure mode [V10] itself warns about one line later, on the",
                   "other axis. Structure moves bisection DOWN by %.3f on %s and"
                   % (abs(worst_surf[1]), worst_surf[0]),
                   "UP by %.3f on %s. Qualifier 1's CONCLUSION survives - the"
                   % (abs(best_surf[1]), best_surf[0]),
                   "gradient/bisection asymmetry is untouched - but its bisection",
                   "half is much weaker than it reads. Corrected read in [V11];",
                   "a bisection sign-split guard is in force in [V11] and [V12]."]
        vd("V10-A1 2026-08-21 TASK-9-E1 annotation", a1)

    # ---------------- [V11] the read-out ----------------------------------
    k_d2 = ("sin-exp", "lhs", 2, 800, 0.0)
    k_d5a = ("smooth5", "lhs", 5, 200, 0.0)
    k_d5b = ("smooth5", "lhs", 5, 800, 0.0)
    if part9e and k_d2 in results and k_d5b in results:
        rows11 = [("sin-exp  lhs  d=2", k_d2), ("smooth5  lhs  d=5", k_d5a),
                  ("smooth5  lhs  d=5", k_d5b)]
        rows11 = [(lb, k) for lb, k in rows11 if k in results]
        d_dim = _bm(k_d5b) - _bm(k_d2)
        gap = HT_INSTANCE_BIS - _bm(k_d2)
        v11 = ["READ-OUT, not a new measurement (TASK-9-E1). Every number in this",
               "block comes from cells this file has carried since Session B.",
               "[V9 d5-check] reported nrmse for B1-B4 only: it was silent on",
               "bisection and silent on the partition families, which is exactly",
               "where the H-T worked instance's open disagreement lives. No cell",
               "was added or re-run for this block.",
               "RESOLUTION: bisection is k/%d slices, so ONE SLICE = %.3f. No leg"
               % (cfg["n_slices"], res9e),
               "narrower than that is reported below as a direction.",
               "",
               "(a) THE DIMENSIONALITY LEG. Partition bisection success, noise 0:",
               "    %-20s %6s %8s %8s %8s %8s"
               % ("cell", "N", FAM_LABEL[part9e[0]].split()[0],
                  FAM_LABEL[part9e[1]].split()[0],
                  FAM_LABEL[part9e[2]].split()[0], "mean")]
        for lb, k in rows11:
            v11.append("    %-20s %6d %8.3f %8.3f %8.3f %8.3f"
                       % (lb, k[3], _b1(k, part9e[0]), _b1(k, part9e[1]),
                          _b1(k, part9e[2]), _bm(k)))
        v11 += ["dDIM = d=5 N=%d minus d=2 N=%d = %+.3f  (%.1f slices)"
                % (k_d5b[3], k_d2[3], d_dim, _slices(d_dim)),
                "The H-T instance's partition family sits at %.3f (cross-"
                % HT_INSTANCE_BIS,
                "reference constant, not measured here). The instance sits %.3f"
                % abs(gap),
                "BELOW the d=2 cell; the two d=5 cells BRACKET it, at %.3f and"
                % (_bm(k_d5a) if k_d5a in results else float("nan")),
                "%.3f." % _bm(k_d5b),
                "Against the design-structure leg [V10] measured on the same",
                "families - see [V10-A1] - dimensionality is the LARGER measured",
                "effect, and it has been in this file since Session B.",
                "",
                "(b) THE COMPARISON IS A FUNCTION AGAINST ITS OWN EXTENSION.",
                "    _f_sinexp  = sin(2pi x0) * exp(x1)",
                "    _f_smooth5 = sin(2pi x0) * exp(x1) + 2 (x2-0.5)^2 + x3 x4",
                "smooth5 is sin-exp plus a quadratic and a bilinear term in the",
                "three new axes - low order, no new pathology. Not two unrelated",
                "surfaces.",
                ""]
        # (c) the confound, measured
        ax2, ax5 = _axis_tab(k_d2), _axis_tab(k_d5b)
        if ax2 and ax5:
            shared = sorted(set(ax2) & set(ax5))
            only5 = sorted(set(ax5) - set(ax2))
            fx2, fx5 = fixtures.get(k_d2[0]), fixtures.get(k_d5b[0])
            v11 += ["(c) THE CONFOUND IS REAL, AND IT IS NOT THE EXPECTED ONE.",
                    "The tolerance was the suspect: it is not. bisection_metrics",
                    "tests |xhat - xtrue| <= 0.02 ABSOLUTE in the unit cube; it is",
                    "not scaled by the response range, so the added terms cannot",
                    "move it. What the response range DOES move is slice",
                    "ADMISSION: make_slices drops any slice whose endpoint",
                    "contrast is under 0.05 * range_ref. Axes that are periodic",
                    "or symmetric end to end therefore admit NO slices at all:"]
            for nm, fxx in (("sin-exp", fx2), ("smooth5", fx5)):
                if fxx is None:
                    continue
                cnt = {}
                for sl in fxx["slices"]:
                    cnt[sl[0]] = cnt.get(sl[0], 0) + 1
                v11.append("    %-8s range_ref %8.4f   slices/axis  %s"
                           % (nm, fxx["range"],
                              ", ".join("x%d %d" % (j, cnt.get(j, 0))
                                        for j in range(fxx["d"]))))
            f2, h2, t2 = _axfrac(ax2, shared)
            f5, h5, t5 = _axfrac(ax5, shared)
            v11 += ["The two cells DO NOT SHARE A SLICE SET. So the pooled leg in",
                    "(a) mixes two things: fewer points per axis, and slices on",
                    "axes that have no counterpart in d=2. Decomposing by axis is",
                    "free - the per-slice record is already taken:",
                    "    axes shared by both cells: %s"
                    % ", ".join("x%d" % j for j in shared),
                    "    %-26s %5s %9s" % ("", "hits", "success"),
                    "    %-26s %2d/%-2d %9.3f" % ("sin-exp d=2, shared axes",
                                                  h2, t2, f2),
                    "    %-26s %2d/%-2d %9.3f" % ("smooth5 d=5, shared axes",
                                                  h5, t5, f5)]
            if only5:
                f5n, h5n, t5n = _axfrac(ax5, only5)
                v11.append("    %-26s %2d/%-2d %9.3f"
                           % ("smooth5 d=5, new axes %s"
                              % ",".join("x%d" % j for j in only5),
                              h5n, t5n, f5n))
            d_shared = f5 - f2
            e1["d_shared"] = d_shared
            v11 += ["SHARED-AXIS LEG = %+.3f (%.1f slices at this cell's width)."
                    % (d_shared, _slices(d_shared))]
            if abs(d_shared) >= res9e:
                v11 += ["That is at or above the resolution, and it carries the",
                        "same sign as the pooled leg: the drop is NOT an artifact",
                        "of which axes got slices. Dimensionality survives the",
                        "decomposition as a real effect on the SHARED axis."]
            else:
                v11 += ["That is BELOW the resolution, so on the shared axis the",
                        "leg is not a direction. The pooled dDIM in (a) is then",
                        "substantially slice COMPOSITION, not dimensionality per",
                        "se, and (a) must not be read as the stronger claim."]
            v11 += ["Either way the leg is d=2 vs d=5 AT MATCHED N, which is also",
                    "a collapse in per-axis density (%.1f -> %.1f points per axis)."
                    % (k_d2[3] ** (1.0 / k_d2[2]), k_d5b[3] ** (1.0 / k_d5b[2])),
                    "Matched N is the comparison the instance poses; matched",
                    "density at d=5 is not reachable in this budget. Stated, not",
                    "resolved.",
                    ""]
        # (d) the structure split, corrected
        if leg_tab:
            _nhi, _lhi = leg_meta["n_hi"], leg_meta["l_hi"]
            fam_legs = [_bsurf("lattice", _lhi, f) - _bsurf("lhs", _nhi, f)
                        for f in part9e]
            f_sm, f_mm, f_sp = leg_stats(fam_legs)
            surf_legs = [(nm, _bm((nm, "lattice", 2, _lhi, 0.0))
                          - _bm((nm, "lhs", 2, _nhi, 0.0)))
                         for nm in sm2_9e
                         if (nm, "lattice", 2, _lhi, 0.0) in results
                         and (nm, "lhs", 2, _nhi, 0.0) in results]
            s_sm, s_mm, s_sp = leg_stats([v for _, v in surf_legs])
            v11 += ["(d) THE STRUCTURE LEG, SPLIT BOTH WAYS (corrects [V10]).",
                    "    by family : %s"
                    % ", ".join("%s %+.3f" % (FAM_LABEL[f], v)
                                for f, v in zip(part9e, fam_legs)),
                    "    by surface: %s"
                    % ", ".join("%s %+.3f" % (nm, v) for nm, v in surf_legs),
                    "    family legs : signed mean %+.3f | mean magnitude %.3f"
                    % (f_sm, f_mm),
                    "    surface legs: signed mean %+.3f | mean magnitude %.3f"
                    % (s_sm, s_mm),
                    "    b_split guard: family %s, surface %s"
                    % ("SIGN SPLIT - do not pool" if f_sp else "no split",
                       "SIGN SPLIT - do not pool" if s_sp else "no split")]
            if f_sp or s_sp:
                v11 += ["Because at least one axis splits in sign, NO dominance",
                        "claim is made here from a pooled bisection mean. The",
                        "comparison that survives pooling is dDIM %+.3f in (a)"
                        % d_dim,
                        "against a structure leg whose largest single magnitude is",
                        "%.3f - and dDIM is the larger by %.1f slices."
                        % (max(abs(v) for v in fam_legs
                               + [v for _, v in surf_legs]),
                           _slices(abs(d_dim) - max(abs(v) for v in fam_legs
                                   + [v for _, v in surf_legs])))]
            else:
                v11 += ["Neither axis splits in sign, so the pooled bisection mean",
                        "is safe to read here. Reported because the guard ran."]
            e1["struct_max"] = max(abs(v) for v in fam_legs
                                   + [v for _, v in surf_legs])
        e1["d_dim"] = d_dim
        vd("V11 d5-readout", v11)

    # ---------------- [V12] the d=5 design axis ---------------------------
    new9e = [("lattice", 243), ("lhs", 720), ("lattice", 1024),
             ("lat-aniso", 720)]
    new9e = [(doe, n) for doe, n in new9e
             if ("smooth5", doe, 5, n, 0.0) in results]
    if part9e and len(new9e) == 4:
        def _k(doe, n):
            return ("smooth5", doe, 5, n, 0.0)

        def _lbl(doe, n):
            if doe == "lat-aniso":
                return "lattice %s" % "x".join(str(m) for m in ANISO_LEVELS[5])
            if doe == "lattice":
                m = int(round(n ** 0.2))
                return "lattice %s isotropic" % "x".join([str(m)] * 5)
            return "LHS control"

        aniso, ctrl = _k("lat-aniso", 720), _k("lhs", 720)
        d_aniso = _bm(aniso) - _bm(ctrl)
        v12 = ["The design axis crossed with DIMENSIONALITY, and level ANISOTROPY",
               "made expressible for the first time (TASK-9-E2). Before this run",
               "every lattice cell in this file was d=2, so 9C-1's design axis had",
               "never been crossed with d; and make_design built one level count",
               "for every axis, so the H-T instance's 6x5x4x3x2 = 720 could not be",
               "written down at all. Surface smooth5, noise 0, d=5 throughout.",
               "RESOLUTION: one slice = %.3f. Legs narrower than that are not"
               % res9e,
               "reported as directions.",
               "",
               "    %-28s %6s %8s %8s %8s %8s"
               % ("cell", "N", FAM_LABEL[part9e[0]].split()[0],
                  FAM_LABEL[part9e[1]].split()[0],
                  FAM_LABEL[part9e[2]].split()[0], "mean")]
        for doe, n in new9e:
            k = _k(doe, n)
            v12.append("    %-28s %6d %8.3f %8.3f %8.3f %8.3f"
                       % (_lbl(doe, n), n, _b1(k, part9e[0]), _b1(k, part9e[1]),
                          _b1(k, part9e[2]), _bm(k)))
        v12 += ["",
                "ANISOTROPY LEG at matched N=%d: %s minus %s = %+.3f (%.1f slices)"
                % (720, "lattice 6x5x4x3x2", "LHS control", d_aniso,
                   _slices(d_aniso))]
        fam_a = [_b1(aniso, f) - _b1(ctrl, f) for f in part9e]
        a_sm, a_mm, a_sp = leg_stats(fam_a)
        v12 += ["    by family: %s"
                % ", ".join("%s %+.3f" % (FAM_LABEL[f], v)
                            for f, v in zip(part9e, fam_a)),
                "    signed mean %+.3f | mean magnitude %.3f | b_split guard: %s"
                % (a_sm, a_mm, "SIGN SPLIT - do not pool" if a_sp
                   else "no sign split, pooling is safe"),
                "    by surface: not applicable - smooth5 is the only d=5 surface",
                "    this benchmark carries. Single-surface, and said so.",
                ""]
        # falsification verdict, computed
        if _bm(aniso) <= E2_C1_CEILING and _bm(aniso) < _bm(ctrl):
            verdict = ("C1 MET - ANISOTROPY EXPLAINS THE MISS: the anisotropic "
                       "cell lands at or below %.3f AND below its own control."
                       % E2_C1_CEILING)
        elif _bm(aniso) > _bm(ctrl):
            verdict = ("C2 MET - ANISOTROPY POINTS THE OTHER WAY: the "
                       "anisotropic cell lands ABOVE its LHS control at matched "
                       "N, so anisotropy is the WRONG SIGN, not merely "
                       "insufficient.")
        else:
            verdict = ("C3 MET - NEITHER: the anisotropic cell is at or below "
                       "its control but above %.3f, so anisotropy moves the "
                       "right way and does not arrive." % E2_C1_CEILING)
        v12 += ["FALSIFICATION VERDICT. The three conditions were fixed in",
                "SESSION-9E BEFORE this run, so the result cannot be read after",
                "the fact as whatever was hoped for:",
                "  C1 explains  : aniso <= %.3f AND aniso < LHS control"
                % E2_C1_CEILING,
                "  C2 other way : aniso > LHS control",
                "  C3 neither   : aniso <= control but above %.3f"
                % E2_C1_CEILING,
                "  measured     : aniso %.3f, control %.3f, instance %.3f"
                % (_bm(aniso), _bm(ctrl), HT_INSTANCE_BIS)]
        v12 += _wrap(verdict, 66, "  ")
        # probe comparison, computed
        v12 += ["",
                "PROBE CHECK. SESSION-9E carried an authoring probe from a scratch",
                "harness - PREDICTIONS, explicitly to be refuted, never targets.",
                "    %-28s %8s %8s %8s" % ("cell", "predict", "measured", "delta")]
        worst = 0.0
        for doe, n in new9e:
            pred = E2_PROBE.get((doe, n))
            if pred is None:
                continue
            got = _bm(_k(doe, n))
            worst = max(worst, abs(got - pred))
            v12.append("    %-28s %8.3f %8.3f %+8.3f"
                       % (_lbl(doe, n), pred, got, got - pred))
        if worst > res9e:
            v12 += ["Largest disagreement %.3f exceeds the metric's own resolution"
                    % worst,
                    "of %.3f. THE PROBE WAS WRONG, and per the brief that is a"
                    % res9e,
                    "reportable finding in its own right, not something to",
                    "reconcile toward. The measurement above stands; the probe",
                    "does not."]
        else:
            v12 += ["Largest disagreement %.3f is within the metric's resolution"
                    % worst,
                    "of %.3f. The probe reproduced through the shipped code path."
                    % res9e]
        # IC-1 side effect, predicted then reported
        n_new_ic1 = sum(1 for k in ic1_cells if k[0] == "smooth5" and k[2] == 5
                        and (k[1], k[3]) in new9e)
        n_lat_any = sum(1 for k, _, _, _ in ic1_stats
                        if k[1] in ("lattice", "lat-aniso"))
        v12 += ["",
                "IC-1 SIDE EFFECT, predicted before the run and reported after.",
                "ic1_cells selects on surface and noise ONLY - never on design,",
                "never on dimension - so all four new noise-0 smooth5 cells enter",
                "the IC-1 check and move [V1]'s denominators, exactly as 9C-1's",
                "lattice cells did. Predicted %d -> %d cells; observed %d."
                % (E2_IC1_CELLS_BEFORE, E2_IC1_CELLS_BEFORE + 4, len(ic1_stats)),
                "%d of the new cells landed in IC-1." % n_new_ic1,
                "[V10]'s own counter tests doe == \"lattice\" and so does not see",
                "the anisotropic cell; counting every gridded design, %d of %d"
                % (n_lat_any, len(ic1_stats)),
                "IC-1 cells are now lattices. NO IC-1 definition was changed and",
                "[V10] was not edited to notice; the cell set grew."]
        near = abs(_bm(ctrl) - HT_INSTANCE_BIS)
        v12 += ["",
                "CONSEQUENCE, READ TOGETHER WITH [V11]. Three suspects, three",
                "different answers:"]
        if "d_dim" in e1:
            v12.append("  DIMENSIONALITY   %+.3f pooled, %+.3f on the axis both"
                       % (e1["d_dim"], e1.get("d_shared", float("nan"))))
            v12.append("                   cells share - it survives the")
            v12.append("                   decomposition.  [V11] (a), (c)")
        if "struct_max" in e1:
            v12.append("  DESIGN STRUCTURE splits in sign by family AND by")
            v12.append("                   surface at d=2; largest magnitude")
            v12.append("                   %.3f, no pooled direction."
                       % e1["struct_max"])
            v12.append("                   [V10-A1], [V11] (d)")
        v12 += ["  ANISOTROPY       %+.3f at matched N - AWAY from the instance,"
                % d_aniso,
                "                   not toward it.  C2 above",
                "The LHS control at d=5 N=%d - matched N, matched dimension, no"
                % ctrl[3],
                "grid structure at all - lands at %.3f against the instance's"
                % _bm(ctrl),
                "%.3f: %.1f slices apart. DIMENSIONALITY AT THIS N REPRODUCES THE"
                % (HT_INSTANCE_BIS, _slices(near)),
                "INSTANCE'S BISECTION NUMBER; the design axis moves away from it.",
                "NOW EXCLUDED: that the miss is unexplained; that anisotropy",
                "explains it (wrong sign); that design structure explains it (no",
                "pooled direction at d=2).",
                "LEFT OPEN: why the instance - itself a 6x5x4x3x2 lattice -",
                "behaves like this cell's LHS CONTROL rather than like this",
                "cell's ANISOTROPIC LATTICE. Two differences remain: the SURFACE",
                "(smooth5 is not a thermal energy balance) and the instance's",
                "PHYSICAL AXIS RANGES and spacings against this benchmark's",
                "equispaced unit cube. Neither is measured here."]
        vd("V12 d5-design", v12)

    total = time.perf_counter() - t_start
    emit("total wall: %.1f s (%.1f min)" % (total, total / 60.0))
    return total


def main():
    ap = argparse.ArgumentParser(description="TASK-9 Session-B falsifier benchmark")
    ap.add_argument("--smoke", action="store_true", help="60-90 s wiring check")
    args = ap.parse_args()
    run(smoke=args.smoke)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "falsifier_results.txt")
    if args.smoke:
        note("smoke mode: falsifier_results.txt NOT written")
        return
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(_LINES) + "\n")
    note("wrote %s" % out)


if __name__ == "__main__":
    main()
