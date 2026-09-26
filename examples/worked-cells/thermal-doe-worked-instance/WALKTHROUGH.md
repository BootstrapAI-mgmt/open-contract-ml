# Thermal DOE worked instance — watching a family get excluded

### The short form: the argument is about requirements, and this folder is the evidence.

> A worked instance for a surrogate-selection taxonomy: a set of rules
> that picks surrogate families from a problem's declared requirements.
> The taxonomy document itself is not published here. Its companions in
> this repository are `examples/problem-spec/` — the format a
> surrogate-family selector reads to reach a verdict from a description
> of your problem — and `examples/falsifier-benchmark/` — the
> experiment that grounds the taxonomy's tolerances.
>
> This is deliberately a **short** walkthrough. The other worked cells
> teach you to build something; this one asks you to watch one thing
> happen, once.
>
> **What ships here:** this walkthrough, the data contract, and the
> dataset with the script that generates it. The head-to-head script
> Step 2 runs (`run_ht_instance.py`) is not part of this repository, so
> read Step 2 onward as a record of what it measured.
>
> You will not write code or make any machine-learning decisions.

---

## 1. The question this exists to settle

Someone built a surrogate for a thermal DOE. They tried a neural
network and they tried a quadratic. By the practitioner's own account,
the two were empirically within a few percent of each other, and the
choice between them was made on the downstream use rather than on test
accuracy. They shipped the quadratic.

That answer is the correct one and it loses the room, because a gap of
a few percent sounds like it does not matter. It matters enormously. It
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

The head-to-head needs Python with `numpy`, `scipy` and `scikit-learn`;
the dataset generator needs only the standard library.

The dataset ships in the folder. If you want to see it rebuilt from
nothing, `synthesize_sample.py` regenerates it byte-for-byte — it
contains no random number of any kind, so "regenerate" means exactly
that.

---

## 3. Step 1 — Look at the data

```
cd examples/worked-cells/thermal-doe-worked-instance
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

**Six clearance levels is not many, and that is deliberate.** One of
the practitioner's own points was that a partition model interpolates
between full-factorial levels as a staircase, while engineers query
between the nodes — and §4 below is where that starts to cost
somebody something.

---

## 4. Step 2 — Run the head-to-head

```
python run_ht_instance.py
```

It takes about a minute. The script is not included in this
repository; what follows is what it measured. It fits three families to
the same 720 rows, through
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
a family on this evidence. This is where the comparison usually
stops.

**The ablation (§3b) is why the quadratic is even in the running.**
The four engineered features — a gap conductance, a linearised
radiation term, and two temperature-rise groups — are handed to all
three families identically. Take them away and the quadratic gets
**36× worse**; the forest gets 1.1× worse and the network gets nothing
worse at all. Same features, same rows; only one family has a way of
using them. That is the whole reason for grouping models by
*estimation principle* rather than by what they are called, and it is
the taxonomy's P1 preference rule demonstrated rather than asserted.

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
   this design" and the forest is a perfectly reasonable answer. For a
   problem described as a measured NVH rig — kinked and noisy, with no
   smoothness requirement — the same selection returns B6. Read the two
   together or you will draw the wrong conclusion from this one.
2. **It does not show that the quadratic is accurate because it is a
   quadratic.** See §3b. It is accurate because somebody wrote down the
   energy balance first.
3. **It is a synthetic surface with an exactly known answer.** That is
   what makes the gradient and inverse comparisons gradeable at all —
   you cannot score a root-find without knowing the root. It also means
   the surface is smoother and cleaner than real conjugate thermal-FE
   output, and the separations here are correspondingly crisp. See
   §7 below.
4. **Family choice is usually not the biggest lever.** Be careful about
   this. The benchmark literature finds that over a large sweep of
   datasets the accuracy gap
   between boosted trees and neural networks is frequently negligible,
   and that modest tuning effort spent on a boosted-tree baseline tends
   to buy more than switching families does ([McElfresh2023]).

   That finding carries a caveat this folder inherits: the study is
   **classification-only**, across 176 OpenML
   datasets, and it transfers to a deterministic regression surrogate at
   N = 720 by analogy rather than by measurement. What this instance
   shows is a case where the family choice is load-bearing **because a
   requirement is** — not a general claim that families matter most.

---

## 7. Where this instance disagrees with the taxonomy

The head-to-head prints a cross-check (§7 of its output) against the
bands the falsifier benchmark published, which the taxonomy quotes in
support of its R1 exclusion. **Six of seven cross-checks land outside
those bands.** The direction of every axis agrees with the taxonomy;
the magnitudes do not.

The separations here are *sharper* than the falsifier predicted at
comparable sample size — the forest solves 7% of inverses where the
falsifier's N ≈ 800 cells gave 57%, and the sweep-roughness ratio is
409× where the taxonomy says ≈ 40×. Two results also sit below band in the
other direction: the network's gradient cosine (0.977 against a
0.999–1.000 smooth-family band) and its inverse success (62% against
85–94%).

The likely mechanism is the one the practitioner's account already
pointed at. The
falsifier's designs are space-filling, so a partition model sees many
distinct values per axis and can build a fine staircase. A six-level
full factorial gives it five interior thresholds and nothing between
them. **The falsifier never varied design structure** — it varied
sample size, dimensionality and noise. That is a real gap in its
coverage, and this instance is the first thing in this repository to walk
into it.

This is recorded here rather than smoothed over because a worked
instance that only ever confirms its document is not evidence of
anything. The follow-on — a falsifier cell that varies design structure
at fixed N — was queued at the time and has since been run (below).

One further result the taxonomy does not predict: **the network fails 15 of 40
inverses on a 0.40 °C held-out error.** The inverse requirement is
tighter than the accuracy requirement — being right to half a degree is
not the same as putting the root in the right place. The taxonomy keeps
B7 out of the admissible set for a different reason (tuning cost). The
conclusion survives; the mechanism the taxonomy gives for it is not the
only one operating.

### What has since been measured — added 2026-08-19

The follow-on flagged above has been run. The taxonomy now carries two
qualifiers on the falsifier's bands, and between them they account for
**one** of the two headline misses on this page and not the other. Read
what follows as a pointer, not a retraction: every number above stands,
and six of seven cross-checks still land outside band.

**Accounted for — the partition gradient cosine (0.000 here).** The
falsifier's design axis was extended to a matched-N full-factorial
lattice — 49 / 196 / 784 against the existing LHS 50 / 200 / 800, on
smooth d = 2 surfaces at noise 0 — and reported as
`falsifier_results.txt` §V10 and the taxonomy's first qualifier. On that
lattice the forest's gradient cosine falls **0.647 → 0.122**: a
structure leg of 0.525, larger than its entire N leg of 0.492, landing
past the low end of the 0.116–0.755 band. That is this instance's
direction, on the family that produced it. The staircase mechanism
named above is now measured rather than hypothesised — on one of the
two axes.

**Now mostly accounted for — the partition bisection success (0.075
here).** *This supersedes the 2026-08-19 reading, which said
nothing explained this miss; the measurement it asked for was made two
days later (§V11, §V12, 2026-08-21).* The design half of that reading holds
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
where for three passes running it was nothing.

**Neither an accounting nor an excuse — the toolchain.** The taxonomy's second qualifier
records that `falsifier_results.txt` is venue-sensitive: re-run on a
different toolchain, most of the file moves. But verdict blocks §V2 and
§V3 — where the bisection and gradient bands quoted on this page are
read from — are byte-identical across both venues it has been run on.
The venue does not explain any of these misses either.

So this page's disagreement with the taxonomy has gone from two open questions to
two measured answers and one sharper question. The gradient miss is
design structure; the bisection miss is dimensionality; and what remains
is not "why does this instance miss" but "why does this instance behave
like a space-filling design when it is a lattice" — a question with two
named candidates and a runtime cost, rather than a blank.

---

## 8. Where to go next

- **`examples/problem-spec/`** — the format for asking the same
  question about *your* problem: a filled problem spec is what a
  surrogate-family selector reads. For this instance the taxonomy's
  rule-by-rule walk runs: R1 excludes B6/B8/B10; P1 puts B1 first; the
  tie-break lands on B1 quadratic with an admissible set of
  {B1, B2, B4, B3}. Everything you just watched is one row of that walk.
- **`examples/falsifier-benchmark/`** — the measurement the
  taxonomy's tolerances rest on, and the thing §7 above disagrees with.
- **The other worked cells** — if what you actually want is to build a
  surrogate rather than choose one, `peak-temperature` is the thermal B1
  example and the closest sibling to this folder's physics.

---

*Instance built 2026-08-16. The physics and the DOE live in
`data/synthesize_sample.py`; the head-to-head script imports them from
there rather than restating them, so there is exactly one copy of the
truth.*

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../../docs/REFERENCES.md).*
