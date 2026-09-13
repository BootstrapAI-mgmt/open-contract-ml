# TASK-9 H-T Worked Instance — watching a family get excluded

### The short form. The argument lives in taxonomy §8; this folder is the part you can run.

> Part of TASK-9 (`TASK-9-TAXONOMY-scalar-surrogate-selection.md`).
> Its two companions are
> `examples/TASK-9-surrogate-selector/` — the tool that reaches the
> verdict from a description of your problem — and
> `examples/TASK-9-falsifier-benchmark/` — the experiment that grounds
> the taxonomy's tolerances.
>
> This is deliberately a **short** walkthrough. The TASK-8 examples
> teach you to build something; this one asks you to watch one thing
> happen, once, and then sends you back to §8 for what it means.
>
> You will not write code or make any machine-learning decisions.
> Two commands.

---

## 1. The question this exists to settle

Someone built a surrogate for a thermal DOE. They tried a neural
network and they tried a quadratic. In the words of the debrief this
card was written from: *"Empirically they were within a few percent
[...] The selection wasn't driven by test accuracy; it was driven by
the downstream use."* They shipped the quadratic.

That answer is the correct one and it loses the room, because "within a
few percent" sounds like "it doesn't matter." It matters enormously. It
just doesn't matter on the axis being measured.

The DOE's product was not a prediction. It was an **inverse**:

> *what clearance keeps this under 120 °C?*

This folder fits all three families to the same data and asks all three
that question. Then it counts.

---

## 2. What you'll need before you start

Nothing from your own work. That is the point of a worked instance —
everyone runs the same 720 rows so the numbers can be reproduced
instead of taken on trust.

You need Python with `numpy`, `scipy` and `scikit-learn`. If you have
run any TASK-8 example's trainer, you already have all three.

The dataset ships in the folder. If you want to see it rebuilt from
nothing, `synthesize_sample.py` regenerates it byte-for-byte — it
contains no random number of any kind, so "regenerate" means exactly
that.

---

## 3. Step 1 — Look at the data

```
cd examples/TASK-9-HT-worked-instance
python data/synthesize_sample.py
```

720 rows. Five things you can change — the clearance gap, the heat
load, the coolant temperature, the surface emissivity, and how well the
mounting feet conduct — and five things that come out, of which the one
everybody cares about is `T_peak_C`.

It is a **full factorial**: six clearance values, five heat loads, four
coolant temperatures, three emissivities, two mount conductances, every
combination present exactly once. `data/data-contract.md` has the
columns, the units and the ranges.

Two lines of that output are worth pausing on, because both are checks
rather than claims:

- `energy-balance closure ... 2.9e-10 W` — the three heat paths add up
  to the heat going in, everywhere, to within a rounding error. The
  physics is closed.
- `worst-case gap Rayleigh number : 32.4 (conduction regime needs
  < 1708)` — the gap model assumes the air in the clearance conducts
  rather than circulates. That assumption is checked on every run
  instead of being asserted once in a comment.

**Six clearance levels is not many, and that is deliberate.** It is the
third bullet of the original debrief — *"staircase interpolation between
full-factorial levels (engineers query between nodes)"* — and §4 below
is where it starts to cost somebody something.

---

## 4. Step 2 — Run the head-to-head

```
python run_ht_instance.py
```

About a minute. It fits three families to the same 720 rows, through
the same engineered features, at the same declared tuning budget — at
most three configurations each, chosen by the same five-fold
cross-validation:

| | family | what its estimation principle is, in one line |
|---|---|---|
| **B1** | quadratic | one global equation fitted to all the data at once |
| **B6** | random forest | chop the space into boxes, average within each box |
| **B7** | neural network | a smooth flexible function fitted by gradient descent |

Everything after that is measurement.

---

## 5. Step 3 — Read the result

Five blocks come out. Read them in this order.

**The accuracy table (§3) is the tie.** All three land within a few
degrees on held-out DOE rows they were never shown. Nobody would reject
a family on this evidence. This is the conversation the interview was
having.

**The ablation (§3b) is why the quadratic is even in the running.**
The four engineered features — a gap conductance, a linearised
radiation term, and two temperature-rise groups — are handed to all
three families identically. Take them away and the quadratic gets
**36× worse**; the forest gets 1.1× worse and the network gets nothing
worse at all. Same features, same rows; only one family has a way of
using them. That is the taxonomy's whole reason for grouping models by
*estimation principle* rather than by what they are called
(doc §2.1/§2.2), and it is P1 demonstrated rather than asserted.

> **Worth sitting with:** on the raw inputs, with no physics basis, the
> network is *better* than the quadratic. The quadratic's accuracy
> advantage is borrowed entirely from the engineering that went into
> the features. If someone tells you polynomials beat neural networks
> on thermal problems, this is the number that says "only when somebody
> did the physics first."

**The inverse (§4) is where it stops being a tie.** Forty operating
points that are *not* on the DOE grid — the "engineers query between
nodes" case — each with a true clearance answer that the exact physics
knows. Same solver, same tolerance, same 2%-of-range success test for
all three:

| family | solves the inverse |
|---|---|
| B1 quadratic | **40 / 40** |
| B6 forest | **3 / 40** |
| B7 network | 25 / 40 |

The forest's 37 failures split into 3 where its prediction never
crosses 120 °C anywhere in the clearance range — there is no bracket, so
there is nothing to bisect — and 34 where it crosses in the wrong place,
by up to 0.59 mm on a 1.50 mm range.

And the test is *generous* to the forest: when its staircase crosses
120 °C several times, the script picks the crossing nearest the true
answer. A real user has no true answer to steer by and would take the
first one. 3 / 40 is the optimistic number.

**The gradients (§5) close the second axis.** Sensitivities — "how much
does peak temperature move if I open the clearance by ten microns" —
come back from the forest as **exactly zero, at 100% of the probe
points**, because inside a box the answer does not depend on where in
the box you are. Cosine against the true gradient: 0.000. The quadratic
manages 0.9994, and hands back a **closed-form** sensitivity — a
formula, not a numerical estimate, agreeing with its own finite
differences to three parts in a billion.

**The sweeps (§6) close the third.** A clearance sweep from the forest
does not move on 92% of its length and then jumps. Roughness ratio
against the quadratic: **409×**.

---

## 6. Reading this responsibly

Four things this folder does **not** show.

1. **It does not show that random forests are bad.** It shows that this
   *question* — an inverse, with gradients, read off a smooth sweep —
   excludes them. Change the question to "predict the temperature of
   this design" and the forest is a perfectly reasonable answer. The
   selector folder ships a spec where the verdict genuinely *is* B6: a
   measured NVH rig, kinked and noisy, with no smoothness requirement.
   Read the two together or you will draw the wrong conclusion from
   this one.
2. **It does not show that the quadratic is accurate because it is a
   quadratic.** See §3b. It is accurate because somebody wrote down the
   energy balance first.
3. **It is a synthetic surface with an exactly known answer.** That is
   what makes the gradient and inverse comparisons gradeable at all —
   you cannot score a root-find without knowing the root. It also means
   the surface is smoother and cleaner than real conjugate thermal-FE
   output, and the separations here are correspondingly crisp. See
   §7 below, and taxonomy §9 for the boundaries on the whole taxonomy.
4. **Family choice is usually not the biggest lever.** The taxonomy is
   careful about this and so should you be. The benchmark literature it
   leans on reports that

   > "the 'NN vs. GBDT' debate is overemphasized: for a surprisingly
   > high number of datasets, either the performance difference between
   > GBDTs and NNs is negligible, or light hyperparameter tuning on a
   > GBDT is more important than choosing between NNs and GBDTs"
   >
   > — [McElfresh2023], abstract, p. 1 (Q-surr-04)

   with the caveat the taxonomy states and this folder inherits: that
   study is **classification-only**, across 176 OpenML datasets, and it
   transfers to a deterministic regression surrogate at N = 720 by
   analogy rather than by measurement. What this instance shows is a
   case where the family choice is load-bearing **because a requirement
   is** — not a general claim that families matter most.

---

## 7. Where this instance disagrees with the document

The head-to-head prints a cross-check (§7 of its output) against the
bands the falsifier benchmark published, which taxonomy §8 quotes in
support of its R1 exclusion. **Six of seven cross-checks land outside
those bands.** The direction of every axis agrees with §8; the
magnitudes do not.

The separations here are *sharper* than the falsifier predicted at
comparable sample size — the forest solves 7% of inverses where the
falsifier's N ≈ 800 cells gave 57%, and the sweep-roughness ratio is
409× where §8 says "≈ 40×". Two results also sit below band in the
other direction: the network's gradient cosine (0.977 against a
0.999–1.000 smooth-family band) and its inverse success (62% against
85–94%).

The likely mechanism is the one the debrief already named. The
falsifier's designs are space-filling, so a partition model sees many
distinct values per axis and can build a fine staircase. A six-level
full factorial gives it five interior thresholds and nothing between
them. **The falsifier never varied design structure** — it varied
sample size, dimensionality and noise. That is a real gap in its
coverage, and this instance is the first thing in the project to walk
into it.

This is recorded here rather than smoothed over because a worked
instance that only ever confirms its document is not evidence of
anything. The follow-on — a falsifier cell that varies design structure
at fixed N — is logged in the session HANDOFF.

One further result §8 does not predict: **the network fails 15 of 40
inverses on a 0.40 °C held-out error.** The inverse requirement is
tighter than the accuracy requirement — being right to half a degree is
not the same as putting the root in the right place. §8 keeps B7 out of
the admissible set for a different reason (tuning cost, IC-5). The
conclusion survives; the mechanism §8 gives for it is not the only one
operating.

### What has since been measured — added 2026-08-19 (TASK-9-D1)

The follow-on flagged above has been run. Taxonomy §8 now carries two
qualifiers on the falsifier's bands, and between them they account for
**one** of the two headline misses on this page and not the other. Read
what follows as a pointer, not a retraction: every number above stands,
and six of seven cross-checks still land outside band.

**Accounted for — the partition gradient cosine (0.000 here).** The
falsifier's design axis was extended to a matched-N full-factorial
lattice — 49 / 196 / 784 against the existing LHS 50 / 200 / 800, on
smooth d = 2 surfaces at noise 0 — and reported as
`falsifier_results.txt` §V10 and taxonomy §8 qualifier 1. On that
lattice the forest's gradient cosine falls **0.647 → 0.122**: a
structure leg of 0.525, larger than its entire N leg of 0.492, landing
past the low end of the 0.116–0.755 band. That is this instance's
direction, on the family that produced it. The staircase mechanism
named above is now measured rather than hypothesised — on one of the
two axes.

**Now mostly accounted for — the partition bisection success (0.075
here).** *This supersedes the 2026-08-19 (TASK-9-D) reading, which said
nothing explained this miss; the measurement it asked for was made two
days later (§V11, §V12, TASK-9-E, 2026-08-21).* The design half of that reading holds
and hardens. On bisection, design structure has **no pooled direction at
all**: it splits in sign by family *and* by surface — quad-int +0.217,
sin-exp −0.150, linear −0.017 — so the 0.133 previously quoted is only
the largest *per-family* leg, and the largest leg outright is 0.217, on
a surface unlike this one. What closes the gap is **dimensionality**.
The falsifier's d = 5 surface is its d = 2 `sin-exp` surface plus two
smooth low-order terms — a function against its own extension — and
across that step the partition families fall **0.483 → 0.150** at
matched N = 800 (**0.067** at N = 200), a leg of **−0.333** that
*brackets* this instance's number. Restricted to the single axis both
cells admit slices on, the leg is still **−0.241**, so it is not an
artefact of which axes got sampled. **Level anisotropy turns out to be
the wrong sign:** a 6×5×4×3×2 lattice — this instance's own design,
built in the falsifier for the first time — scores **0.317** at N = 720
against its space-filling control's **0.050**, moving bisection *away*
from this number by +0.267. And that space-filling control, at matched N
and matched dimension with no grid structure at all, lands within one
slice (0.05) of this instance's 0.075. **Still open:** why this
instance, itself a 6×5×4×3×2 lattice, behaves like that control rather
than like the falsifier's anisotropic one. Two differences are left —
the surface (the falsifier's is not a thermal energy balance) and this
instance's physical axis ranges against the falsifier's equispaced unit
cube. Reported, not resolved — but the list of candidates is now two,
where three sessions running it was "nothing".

**Neither an accounting nor an excuse — the toolchain.** §8 qualifier 2
records that `falsifier_results.txt` is venue-sensitive: re-run on a
different toolchain, most of the file moves. But verdict blocks §V2 and
§V3 — where the bisection and gradient bands quoted on this page are
read from — are byte-identical across both venues it has been run on.
The venue does not explain any of these misses either.

So this page's disagreement with §8 has gone from two open questions to
two measured answers and one sharper question. The gradient miss is
design structure; the bisection miss is dimensionality; and what remains
is not "why does this instance miss" but "why does this instance behave
like a space-filling design when it is a lattice" — a question with two
named candidates and a runtime cost, rather than a blank.

---

## 8. Where to go next

- **`TASK-9-TAXONOMY-scalar-surrogate-selection.md` §8** — the
  rule-by-rule walk this folder executes. R1 excludes B6/B8/B10; P1
  puts B1 first; the tie-break lands on B1 quadratic with an admissible
  set of {B1, B2, B4, B3}. Everything you just watched is one row of
  that table.
- **`examples/TASK-9-surrogate-selector/`** — ask the same question
  about *your* problem. `data/spec-HT-thermal-doe.yaml` is this
  instance as a filled spec; run it and you get the §8 verdict from the
  rule engine rather than from an experiment.
- **`examples/TASK-9-falsifier-benchmark/`** — the measurement the
  taxonomy's tolerances rest on, and the thing §7 above disagrees with.
- **`presentations/Presentation-TASK-9-Surrogate-Selection.pptx`** — the
  same argument for a room.
- **The TASK-8 arc** — if what you actually want is to build a
  surrogate rather than choose one, `TASK-8-1104` is the thermal B1
  example and the closest sibling to this folder's physics.

---

*Instance built 2026-08-16 (session TASK-9-B3), closing audit finding
F-4. Physics, DOE and grading all live in this folder; there is exactly
one copy of the truth and `run_ht_instance.py` imports it from
`data/synthesize_sample.py` rather than restating it.*
