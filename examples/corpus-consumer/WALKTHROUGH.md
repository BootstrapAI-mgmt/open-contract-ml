# WALKTHROUGH -- corpus consumer (G1 -> M1 -> V1/V2/V3)

You need Python 3.10+ with numpy, pandas, scipy and scikit-learn
(`pip install numpy pandas scipy scikit-learn pyarrow pytest`). Only
Step 0 needs thermal-mesh-calculators (`pip install -e
C:\path\to\thermal-mesh-calculators`).

All commands run from this folder (`examples/TASK-10-corpus-consumer/`).
Outputs go under `out/`.

## Step 0 (optional) -- make a corpus you can trust, and two you cannot

```
python synth_corpus.py --out out/honest --n 200
python synth_corpus.py --out out/f1shape --n 60 --defect mesh-only
python synth_corpus.py --out out/diverged --n 60 --defect diverged
```

The honest one is a three-component heat-shield chain solved by
thermal-mesh-calculators; the `mesh-only` one reproduces the shape of
cfd-automation's PSW05 sweep as specified (finding F-1 of the verticals
plan): the swept axes change only the mesh, never the physics. If you skip
this step, use `evidence/synthetic_pv-c2/honest_n200/` or one of the real
E-1 corpora under `evidence/real_*`.

## Step 1 -- G1: is the corpus fit to train on?

```
python corpus_gate.py --corpus out/honest/training_corpus.parquet --rules rules/pv-c2.physics_rules.json --report out/honest_G1.json
python corpus_gate.py --corpus out/f1shape/training_corpus.parquet --rules rules/pv-c2.physics_rules.json --report out/f1shape_G1.json
```

Expected: the first prints seven `[PASS]` lines and `G1 PASS`; the second
fails G1.3 with `SWEEP_AXIS_NOT_A_PHYSICS_INPUT`, `SWEEP_AXIS_UNREACHED
(structural): 60 distinct parameter points map to only 1 distinct solver
inputs` and ten `MESH_DOMINANT` lines, and exits 1. Open the report: the
`admissible_index` list is what the trainer will use; `per_axis` holds
every association statistic; `mesh_dominance` the von Neumann ratios.

For a real corpus, the rules file must know the corpus's vocabulary:
`physics_inputs` lists the dotted parameter paths that are boundary
conditions, materials or geometry for that vertical, and `bounds` may
reference them by column. `rules/pv-f3.physics_rules.json` is the
fea-automation disc lane; `rules/pv-f1.physics_rules.json` the plate lane.

## Step 2 -- M1: train

```
python train_b1.py --corpus out/honest/training_corpus.parquet --gate-report out/honest_G1.json --rules rules/pv-c2.physics_rules.json --out out/honest_model
```

Expected: one line per (component, target) with the calibration RMSE of
every candidate and the champion, e.g. `heat_shield/T_max_K
champion=gp cal-RMSE ens=16.1 lin=5.74 poly2=0.967 gp=0.0384`. The
trainer refuses (exit 2) when the G1 report says FAIL -- try it with
`out/f1shape_G1.json`. `out/honest_model/model_meta.json` records the
corpus sha256, the split indices, seeds and library versions.

## Step 3 -- V1 / V2 / V3: validate

```
python model_gate.py --corpus out/honest/training_corpus.parquet --gate-report out/honest_G1.json --rules rules/pv-c2.physics_rules.json --model out/honest_model --card out/honest_model_card.json
```

Expected: per model, `[PASS]` on V1.1 (held-out accuracy), V1.2 (corner
extrapolation), V1.3 (interval coverage), V1.4 (baseline beat), the V2.1
monotone pairs and V2.2 bounds; then V1.5 reproducibility, the V2.3/V2.4
declarations, the V3 fields, and `MODEL GATE PASS`. The model card is the
deliverable a reviewer reads: every number above plus the use statement
(`extrapolation-tolerant on <axis> up to the corner threshold` or
`interpolation-only`).

## Step 4 -- the same ladder on a real solver corpus

```
python corpus_gate.py --corpus evidence/real_pv-f3_disc_lhs96/training_corpus.parquet --rules rules/pv-f3.physics_rules.json --report out/disc_G1.json
python train_b1.py --corpus evidence/real_pv-f3_disc_lhs96/training_corpus.parquet --gate-report out/disc_G1.json --rules rules/pv-f3.physics_rules.json --out out/disc_model
python model_gate.py --corpus evidence/real_pv-f3_disc_lhs96/training_corpus.parquet --gate-report out/disc_G1.json --rules rules/pv-f3.physics_rules.json --model out/disc_model --card out/disc_model_card.json
```

This corpus is 96 CalculiX solves of the A81 annular disc from
`examples/TASK-10-fea-automation-v0/` (regenerate it there with
`python -m fea_auto sweep --config configs/sweep_disc_lane2_lhs96.json ...`).
Expected: G1 PASS, GP champions for `T_min_K` and `max_vm_stress_Pa`, a
linear champion for `margin_K` (it is an identity), MODEL GATE PASS.

When cfd-automation's PSW05 corpus exists (plan section 5: TC-PSW07 ->
TC-PSW05 -> VP-1), this is the exact command sequence for VP-8, with
`rules/pv-c2.physics_rules.json` and its `physics_inputs` renamed to that
repo's zone-thermal overlay paths.

## Step 5 -- make the gates fail on purpose

```
python -m pytest tests -q
```

12 tests. Five of them are the plan's fail demonstrations: shuffled targets
fail V1.1 and V1.4; a zero-width interval fails V1.3; an inverted feature
fails V2.1; a linear target makes the linear model the honest champion; and
the F-1 corpus fails G1.3 with and without the `solver_input_hash` column.
The last test re-runs the whole ladder on the two real corpora.

## Things worth knowing

- The gate report's `admissible_index` is the only bridge between G1 and
  M1. Keep the report next to the model; the model card records the corpus
  sha256 so a mismatch is visible.
- A null `margin_K` on a component without a limit is legitimate; the
  trainer drops nulls per target, and G1.2 reports them.
- Thresholds in the rules files are provisional (plan section 3.2). Change
  them in the rules file, never in the code, and say why in the file.
- `mesh_size_mm` and `n_cells` are never features (feature_policy). They
  are provenance; G1.3(d) is what watches them.
- Log transforms are a rules-file decision per target and per feature;
  the model gate works in original units regardless.
