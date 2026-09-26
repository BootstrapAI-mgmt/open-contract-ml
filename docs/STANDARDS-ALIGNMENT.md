# Standards alignment

Where the Contract sits relative to the ASME VVUQ standards and to the nearest
related work, stated in each standard's own vocabulary — and, more usefully,
where it does **not** reach.

This is a mapping note, not a conformance claim. The Contract has not been
assessed against any ASME standard by ASME or by anyone else, and nothing below
should be read as saying it has. Where a term is used in a standard's technical
sense it is marked as such, because the same English word means different things
in the machine-learning and the computational-mechanics literatures, and most of
the confusion in this area comes from that collision rather than from any real
disagreement.

Every source is listed with its verification status in [Sources](#sources) at
the end. Two claims commonly repeated about these standards turned out to be
wrong and are corrected in place.

---

## 1. The word "validation" means three different things here

This is the single most important thing in this document, and everything below
depends on it.

| Sense | Who uses it | What is compared against what |
|---|---|---|
| **V&V validation** | ASME V&V 10, V&V 20 | the simulation result **S** against **experimental data D** measured on the physical system, with the experimental uncertainty quantified |
| **ML validation** | the ML literature, and the Contract's ladder | a model's prediction against a **held-out split of the corpus it was trained from** |
| **Package validation** | `opencontractml.verify` | a directory against the Contract's structural rules |

The Contract's `validation_report.json` is the **second** sense, and its Tier A
checks are computed against a held-out split, not against experiment. In V&V
terms a surrogate scored that way has been asked *"do you reproduce the solver
you were trained on?"* — which is a question about the surrogate, not about
reality. If the underlying solver is itself unvalidated, a perfect Tier A score
carries that forward silently.

`opencontractml.verify` is the **third** sense and is narrower still: it decides
whether a package *declares* what the Contract requires, and whether the numbers
it declares are internally consistent and cryptographically pinned. It does not
and cannot decide whether a threshold was the right threshold.

Stating this plainly is the point of the document. A model package that passes
`verify` is a package that can be argued about; it is not a validated model in
the ASME sense.

---

## 2. ASME VVUQ 1-2022 — terminology

*Verification, Validation, and Uncertainty Quantification Terminology in
Computational Modeling and Simulation.* The terminology standard that harmonises
vocabulary across the ASME VVUQ series; ASME describes its purpose as helping
developers and users "better communicate the evidence that justifies application
of their models for the context of use."

That framing — *evidence justifying application for a context of use* — is
almost exactly what the Contract's package is for, so the mapping is close:

| VVUQ 1 concept | Contract surface | Notes |
|---|---|---|
| **Context of use** | `model_card.md` §2 `Intended use`, §3 `Out of scope`, and the manifest's `identity.purpose` / `domain` / `modality` | The Contract requires the boundary to be written down, and `C004` requires at least 40 non-whitespace characters, so a heading over "TBD" is not a stated context of use. |
| **Verification** (are the equations solved right) | **not covered** | The Contract has no code- or solution-verification surface. For a surrogate there is no discretisation to refine, so the standard's verification activity has no direct analogue — but the *solver that generated the corpus* has one, and the Contract does not ask about it. See §3. |
| **Validation** (are the right equations solved) | Tier A and Tier B of the ladder | In the ML sense, not the V&V sense. See §1. |
| **Uncertainty quantification** | `manifest.uncertainty.per_output` (required for every output, `M007`), card §8, and ladder key `A3_uq_calibration` | `V010` requires `A3` to report `nominal`, `empirical_coverage`, `n` and `method`, so the instrument is legible rather than merely asserted. |
| **Credibility** | the ladder's `overall`, recomputed from the checks (`V008`) | The Contract's contribution is refusing to let the rollup lie: a declared `overall` that disagrees with the recomputation is rejected. |
| **Predictive capability** outside the validation domain | `A2_extrapolation` and `C1_ood_guard` | Partial. `A2`'s band is *declared by the producer*, not derived — a stated limitation of v1.0. |

**Where the Contract adds something.** VVUQ 1 is a vocabulary; it does not
specify an artifact. The Contract specifies a directory, a required section set,
a fifteen-key ladder and a checker that exits non-zero — so the evidence VVUQ 1
asks practitioners to communicate has somewhere concrete to live and something
mechanical to reject it when it is missing.

**Where it falls short.** VVUQ 1's `verification` branch is simply absent.

---

## 3. ASME V&V 20-2009 (R2021) — CFD and heat transfer

*Standard for Verification and Validation in Computational Fluid Dynamics and
Heat Transfer.* Scope, verbatim from ASME: "The quantification of the degree of
accuracy of simulation of specified validation variables at a specified
validation point for cases in which the conditions of the actual experiment are
simulated."

> **Correction.** This standard is sometimes cited as "V&V 20-2016". There is no
> 2016 edition. The standard was issued as **V&V 20-2009** and reaffirmed in
> 2016 and again in 2021; the current designation is **V&V 20-2009 (R2021)**.

### 3.1 The machinery

V&V 20 compares a simulation result **S** against experimental data **D** and
isolates the modelling error:

```
comparison error        E = S - D
modelling error         δ_model = E - (δ_input + δ_num - δ_D)
validation uncertainty  u_val = ( u_num² + u_input² + u_D² )^(1/2)
conclusion              δ_model lies within the interval  E ± u_val
```

`u_num` comes from code and solution verification, `u_input` from propagating
uncertainty in the simulation's input parameters, and `u_D` from the
experimental uncertainty analysis. The standard's substance is the *estimation
of `u_val`*; `E` on its own is not a validation result.

### 3.2 What the Contract carries, and what it does not

| V&V 20 quantity | Contract |
|---|---|
| `E`, the comparison error | **Present in form.** `A1_accuracy` and `B3_residual` record an error measure against a threshold. |
| `D`, experimental data | **Absent.** The Contract's comparison target is a held-out corpus split, which is solver output, not measurement. |
| `u_D`, experimental uncertainty | **Absent**, and cannot be supplied without `D`. |
| `u_num`, numerical uncertainty | **Absent.** The corpus solver's discretisation error does not appear anywhere in a Contract package. |
| `u_input`, input-parameter uncertainty | **Absent** as a propagated quantity. `A3_uq_calibration` reports the *predictive* interval's empirical coverage, which is a different object: it characterises the surrogate's own spread, not the propagation of input uncertainty through the physics. |
| `u_val` | **Not computable** from a Contract package. |

This is the honest headline: **a Contract package does not contain enough
information to compute a V&V 20 validation uncertainty**, and the gap is not a
matter of adding a field. It is missing the experimental leg entirely.

### 3.3 The one place they meet

`B4_conservation` is the exception, and it is worth reading carefully because it
is the closest the Contract gets to V&V discipline. It requires a dimensionless
relative imbalance

```
r_Q = |sum(in) - sum(out) - sum(stored)| / sum(|gross flow|)
```

evaluated **on the model's own prediction, with no reference solution**, over a
named control volume, with the threshold and the sample count it was compared
against. Because it needs no `D`, it is a physics check a surrogate can actually
be held to on its own — and rule `V009` makes declaring it without measuring it
an error. That rule exists because a shipped scalar gate passed a card whose
conservation field read `applicable_not_implemented_v0`: the gate tested that a
free-text field was non-empty, and a test enshrined the pass.

A Contract package therefore gives a V&V 20 reader something real (a conserved
quantity checked on the prediction) and withholds the thing V&V 20 is actually
about (a quantified interval containing the modelling error).

### 3.4 An ordering the Contract does not enforce

V&V 20 presumes code and solution verification have been done *before*
validation is attempted. A surrogate trained on an unverified solver's output
inherits that solver's numerical error as signal and will reproduce it
faithfully. Nothing in the Contract asks whether the corpus solver was verified.
`provenance.dataset.solver_version` records *which* solver, which is the hook a
future revision would hang this on, but it records a string and asks nothing of
it.

---

## 4. ASME V&V 10-2019 (R2025) — computational solid mechanics

*Standard for Verification and Validation in Computational Solid Mechanics.*
ASME describes its purpose as providing the CSM community with "a common
language, a conceptual framework, and general guidance for implementing the
processes of computational model V&V", written from the perspective of
high-consequence predictions for complex engineering systems.

V&V 10 is a process and framework standard rather than a computational recipe,
so the mapping is structural rather than numerical:

| V&V 10 element | Contract |
|---|---|
| Hierarchical decomposition of a system into subsystem and component validation problems | **Absent.** A Contract package describes one model. The worked chain in `examples/worked-model-cards/` (thermal → thermo-mechanical → fatigue) is three independent packages, not a validation hierarchy — nothing in the manifest expresses that one link's output is another's input, or propagates uncertainty across the join. |
| Validation experiment planning and hierarchy | **Out of scope**, for the same reason as §3.2. |
| Documented modelling assumptions and their rationale | `model_card.md` §3 `Out of scope`, §9 `Known failure modes`, and the reserved `Alternatives considered` / `Disclosure` sections |
| Accuracy requirements agreed before the comparison | **Partly.** The ladder requires a `threshold` alongside every measurement, and `V006` rejects a `PASS` carrying a measurement with no threshold or a threshold with no measurement. It does **not** recompute the comparison — see the caveat below. |
| Sensitivity of the prediction to inputs | `B1_monotonicity`, `B2_bounds`, `B5_invariance` | Directional and bound checks on probe sets, not a formal sensitivity analysis. Probe geometry is unspecified in v1.0 — two packages can both comply and not be comparable. |

**Where the Contract adds something.** V&V 10's requirement that accuracy
requirements be agreed in advance is exactly what `V006` mechanises: a check
that compares against nothing cannot fail, and a check that cannot fail is not a
check. The Contract turns that principle into a non-zero exit code.

> **Caveat, measured rather than assumed.** `V006` requires at least one numeric
> value in `metrics` *and* at least one in `thresholds`. It does not pair them
> and does not recompute the comparison — that is the producing gate's job, and
> the checker has no naming convention telling it which threshold governs which
> metric. A report declaring `A1_accuracy: PASS` with `r2: 0.996` against
> `r2_min: 900.0` is accepted by `python -m opencontractml.verify check`.
> Section 2 of the spec says a bar must be "stated and compared against a
> measurement"; the checker enforces *stated* and takes *compared* on trust from
> the producer. That distance is small, but it is the same distance that produced
> `V009`, and it is recorded here rather than left to be discovered.

**Where it falls short.** The hierarchy — V&V 10's central organising idea — has
no representation at all, and the chained worked example is precisely the case
where its absence would bite.

---

## 5. VVUQ 70 readiness

ASME committee **VVUQ 70 — Verification, Validation, and Uncertainty
Quantification of Artificial Intelligence and Machine Learning** is the
subcommittee whose subject matter this repository is inside. Its charter, verbatim:

> "Coordinate, promote, and foster the development of standards that provide
> procedures for assessing and quantifying the credibility of artificial
> intelligence and machine learning algorithms applied to mechanistic and
> process modeling."

**Status: under development, with no published date.** ASME's digital
engineering page lists "VVUQ 70 – 20XX Verification and Validation of Machine
Learning Algorithms" among standards in preparation; the `20XX` is ASME's own
placeholder. Nothing below anticipates the content of a document that does not
exist — the point of this section is only to record what a Contract package
would already be able to answer, and what it would not, whenever such a
standard does arrive.

### Already answerable from a conformant package

- **What the model is for, and explicitly not for** — card §2, §3; `M003`.
- **What it takes and returns, with types and units** — `manifest.inputs` /
  `outputs`; `M004`, `M005`.
- **What its uncertainty contract is, per output** — `M007`, and `A3`'s
  `nominal` / `empirical_coverage` / `n` / `method` under `V010`.
- **Whether a reported pass was measured** — `V006`, `V009`.
- **Whether a skipped check was noticed** — `NOT_RUN` blocks the rollup always;
  `NOT_APPLICABLE` requires a stated reason (`V007`).
- **What data and code produced it, with digests that re-verify** — the
  `provenance` block; `M013` re-hashes every artifact against the file on disk.
- **Whether the claimed overall verdict follows from the checks** — `V008`.
- **Whether determinism is bitwise or seeded-tolerance, and at what tolerance** —
  `A5`, `V011`. This one matters more than it looks: two validation ladders
  used the same word for tolerances four orders of magnitude apart.

### Not answerable, and known to be

- **Anything requiring experimental data** — see §3.2. This is the largest gap
  and the one most likely to matter to a mechanistic-modelling standard.
- **Numerical uncertainty of the corpus solver** — §3.4.
- **Training-data representativeness.** The card has a `Training data` section
  and the manifest has a dataset digest and `n_samples`; neither asks whether
  the sample covers the intended domain.
- **Who packaged it.** The Contract proves the bytes have not changed since
  packaging; it does not prove authorship. See
  [PROVENANCE-SIGNING.md](spec/PROVENANCE-SIGNING.md).
- **Field I/O signatures.** `modality: field_in_field_out` is in the enum but
  the `outputs` block was designed for scalars; a field output's shape, mesh
  reference and units need a v1.1 addition. This is the largest structural hole
  in v1.0.
- **Cross-model uncertainty propagation** — §4.

---

## 6. Related work

Each entry states what the Contract **adds** relative to it and what it
**lacks**. All four were read before being characterised.

### 6.1 MLTE — Machine Learning Test and Evaluation

> **Correction.** MLTE is often attributed to the SEI alone. The
> published work is a collaboration: the lead authors are at the **US Army AI
> Integration Center**, with co-authors from the **Army Cyber Institute at
> USMA**, the **Carnegie Mellon University Software Engineering Institute** and
> **Carnegie Mellon University**. SEI is one contributing organisation, not the
> owner. Its PyPI name is also given as `mlte-python`; both `mlte`
> (2.7.0) and `mlte-python` (1.0.3) exist, and the maintained distribution is
> `mlte`.

MLTE is a process plus a Python toolset. It is organised around a **negotiation card**
recording what developers and stakeholders agreed the model must do, **quality
attribute scenarios** turning vague requirements into measurable ones, a **test
suite** of test cases each carrying a metric, a measurement method and a
passing condition, a reusable **test catalog**, and an **MLTE report**.

**What the Contract adds:** a byte-level provenance block whose digests
re-verify (`M013`), a physics tier (`B1`–`B6`) with a specific conservation
definition, and a conformance checker that a third party can run on a directory
they were handed, offline, with no access to the team that produced it. MLTE's
artifacts are produced by the team for the team; the Contract's are produced for
someone who did not train the model and may not trust the people who did.

**What the Contract lacks:** the entire front half. MLTE's negotiation card
captures *how the requirements came to be* — the stakeholder conversation, the
system context, the deployment constraints. The Contract begins after that
conversation has happened and simply requires its outputs to be written down. A
Contract card's thresholds appear with no record of who agreed them or why,
which is exactly the gap the negotiation card exists to fill. MLTE also covers
system-level qualities beyond the model boundary, which the Contract does not
address at all.

### 6.2 OpenSSF Model Signing (OMS) v1 / Sigstore

A specification for cryptographically signing model artifacts — weights, config,
tokenizers, datasets — as one verifiable unit. The signature is **detached**,
distributed inside the model folder, and formatted as a **Sigstore Bundle**
containing a DSSE envelope wrapping an in-toto statement. The payload manifest
references every file **by cryptographic hash** (SHA-256 or BLAKE2b). It is
PKI-agnostic: bare keys, PKI certificate chains, or keyless identity-based
signing through Sigstore.

The two designs overlap almost exactly on one surface — a manifest of per-file
digests — and are disjoint everywhere else.

**What the Contract adds:** OMS explicitly does not cover model quality. Its own
documentation says so: it does not guarantee quality, fairness, ethical
behaviour, or privacy. Everything in the Contract's ladder, card and uncertainty
contract is outside OMS's stated scope, by OMS's own design.

**What the Contract lacks:** authenticity. The Contract's `provenance` proves
*the bytes have not changed since the manifest was written*. It does not prove
*who wrote the manifest*, and an attacker who can rewrite the artifact can
rewrite the digest beside it in the same commit. `CONTRACT-v1.md` §10.4 states
this as a known limitation. The design for closing it without adopting a
dependency is [PROVENANCE-SIGNING.md](spec/PROVENANCE-SIGNING.md).

### 6.3 Model Openness Framework (MOF)

A three-tiered ranked classification rating models on completeness and openness,
from White, Haddad, Osborne, Liu, Abdelmonsef, Varghese and Le Hors
(Linux Foundation / LF AI & Data). Each tier names which components — code,
data, and lifecycle documentation — must be released, with licensing guidance
per component, and a companion Model Openness Tool.

MOF and the Contract answer orthogonal questions. MOF asks *how much of this
model was released, and under what licence*. The Contract asks *is what was
released internally consistent and checkable*. A model can rank at MOF's highest
tier and ship a validation report whose `PASS` rows carry no numbers.

**What the Contract adds:** a mechanical decision. MOF classifies; it does not
reject. The Contract exits 1 and names the rule.

**What the Contract lacks:** any notion of openness or licensing. The manifest
has no licence field for the model, the weights or the training corpus — a real
omission for a standard published under Apache-2.0, and a
candidate for v1.1. MOF's component checklist is also broader than the
Contract's `provenance` block: the Contract records a dataset digest, not
whether the dataset is released or releasable.

### 6.4 NVIDIA PhysicsNeMo-CFD

A sub-module of NVIDIA's PhysicsNeMo providing tools for integrating pretrained
AI models into CFD workflows, with config-driven evaluation. The benchmarking
post evaluates a pretrained GeoTransolver model against the DrivAerML dataset,
reporting, in its own words, "L2 pressure, L2 turbulent viscosity, L2 velocity,
and integrated quantities such as drag and lift coefficient errors", alongside
physics-aware diagnostics and visual comparison.

This is the closest thing in the field to the Contract's Tier A/B split done for
real, at scale, on a public dataset — and it is the sharpest illustration of
what a benchmark is not.

**What the Contract adds:** the post reports field L2 errors and integrated
coefficient errors. It states no uncertainty contract, ships no model card, runs
no conservation check, and — decisively — has no pass/fail gate. Every number is
a number; none is compared against a declared threshold that could have rejected
the model. Under the Contract those rows are not `PASS` and not `FAIL`; a
measurement with no threshold cannot be either, which is the whole content of
`V006`. Its integrated drag and lift coefficients map onto `B6`, its field L2
errors onto `A1`, and it has nothing at `A3`, `B4` or anywhere in Tier C.

**What the Contract lacks:** everything that makes the comparison real. The
Contract ships one synthetic reference package. PhysicsNeMo-CFD runs against
DrivAerML with a production model and an actual GPU stack. A gate that has never
been run against a hard problem has not been shown to be a useful gate, only a
consistent one. Building an adapter that emits a Contract package from a
PhysicsNeMo-CFD evaluation is the obvious way to find out.

---

## 7. Summary

| | Contract | VVUQ 1 | V&V 20 | V&V 10 | MLTE | OMS | MOF | PhysicsNeMo-CFD |
|---|---|---|---|---|---|---|---|---|
| Machine-checkable artifact | yes | no | no | no | yes | yes | partly | no |
| Rejects non-conformance | yes | — | — | — | yes | yes | no | no |
| Requires a threshold per measurement | declared only | — | yes | yes | yes | no | no | **no** |
| Experimental comparison / `u_val` | **no** | defines | **yes** | yes | no | no | no | no |
| Numerical (solver) uncertainty | **no** | defines | **yes** | yes | no | no | no | no |
| Per-output uncertainty contract | yes | defines | yes | yes | partly | no | no | **no** |
| Conservation on the prediction | yes | — | — | — | no | no | no | **no** |
| Byte-level provenance that re-verifies | yes | — | — | — | no | **yes** | partly | no |
| Signature / authorship | **no** | — | — | — | no | **yes** | no | no |
| Requirements provenance | **no** | — | — | — | **yes** | no | no | no |
| Openness / licensing | **no** | — | — | — | no | no | **yes** | no |
| Validated at production scale | **no** | — | — | — | — | — | — | **yes** |

Read the bold cells as the working list. The Contract's distinctive
contributions are the enforced measurement-plus-threshold rule, the conservation
definition, and provenance digests that re-verify. Its distinctive gaps are the
missing experimental leg, the missing signature, and the fact that it has never
been run in anger.

---

## Sources

Every URL below was fetched during the writing of this note. Bibliographic
references for scientific works cited elsewhere in this repository live in
[REFERENCES.md](REFERENCES.md); these are standards and projects, not literature,
so they are listed here.

| Source | Status |
|---|---|
| ASME, *Digital Engineering* technology highlights — https://www.asme.org/codes-standards/about-standards/technology-highlights/digital-engineering | **Verified.** Names "VVUQ 70 – 20XX Verification and Validation of Machine Learning Algorithms" as under development with no publication date. Also states VVUQ 1-2022 is available free of charge; a free download link was **not** independently confirmed. |
| ASME committee page, VVUQ 70 — https://cstools.asme.org/csconnect/CommitteePages.cfm?Committee=103099834 | **Verified.** Committee name and charter quoted verbatim in §5. |
| ASME V&V 20 product page — https://www.asme.org/codes-standards/find-codes-standards/standard-for-verification-and-validation-in-computational-fluid-dynamics-and-heat-transfer | **Verified.** Designation `VV 20 - 2009 (R2021)` and the scope statement quoted in §3. |
| V&V 20 methodology overview (OSTI 1368927) and Coleman, *An Overview of ASME V&V 20* | **Verified.** The equations in §3.1 were extracted from these two independent public presentations, not from the standard itself, which is paywalled. The standard's own wording may differ; the machinery does not. |
| ASME V&V 10-2019 — https://www.asme.org/codes-standards/find-codes-standards/standard-for-verification-and-validation-in-computational-solid-mechanics | **Verified** via ASME and ANSI listings. Current designation includes a 2025 reaffirmation: **V&V 10-2019 (R2025)**. |
| ASME VVUQ 1-2022 | **Verified** as to designation, full title and scope via ASME and distributor listings. The standard's body text was **not** read — it is paywalled — so §2's mapping is against its published scope and the general VVUQ vocabulary, not against its clause-by-clause definitions. |
| MLTE — https://mlte.readthedocs.io/, https://github.com/mlte-team/mlte, PyPI | **Verified.** v2.7.0. Authorship corrected in §6.1 from the published papers. |
| OpenSSF Model Signing — https://github.com/ossf/model-signing-spec | **Verified.** Format, sidecar placement, hash algorithms and the explicit non-goals are the specification's own. |
| Model Openness Framework — https://arxiv.org/abs/2403.13784 | **Verified.** Authors and the three-tier structure from the abstract and listing. The full paper was **not** read end to end; the per-tier component lists are described from the abstract and summary only. |
| NVIDIA PhysicsNeMo-CFD — https://nvidia.github.io/physicsnemo/blog/2026/05/29/physicsnemo-cfd/ | **Verified.** The metric list in §6.4 is quoted from the post. The absence of UQ, a model card, a conservation check and a pass/fail gate is an absence in *that post*; the wider PhysicsNeMo project was not audited for them. |

### Unverified

- Whether ASME VVUQ 1-2022 is in fact downloadable at no cost. ASME's own page
  says it is; no free download was reached.
- The clause-level content of VVUQ 1-2022, V&V 20-2009 and V&V 10-2019. All
  three are paywalled and none was read in full. Mappings above are against
  published scopes, official summaries and, for V&V 20, two public technical
  presentations of its methodology.
- Anything about the eventual content of VVUQ 70. The standard does not exist.
