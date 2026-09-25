# The Contract, version 1.0

**Status:** normative. **Spec authority:** this repository; the text below is
self-contained. **Checker:** `opencontractml.verify` in this repository
(`open-contract-ml check`). **Roles:** a *producer* emits contract packages; a
*consumer* (a dispatching GUI, a registry, a checker) reads and enforces them.

---

## 1. Why this exists

The goal is one model-card / manifest / provenance contract shared by every
producer and consumer. As of 2026-09-12 that contract did not exist. What existed was
five artifacts with the same ambitions and almost no shared surface, spread over a
scalar-surrogate producer, a field-surrogate producer and a consumer:

| # | Artifact | Where | Kind |
|---|---|---|---|
| 1 | a worked-instance model card (the cards in `examples/worked-model-cards/`) | scalar producer | human prose, 9 numbered sections, no front-matter |
| 2 | `model_card.json` from the scalar model gate (`opencontractml.gate` here) | scalar producer | machine gate report keyed V1/V2/V3 |
| 3 | `model_card.json` from the grid, mesh and point-cloud field gates | field producer | machine gate report keyed FG1..FG10 |
| 4 | `model_card.md` | consumer (a dispatching GUI) | human prose, 9 named sections, YAML front-matter |
| 5 | `manifest.yaml` | consumer (a dispatching GUI) | the machine contract that actually gates admission |

Three facts, each reproduced rather than asserted when this version was written:

1. **The enforcer rejects the pioneer.** The consumer's card validator rejected
   all three of the worked-instance model cards with **10 errors each** -- one
   missing front-matter, nine section mismatches.
2. **The two prose cards share two concepts and zero labels.** Only *architecture*
   and *uncertainty quantification* appear on both lists, and neither under the same
   heading string.
3. **`model_card` names two different things.** In the consumer it is prose for a
   human reader. In the two producers it is the machine gate report. These are
   not the same artifact and should never have shared a name. **Contract v1 renames the
   machine one to `validation_report.json`** and reserves `model_card.md` for prose.

Net: four incompatible artifacts, two non-composing ladders, one name collision, and
no converter.

## 2. Scope

This document defines:

- **2.1** the *package* -- what a shipped model is, as a directory;
- **2.2** the *manifest* -- artifact paths, format, entrypoint, I/O signature, hashes;
- **2.3** the *model card* -- one reconciled section set, human-readable;
- **2.4** the *validation report* -- one tiered ladder under which the scalar and field
  ladders are tiers;
- **2.5** *provenance* -- built on the sha256 the two producer repos already carry;
- **2.6** the *compatibility rule* and the conformance vocabulary.

It does **not** set physics thresholds. Every numeric bar stays where it is, owned by
the producer that sets it. The contract requires that a bar be *stated and compared against a
measurement*; what the bar should be is not its business.

## 3. The package

A **contract package** is a directory:

```
<package>/
  manifest.yaml            # or manifest.json -- the machine contract   (required)
  model_card.md            # human prose, eleven required H2 sections    (required)
  validation_report.json   # the tiered ladder verdicts                  (required)
  <entrypoint>             # the file invocation.executable names        (required)
  <weights, assets...>     # whatever the entrypoint loads
```

`manifest.yaml` is normative, because that is what the consumer reads. `manifest.json`
is an accepted byte-for-byte-equivalent alternative for environments with no YAML
parser; a consumer MUST accept either. A checker that cannot parse the manifest MUST
report an error -- never a skip (`verify.py` rule `E002`).

**Line endings.** Hashed artifacts MUST be stored with LF line endings, or be true
binaries. A text artifact that is CRLF on one machine and LF on another cannot be
pinned by byte hash; an EOL-normalising VCS silently changes the bytes on checkout and
rule `M013` fires on a package that was conformant when it was built. This rule was
learned the hard way: the first build of the reference package in this repo tripped it.

## 4. The model card

### 4.1 Front-matter

A card MUST open with a YAML front-matter block delimited by `---` fences containing a
**flat mapping of scalars**. The flatness is a deliberate tightening: it lets any
consumer read a card's identity without a YAML dependency, and every card this
version was reconciled against already satisfies it.

```markdown
---
model_id: contract_reference_tmf_v1
version: 1.0.0
spec_version: "1.0"
---
```

`model_id` MUST equal the manifest's `id`, `version` the manifest's `version`, and
`spec_version` the manifest's `spec_version` (rule `C002`).

### 4.2 The reconciled section set

The **first eleven H2 headings**, in this exact order:

| # | Section | Origin |
|---|---|---|
| 1 | `TL;DR` | consumer card |
| 2 | `Intended use` | consumer card |
| 3 | `Out of scope` | consumer card |
| 4 | `Training data` | consumer card |
| 5 | `Architecture` | both (consumer `Architecture`, worked-instance `Architecture topology`) |
| 6 | `Training configuration` | **inserted** -- worked-instance sections 3, 4 and 5 |
| 7 | `Performance` | consumer card |
| 8 | `Uncertainty quantification` | both (consumer, worked-instance `UQ approach`) |
| 9 | `Known failure modes` | consumer card |
| 10 | `Provenance` | **inserted** -- new; no artifact had it |
| 11 | `Version history` | consumer card |

The nine consumer-card sections keep their original **relative order**. That is the
whole design of this table: moving a nine-section validator to the eleven is *two
inserted strings* in its section list, not a re-ordering and not a rewrite.

After the eleven, a card MAY carry any of these reserved sections, and no others
(rule `C006`, warning severity):

`Alternatives considered` -- `Disclosure` -- `Open questions` -- `References`

`Alternatives considered` and `Disclosure` exist so that the worked-instance cards'
rejected-option tables and their anchored-versus-illustrative discipline survive the
reconciliation rather than being dropped for tidiness. `Disclosure` is the strongest
thing those cards do that no other artifact does, and it is preserved verbatim.

### 4.3 Anti-stub rules

- Every required section MUST carry at least 40 non-whitespace characters (`C004`). A
  heading over `TBD` is not a written section.
- `Uncertainty quantification` MUST name a method and state a number (`C005`). "We are
  confident in this model" is not a UQ section.

## 5. The tiered validation vocabulary

### 5.1 The problem

Two ladders, zero shared keys:

| | scalar (`opencontractml.gate`) | field (the field producer's grid, mesh and cloud gates) |
|---|---|---|
| keys | `V1.1`-`V1.5`, `V2.1`-`V2.4`, `V3` | `FG1`-`FG9` (grid), `FG1`-`FG10` (mesh, cloud) |

The concepts map almost one to one, so convergence is cheap. But the mapping is not
clean, and pretending it is would be the wrong kind of tidy.

### 5.2 The ladder

Fifteen keys. Every key MUST appear in a validation report with one of four statuses.
**A key that is absent is an error** (`V004`), because both producers already held the
principle that a skipped check is never a silent pass -- the field gate says so in its
own docstring -- and the contract promotes that principle to a rule.

**Tier A -- statistical validity.** Applies to every model of every modality.

| key | legacy | what |
|---|---|---|
| `A1_accuracy` | `V1.1` / `FG1` | held-out accuracy on an interior test split |
| `A2_extrapolation` | `V1.2` / `FG2` | the same on a declared extrapolation band, plus a degradation ratio |
| `A3_uq_calibration` | `V1.3` / `FG3` | empirical coverage of the nominal predictive interval |
| `A4_baseline_beat` | `V1.4` / `FG4` | beats a declared baseline roster |
| `A5_reproducibility` | `V1.5` / `FG5` | a same-seed repeat reproduces the metric |

**Tier B -- physics validity.** Modality-conditional. Each is measure-or-declare, and a
declaration is never a pass.

| key | legacy | what |
|---|---|---|
| `B1_monotonicity` | `V2.1` | declared (feature, target, direction) triples on probe lines |
| `B2_bounds` | `V2.2` | declared bounds on a probe set covering the hull |
| `B3_residual` | `FG6` | the governing-equation residual of the *predicted* field |
| `B4_conservation` | `V2.3` / `FG7` (grid, mesh) | see 5.4 |
| `B5_invariance` | `V2.4` / `FG10` | the prediction does not depend on the discretisation or the sampling |
| `B6_integrated_quantities` | `FG11` (cloud; `FG7` before the rename, now retired) | an integrated quantity re-derived from the predicted field |

**Tier C -- deployment readiness.**

| key | legacy | what |
|---|---|---|
| `C1_ood_guard` | `FG8` | the input-space guard passes in-distribution and refuses a far-out design |
| `C2_serve_parity` | `FG9` | the exported forward agrees with the training-framework one |
| `C3_provenance_integrity` | *(new)* | every declared artifact hash re-verifies |
| `C4_deployment_readiness` | `V3` | the deployment declarations, plus a measured runtime against the timeout |

### 5.3 Statuses

| status | meaning | blocks `overall`? |
|---|---|---|
| `PASS` | measured and within the stated threshold | no |
| `FAIL` | measured and outside it | yes |
| `NOT_RUN` | the check applies and was not executed | **yes, always** |
| `NOT_APPLICABLE` | the check cannot apply, with a stated `reason` | no |

`overall` MUST be recomputable from the checks, and a report whose declared `overall`
disagrees with the recomputation is rejected (`V008`). This catches a lying rollup.

`V010` and `V011` grade the instrument of an `A3` or `A5` check that was run: `PASS`
or `FAIL`. A `NOT_RUN` or `NOT_APPLICABLE` check carries no measurement for them to
read, so neither rule applies to it. A `NOT_RUN` key still blocks `overall`, and `V008`
rejects a report that claims otherwise.

The `NOT_RUN` / `NOT_APPLICABLE` split replaces the field producer's `allow_not_run`
allow-list. An allow-list records *that* a skip was tolerated; it does not record *why*,
so the reason is lost at the moment it becomes interesting. The cloud lane's
`allow_not_run_by_task: {full: [FG2]}` becomes `A2_extrapolation: {status:
NOT_APPLICABLE, reason: "the full task has no extrapolation split"}` -- same verdict,
recoverable rationale.

**Presence is not compliance (`V006`).** A check reporting `PASS` MUST carry at least one
numeric value in `metrics` *and* at least one in `thresholds`. Booleans do not count as
numbers. A check that compares against nothing cannot fail, and a check that cannot fail
is not a check.

### 5.4 One definition of conservation

This is where the two ladders most need a single answer, and where one of them is
currently vacuous.

> **B4 conservation.** For each extensive quantity `Q` the model's physics conserves,
> the report MUST state a dimensionless **relative imbalance**
>
> ```
> r_Q = |sum(in) - sum(out) - sum(stored)| / sum(|gross flow|)
> ```
>
> evaluated **on the model's own prediction** -- no reference solution -- over a named
> `control_volume`, with a `scope` of `control_volume` (an integral balance) or `local`
> (a per-cell balance), together with the `threshold` it was compared against and the
> `n` it was evaluated over.
>
> A model that conserves nothing MUST declare `applicable: false` **with a reason**, and
> carry status `NOT_APPLICABLE`. That is not a `PASS` and it is visible in the rollup.

Consequences, stated plainly:

- **The field producer's FG7 (grid, mesh) already complies.** It computes
  `|source - sink - edge| / gross` from the predicted field against `imbalance_max`.
  It is the reference implementation of B4 and no change to its mathematics is proposed.
- **The scalar ladder's `V2.3` cannot comply and currently reports the wrong verdict.**
  `opencontractml.gate` grades V2.3 by `v not in ("not declared", None, "")` -- a
  presence-of-non-empty-string test. A real shipped gate report carried
  `"V2.3 conservation": "applicable_not_implemented_v0 (...)"`, which *asserts the check
  applies* and supplies no measurement, and the gate passes it. Under B4 that is a
  `FAIL`: asserting applicability obliges a number.
- **The cloud lane's conservation content is in FG6, not FG7.** Its divergence term
  (`div_over_grad`) is mass conservation at `scope: local`. Under the contract it is
  reported as B4 with `scope: local`, and the lift check moves to B6.

Fixing the scalar gate is **not** part of this spec. The spec's job is to make the
defect *nameable and measurable*, and it does: rule `V009`, with a test
(`test_a_declaration_string_is_not_a_conservation_measurement`) that plants the exact
string the scalar gate passes and asserts the contract rejects it.

### 5.5 Where the ladders genuinely disagree

Not every difference is a naming accident. These four are real, and the contract records
them rather than papering over them.

**(a) `FG7` is two different physical claims.** In the grid and mesh lanes it is
conservation -- a global energy balance. In the cloud lane it is *integrated quantities*
-- a lift coefficient re-derived from the predicted field, checked against the released
labels by relative error and Spearman's rho. These are not variants of one idea; one
needs no reference and the other needs the labels. **This is an identifier collision
inside a single producer**, not a divergence between producers, and the contract breaks
it into `B4` and `B6`. `verify.legacy_key(lane, "FG7")` is deliberately lane-dependent and
`"FG7"` is deliberately absent from the flat alias map, so no caller can resolve it
without saying which lane it means.

The producer has since broken the collision at its source: the cloud check is now
emitted as `FG11`, which resolves to `B6` with no qualifier, and `FG7` means
conservation wherever it is still emitted. `FG7` on the cloud ladder is **retired**,
not deleted: `legacy_key("cloud", "FG7")` still returns `B6`, because a report written
before the rename is a record and is not rewritten. The machine vocabulary lists it
under `legacy_aliases_retired`, mapped to its replacement.

**(b) Reproducibility means two different things.** The scalar ladder compares a
re-trained scikit-learn model at `tol = 1e-6` -- effectively bitwise. The field ladder
compares a re-trained network at `rel_tol = 2e-2`, because GPU kernels are not
deterministic. Four orders of magnitude apart under one name. The contract does not pick a
winner: `A5` MUST declare `determinism_class` as `bitwise` or `seeded_tolerance` and
state its `tolerance` (`V011`). A reader can then see which claim is being made.

**(c) UQ calibration uses different instruments.** The scalar ladder uses a declared
band `[0.85, 0.95]` widened by a sample-size term. The field ladder uses `[0.85, 0.96]`
with a re-split mean and a standard-deviation floor on the frozen draw. Both are
honest; neither is wrong. `A3` requires `nominal`, `empirical_coverage`, `n` and
`method` (`V010`) so the instrument is legible, and leaves the band to the producer.

**(d) The baseline roster is lane-specific.** Scalar beats {mean predictor, linear};
grid beats {mean field, POD-ridge}; cloud beats {mean field, k-NN}. This is a legitimate
difference -- a POD-ridge baseline is meaningless for a tabular regressor. `A4` requires
that the roster be declared and the ratios reported; it does not impose a roster.

**Asymmetries the unification makes visible.** Tiering the two ladders side by side
exposes holes neither producer could see alone: the scalar ladder has **no OOD guard
(`C1`)** and **no serve-parity check (`C2`)**, and the field ladder has **no
monotonicity or bounds checks (`B1`, `B2`)** and **no deployment-readiness declaration
(`C4`)**. Under the contract each of those is a `NOT_RUN`, which blocks. That is the
intended pressure.

## 6. Provenance

The consumer's manifest schema -- package-v1, shipped here as
`schemas/package-v1/manifest.schema.json` -- contains **no hash of any kind**: not in
`lineage`, not anywhere. The artifact that actually gates admission carries no
provenance at all. The two producers did carry sha256, but only of the *corpus*, and only
inside the gate report that the consumer never reads.

The contract's `provenance` block closes that. It is modelled on the field producer's
run registry, which already hashed the tuple (checkpoint, corpus, splits, guard config,
rules) and cross-checked that a card matches its dataset. That design is promoted rather
than reinvented.

```yaml
provenance:
  artifacts:                       # every file needed to EXECUTE the model
    - path: ./predict.py
      role: entrypoint             # entrypoint | weights | asset
      sha256: a196f1cb...          # 64 lowercase hex
      bytes: 2418
  dataset:
    sha256: 7bd50c57...
    n_samples: 600
    generator_version: contract-reference-corpus-1.0
    solver_version: "none (synthetic closed-form corpus)"
  code:
    repo: example-org/example-models
    commit: 1a2b3c4...             # >= 7 hex
    version: contract-reference-1.0.0
  environment:
    python: "3.13.3"
    packages: {numpy: "2.4.2"}
```

Three properties are load-bearing:

1. **Hashes are verified, not merely present** (`M013`). `python -m opencontractml.verify check`
   re-hashes every declared artifact against the file on disk. Demonstrated: appending
   one line to the reference package's `predict.py` turns the check red on both the
   sha256 and the byte count, and restoring it turns it green.
2. **The dispatched executable must be one of the hashed artifacts** (`M012`, `M013`).
   `invocation.executable` MUST equal the `path` of the single `role: entrypoint`
   artifact. An unhashed entrypoint is an unverifiable model however complete the rest
   of the block is.
3. **The card and the report are not self-hashed.** Both are written *after* the
   artifacts they describe, so hashing them would be circular. They are bound instead by
   the `model_id` / `version` / `dataset_sha256` triple (`C002`, `V002`, `V003`) -- which
   is exactly the run registry's card-matches-dataset check, generalised.

**Known wrinkle.** `provenance.code.commit` records the tree a package was *built from*,
which necessarily precedes the commit that lands the package itself. A package built in
CI from a tag does not have this problem; a package committed by hand always lags by one.
The contract does not try to resolve this by rule -- it would need a post-commit rewrite --
and states it instead.

## 7. Versioning and compatibility

The manifest and the card both carry `spec_version` as `MAJOR.MINOR`. The field name is
deliberately the package-v1 manifest's existing one, not a third name.

- **MINOR** bumps are additive and back-compatible. Unknown additive keys MUST be
  ignored, not rejected.
- **MAJOR** bumps are breaking. A consumer MUST reject a package whose `spec_version`
  major exceeds the major it supports, loudly, rather than reinterpreting it.
- Contract v1.0 is defined to be a **superset of the package-v1 manifest spec 1.0**: it
  adds `provenance` and `validation` and changes nothing existing. The two numbers can
  therefore stay aligned, and a contract-v1 manifest is a valid package-v1 manifest.
- A contract-v1 **card** was *not* a valid card for a nine-section package-v1 validator at
  contract 1.0, for exactly one reason: that validator required its nine sections to be
  the *first nine*, and the contract inserts two. The change is two inserted strings in
  the validator's section list. The package-v1 card validator shipped in this package,
  `opencontractml.model_card`, has made that change: it enforces the same eleven sections
  as `open-contract-ml check` (it reads the checker's own list), so one card satisfies both.

## 8. Conformance

`python -m opencontractml.verify check <package>` -- exit 0 clean, 1 on findings. 35 rules;
`python -m opencontractml.verify rules` prints the table. Machine-readable output with `--json`.

Every `ERROR` rule has a negative test in `tests/test_verify.py`, and
`test_every_error_rule_has_a_negative_test` fails the build if a rule is added without
one. Rules with several independent branches carry one mutation per branch. The suite
was itself mutation-tested: neutering `V009`'s number requirement, `V006`'s
numeric-metric branch and `M013`'s missing-file branch each turned exactly the intended
test red, and the checker was restored byte-exact afterwards.

The worked conformant instance is `examples/reference-package/`. Every number in
its `validation_report.json` was measured, every hash is real, its entrypoint really
runs under `stdio_json`, and its `C2_serve_parity` check really shells out to that
entrypoint and compares against the in-process fit.

## 9. What this spec is careful not to do

- **It sets no physics thresholds.** Every bar stays with the producer that sets it.
- **It does not fix the scalar gate.** The vacuous `V2.3` in `opencontractml.gate` is
  measurable under this spec; making it right is separate work.
- **It does not build a generator.** Turning a producer's training run into a contract
  package is the producer's job. This spec makes the target unambiguous.
- **It does not assume a running consumer.** Nothing here requires dispatch to work;
  conformance is checkable entirely offline.

## 10. Known limitations of v1.0

1. **`B1`/`B2` probe geometry is not specified.** The spec requires declared
   (feature, target, direction) triples and a probe set, and requires the violation
   fraction to be reported. It does not say how the probe set is constructed. Two lanes
   could both comply and not be comparable.
2. **`A2`'s extrapolation band is declared, not derived.** A producer chooses its own
   corner axis and threshold. The contract requires them to be *stated* so a reader can
   disagree; it cannot tell whether the band is a real extrapolation.
3. **Field I/O signatures are under-specified.** `modality: field_in_field_out` exists
   in the enum, but the manifest's `outputs` block was designed for scalars and
   categoricals. A field output's shape, mesh reference and units need a v1.1 addition
   before a field producer can describe a field model fully. This is the largest single
   hole in v1.0, and it is on the critical path for field surrogates adopting the
   Contract.
4. **No signature or attestation.** `provenance` proves the bytes have not changed since
   packaging. It does not prove who packaged them. Signing is a v2 concern.
   [PROVENANCE-SIGNING.md](PROVENANCE-SIGNING.md) designs an optional
   OpenSSF-Model-Signing sidecar and concludes the *field* can land additively at
   1.1 while *enforcement* stays a v2 concern. It also records what `provenance`
   does not cover: the manifest, the card and the validation report are not
   hashed by anything, so their contents are not tamper-evident.
5. **The checker's front-matter parser accepts only flat scalars.** This is stated as a
   spec rule (4.1) rather than hidden as an implementation limit, but a future card
   needing structured front-matter would need both changed together.
