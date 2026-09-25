# Corpus consumer -- G1 / M1 / V1 / V2 / V3 for corpus-consumer-schema corpora

> The scalar gate engine in `src/opencontractml/` answers three questions
> about a training corpus produced by a CAE sweep: is the corpus fit to
> train on (G1), what is the best honest scalar surrogate it supports
> (M1), and does that surrogate pass validation, physics-validity and
> readiness checks (V1 / V2 / V3). This folder documents it;
> `WALKTHROUGH.md` is the step-by-step. The rules files, test suite and
> evidence corpora it was developed against are not part of this
> repository (`docs/EXTRACTION.md`, known gap 5), so the results quoted
> below are a record of runs, not something this folder can re-run.

## What it is

Four modules and a shared helper, driven by a per-vertical *rules file*:

| Module | Gate | Reads | Writes | Exit code |
|---|---|---|---|---|
| `opencontractml.corpus_gate` | **G1** corpus acceptance (G1.1-G1.7) | `training_corpus.parquet` (+ `sweep_config.json`, `data_card.json` beside it), rules | `corpus_gate_report.json` with the admissible-row index | 1 on any failed check |
| `opencontractml.train_b1` | **M1** model build | corpus, the G1 report (required -- nothing trains on a corpus the gate did not admit), rules | `model_bundle.pkl`, `model_meta.json` | 2 if the G1 report says FAIL |
| `opencontractml.gate` | **V1** validation, **V2** physics validity, **V3** readiness fields | corpus, G1 report, rules, model dir | `model_card.json` | 1 on any failed check |
| `opencontractml.synth_corpus` | (synthetic corpus writer) | thermal-mesh-calculators | a sweep-shaped directory in the corpus-consumer schema, with defect modes for the fail demonstrations | -- |
| `opencontractml.cc_common` | schema, loader, statistics | | | |

A rules file carries the targets, the feature policy, the vertical's
`physics_inputs` vocabulary, admissibility and coverage floors, bounds,
the corner-split axis, the V1 thresholds (**provisional**), monotone
pairs, V2.3/V2.4 declarations, optional log transforms, and the V3
anchor statements. Adapting the consumer to a new vertical or corpus is a
rules file, not code. No example rules file ships yet.

## What the gates check, concretely

**G1 corpus acceptance.** Schema kinds; admissibility (`convergence_status`
in the accepted set, `final_residual_T` below the floor, admissible
fraction of cases >= 0.90 -- too many solver failures means the DOE ranges
are wrong, not the rows); **physics reach** in four parts -- (a) every
swept axis must be in the vertical's declared `physics_inputs`
(`mesh.t_fluid_K` is not: a sweep that only reaches mesh sizing fails
here first), (b) when the corpus carries `solver_input_hash`, distinct
parameter points must give distinct solver inputs, (c) a raw or partial
(after the other axes) Spearman / ANOVA association with at least one
target, (d) no target may be a function of `mesh_size_mm` / `n_cells`
alone (a von Neumann ratio of the target sorted by mesh size: 0.19-0.96
on honest corpora, 0.0003 on a mesh-only corpus); DOE coverage against the
intended ranges recorded in `sweep_config.json`, plus enough cases in the
extrapolation corner; regime bounds from the rules (constants or column
references) and margin/pass-fail consistency; degeneracy (duplicate
points, constant targets); data-card completeness (solver, mesh policy,
sampler + seed, generator commit, units, date range, analyst).

**M1 model build.** Per (component, target): a random 20 % test split plus
a **corner** split -- rows at or above the 0.9 quantile of the declared
extrapolation axis are held out entirely. Candidates: a 5-seed
gradient-boosted-tree ensemble, a quadratic ridge, an anisotropic RBF
Gaussian process (the GP variant the thermal worked cells name), with a
linear model and a mean predictor as the mandatory baselines; the champion
is the lowest calibration RMSE, and it may honestly be the linear model.
Split-conformal 90 % prediction intervals from a calibration subset. Fixed
seeds, `OMP_NUM_THREADS=1`. Optional per-target / per-feature log
transforms from the rules (a plate-deflection corpus needs them: delta =
P L^3 / 3 E I is linear in logs).

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
skipped silently -- but see the known defect below.

**V3.** The rung-4 anchor, inference target and Stage-8 status must be
present; the model card records a use statement (extrapolation-tolerant on
the corner axis, or interpolation-only) from the V1.2 outcome.

## Known defect: V2.3 / V2.4 declarations pass unchecked

`opencontractml.gate` accepts *any* non-empty V2.3 / V2.4 declaration
string as satisfying the "checked or declared not applicable" pass rule.
A rules file that declares a conservation class applicable but not
implemented therefore passes V2 while that class was neither checked nor
waived. Read a V2 PASS from this engine as "V2.1 / V2.2 only". The fix,
in fail-first order: make an applicable-but-not-implemented declaration
fail (the affected cards turn honestly RED, with a test), then implement
V2.3 per vertical and re-issue them. This is the failure the Contract's
rule `V006` exists to catch (see the repository `README.md`).

## Results as run 2026-09-01

The corpora, rules files and reports behind these tables are not included
in this repository.

### G1 on the six synthetic corpora (thermal-mesh-calculators shield chain)

| Corpus | Defect | G1 verdict | Which check failed, and why |
|---|---|---|---|
| honest, 200 cases | none | **PASS** (600/600 rows) | -- |
| mesh-only, 60 cases | only mesh axes swept (`mesh.t_fluid_K`, `mesh.t_surr_K`); physics fixed | **FAIL** | G1.3 -- 14 flags: both axes are not physics inputs; 60 distinct parameter points map to **1** solver input; `mesh.t_surr_K` shows no response; every target is a function of mesh size alone (ratio 0.0003). G1.5 -- the bounds reference physics columns the corpus does not carry |
| same, `--no-hash-column` | as above, structural check unavailable | **FAIL** | G1.3 by vocabulary + statistics + mesh dominance alone |
| diverged, 60 cases | 20 % of cases non-converged | **FAIL** | G1.2 -- admissible fraction below 0.90 |
| celsius-bug (10 % of rows in deg C) | | **FAIL** | G1.5 -- temperatures below the sink temperature |
| no data card | | **FAIL** | G1.7 (and nothing else: a small honest corpus passes physics reach) |

### The ladder on three corpora

| Corpus | Model | Champion | Held-out RMSE / MAE | R2 | Corner degradation (passed by) | 90 % PI coverage (n test) | RMSE mean-predictor / linear |
|---|---|---|---|---|---|---|---|
| synthetic shield chain (200 cases, 3 components) | exhaust/T_max_K | linear | 7.4e-07 / 6.4e-07 K | 1.0000 | 1.87 (ratio) | 1.000 (36) | 79 / 7.4e-07 |
| | heat_shield/T_max_K | **gp** | 0.026 / 0.017 K | 1.0000 | 5.20 (abs floor 5 K) | 0.944 (36) | 69.5 / 5.7 |
| | protected_part/T_max_K | **gp** | 0.139 / 0.095 K | 1.0000 | 5.77 (abs floor 5 K) | 0.972 (36) | 43 / 12.7 |
| **real** annular brake disc, CalculiX, 96 cases | disc/T_min_K | **gp** | 0.057 / 0.025 K | 1.0000 | 2.23 (ratio) | 1.000 (17) | 106 / 6.0 |
| | disc/max_vm_stress_Pa | **gp** | 0.157 / 0.092 MPa | 0.9999 | 3.76 (abs floor 1.3 MPa) | 0.882 (17) | 17.8 / 4.5 MPa |
| | disc/margin_K | linear | 3.6e-05 K | 1.0000 | 0.74 (ratio) | 0.882 (17) | 122 / 3.6e-05 |
| **real** plate, CalculiX, 48 cases, log-log | plate/max_disp_m | **gp** | 1.8e-06 / 1.2e-06 m | 1.0000 | 0.30 (ratio) | 0.889 (9) | 0.026 / 2.0e-05 |
| | plate/max_vm_stress_Pa | linear (in logs) | 0.87 / 0.64 MPa | 1.0000 | 0.35 (ratio) | 0.778 (9) | 404 / 0.87 MPa |

All three model cards: **PASS** on every V1/V2/V3 check, V1.5 reproducible
to 0.0 -- with the V2 caveat above: the two real-corpus rules files declare
their conservation classes applicable but not implemented, so read those
two cards' V2 status as "V2.1 / V2.2 only". Reading the table honestly:
the identity targets (`exhaust/T_max_K = t_surf`, `disc/margin_K = limit
- t_inner_K`) pick the linear model, as they should; the tree ensemble
never wins on these smooth 4-D responses with 26-108 fit rows (calibration
RMSE 3-16 K against 0.03-0.2 K for the GP) -- "GBM as the deployed
default" is the wrong default for this regime and the champion rule
corrects it per target; the 9-row plate test set gives coverage 0.778,
inside the sample-size-aware band but a reminder that 48 cases is a
demonstration, not a production corpus.

### Things the gates caught along the way (kept as evidence that a gate must be able to fail)

- CalculiX prints temperatures to 7 significant digits, so `T_max_K =
  708.1881` exceeded the swept `t_inner_K = 708.188057` and failed a 1e-6
  bounds tolerance; the disc rules now carry `tol = 0.01 K` with the reason.
- The plate corpus at 26 fit rows in raw units reached R2 0.75 on
  displacement and the linear champion predicted negative displacements on
  the expanded probe -- refused by V1.1 and V2.2; log-log transforms (a
  rules-file decision) make the same corpus exact.
- The first version of the mesh-confound test (regress the target on mesh
  size, test the residual) produced false alarms on honest corpora because
  mesh sizing is itself physics-driven; it was replaced by the vocabulary +
  structural + dominance trio above.

### Re-run 2026-09-02

Every claim above was re-executed rather than re-read. Run from the
committed evidence corpora without thermal-mesh-calculators installed:
the honest corpus passes G1 7/7 and the ladder PASSes with a GP champion
at held-out RMSE 0.0257 K; the mesh-only shape fails G1.3 with 14 flags
(von Neumann ratio 0.0027 on the 60-case instance vs 0.19-0.96 honest --
the ratio scales with corpus size, hence the 0.0003 quoted above for a
120-case instance); the diverged corpus fails G1.2 at admissible 0.817;
shuffled targets fail V1.1 (R2 -0.003) and V1.4; zero-width intervals fail
V1.3 (coverage 0.000); the inverted feature fails V2.1 (violation fraction
1.000); the linear target makes the linear model the champion. With
thermal-mesh-calculators 0.6.0 staged onto `PYTHONPATH` the full 12-test
suite passed in 82 s.

## Layout

```
src/opencontractml/cc_common.py     corpus-consumer schema constants, corpus loader, Spearman / ANOVA / OLS-residual helpers, JSON I/O
src/opencontractml/corpus_gate.py   G1
src/opencontractml/train_b1.py      M1 (+ predict_entry, used by the model gate)
src/opencontractml/gate.py          V1 / V2 / V3
src/opencontractml/synth_corpus.py  synthetic corpus writer (thermal-mesh-calculators) with defect modes
examples/corpus-consumer/           this README and WALKTHROUGH.md
```

Dependencies: the `[gate]` extra (numpy, pandas, scikit-learn; scipy comes
with scikit-learn); pyarrow for Parquet (CSV works without it);
thermal-mesh-calculators for `synth_corpus` only
(`pip install thermal-mesh-calculators`). ASCII-only source.

## Things learned while building it (kept so nobody re-learns them)

- `SingleLayerShieldCalculator.solve_temperature` converges to `tol = 0.1 K`
  by default; the synthesizer passes `tol = 1e-6` so the response surface
  is smooth rather than 0.1 K-jagged (a jagged deterministic surface would
  look like noise to every learner and to G1.3).
- thermal-mesh-calculators is an ordinary dependency of `synth_corpus`
  (`pip install thermal-mesh-calculators`).
  Its `__init__.py` says 0.6.0 while its `pyproject.toml` says 0.5.1 --
  the data card records the `__version__` value.
- The first admissibility rule quarantined every row with a null target,
  which threw out all `exhaust` rows because a component without a limit
  has no `margin_K`; nulls are now reported per (component, target) and
  dropped per target by the trainer.
- The first G1.3 confound test (regress the target on mesh size, test the
  residual) flagged an honest 60-case corpus, because tmc's boundary-driven
  sizing makes `mesh_size_mm` a function of the same physics inputs the
  targets depend on. The vocabulary + structural + dominance trio replaced
  it: where statistics cannot discriminate, a structural check comes first.
- V1.5 re-trains every model in a temporary directory, so the model gate
  takes about twice the trainer's time (10 s on the 200-case synthetic
  corpus, 3-4 s on the real ones).
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

Field targets (B2/B3) -- the gates are scalar-row gates, and the
corpus-consumer schema is scalar. V2.3 conservation checks are declared,
not implemented -- and the gate currently lets that declaration pass (the
known defect above). The thresholds are provisional until pinned. And a
CFD sweep corpus has not been through it yet;
the two real corpora above are the same schema from a different solver
(CalculiX), which is the point.
