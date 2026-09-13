# TASK-10 / E-2 -- corpus consumer: G1 / M1 / V1 / V2 / V3 for PSW04-schema corpora

> Built 2026-09-01 (SESSION-10B) as the second executed item of
> `VERTICALS-BUILD-TEST-VALIDATE-PLAN.md` (section 6.2). It is the downstream
> half of TASK-10 queue item VP-1 that did not exist: nothing in the tree
> could ingest cfd-automation's `training_corpus.parquet` (finding F-6),
> nothing decided whether a corpus was fit to train on (F-2), and nothing
> turned "train the TASK-5 B1 blueprint against it" into a pass/fail
> verdict (F-3, F-4). This folder is that missing segment of the critical
> path, and it has already run end to end on two real-solver corpora from
> E-1 (`examples/TASK-10-fea-automation-v0/`).

## What it is

Four scripts and a shared module, driven by a per-vertical *rules file*:

| Script | Gate (plan section 4.2) | Reads | Writes | Exit code |
|---|---|---|---|---|
| `corpus_gate.py` | **G1** corpus acceptance (G1.1-G1.7) | `training_corpus.parquet` (+ `sweep_config.json`, `data_card.json` beside it), rules | `corpus_gate_report.json` with the admissible-row index | 1 on any failed check |
| `train_b1.py` | **M1** model build | corpus, the G1 report (required -- nothing trains on a corpus the gate did not admit), rules | `model_bundle.pkl`, `model_meta.json` | 2 if the G1 report says FAIL |
| `model_gate.py` | **V1** validation, **V2** physics validity, **V3** readiness fields | corpus, G1 report, rules, model dir | `model_card.json` | 1 on any failed check |
| `synth_corpus.py` | (rung-1.5 corpus writer) | thermal-mesh-calculators | a sweep-shaped directory in the exact PSW04 schema, with defect modes for the fail demonstrations | -- |
| `cc_common.py` | schema, loader, statistics | | | |

`rules/` carries `pv-c2`, `pv-f3` and `pv-f1` rules files (the plan's
section 4.3 cards made machine-readable): targets, feature policy, the
vertical's `physics_inputs` vocabulary, admissibility and coverage floors,
bounds, the corner-split axis, the V1 thresholds (**provisional** per plan
section 3.2), monotone pairs, V2.3/V2.4 declarations, optional log
transforms, and the V3 anchor statements. Adapting the consumer to a new
vertical or corpus is a rules file, not code.

## What the gates check, concretely

**G1 corpus acceptance.** Schema kinds; admissibility (`convergence_status`
in the accepted set, `final_residual_T` below the floor, admissible
fraction of cases >= 0.90 -- too many solver failures means the DOE ranges
are wrong, not the rows); **physics reach** in four parts -- (a) every
swept axis must be in the vertical's declared `physics_inputs`
(`mesh.t_fluid_K` is not: the F-1 shape fails here first), (b) when the
corpus carries `solver_input_hash`, distinct parameter points must give
distinct solver inputs, (c) a raw or partial (after the other axes)
Spearman / ANOVA association with at least one target, (d) no target may
be a function of `mesh_size_mm` / `n_cells` alone (a von Neumann ratio of
the target sorted by mesh size: 0.19-0.96 on honest corpora, 0.0003 on the
F-1 corpus); DOE coverage against the intended ranges recorded in
`sweep_config.json`, plus enough cases in the extrapolation corner;
regime bounds from the rules (constants or column references) and
margin/pass-fail consistency; degeneracy (duplicate points, constant
targets); data-card completeness (solver, mesh policy, sampler + seed,
generator commit, units, date range, analyst).

**M1 model build.** Per (component, target): a random 20 % test split plus
a **corner** split -- rows at or above the 0.9 quantile of the declared
extrapolation axis are held out entirely (TASK-5 B1 Stage 4). Candidates: a
5-seed gradient-boosted-tree ensemble, a quadratic ridge, an anisotropic
RBF Gaussian process (the TASK-8 thermal cell's deferred GP variant), with
a linear model and a mean predictor as the mandatory baselines; the
champion is the lowest calibration RMSE, and it may honestly be the linear
model. Split-conformal 90 % prediction intervals from a calibration
subset. Fixed seeds, `OMP_NUM_THREADS=1`. Optional per-target / per-feature
log transforms from the rules (the plate lane needs them: delta = P L^3 /
3 E I is linear in logs).

**V1 model validation.** Held-out R2 / MAE against the card; corner
degradation ratio <= 3 *or* corner RMSE below an absolute floor (mae_max,
or 1 % of the target range -- a GP with 0.03 K in-distribution error should
not fail for a 0.13 K corner error); conformal coverage inside a
sample-size-aware band (the declared [0.85, 0.95] widened by 2 sqrt(p(1-p)/n)
for small test sets), with over-coverage accepted only when the interval is
narrow; baseline beat (RMSE <= 0.5 x mean predictor, and <= 0.8 x linear
when the champion is not linear); reproducibility (re-train with the same
seeds -> identical metrics to 1e-6).

**V2 physics validity.** Monotonicity of declared (feature, target,
direction) pairs on 50 probe lines through the training hull (violations
counted only beyond 0.1 % of the target range, so piecewise-constant tree
predictions are not penalised for plateaus); bounds on a 500-point probe
set covering the hull expanded by 10 % per axis; conservation and symmetry
are *declared* applicable-or-not in every rules file so they are never
skipped silently (PV-F3's stress-scaling identity and PV-C3's energy
balance are declared applicable and queued).

**V3.** The rung-4 anchor, inference target and Stage-8 status must be
present; the model card records a use statement (extrapolation-tolerant on
the corner axis, or interpolation-only) from the V1.2 outcome.

## Results as run 2026-09-01

Every corpus below and every report is under `evidence/`.

### G1 on the six synthetic corpora (thermal-mesh-calculators shield chain)

| Corpus | Defect | G1 verdict | Which check failed, and why |
|---|---|---|---|
| `synthetic_pv-c2/honest_n200` | none | **PASS** (600/600 rows) | -- |
| `synthetic_pv-c2/defect_mesh-only_n60` | the F-1 shape (`mesh.t_fluid_K`, `mesh.t_surr_K` swept; physics fixed) | **FAIL** | G1.3 -- 14 flags: both axes are not physics inputs; 60 distinct parameter points map to **1** solver input; `mesh.t_surr_K` shows no response; every target is a function of mesh size alone (ratio 0.0003). G1.5 -- the bounds reference physics columns the corpus does not carry |
| same, `--no-hash-column` | as above, structural check unavailable | **FAIL** | G1.3 by vocabulary + statistics + mesh dominance alone |
| `synthetic_pv-c2/defect_diverged_n60` | 20 % of cases non-converged | **FAIL** | G1.2 -- admissible fraction below 0.90 |
| celsius-bug (10 % of rows in deg C) | | **FAIL** | G1.5 -- temperatures below the sink temperature |
| no data card | | **FAIL** | G1.7 (and nothing else: a small honest corpus passes physics reach) |

### The ladder on three corpora

| Corpus | Model | Champion | Held-out RMSE / MAE | R2 | Corner degradation (passed by) | 90 % PI coverage (n test) | RMSE mean-predictor / linear |
|---|---|---|---|---|---|---|---|
| synthetic PV-C2 (200 cases, 3 components) | exhaust/T_max_K | linear | 7.4e-07 / 6.4e-07 K | 1.0000 | 1.87 (ratio) | 1.000 (36) | 79 / 7.4e-07 |
| | heat_shield/T_max_K | **gp** | 0.026 / 0.017 K | 1.0000 | 5.20 (abs floor 5 K) | 0.944 (36) | 69.5 / 5.7 |
| | protected_part/T_max_K | **gp** | 0.139 / 0.095 K | 1.0000 | 5.77 (abs floor 5 K) | 0.972 (36) | 43 / 12.7 |
| **real** PV-F3 disc, E-1 CalculiX, 96 cases over the A81 ranges | disc/T_min_K | **gp** | 0.057 / 0.025 K | 1.0000 | 2.23 (ratio) | 1.000 (17) | 106 / 6.0 |
| | disc/max_vm_stress_Pa | **gp** | 0.157 / 0.092 MPa | 0.9999 | 3.76 (abs floor 1.3 MPa) | 0.882 (17) | 17.8 / 4.5 MPa |
| | disc/margin_K | linear | 3.6e-05 K | 1.0000 | 0.74 (ratio) | 0.882 (17) | 122 / 3.6e-05 |
| **real** PV-F1 plate, E-1 CalculiX, 48 cases, log-log | plate/max_disp_m | **gp** | 1.8e-06 / 1.2e-06 m | 1.0000 | 0.30 (ratio) | 0.889 (9) | 0.026 / 2.0e-05 |
| | plate/max_vm_stress_Pa | linear (in logs) | 0.87 / 0.64 MPa | 1.0000 | 0.35 (ratio) | 0.778 (9) | 404 / 0.87 MPa |

All three model cards: **PASS** on every V1/V2/V3 check, V1.5 reproducible
to 0.0. Reading the table honestly: the identity targets (`exhaust/T_max_K
= t_surf`, `disc/margin_K = limit - t_inner_K`) pick the linear model, as
they should; the tree ensemble never wins on these smooth 4-D responses
with 26-108 fit rows (calibration RMSE 3-16 K against 0.03-0.2 K for the
GP) -- the plan's "GBM as the deployed default" is the wrong default for
this regime and the champion rule corrects it per target; the 9-row plate
test set gives coverage 0.778, inside the sample-size-aware band but a
reminder that 48 cases is a demonstration, not a production corpus.

### Things the gates caught along the way (kept as evidence of the L18 rule)

- CalculiX prints temperatures to 7 significant digits, so `T_max_K =
  708.1881` exceeded the swept `t_inner_K = 708.188057` and failed a 1e-6
  bounds tolerance; the PV-F3 rules now carry `tol = 0.01 K` with the reason.
- The plate lane at 26 fit rows in raw units reached R2 0.75 on
  displacement and the linear champion predicted negative displacements on
  the expanded probe -- refused by V1.1 and V2.2; log-log transforms (a
  rules-file decision) make the same corpus exact.
- The first version of the mesh-confound test (regress the target on mesh
  size, test the residual) produced false alarms on honest corpora because
  mesh sizing is itself physics-driven; it was replaced by the vocabulary +
  structural + dominance trio above. The plan's section 6.3 records this.

### Re-run 2026-09-02 (SESSION-10C, VP-7 verification-mode re-read)

Every claim above was re-executed rather than re-read. In a sandbox
without thermal-mesh-calculators the pytest suite reports `1 passed,
11 skipped` (the fixtures regenerate the synthetic corpora), so the fail
demonstrations were re-run from the **committed** evidence corpora --
now scripted as `evidence/fail_demos_without_tmc.py` (53 s; writes
`evidence/reports/fail_demos_summary.json`): honest corpus G1 7/7 and the
ladder PASS with a GP champion at held-out RMSE 0.0257 K; the F-1 shape
fails G1.3 with 14 flags (von Neumann ratio 0.0027 on the 60-case instance
vs 0.19-0.96 honest -- the ratio scales with corpus size, hence the 0.0003
quoted above for the 120-case test fixture); the diverged corpus fails
G1.2 at admissible 0.817; shuffled targets fail V1.1 (R2 -0.003) and V1.4;
zero-width intervals fail V1.3 (coverage 0.000); the inverted feature
fails V2.1 (violation fraction 1.000); the linear target makes the linear
model the champion. With thermal-mesh-calculators 0.6.0 staged onto
`PYTHONPATH` the full suite is **12 passed in 82 s**.

**Known defect found by the re-read (plan F-13, queued VP-10).**
`model_gate.py` accepts *any* non-empty V2.3 / V2.4 declaration string as
satisfying the plan's "checked or declared `not_applicable`" pass rule.
`rules/pv-f1` and `rules/pv-f3` declare `applicable_not_implemented_v0`,
so the two real CalculiX model cards under `evidence/reports/` PASS while
an applicable conservation class (displacement proportional to load;
stress proportional to alpha*E*dT) was neither checked nor waived. Read
those two cards' V2 status as "V2.1/V2.2 only". The fix, in L18 order:
make `applicable_not_implemented` fail (the cards turn honestly RED, with
a test), then implement V2.3 for both lanes and re-issue them.

## Layout

```
cc_common.py       PSW04 schema constants, corpus loader, Spearman / ANOVA / OLS-residual helpers, JSON I/O
corpus_gate.py     G1
train_b1.py        M1 (+ predict_entry, used by the model gate)
model_gate.py      V1 / V2 / V3
synth_corpus.py    rung-1.5 corpus writer (thermal-mesh-calculators) with defect modes
rules/             pv-c2 / pv-f3 / pv-f1 physics_rules.json
tests/             12 pytest tests: the honest corpus passes; each defect fails on the right check;
                   shuffled targets, zero-width intervals, an inverted feature and a linear target
                   each fail or resolve exactly as the plan's fail demonstrations say; the two real
                   E-1 corpora pass the whole ladder (regression)
evidence/          the synthetic and real corpora, every G1 report, model_meta and model_card;
                   fail_demos_without_tmc.py re-runs the L18 demonstrations from the committed
                   corpora with no thermal-mesh-calculators (plan F-14; VP-11 is the pytest fixture)
WALKTHROUGH.md     reader-facing steps
```

Dependencies: numpy, pandas, scipy, scikit-learn (all in the CAE-ML
sandbox venue); pyarrow for Parquet (CSV works without it);
thermal-mesh-calculators for `synth_corpus.py` only (`pip install -e` the
local clone). ASCII-only source.

## Things learned while building it (kept so nobody re-learns them)

- `SingleLayerShieldCalculator.solve_temperature` converges to `tol = 0.1 K`
  by default; the synthesizer passes `tol = 1e-6` so the response surface
  is smooth rather than 0.1 K-jagged (a jagged deterministic surface would
  look like noise to every learner and to G1.3).
- In the cloud sandbox thermal-mesh-calculators was used by staging its
  eleven `thermal_mesh_calculators/*.py` files with `device_stage_files`
  and pointing `PYTHONPATH` at the staged package (2026-09-02: one 44 KB
  tarball of the package dir, staged and extracted, does the same -- the
  clone must be a connected folder first, it is private on GitHub); on Windows,
  `pip install -e C:\Users\jpcol\Documents\thermal-mesh-calculators`.
  Its `__init__.py` says 0.6.0 while its `pyproject.toml` says 0.5.1 -- the
  data card records the `__version__` value.
- The first admissibility rule quarantined every row with a null target,
  which threw out all `exhaust` rows because a component without a limit
  has no `margin_K`; nulls are now reported per (component, target) and
  dropped per target by the trainer.
- The first G1.3 confound test (regress the target on mesh size, test the
  residual) flagged an honest 60-case corpus, because tmc's boundary-driven
  sizing makes `mesh_size_mm` a function of the same physics inputs the
  targets depend on. The vocabulary + structural + dominance trio replaced
  it (verticals plan section 4.2, LESSONS L20).
- V1.5 re-trains every model in a temporary directory, so the model gate
  takes about twice the trainer's time (10 s on the 200-case synthetic
  corpus, 3-4 s on the real ones). The whole 12-test suite runs in ~45 s.
- A GP with 108 fit rows in 4-D fits in under a second; the
  `ConvergenceWarning` scikit-learn emits when a kernel hyper-parameter
  sits on its bound is silenced in the trainer -- the fit is still
  deterministic (V1.5 proves it).

## Known-untested paths

The CSV branch of `load_corpus` (every corpus here was Parquet; the CSV
copies exist but were not loaded); string-valued (categorical) swept
parameters and the one-hot path in `design_matrix`; a V2.2 bound that
references a non-feature column (the `evaluable = False` branch); the
scipy-free fallbacks in `cc_common` (scipy was present); `--component`
with several names; corpora with more than one row per (case, component).

## What this is not, yet

Field targets (B2/B3) -- the gates are scalar-row gates; the PSW04 schema is
scalar. V2.3 conservation checks are declared, not implemented -- and the
gate currently lets that declaration pass (F-13 above). The
thresholds are provisional until pinned per plan section 3.2 / section 9
item 9. And a cfd-automation corpus has not been through it yet, because
none exists (TC-PSW07 -> TC-PSW05 -> VP-1 -> VP-8 in the plan's section 5);
the two E-1 corpora are the same schema from a different solver, which is
the point.
