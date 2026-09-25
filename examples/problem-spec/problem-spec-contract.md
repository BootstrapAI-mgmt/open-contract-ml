# Problem-spec contract — surrogate-family selector

The machine-readable definition of exactly what a surrogate-family
selector expects as its problem spec. It is the requirements-side
analogue of the data-contract sheets the worked cells ship
(`examples/worked-cells/*/data/data-contract.md`): the same role, but the
thing being contracted is a description of *requirements* rather than a
table of CAE runs — the selector never sees your data. The selector
itself is not part of this repository; this sheet and
`problem-spec-template.yaml` are published as the definition of the
format it reads.

Fill in `problem-spec-template.yaml` against this sheet, or answer the same
questions conversationally in the selector's `--interactive` mode and let
it write the file for you.

---

## 1. File format

One field per line:

```
field_name: value
```

- Anything from a `#` to end of line is a comment.
- Field order does not matter. Blank lines are ignored.
- Values may be quoted (`'x'` or `"x"`); the quotes are stripped.
- Yes/no fields accept `yes` / `no` / `true` / `false` / `y` / `n` / `1` / `0`
  / `on` / `off`, in any case.
- `problem_name`, `author`, `notes` and `date` are recorded on the verdict
  sheet and ignored by the rules. Any other unrecognised field is an error,
  with a did-you-mean suggestion.

This is a deliberately small subset of YAML, parsed by the tool itself, so
running the selector needs nothing beyond what the engine already needed
(`numpy` + `scikit-learn`). Nested structures, lists and multi-line values
are **not** supported and are not needed.

**All sixteen fields below must be present.** A missing, misspelled or
out-of-vocabulary field stops the run before any rule fires, and the message
names the field and lists its allowed values. Nothing is guessed and nothing
is defaulted silently — a default you did not see is a requirement you did
not declare.

---

## 2. The sixteen fields

`reads` names the Stage-1 hard filters (R1–R9) and Stage-2 preference rules
(P1–P6) that branch on the field. Three fields are carried by the schema and
read by no rule; they are recorded on the verdict sheet so the assumption is
stated aloud rather than hidden.

### 2.1 How the response behaves

| field | allowed values | reads |
|---|---|---|
| `response_class` | `known_physics_low_order`, `smooth_nonlinear`, `kinked_nonsmooth`, `discontinuous`, `unknown` | R4 (one arm), P1–P6, the accuracy-tie class |

- **`known_physics_low_order`** — a known physical relation underlies it and,
  in the right variables, it is close to linear or quadratic. A steady energy
  balance, a similarity law, a beam formula. This is the strongest claim on
  the list; it is what puts the fixed-basis polynomial family first.
- **`smooth_nonlinear`** — curved but smooth: no kinks, no jumps.
- **`kinked_nonsmooth`** — continuous but with kinks, thresholds or regime
  changes. Contact engaging, flow reattaching, a mode crossing.
- **`discontinuous`** — it jumps across some boundary in the design space.
- **`unknown`** — not characterised yet, or it varies by region. A legitimate
  answer; it routes to the exploratory and catch-all preference rules rather
  than to a wrong one.

### 2.2 Repeatability of the source

| field | allowed values | reads |
|---|---|---|
| `deterministic` | `yes`, `no` | R9, P2 / P3 / P6 |
| `noise` | `none`, `low`, `high` | R9, P2 / P3 / P6 |

**Coherence rule, enforced:** `deterministic: yes` requires `noise: none`, and
`deterministic: no` requires `noise: low` or `noise: high`. The pair describes
one physical fact — whether re-running an input reproduces the number — and
the tool refuses a spec that answers it two ways. `--interactive` asks it as a
single question for this reason.

### 2.3 The dataset you already have

| field | allowed values | reads |
|---|---|---|
| `doe` | `full_factorial`, `space_filling`, `observational` | *(recorded only)* |
| `N_bin` | `tiny` (<30), `small` (30–300), `medium` (300–5,000), `large` (>5,000) | R7 (large), R8 (tiny), P2 / P3 / P5 |
| `d_bin` | `d1_3`, `d4_10`, `d11_20` | *(recorded only)* |

- `N_bin` is a hard filter at both ends: above roughly 5,000 runs the exact
  Gaussian-process family is excluded on cost and the amortized in-context
  family on its published sample cap; below 30 the MLP family is excluded and
  the partition families are disfavoured.
- `doe` is recorded, not branched on. DOE geometry decides whether a family
  that is *admissible* is also adequately *sampled*, which is a question the
  falsifier benchmark measures and this selector does not.
- `d_bin` is recorded, not branched on: every bin is inside the selector's
  declared scope (d ≤ 20), so no rule discriminates between them. **If your
  problem varies more than 20 inputs you are outside the scope this selector
  was built and tested for** — the verdict is still computed, but say so
  wherever you use it.

### 2.4 What you will do with the model

These are the answers that prune families. Answer `yes` only for things you
will actually do.

| field | allowed values | reads |
|---|---|---|
| `needs_inverse` | `yes`, `no` | R1 |
| `needs_gradients` | `yes`, `no` | R1 |
| `needs_smooth_sweeps` | `yes`, `no` | R1 |
| `needs_monotonicity` | `yes`, `no` | R2 |
| `needs_native_uq` | `yes`, `no` | R3 |
| `conformal_ok` | `yes`, `no` | R3, R4 |
| `needs_honest_extrapolation` | `yes`, `no` | R4 |
| `deployment_tiny` | `yes`, `no` | R5 |
| `needs_equation_interpretability` | `yes`, `no` | R6 |

- **The three R1 fields are the most consequential answers in the spec.** Any
  one of them set to `yes` removes the recursive-partition, memory-based and
  amortized families from consideration — because a root-find needs a
  continuous surface with a sign change across the bracket, and those three
  do not provide one. `needs_inverse` means you will solve the model
  *backwards* numerically; `needs_gradients` means something will
  differentiate the model itself; `needs_smooth_sweeps` means somebody will
  read a design trend off a fine sweep and the staircase of a piecewise-
  constant model would be read as physics.
- **`needs_monotonicity` is a requirement, not a hope.** Set it `yes` only if
  a non-monotone prediction would be rejected as invalid rather than merely
  surprising. It is a strong filter: three families survive it.
- **`conformal_ok` does double duty and is easy to get wrong.** It answers
  "is a band calibrated after the fact acceptable?" for R3 *and* "is an
  explicit out-of-range guard acceptable?" for R4. `yes` is the permissive
  answer and keeps families in play; `no` says you need the model's own
  posterior and no bolt-on, which combined with
  `needs_honest_extrapolation: yes` leaves exactly one family.
- **`needs_equation_interpretability` is about the artifact, not about
  trust.** Set it `yes` when a readable closed-form expression is itself a
  deliverable — a design guide, a standards submission, a hand-checkable
  calculation. Wanting to understand what the model is doing is not this
  requirement.
- **`deployment_tiny`** means the finished model ships inside a spreadsheet
  or a small standalone executable. It rarely changes the top pick, but it
  flags families whose stored artifact would be expensive to carry.

### 2.5 Recorded, never branched on

| field | allowed values | reads |
|---|---|---|
| `low_tuning_budget` | `yes`, `no` | *(recorded only)* |

No rule reads it, because tuning burden is exactly what the final tie-break
already orders on, in every scenario. It is in the spec so the verdict sheet
states the assumption out loud.

---

## 3. What the tool returns

One Markdown verdict sheet, `surrogate-verdict-<problem_name>.md`, written to
the folder you point `--out` at (this folder by default). It carries the
recommended family, the admissible set with per-family similarity, every
answer you gave, the rule trace with its citation keys,
the four things the verdict does not claim, and a provenance block stamping
the engine's sha256 and the run date. It is written to stand on its own in an
email.

If the verdict is `NONE`, the sheet says so and explains what to do about it.
`NONE` is not an error: it means the requirements you declared are
individually satisfiable but jointly over-determined, which is a real and
useful finding about the problem — roughly 30% of the selector's full
scenario enumeration lands there.

---

## 4. Worked examples

Three specs the selector was exercised on. The spec files are not
included here; the first describes the dataset in
`examples/worked-cells/thermal-doe-worked-instance/`.

| spec | what it is | expected verdict |
|---|---|---|
| thermal DOE | the 720-row full-factorial thermal DOE of the thermal DOE worked instance — inverse solve, sensitivities, smooth sweeps, Excel-tier deployment | **B1**, admissible {B1, B2, B4, B3} |
| the selector's own problem | predict a family from a problem's shape | **B6**, admissible {B6} |
| NVH rig peak SPL | a problem described as a measured NVH rig peak sound-pressure level: kinked, noisy, ~1,200 runs, no smoothness requirement | **B6**, admissible {B6, B7, B10} |

The first and third are the pair worth reading together. Same tool, same
rules, opposite verdicts — because the requirements differ, not because the
taxonomy prefers smooth families.

---

*Contract written 2026-08-15. The selector reads the field schema,
vocabularies and coherence rule from its own engine at run time; this
sheet documents them and does not redefine them. If the two ever
disagree, the engine is right and this sheet is the defect.*
