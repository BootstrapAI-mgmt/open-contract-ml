# WALKTHROUGH -- corpus consumer (G1 -> M1 -> V1/V2/V3)

You need Python 3.11+ with this package and its `[gate]` extra
(`pip install "open-contract-ml[gate]" pyarrow`). Only Step 0 needs
thermal-mesh-calculators (`pip install thermal-mesh-calculators`).

Outputs go under `out/`. Steps 1-3 also need a rules file for the
corpus's vertical, written below as `<rules.json>`. No example rules file
ships with this repository yet (`docs/EXTRACTION.md`, known gap 5), so
the expected output quoted in those steps is what the engine printed
against the rules file it was developed with; the README says what a
rules file carries.

## Step 0 (optional) -- make a corpus you can trust, and two you cannot

```
python -m opencontractml.synth_corpus --out out/honest --n 200
python -m opencontractml.synth_corpus --out out/meshonly --n 60 --defect mesh-only
python -m opencontractml.synth_corpus --out out/diverged --n 60 --defect diverged
```

The honest one is a three-component heat-shield chain solved by
thermal-mesh-calculators; the `mesh-only` one reproduces the shape of a
sweep whose swept axes change only the mesh, never the physics.

## Step 1 -- G1: is the corpus fit to train on?

```
python -m opencontractml.corpus_gate --corpus out/honest/training_corpus.parquet --rules <rules.json> --report out/honest_G1.json
python -m opencontractml.corpus_gate --corpus out/meshonly/training_corpus.parquet --rules <rules.json> --report out/meshonly_G1.json
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
reference them by column.

## Step 2 -- M1: train

```
python -m opencontractml.train_b1 --corpus out/honest/training_corpus.parquet --gate-report out/honest_G1.json --rules <rules.json> --out out/honest_model
```

Expected: one line per (component, target) with the calibration RMSE of
every candidate and the champion, e.g. `heat_shield/T_max_K
champion=gp cal-RMSE ens=16.1 lin=5.74 poly2=0.967 gp=0.0384`. The
trainer refuses (exit 2) when the G1 report says FAIL -- try it with
`out/meshonly_G1.json`. `out/honest_model/model_meta.json` records the
corpus sha256, the split indices, seeds and library versions.

## Step 3 -- V1 / V2 / V3: validate

```
python -m opencontractml.gate --corpus out/honest/training_corpus.parquet --gate-report out/honest_G1.json --rules <rules.json> --model out/honest_model --card out/honest_model_card.json
```

Expected: per model, `[PASS]` on V1.1 (held-out accuracy), V1.2 (corner
extrapolation), V1.3 (interval coverage), V1.4 (baseline beat), the V2.1
monotone pairs and V2.2 bounds; then V1.5 reproducibility, the V2.3/V2.4
declarations, the V3 fields, and `MODEL GATE PASS`. The model card is the
deliverable a reviewer reads: every number above plus the use statement
(`extrapolation-tolerant on <axis> up to the corner threshold` or
`interpolation-only`). Read the V2.3/V2.4 lines with the README's known
defect in mind: a declaration passes whether or not it was checked.

## Step 4 -- the same ladder on a real solver corpus

The three commands of Steps 1-3 run unchanged on a real solver corpus in
the same schema, with that vertical's rules file. On a corpus of 96
CalculiX solves of an annular brake disc, the expected outcome was G1
PASS, GP champions for `T_min_K` and `max_vm_stress_Pa`, a linear
champion for `margin_K` (it is an identity), and MODEL GATE PASS. That
corpus and its rules file are not included here.

## Step 5 -- make the gates fail on purpose

The engine was developed with a 12-test suite that is not included here.
Five of its tests are fail demonstrations: shuffled targets fail V1.1
and V1.4; a zero-width interval fails V1.3; an inverted feature fails
V2.1; a linear target makes the linear model the honest champion; and the
mesh-only corpus fails G1.3 with and without the `solver_input_hash`
column. Step 1's second command is the one you can reproduce from here.

## Things worth knowing

- The gate report's `admissible_index` is the only bridge between G1 and
  M1. Keep the report next to the model; the model card records the corpus
  sha256 so a mismatch is visible.
- A null `margin_K` on a component without a limit is legitimate; the
  trainer drops nulls per target, and G1.2 reports them.
- Thresholds in the rules files are provisional. Change them in the rules
  file, never in the code, and say why in the file.
- `mesh_size_mm` and `n_cells` are never features (feature_policy). They
  are provenance; G1.3(d) is what watches them.
- Log transforms are a rules-file decision per target and per feature;
  the model gate works in original units regardless.
