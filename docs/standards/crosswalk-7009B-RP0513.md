# Clause-by-Clause Crosswalk: Contract 1.2 to NASA-STD-7009B, DNV-RP-0513, and ASME V&V 40 / V&V 20

**Scope:** how the fifty rules (`E001`–`E004`, `M001`–`M024`, `C001`–`C006`,
`V001`–`V013`, `S001`–`S003`), the twenty-seven manifest fields, the fifteen
model-card sections, and the fifteen validation-ladder keys (`A1`–`A5`,
`B1`–`B6`, `C1`–`C4`) of [the Contract, version 1.2](../spec/CONTRACT-v1.md) map
to the clauses of **NASA-STD-7009B** / **NASA-HDBK-7009B**, **DNV-RP-0513** /
**DNV-RP-0510**, **ASME V&V 40-2018**, and **ASME V&V 20-2009 (R2021)**. For
the broader discussion of where the Contract sits relative to adjacent VVUQ and
ML-packaging specifications and where it deliberately stops, see
[STANDARDS-ALIGNMENT.md](../STANDARDS-ALIGNMENT.md); full bibliographic citations
are in [REFERENCES.md](../REFERENCES.md).

---

## 1. What this crosswalk states, and what it does not claim

Engineering credibility and assurance standards ask two different kinds of
questions about a computational or machine-learned model:

1. **Structural and numerical evidence questions** — *Are the inputs, outputs,
   physical units, and valid operating ranges declared? Does every output carry
   an uncertainty declaration? Do the artifact SHA-256 digests on disk match
   the manifest? Are the eleven required model-card sections present and
   non-stubbed? Does every `PASS` or `FAIL` check carry numeric measurements,
   numeric thresholds, and recomputable comparators? Does the declared `overall`
   verdict follow from the fifteen ladder checks? Does the entrypoint answer
   each declared example in an isolated working directory within its timeout?*
2. **Engineering and programmatic judgement questions** — *Is the chosen Context
   of Use appropriate for the engineering decision at stake? Are the threshold
   bars strict enough for the model risk level? Is the training referent a
   validated physical experiment or a numerical solver whose own discretization
   uncertainty $u_{\text{num}}$ and input uncertainty $u_{\text{input}}$ must be
   accounted for under ASME V&V 20? What score on NASA-STD-7009B's 1–4
   Credibility Assessment Scale (CAS) does the programme require?*

`open-contract-ml check` (and `open-contract-ml check --smoke`) answers the
first class of questions mechanically and deterministically, exiting `0` when a
package satisfies all enforced rules and `1` when any `ERROR` rule fires. It
does **not** answer the second class: a green conformance check means the
package supplies a complete, internally consistent, cryptographically verified
record for an engineering review; it never substitutes for the review itself.

---

## 2. Package artifacts and rule inventory (Contract 1.2, `open-contract-ml` 0.3.0)

| Artifact | Schema / Enforcer | What Contract 1.2 enforces | Rules |
|---|---|---|---|
| **`manifest.yaml`** (or `manifest.json`) | [schemas/contract-v1/manifest.schema.json](../../src/opencontractml/schemas/contract-v1/manifest.schema.json) + `opencontractml.verify` | `spec_version`, identity (`id`, `name`, `version`, `owner`, `domain`, `modality`, `purpose`), `when_to_use`, `when_not_to_use`, `inputs[]` (`name`, `type`, `required`, `units`, `range: [min, max]`), `outputs[]` (`name`, `type`, `viewer`, `units`, `field`), `uncertainty` (`form`, `per_output`, `calibration`), `invocation` (`executable`, `protocol: "stdio_json"`, `timeout_s`), `lineage`, `model_card`, `provenance` (`artifacts[]`, `dataset`, `code`, `environment`, `signature`), `validation` (`report`, `overall`), `licence` (`model`, `weights`, `training_data`), `taxonomy_cell`, `taxonomy_registry`, `examples[]` | `E001`–`E004`, `M001`–`M024` |
| **`model_card.md`** | `opencontractml.verify` + [model_card.template.md](../../src/opencontractml/templates/model_card.template.md) | Flat scalar YAML front-matter (`model_id`, `version`, `spec_version`) matching the manifest, followed by the **eleven required H2 sections** in exact order (≥ 40 non-whitespace characters each) and up to **four reserved optional H2 sections** (`Alternatives considered`, `Disclosure`, `Open questions`, `References`) | `C001`–`C006` |
| **`validation_report.json`** | [schemas/contract-v1/contract-vocabulary.json](../../src/opencontractml/schemas/contract-v1/contract-vocabulary.json) + `opencontractml.verify` | Identity header (`model_id`, `model_version`, `spec_version`, `dataset_sha256`), the **fifteen validation-ladder checks** (`A1`–`A5`, `B1`–`B6`, `C1`–`C4`) with statuses in `("PASS", "FAIL", "NOT_RUN", "NOT_APPLICABLE")`, numeric metrics/thresholds, explicit `comparators` (`{metric, op, bar}`), and a recomputed `overall` verdict | `V001`–`V013` |
| **Entrypoint smoke run (`--smoke`)** | `opencontractml.verify` (`check --smoke`) | Executes `invocation.executable` under `stdio_json` in a fresh working directory per request (single and, where declared, batch), checking exit 0 within `timeout_s`, frame structure (`run_id`, `status`, every declared output and uncertainty key), and every field artifact reference (`bytes`, `sha256`, `media_type`, `units`) | `S001`–`S003` |
| **Total rule table** | `python -m opencontractml.verify rules` | **50 rules**: **44 `ERROR`** and **6 `WARN`** (`M016`, `M017`, `M021`, `M024`, `C006`, `S002`) | `50` total |

---

## 3. Clause-by-clause crosswalk: NASA-STD-7009B and NASA-HDBK-7009B

### 3.1 Programmatic requirements (NASA-STD-7009B §4.1 – §4.8)

| NASA-STD-7009B Clause | Requirement summary | Contract 1.2 artifact and field path | Enforced rules (`opencontractml.verify`) | What remains a human / programme judgement |
|---|---|---|---|---|
| **§4.1 Problem Formulation** | State the decision supported, the physical system modelled, and the quantities of interest (QoIs). | `model_card.md` `## TL;DR`, `## Intended use`; `manifest.yaml` `id`, `name`, `domain`, `modality`, `purpose`, `outputs[]` (`name`, `type`, `units`, `viewer`, `field`), `taxonomy_cell` | `C003`, `C004`, `M003`, `M005`, `M019` (`field` block on `type: field`), `M022` (`taxonomy_cell` in pinned cell vocabulary) | Whether the declared QoIs and analysis cell are sufficient for the programme's engineering decision. |
| **§4.2 Abstraction & Fidelity** | Record governing assumptions, geometric/physical simplifications, valid input bounds, and regimes where the abstraction does not apply. | `model_card.md` `## Out of scope`, `## Architecture`, `## Known failure modes`, `## Alternatives considered`; `manifest.yaml` `when_to_use`, `when_not_to_use`, `inputs[].range` (`[min, max]`, `min < max`) | `C003`, `C004`, `C006`, `M004` (`inputs` units and `[min, max]` range), `M018` | Whether the model form and input bounds cover the physical regime of the intended application. |
| **§4.3 Verification** | Verify software implementation, numerical determinism across runs, and runtime execution integrity. | `validation_report.json` `A5_reproducibility`, `C2_serve_parity`, `C3_provenance_integrity`; `manifest.yaml` `provenance.artifacts[]`; `check --smoke` | `V004`, `V006`, `V011` (`A5_reproducibility` determinism class and tolerance; `bitwise` requires tolerance `0`), `M008`, `M012`, `M013`, `S001`–`S003` | Discretization error estimation ($u_{\text{num}}$) of the upstream solver that generated the training corpus. |
| **§4.4 Validation** | Quantitatively compare model predictions against a referent across the declared envelope, including physical conservation and residuals. | `validation_report.json` `A1_accuracy`, `A2_extrapolation`, `A4_baseline_beat`, `B1_monotonicity`, `B2_bounds`, `B3_residual`, `B4_conservation`, `B5_invariance`, `B6_integrated_quantities` | `V006` (numeric measurement and threshold required for `PASS`), `V007` (`NOT_APPLICABLE` requires a stated reason), `V009` (`B4_conservation` measured, not declared), `V012`, `V013` (`comparators` recomputation) | Whether the referent is physical test data or a higher-order numerical solver, and whether the comparator bars (`bar`) meet programme accuracy needs. |
| **§4.5 Uncertainty Quantification (UQ)** | Characterize prediction uncertainty and empirical interval calibration across outputs, and guard against out-of-envelope inputs. | `manifest.yaml` `uncertainty` (`form`, `per_output`, `calibration`); `model_card.md` `## Uncertainty quantification`; `validation_report.json` `A3_uq_calibration`, `C1_ood_guard` | `M007` (`uncertainty.per_output` covers every output, or `form: none`), `C005` (uncertainty section names a method and states a number), `V010` (`A3_uq_calibration` reports `nominal`, `empirical`, `n`, `method`), `V012`, `V013` | Whether the uncertainty method captures epistemic model-form error in addition to interpolation variance. |
| **§4.6 Results Credibility & Reporting** | Present predictions together with explicit limitations, warnings, and an overall verdict that cannot mask a failed check. | `validation_report.json` `overall`, `checks`, `comparators`; `model_card.md` `## Performance`, `## Known failure modes`, `## Open questions` | `V005` (`PASS`, `FAIL`, `NOT_RUN`, `NOT_APPLICABLE`), `V008` (declared `overall` matches recomputed verdict; any `FAIL` or `NOT_RUN` blocks `PASS`), `V013` | Programme sign-off decision when one or more checks are `NOT_APPLICABLE` with a stated reason. |
| **§4.7 Configuration Management** | Maintain versioned control of model weights, dataset digest, source code commit, runtime environment, and licences. | `manifest.yaml` `provenance.artifacts[]`, `provenance.dataset` (`sha256`), `provenance.code` (`repo`, `commit`), `provenance.environment` (`python`), `provenance.signature`, `licence`, `taxonomy_registry` | `M011`–`M017`, `M020`, `M021`, `M023`, `M024`, `V002`, `V003` | Cryptographic verification of detached signatures (`M017` checks the declaration only; signature verification is a v2 concern). |
| **§4.8 Reproducibility** | Enable an independent party to re-verify the package and execute inference with consistent results. | `manifest.yaml` `invocation` (`stdio_json`), `examples[]`; `model_card.md` `## Training configuration`, `## Provenance`, `## Version history`; `check --json` conformance record | `M008`, `V011`, `S001`–`S003` | Long-term archive retention of external training corpora not bundled inside the model package. |

### 3.2 NASA-STD-7009B Appendix B & NASA-HDBK-7009B §4.5.2 — Eight-Factor Credibility Assessment Scale (CAS)

NASA-STD-7009B Table B-1 grades M&S credibility across eight factors on Levels 1–4.
The Contract does not assign a CAS level (see [STANDARDS-ALIGNMENT.md](../STANDARDS-ALIGNMENT.md));
instead, a conformant package provides the structured evidence an assessor reads
when grading each factor:

| CAS Category | CAS Factor (Table B-1) | Evidence supplied by a conformant Contract 1.2 package | Rules enforcing the evidence |
|---|---|---|---|
| **M&S Development** | **1. Verification** | Re-hashed artifact digests on disk (`M013`), recomputed comparator statuses (`V013`), declared determinism class and tolerance on `A5_reproducibility` (`V011`), `C2_serve_parity`, `C3_provenance_integrity`, and isolated smoke execution (`S001`–`S003`). | `M012`, `M013`, `V011`, `V012`, `V013`, `S001`–`S003` |
| **M&S Development** | **2. Validation** | Quantitative comparator records (`{metric, op, bar}`) across `A1_accuracy`, `A2_extrapolation`, `A4_baseline_beat`, and Tier B physics checks (`B1_monotonicity`, `B2_bounds`, `B3_residual`, `B4_conservation`, `B5_invariance`, `B6_integrated_quantities`). | `V004`–`V009`, `V012`, `V013` |
| **M&S Operations** | **3. Input Pedigree** | Typed `inputs[]` with explicit physical `units` and `[min, max]` `range` (`M004`), `provenance.dataset.sha256` bound across manifest and validation report (`M014`, `V003`), and corpus-level checks in `opencontractml.corpus_gate` (`G1.1`–`G1.7`). | `M004`, `M006`, `M014`, `V003` |
| **M&S Operations** | **4. Results Uncertainty** | Mandatory per-output uncertainty coverage (`M007`), quantitative `## Uncertainty quantification` prose (`C005`), calibrated coverage reporting in `A3_uq_calibration` (`nominal`, `empirical`, `n`, `method` via `V010`), and runtime `C1_ood_guard`. | `M007`, `C005`, `V010`, `V012`, `V013` |
| **M&S Operations** | **5. Results Robustness** | Boundary/extrapolation degradation (`A2_extrapolation`), physical trend preservation (`B1_monotonicity`), symmetry/discretization invariance (`B5_invariance`), and `model_card.md` `## Known failure modes`. | `C003`, `C004`, `V004`, `V006`, `V012`, `V013` |
| **Supporting Evidence** | **6. Use History** | `manifest.yaml` `version`, `lineage` (`training_data_version`, `training_date`, `metrics`, `retrain_cadence`), `taxonomy_cell`, and `model_card.md` `## Version history`. | `M003`, `M018`, `M022`, `C002`, `C003`, `C004` |
| **Supporting Evidence** | **7. M&S Management** | Content-addressed `provenance` block (`artifacts[]`, `dataset.sha256`, `code.repo` and `commit`, `environment.python`, optional `signature`), `licence` block (`model`, `weights`, `training_data`), and `taxonomy_registry` pin. | `M011`–`M018`, `M020`, `M021`, `M023`, `M024`, `V002`, `V003` |
| **Supporting Evidence** | **8. People Qualification** | `manifest.yaml` `owner` (`team`, `contact`), `model_card.md` `## Disclosure` and `## Open questions` (`C006`), and `V008`'s refusal of an `overall: PASS` when any check is `FAIL` or `NOT_RUN`. | `M003`, `C006`, `V008` |

---

## 4. Clause-by-clause crosswalk: DNV-RP-0513 and DNV-RP-0510

DNV's recommended practices for data-driven and AI-enabled engineering systems
(**DNV-RP-0510** *Framework for Assurance of Data-Driven Models* and
**DNV-RP-0513** *Assurance of AI-Enabled Systems*) structure assurance around
five pillars:

| DNV-RP-0513 / RP-0510 Pillar | Assurance requirement | Contract 1.2 implementation | Enforced rules (`opencontractml.verify` & `corpus_gate`) |
|---|---|---|---|
| **1. Assurance Case & Intended Context** (RP-0513 §3) | Define system boundaries, physical domain, operating envelope, and prohibited uses prior to deployment. | `manifest.yaml` `domain`, `modality`, `purpose`, `when_to_use`, `when_not_to_use`, `taxonomy_cell`; `model_card.md` `## Intended use`, `## Out of scope`, `## Known failure modes`. | `M003`, `M018`, `M022`, `C003`, `C004` |
| **2. Data Quality, Pedigree & Representativeness** (RP-0510 §4, RP-0513 §4.2) | Trace training and validation datasets to verified sources, verify schema/unit completeness, and check for non-converged or confounding samples. | `manifest.yaml` `provenance.dataset` (`sha256`, `n_samples`, `generator_version`, `solver_version`), `V003` dataset digest match; `opencontractml.corpus_gate` (`G1.1` schema/units, `G1.2` solver convergence, `G1.3` design-space coverage & mesh-dominance check, `G1.4` physical bounds, `G1.5` duplicate detection, `G1.6` group-aware split integrity, `G1.7` provenance). | `M014`, `V003`; corpus gate checks `G1.1`–`G1.7` |
| **3. Model Verification & Physics Consistency** (RP-0513 §4.3) | Demonstrate that the model satisfies governing physical laws (monotonicity, hard bounds, PDE residuals, conservation, invariances, integrated quantities) and beats simple baselines. | `validation_report.json` `A4_baseline_beat` and Tier B (`B1_monotonicity`, `B2_bounds`, `B3_residual`, `B4_conservation`, `B5_invariance`, `B6_integrated_quantities`) with recomputed `comparators`. | `V004`–`V009`, `V012`, `V013` |
| **4. Operational Envelope & Runtime Safeguards** (RP-0513 §4.4, §5.1–§5.2) | Enforce declared input ranges, attach calibrated uncertainty to every prediction, and detect out-of-distribution (OOD) inputs at runtime. | `manifest.yaml` `inputs[].range` (`[min, max]`), `uncertainty.per_output`; `validation_report.json` `A2_extrapolation`, `A3_uq_calibration`, `C1_ood_guard`; `check --smoke` frame and uncertainty-key verification. | `M004`, `M007`, `C005`, `V010`, `V012`, `V013`, `S001`–`S003` |
| **5. Lifecycle Traceability & Supply-Chain Integrity** (RP-0513 §6) | Maintain cryptographic binding across weights, dataset, code, environment, cell vocabulary, and SPDX licences across model updates. | `manifest.yaml` `provenance.artifacts[]` (`path`, `role`, `sha256`, `bytes`), `licence` (`model`, `weights`, `training_data`), `taxonomy_registry` (`registry`, `version`, `sha256`, `document_sha256`, `bytes`, `cells`), and `conformance_record()` (`check --json`). | `E001`–`E004`, `M011`–`M017`, `M020`, `M021`, `M023`, `M024`, `C001`, `C002`, `V001`–`V003`, `V008` |

---

## 5. Clause-by-clause crosswalk: ASME V&V 40-2018 and ASME V&V 20-2009 (R2021)

| ASME V&V 40 / V&V 20 Section | Credibility element | Contract 1.2 mapping | Enforced rules and scope note |
|---|---|---|---|
| **V&V 40 §3.1 Question of Interest (QoI)** | The specific engineering question or decision the model informs. | `model_card.md` `## Intended use`; `manifest.yaml` `purpose` and `outputs[]` (`name`, `type`, `units`, `viewer`, `field`). | `M003`, `M005`, `M019`, `C003`, `C004` |
| **V&V 40 §3.2 Context of Use (CoU)** | The role and scope of the computational or surrogate model relative to full-order simulation or physical testing. | `model_card.md` `## Intended use`, `## Out of scope`, `## Alternatives considered`; `manifest.yaml` `domain`, `modality`, `when_to_use`, `when_not_to_use`, `taxonomy_cell`. | `M003`, `M022`, `C003`, `C004`, `C006` |
| **V&V 40 §4 Model Risk Assessment** | Combination of *Model Influence* and *Decision Consequence* that sets the required credibility bar. | The numerical threshold bars (`thresholds` and `comparators[].bar`) recorded in `validation_report.json`. | `V006`, `V012`, `V013` verify that every `PASS` or `FAIL` check states its bar and satisfies its comparator; the risk level itself is chosen by the engineering programme. |
| **V&V 40 §5.1 Verification (Code & Calculation)** | Software quality assurance, numerical determinism, and discretization sensitivity. | `provenance` (`M011`–`M017`), `licence` (`M020`, `M021`), `A5_reproducibility` (`V011`), `B5_invariance` (remesh/regrid/resampling invariance), `C2_serve_parity`, `C3_provenance_integrity`, and `check --smoke` (`S001`–`S003`). | `M011`–`M017`, `M020`, `M021`, `V011`, `S001`–`S003` |
| **V&V 40 §5.2 & V&V 20 Validation (Comparator)** | Quantitative comparison of model outputs ($S$) against a referent ($D$) with explicit comparison error $E = S - D$ and uncertainty. | `provenance.dataset.sha256` (`M014`, `V003`), `validation_report.json` Tiers A & B (`A1_accuracy`, `A2_extrapolation`, `A3_uq_calibration`, `A4_baseline_beat`, `B1`–`B6`). | `M014`, `V003`, `V006`, `V009`, `V010`, `V012`, `V013`. **V&V 20 scope boundary:** as noted in [STANDARDS-ALIGNMENT.md](../STANDARDS-ALIGNMENT.md), a surrogate trained on solver output measures surrogate-to-solver error; it does not estimate the solver's discretization uncertainty $u_{\text{num}}$ or experimental uncertainty $u_D$ required to compute $u_{\text{val}} = \sqrt{u_{\text{num}}^2 + u_{\text{input}}^2 + u_D^2}$. |
| **V&V 40 §5.3 Applicability** | Relevance of the validation dataset and test envelope to the Context of Use. | `manifest.yaml` `inputs[].range` (`M004`), `when_to_use`, `when_not_to_use`, `taxonomy_cell` (`M022`), `taxonomy_registry` (`M023`, `M024`), and `C1_ood_guard`. | `M004`, `M022`–`M024`, `V006`, `V012`, `V013` |

---

## 6. Complete rule-to-standard reference matrix (all 50 rules)

Every rule in `opencontractml.verify.RULES` (`python -m opencontractml.verify rules`)
is listed below with its severity, the Contract version from which it applies,
its exact title, and the corresponding clauses in NASA-STD-7009B, DNV-RP-0513,
and ASME V&V 40:

| Rule ID | Severity | Contract version | Exact rule title (`opencontractml.verify`) | NASA-STD-7009B | DNV-RP-0513 | ASME V&V 40 |
|---|---|---|---|---|---|---|
| `E001` | `ERROR` | 1.0+ | `package directory exists and is readable` | §4.7 | Pillar 5 | §5.1.1 |
| `E002` | `ERROR` | 1.0+ | `a YAML parser is available for a .yaml artifact` | §4.7 | Pillar 5 | §5.1.1 |
| `E003` | `ERROR` | 1.0+ | `the contract-v1 manifest schema loads and the checker applies every keyword it uses` | §4.7 | Pillar 5 | §5.1.1 |
| `E004` | `ERROR` | 1.2 | `the pinned cell vocabulary loads and holds together, wherever a manifest declares a taxonomy key` | §4.1, §4.2 | Pillar 1, 5 | §3.2, §5.3 |
| `M001` | `ERROR` | 1.0+ | `manifest present and parses to a mapping` | §4.7 | Pillar 5 | §5.1.1 |
| `M002` | `ERROR` | 1.0+ | `spec_version present, MAJOR.MINOR, major supported` | §4.7 | Pillar 5 | §5.1.1 |
| `M003` | `ERROR` | 1.0+ | `identity block complete (id, name, version, owner, domain, modality, purpose)` | §4.1, §4.7 | Pillar 1, 5 | §3.1, §3.2 |
| `M004` | `ERROR` | 1.0+ | `inputs declared and well formed (float inputs state units; a range is [min, max], min < max)` | §4.1, CAS-3 | Pillar 2, 4 | §5.2.2, §5.3 |
| `M005` | `ERROR` | 1.0+ | `outputs declared and well formed (float outputs state units)` | §4.1 | Pillar 1 | §3.1 |
| `M006` | `ERROR` | 1.0+ | `no duplicate input or output names` | §4.1, CAS-3 | Pillar 2 | §5.1.1 |
| `M007` | `ERROR` | 1.0+ / 1.1+ | `every output is covered by an uncertainty.per_output block; uncertainty.form none (from contract 1.1) declares no block and no calibration` | §4.5, CAS-4 | Pillar 4 | §5.1.2, §5.2 |
| `M008` | `ERROR` | 1.0+ | `invocation block complete and protocol is supported` | §4.3, §4.8 | Pillar 5 | §5.1.1 |
| `M009` | `ERROR` | 1.0+ | `model_card path declared, inside the package, and the file exists` | §4.6, §4.7 | Pillar 1, 5 | §3.2 |
| `M010` | `ERROR` | 1.0+ | `validation.report path declared, inside the package, and the file exists` | §4.4, §4.6 | Pillar 3, 5 | §5.2 |
| `M011` | `ERROR` | 1.0+ | `provenance block present` | §4.7, CAS-7 | Pillar 2, 5 | §5.1.1 |
| `M012` | `ERROR` | 1.0+ | `provenance.artifacts entries well formed (a path inside the package, a role, a sha256, an integer byte count)` | §4.3, §4.7 | Pillar 5 | §5.1.1 |
| `M013` | `ERROR` | 1.0+ | `every declared artifact exists and its sha256 matches the file on disk` | §4.3, §4.7 | Pillar 5 | §5.1.1 |
| `M014` | `ERROR` | 1.0+ | `provenance.dataset carries a well formed sha256` | §4.4, §4.7, CAS-3 | Pillar 2, 5 | §5.2.1 |
| `M015` | `ERROR` | 1.0+ | `provenance.code carries repo and commit` | §4.7, CAS-7 | Pillar 5 | §5.1.1 |
| `M016` | `WARN` | 1.0+ | `provenance.environment names the interpreter` | §4.7, §4.8 | Pillar 5 | §5.1.1 |
| `M017` | `WARN` | 1.1+ | `a declared provenance.signature is {format: oms, path} naming a file in the package that is not a pinned artifact (the checker verifies no signature)` | §4.7 | Pillar 5 | §5.1.1 |
| `M018` | `ERROR` | 1.0+ | `the manifest conforms to the contract-v1 manifest schema (required keys, types, enumerations, patterns, bounds)` | §4.7 | Pillar 1, 5 | §5.1.1 |
| `M019` | `ERROR` | 1.1+ | `a type: field output declares its field block (kind, units, support, media_type) from contract 1.1, and a declared block is complete and sits on a field output` | §4.1, §4.2 | Pillar 1, 3 | §3.1, §5.1.2 |
| `M020` | `ERROR` | 1.1+ | `a declared licence block names the model, the weights and the training data, each by an SPDX license expression with its text or URL, or by NOASSERTION with a note` | §4.7, CAS-8 | Pillar 5 | §5.1.1 |
| `M021` | `WARN` | 1.1+ | `a package declaring contract 1.1 or later declares a licence block` | §4.7 | Pillar 5 | §5.1.1 |
| `M022` | `ERROR` | 1.2 | `a declared taxonomy_cell is an id the pinned cell vocabulary lists as live (well formed, listed, not retired)` | §4.1, §4.2 | Pillar 1 | §3.2, §5.3 |
| `M023` | `ERROR` | 1.2 | `a declared taxonomy_registry comes with a taxonomy_cell and pins the cell vocabulary the checker carries: registry, version, sha256, document_sha256, bytes and cells, each well formed` | §4.7 | Pillar 5 | §5.1.1 |
| `M024` | `WARN` | 1.2 | `a declared taxonomy_registry pins the content of the cell vocabulary the checker carries (sha256, document_sha256, bytes, cells); another version is warned, never failed` | §4.7 | Pillar 5 | §5.3 |
| `C001` | `ERROR` | 1.0+ | `model card parses with a flat scalar front-matter` | §4.6, §4.7 | Pillar 1, 5 | §3.2 |
| `C002` | `ERROR` | 1.0+ | `card front-matter identity matches the manifest` | §4.7 | Pillar 5 | §5.1.1 |
| `C003` | `ERROR` | 1.0+ | `the eleven required card sections are present, first, in order` | §4.1–§4.8 | Pillar 1–5 | §3.1–§5.3 |
| `C004` | `ERROR` | 1.0+ | `no required card section is a stub` | §4.6 | Pillar 1 | §3.2 |
| `C005` | `ERROR` | 1.0+ | `the uncertainty section states a method and a number, or, under uncertainty.form none, that the model reports no uncertainty` | §4.5, CAS-4 | Pillar 4 | §5.1.2, §5.2 |
| `C006` | `WARN` | 1.0+ | `extra H2 sections use reserved names` | §4.6 | Pillar 1 | §3.2 |
| `V001` | `ERROR` | 1.0+ | `validation report parses and declares its identity` | §4.4 | Pillar 3 | §5.2 |
| `V002` | `ERROR` | 1.0+ | `validation report identity (model_id, model_version, spec_version) matches the manifest` | §4.7 | Pillar 5 | §5.1.1 |
| `V003` | `ERROR` | 1.0+ | `validation report dataset hash matches the manifest provenance` | §4.4, §4.7, CAS-3 | Pillar 2, 5 | §5.2.1 |
| `V004` | `ERROR` | 1.0+ | `every ladder key is present` | §4.3–§4.5 | Pillar 3, 4 | §5.1, §5.2 |
| `V005` | `ERROR` | 1.0+ | `every check declares a known status` | §4.6 | Pillar 3 | §5.2 |
| `V006` | `ERROR` | 1.0+ | `a PASS carries a numeric measurement and a numeric threshold` | §4.4, §4.6 | Pillar 3 | §5.2 |
| `V007` | `ERROR` | 1.0+ | `NOT_APPLICABLE states a reason` | §4.2, §4.4 | Pillar 1, 3 | §3.2, §5.2 |
| `V008` | `ERROR` | 1.0+ | `the declared overall verdict matches the recomputed one` | §4.6 | Pillar 3, 5 | §5.2 |
| `V009` | `ERROR` | 1.0+ | `B4 conservation is measured, not declared (a NOT_RUN check declares applicable: true and carries no measurement)` | §4.4 | Pillar 3 | §5.2 |
| `V010` | `ERROR` | 1.0+ | `A3 uq_calibration reports nominal, empirical coverage, n and method` | §4.5, CAS-4 | Pillar 4 | §5.2 |
| `V011` | `ERROR` | 1.0+ | `A5 reproducibility declares a determinism class and a tolerance (bitwise means tolerance 0, from contract 1.1)` | §4.3, §4.8, CAS-1 | Pillar 3, 5 | §5.1.1 |
| `V012` | `ERROR` | 1.1+ | `comparators are well formed, and every PASS or FAIL check has one from contract 1.1` | §4.4, §4.6 | Pillar 3 | §4, §5.2 |
| `V013` | `ERROR` | 1.1+ | `each measured check's declared status agrees with the status its comparators give` | §4.4, §4.6 | Pillar 3 | §5.2 |
| `S001` | `ERROR` | 1.0+ | `check --smoke: the entrypoint answers each example, and a batch of them where batch is supported, in the stdio_json frame: exit 0 within its timeout, a frame per row, every declared output and uncertainty key (and, from contract 1.1, status and run_id)` | §4.3, §4.8 | Pillar 4, 5 | §5.1.1 |
| `S002` | `WARN` | 1.0+ | `check --smoke: the smoke test could run (examples declared, the entrypoint verified and launchable here)` | §4.3, §4.8 | Pillar 4 | §5.1.1 |
| `S003` | `ERROR` | 1.0+ | `check --smoke: every artifact reference an answer carries, and every declared field and *_artifact value, names a file in the run's working directory with its declared bytes, sha256 and media type` | §4.3, §4.7 | Pillar 4, 5 | §5.1.1 |

---

## 7. Field, section, and ladder-key reference tables

### 7.1 `manifest.yaml` fields (`schemas/contract-v1/manifest.schema.json`)

| `manifest.yaml` field path | Enforced by | NASA-STD-7009B / NASA-HDBK-7009B | DNV-RP-0513 / RP-0510 |
|---|---|---|---|
| `spec_version` (`"1.0"`, `"1.1"`, `"1.2"`) | `M002`, `M018`, `C002`, `V002` | §4.7 Configuration Management (CAS-7) | RP-0513 §6.2 Configuration & Schema Versioning |
| `id` (`^[a-z][a-z0-9_]*$`) | `M003`, `M018`, `C002`, `V002` | §4.7 Unique M&S Identification (CAS-7) | RP-0513 §3.1 System Identifier |
| `name` | `M003`, `M018` | §4.7.1 Model Registry Metadata | RP-0513 §3.1 System Description |
| `version` | `M003`, `M018`, `C002`, `V002` | §4.7.2 Use History & Version Control (CAS-6, CAS-7) | RP-0513 §6.2 Change Management |
| `owner` (`team`, `contact`) | `M003`, `M018` | §4.6.3 Technical Review & Ownership (CAS-8) | RP-0513 §3.3 Organizational Accountability |
| `domain`, `analysis_type`, `tags[]` | `M003`, `M018` | §4.1.1 Physical Domain Definition | RP-0513 §3.2 Intended Context |
| `modality` (`scalar_in_scalar_out` .. `field_in_field_out`) | `M003`, `M018` | §4.1.2, §4.2.1 Input/Output Representation | RP-0513 §3.2, §4.1 Interface Modality |
| `purpose`, `when_to_use`, `when_not_to_use` | `M003`, `M018` | §4.1.2 M&S Role, §4.2.2 Applicability Limits | RP-0513 §3.2, §5.1 Operational Envelope |
| `taxonomy_cell` (`A.<d>.<n>/B<k>/<m>`, Contract 1.2) | `E004`, `M018`, `M022` | §4.1, §4.2 Problem Formulation & Abstraction | RP-0513 §3.2, §4.1 Analysis & Architecture Class |
| `taxonomy_registry` (`registry`, `version`, `sha256`, `document_sha256`, `bytes`, `cells`, Contract 1.2) | `E004`, `M018`, `M023`, `M024` | §4.7 Reference Vocabulary Pin (CAS-7) | RP-0513 §6.2 Lifecycle Traceability |
| `inputs[].name`, `type`, `required`, `description`, `file_kind`, `choices` | `M004`, `M006`, `M018` | §4.3.2, §4.5.1 Input Interface (CAS-3) | RP-0510 §4.2, RP-0513 §4.2 Data Schema |
| `inputs[].units`, `canonical_units` | `M004`, `M018` | §4.3.2 Dimensional Consistency (CAS-3) | RP-0510 §4.2 Physical Units |
| `inputs[].range` (`[min, max]`, `min < max`) | `M004`, `M018` | §4.2.2 Valid Input Range (CAS-3) | RP-0513 §5.1 Operational Design Domain Bounds |
| `outputs[].name`, `type`, `viewer`, `units`, `choices` | `M005`, `M006`, `M018` | §4.1.3 Quantities of Interest, §4.6 Reporting | RP-0513 §4.2, §5.1 Output Specification |
| `outputs[].field` (`kind`, `units`, `support`, `media_type`, `shape`, `coordinate_ref`, Contract 1.1+) | `M018`, `M019` | §4.2.1, §4.3.2 Field Support & Discretization Layout | RP-0513 §4.2, §5.3 Field Payload Contract |
| `uncertainty` (`form`, `per_output`, `calibration`) | `M007`, `M018`, `C005` | §4.5.1 Per-Output UQ Coverage (CAS-4) | RP-0513 §4.4, §5.2 Uncertainty Estimation |
| `invocation` (`executable`, `protocol: "stdio_json"`, `timeout_s`, `expected_runtime_s`, `batch_supported`) | `M008`, `M018`, `S001` | §4.3.1, §4.8 Executable Verification (CAS-1) | RP-0513 §5.3 Runtime Dispatch Contract |
| `lineage` (`training_data_version`, `training_date`, `metrics`, `retrain_cadence`) | `M018` | §4.7.2 Use History & Lineage (CAS-6, CAS-7) | RP-0513 §6.1, §6.2 Lifecycle Monitoring |
| `model_card` | `M009`, `M018` | §4.6 Documentation Binding | RP-0513 §6.2 Assurance Documentation Link |
| `validation` (`report`, `overall`) | `M010`, `M018` | §4.4, §4.6 Validation Report Binding | RP-0513 §4.3, §6.2 Validation Record Link |
| `provenance.artifacts[]` (`path`, `role`, `sha256`, `bytes`) | `M011`, `M012`, `M013`, `M018` | §4.3.1, §4.7 Artifact Integrity (CAS-1, CAS-7) | RP-0513 §6.2 Cryptographic Artifact Pinning |
| `provenance.dataset` (`sha256`, `n_samples`, `generator_version`, `solver_version`) | `M011`, `M014`, `M018`, `V003` | §4.4.2, §4.7 Data Pedigree (CAS-2, CAS-3) | RP-0510 §4.3, RP-0513 §4.2 Dataset Lineage |
| `provenance.code` (`repo`, `commit`, `version`) | `M011`, `M015`, `M018` | §4.3.1, §4.7 Source Control (CAS-1, CAS-7) | RP-0513 §6.2 Software Configuration Management |
| `provenance.environment` (`python`, `packages`) | `M016`, `M018` | §4.7, §4.8 Environment Record (CAS-7) | RP-0513 §6.2 Execution Environment |
| `provenance.signature` (`{format: "oms", path}`, Contract 1.1+) | `M017` | §4.7.3 Detached Signature Declaration | RP-0513 §6.2 Authorship Sidecar Declaration |
| `licence` (`model`, `weights`, `training_data`, Contract 1.1+) | `M018`, `M020`, `M021` | *No direct counterpart in 7009B* (IP & redistribution rights) | RP-0513 §6.3 Supply-Chain & Licensing Governance |
| `examples[]` | `M018`, `S001`–`S003` | §4.3.1 Executable Smoke Cases (CAS-1) | RP-0513 §4.3 Acceptance Smoke Inputs |

### 7.2 `model_card.md` H2 sections (11 required, 4 reserved optional)

| `model_card.md` section | Status | Enforced by | NASA-STD-7009B / NASA-HDBK-7009B | DNV-RP-0513 / RP-0510 |
|---|---|---|---|---|
| **YAML Front-Matter** (`model_id`, `version`, `spec_version`) | Required | `C001`, `C002` | §4.7 Configuration Identification | RP-0513 §6.2 Document-to-Manifest Binding |
| `## TL;DR` | Required (#1) | `C003`, `C004` | §4.6.1 Executive Summary | RP-0513 §3.1 Assurance Summary |
| `## Intended use` | Required (#2) | `C003`, `C004` | §4.1 Problem Formulation & Intended Use | RP-0513 §3.2 Intended Context of Use |
| `## Out of scope` | Required (#3) | `C003`, `C004` | §4.2.3, §4.6.2 Prohibited Uses & Limits | RP-0513 §3.2, §5.1 Out-of-Scope Regimes |
| `## Training data` | Required (#4) | `C003`, `C004` | §4.4.2 Data Pedigree & Referent (CAS-3) | RP-0510 §4.1–§4.4 Data Pedigree & Coverage |
| `## Architecture` | Required (#5) | `C003`, `C004` | §4.2.1 Mathematical & Algorithmic Form | RP-0513 §4.1 Model Architecture |
| `## Training configuration` | Required (#6) | `C003`, `C004` | §4.3.2, §4.8 Calibration & Training Protocol | RP-0513 §4.2 Training Reproducibility |
| `## Performance` | Required (#7) | `C003`, `C004` | §4.4.3 Validation Results (CAS-2) | RP-0513 §4.3 Quantitative V&V Performance |
| `## Uncertainty quantification` | Required (#8) | `C003`, `C004`, `C005` | §4.5 Results Uncertainty (CAS-4) | RP-0513 §4.4, §5.2 UQ Method & Calibration |
| `## Known failure modes` | Required (#9) | `C003`, `C004` | §4.2.3, §4.5.2 Robustness Limits (CAS-5) | RP-0513 §5.2 Failure Mode Analysis |
| `## Provenance` | Required (#10) | `C003`, `C004` | §4.7 Lineage of Solver, Data & Code (CAS-7) | RP-0513 §6.2 End-to-End Traceability |
| `## Version history` | Required (#11) | `C003`, `C004` | §4.7.2 Use History & Change Log (CAS-6) | RP-0513 §6.2 Lifecycle Change Log |
| `## Alternatives considered` | Optional (Reserved) | `C006` | §4.2.1 Model-Form Trade-Offs | RP-0513 §4.1 Baseline & Architecture Comparison |
| `## Disclosure` | Optional (Reserved) | `C006` | §4.6.3 Independence & Qualification (CAS-8) | RP-0513 §3.3 Governance Disclosure |
| `## Open questions` | Optional (Reserved) | `C006` | §4.6.2 Residual Risks & Open Items | RP-0513 §3.4 Open Assurance Conditions |
| `## References` | Optional (Reserved) | `C006` | §4.4.2 Normative & Literature Citations | RP-0513 §2 Normative & Technical References |

### 7.3 `validation_report.json` fifteen-key ladder (`V001`–`V013`)

| Ladder key (`opencontractml.verify`) | Legacy aliases (`verify.LEGACY_ALIASES`) | Tier | What the check grades | NASA-STD-7009B / NASA-HDBK-7009B | DNV-RP-0513 / RP-0510 |
|---|---|---|---|---|---|
| `A1_accuracy` | `V1.1`, `FG1` | Tier A (Statistical) | Held-out test accuracy (relative $L_2$, MAE, RMSE) against the referent | §4.4.3 Validation (CAS-2) | RP-0513 §4.3 Predictive Accuracy |
| `A2_extrapolation` | `V1.2`, `FG2` | Tier A (Statistical) | Held-out boundary, corner, or tail regime degradation | §4.4.3, §4.5.3 Robustness (CAS-5) | RP-0513 §4.3.3 Boundary Stress Testing |
| `A3_uq_calibration` | `V1.3`, `FG3` | Tier A (Statistical) | Empirical interval coverage vs. nominal (`nominal`, `empirical`, `n`, `method` required by `V010`) | §4.5.1 Results Uncertainty (CAS-4) | RP-0513 §4.4 Probabilistic Calibration |
| `A4_baseline_beat` | `V1.4`, `FG4` | Tier A (Statistical) | Superiority over simple baseline estimators | §4.2.1, §4.4.3 Validation (CAS-2) | RP-0513 §4.1, §4.3 Baseline Benchmarking |
| `A5_reproducibility` | `V1.5`, `FG5` | Tier A (Statistical) | Determinism class (`bitwise` requires tolerance `0`) and seed stability (`V011`) | §4.3, §4.8 Verification (CAS-1) | RP-0513 §4.2, §6.2 Reproducibility |
| `B1_monotonicity` | `V2.1` | Tier B (Physics) | Preservation of known physical monotonicity trends | §4.4.3 Validation & Robustness (CAS-2, CAS-5) | RP-0513 §4.3.2 Physical Trend Consistency |
| `B2_bounds` | `V2.2` | Tier B (Physics) | Satisfaction of hard physical bounds (positivity, absolute temperature, mass fractions) | §4.2, §4.4 Abstraction & Validation | RP-0513 §4.3.2 Physical Admissibility Bounds |
| `B3_residual` | `FG6` | Tier B (Physics) | Interior governing PDE or operator residual magnitude | §4.3.2, §4.4 Solution Verification & Validation | RP-0513 §4.3.2 Governing Equation Residual |
| `B4_conservation` | `V2.3`, `FG7` (grid/mesh) | Tier B (Physics) | Measured global conservation imbalance (`relative_imbalance`, enforced by `V009`) | §4.3.2, §4.4.3 Validation (CAS-2) | RP-0513 §4.3.2 Global Conservation Law |
| `B5_invariance` | `V2.4`, `FG10` | Tier B (Physics) | Frame/galilean/permutation and discretization (remesh/resample/regrid) invariance | §4.3.2, §4.5.2 Verification & Robustness (CAS-1, CAS-5) | RP-0513 §4.3.2 Symmetry & Mesh Invariance |
| `B6_integrated_quantities` | `FG11` | Tier B (Physics) | Surface- or volume-integrated engineering quantities of interest ($C_D, C_L$, net flux) | §4.1.3, §4.4.3 QoI Validation (CAS-2) | RP-0513 §4.3.1 Integrated Engineering QoIs |
| `C1_ood_guard` | `FG8` | Tier C (Deployment) | Runtime out-of-distribution detector separation between in-envelope and corrupted inputs | §4.5.3, §4.6.2 Operational Limits | RP-0513 §5.2 Active Runtime Envelope Guard |
| `C2_serve_parity` | `FG9` | Tier C (Deployment) | Numerical agreement between training evaluation and packaged `stdio_json` entrypoint | §4.3.1 Code Verification (CAS-1) | RP-0513 §5.3 Packaged Deployment Parity |
| `C3_provenance_integrity` | — | Tier C (Deployment) | End-to-end digest verification across weights, dataset, and code | §4.7 Configuration Management (CAS-7) | RP-0513 §6.2 Artifact & Lineage Integrity |
| `C4_deployment_readiness` | `V3` | Tier C (Deployment) | Single-call and batch inference latency, memory footprint, and dispatch readiness | §4.8 Operational Readiness | RP-0513 §5.3 Runtime Resource Compliance |

---

## 8. Known gaps between Contract 1.2 and the standards (candidates for future revisions)

Consistent with [STANDARDS-ALIGNMENT.md](../STANDARDS-ALIGNMENT.md), the table
below lists seven places where NASA-STD-7009B, DNV-RP-0513, or ASME V&V 40 /
V&V 20 call for structured information that Contract 1.2 leaves to prose in
`model_card.md` or does not yet verify mechanically:

| # | Standard clause | What Contract 1.2 does today | Candidate extension for a future Contract revision |
|---|---|---|---|
| 1 | **NASA-STD-7009B §4.6.1 & Appendix B (Table B-1)** — achieved vs. required 1–4 scores across the eight CAS factors | Supplies the underlying evidence for each factor; carries no CAS score block. | Optional `credibility_assessment` block in `validation_report.json` recording `{achieved, required, rationale}` per CAS factor. |
| 2 | **ASME V&V 40-2018 §4 & NASA-STD-7009B §4.1.4** — *Model Influence* × *Decision Consequence* risk grading | Leaves risk context to `model_card.md` `## Intended use` and `## Out of scope`. | Optional `risk_classification: {model_influence, decision_consequence, risk_level}` block in `manifest.yaml`. |
| 3 | **ASME V&V 20-2009 (R2021) & NASA-STD-7009B §4.4.1** — distinguishing a numerical solver referent ($u_{\text{num}}$) from a physical experiment ($u_D$) | `provenance.dataset` records `solver_version` and `generator_version`, but does not require a structured referent kind or solver discretization uncertainty. | Optional `provenance.referent: {kind: "numerical_solver" | "physical_experiment" | "hybrid", discretization_uncertainty_quantified: bool}` block. |
| 4 | **DNV-RP-0513 §4.1 / §4.3** — benchmarking against both a trivial baseline and a linear/subspace baseline | `V012` and `V013` verify that `A4_baseline_beat` has at least one satisfied comparator (`>= 1`), without requiring two distinct baseline classes. | A warning or rule checking that `A4_baseline_beat` compares against both a trivial and a non-trivial baseline where applicable. |
| 5 | **DNV-RP-0510 §4.3 & NASA-STD-7009B CAS Factor 3** — machine-verified corpus gate report binding | `M014` and `V003` verify `provenance.dataset.sha256`, without linking the digest of a `corpus_gate` (`G1.1`–`G1.7`) report. | Optional `provenance.dataset.corpus_gate_report_sha256` field in `manifest.yaml`. |
| 6 | **DNV-RP-0513 §6.1** — quantitative post-deployment drift and recalibration triggers | `lineage.retrain_cadence` is a free-text string in `manifest.yaml`. | Optional structured `lineage.recalibration_triggers` block (for example, maximum OOD rejection rate or solver spot-check interval). |
| 7 | **NASA-STD-7009B §4.7.3 & DNV-RP-0513 §6.2** — cryptographic verification of detached signatures | `M017` validates the shape of `provenance.signature: {format: "oms", path}` and warns if malformed; the checker verifies no signature ([PROVENANCE-SIGNING.md](../spec/PROVENANCE-SIGNING.md)). | Optional signature verification once a zero-mandatory-dependency verification path is ratified in a future major/minor version. |
