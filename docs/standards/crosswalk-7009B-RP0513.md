# Clause-by-Clause Crosswalk: Contract 1.2 to NASA-STD-7009B, DNV-RP-0513 / RP-0671, BV NI 692, MIL-STD-3022, and ASME V&V 40 / V&V 20

**Scope:** how the fifty rules (`E001`–`E004`, `M001`–`M024`, `C001`–`C006`,
`V001`–`V013`, `S001`–`S003`), the twenty-seven manifest fields, the fifteen
model-card sections, and the fifteen validation-ladder keys (`A1`–`A5`,
`B1`–`B6`, `C1`–`C4`) of [the Contract, version 1.2](../spec/CONTRACT-v1.md) map
to the clauses and tables of **NASA-STD-7009B** (2024-03-05) and
**NASA-HDBK-7009B** (2026-02-03), **DNV-RP-0513** (June 2021) and
**DNV-RP-0671** (September 2023) (with **DNV-RP-0510**), **Bureau Veritas
NI 692 R00** (October 2025), **MIL-STD-3022 w/ Change 1** (2012-04-05), and the
conceptual frameworks of **ASME V&V 40-2018** and **ASME V&V 20-2009 (R2021)**.
For the broader discussion of where the Contract sits relative to adjacent VVUQ
and ML-packaging specifications and where it deliberately stops, see
[STANDARDS-ALIGNMENT.md](../STANDARDS-ALIGNMENT.md); bibliographic citations for
scientific literature are in [REFERENCES.md](../REFERENCES.md).

---

## 1. What this crosswalk states, and what it does not claim

Engineering credibility and assurance standards ask two different kinds of
questions about a computational or machine-learned model:

1. **Structural and numerical evidence questions** — *Are the inputs, outputs,
   physical units, coordinate conventions, and valid operating ranges declared?
   Does every output carry an uncertainty declaration? Do the artifact SHA-256
   digests on disk match the manifest? Are the eleven required model-card
   sections present and non-stubbed? Does every `PASS` or `FAIL` check carry
   numeric measurements, numeric thresholds, and recomputable comparators? Does
   the declared `overall` verdict follow from the fifteen ladder checks? Does
   the entrypoint answer each declared example in an isolated working directory
   within its timeout?*
2. **Engineering and programmatic judgement questions** — *Is the chosen
   Intended Use or Context of Use appropriate for the engineering decision at
   stake? Are the threshold bars strict enough for the assessed criticality or
   confidence level? Is the training referent a validated physical experiment
   ($D \pm u_D$) or a numerical solver whose own discretization uncertainty
   $u_{\text{num}}$ and input uncertainty $u_{\text{input}}$ must be accounted
   for under ASME V&V 20? Which achievement levels (`0`–`4`) across
   NASA-STD-7009B Appendix E's eleven capability and results factors, or which
   confidence and maturity levels (`CL0`–`CL4`, `ML0`–`ML4`) under DNV-RP-0513,
   does the programme require?*

`open-contract-ml check` (and `open-contract-ml check --smoke`) answers the
first class of questions mechanically and deterministically, exiting `0` when a
package satisfies all enforced rules and `1` when any `ERROR` rule fires. It
does **not** answer the second class: a green conformance check means the
package supplies a complete, internally consistent, cryptographically verified
record for an engineering review; it never substitutes for the review itself.

**Verification provenance:** Sections 3, 4, and 5 below were checked directly
against the primary published editions of `NASA-STD-7009B` (2024-03-05, 88 pp.),
`NASA-HDBK-7009B` (2026-02-03, 175 pp.), `DNV-RP-0513` (June 2021, 97 pp.),
`DNV-RP-0671` (September 2023, 73 pp.), `Bureau Veritas NI 692 R00` (October
2025, 40 pp.), and `MIL-STD-3022 w/ Change 1` (2012-04-05, 55 pp.). Section 6
maps against the published scopes and public methodology summaries of the
paywalled ASME standards (`ASME V&V 40-2018`, `ASME V&V 20-2009 (R2021)`,
`ASME V&V 10-2019 (R2025)`, `ASME VVUQ 1-2022`) rather than asserting
clause-by-clause wording from unread paywalled texts.

---

## 2. Package artifacts and rule inventory (Contract 1.2, `open-contract-ml` 0.3.1)

| Artifact | Schema / Enforcer | What Contract 1.2 enforces | Rules |
|---|---|---|---|
| **`manifest.yaml`** (or `manifest.json`) | [schemas/contract-v1/manifest.schema.json](../../src/opencontractml/schemas/contract-v1/manifest.schema.json) + `opencontractml.verify` | `spec_version`, identity (`id`, `name`, `version`, `owner`, `domain`, `modality`, `purpose`), `when_to_use`, `when_not_to_use`, `inputs[]` (`name`, `type`, `required`, `units`, `range: [min, max]`), `outputs[]` (`name`, `type`, `viewer`, `units`, `field`), `uncertainty` (`form`, `per_output`, `calibration`), `invocation` (`executable`, `protocol: "stdio_json"`, `timeout_s`), `lineage`, `model_card`, `provenance` (`artifacts[]`, `dataset`, `code`, `environment`, `signature`), `validation` (`report`, `overall`), `licence` (`model`, `weights`, `training_data`), `taxonomy_cell`, `taxonomy_registry`, `examples[]` | `E001`–`E004`, `M001`–`M024` |
| **`model_card.md`** | `opencontractml.verify` + [model_card.template.md](../../src/opencontractml/templates/model_card.template.md) | Flat scalar YAML front-matter (`model_id`, `version`, `spec_version`) matching the manifest, followed by the **eleven required H2 sections** in exact order (≥ 40 non-whitespace characters each) and up to **four reserved optional H2 sections** (`Alternatives considered`, `Disclosure`, `Open questions`, `References`) | `C001`–`C006` |
| **`validation_report.json`** | [schemas/contract-v1/contract-vocabulary.json](../../src/opencontractml/schemas/contract-v1/contract-vocabulary.json) + `opencontractml.verify` | Identity header (`model_id`, `model_version`, `spec_version`, `dataset_sha256`), the **fifteen validation-ladder checks** (`A1`–`A5`, `B1`–`B6`, `C1`–`C4`) with statuses in `("PASS", "FAIL", "NOT_RUN", "NOT_APPLICABLE")`, numeric metrics/thresholds, explicit `comparators` (`{metric, op, bar}`), and a recomputed `overall` verdict | `V001`–`V013` |
| **Entrypoint smoke run (`--smoke`)** | `opencontractml.verify` (`check --smoke`) | Executes `invocation.executable` under `stdio_json` in a fresh working directory per request (single and, where declared, batch), checking exit 0 within `timeout_s`, frame structure (`run_id`, `status`, every declared output and uncertainty key), and every field artifact reference (`bytes`, `sha256`, `media_type`, `units`) | `S001`–`S003` |
| **Total rule table** | `python -m opencontractml.verify rules` | **50 rules**: **44 `ERROR`** and **6 `WARN`** (`M016`, `M017`, `M021`, `M024`, `C006`, `S002`) | `50` total |

---

## 3. Clause-by-clause crosswalk: NASA-STD-7009B (2024) and NASA-HDBK-7009B (2026)

### 3.1 Normative requirements (NASA-STD-7009B §4.1–§4.3, Appendix A Table 1, and Appendix D) and NASA-HDBK-7009B §4.5

NASA-STD-7009B (approved 2024-03-05, superseding NASA-STD-7009A w/ Change 1)
organizes its forty-three verifiable `shall` statements (`[M&S xx]`, indexed in
Appendix A Table 1, with non-mandatory recommendations in Appendix B Table 2)
into three lifecycle sections: **§4.1 M&S Programmatics**, **§4.2 M&S
Development**, and **§4.3 M&S Use**, paired with **Appendix D** (*M&S
Criticality Assessment*, Figure 1 and Tables 3–4) and **Appendix E** (*M&S
Capability & M&S Results Assessments*, Tables 5–20). NASA-HDBK-7009B (approved
2026-02-03) adds explicit guidance in **§4.5.1** (*Pedigree and Provenance in
M&S*), **§4.5.2** (*Models of Models* — coupled/linked sub-models, surrogate
models, and metamodels), **§4.5.3** (*NASA's Use of Artificial Intelligence (AI)
Models*), and **Appendix F** (the five use statements: *Intended, Permissible,
Proposed, Accepted, Actual Use*).

| NASA-STD-7009B / HDBK-7009B Clause | Requirement summary | Contract 1.2 artifact and field path | Enforced rules (`opencontractml.verify`) | What remains a human / programme judgement |
|---|---|---|---|---|
| **§4.1.1.1 `[M&S 40]` & HDBK App. F** — Intended Use | Maintain a record of the expected purpose, real-world system (RWS) aspects, and decisions informed. | `model_card.md` `## TL;DR`, `## Intended use`; `manifest.yaml` `id`, `name`, `domain`, `modality`, `purpose`, `outputs[]` (`name`, `type`, `units`, `viewer`, `field`), `taxonomy_cell` | `C003`, `C004`, `M003`, `M005`, `M019`, `M022` (`taxonomy_cell` in pinned cell vocabulary) | Whether the declared QoIs and analysis cell are sufficient for the programme's engineering decision. |
| **§4.1.1.2 `[M&S 6]` & Appendix D (Fig. 1, Tables 3–4)** — Criticality Assessment | Assess and record M&S results influence (`1`–`5`) and decision consequence (`I`–`V`). | `model_card.md` `## Intended use`, `## Out of scope`; threshold bars in `validation_report.json` | `C003`, `C004`, `V006`, `V012`, `V013` | Assigning the `5×5` criticality cell and deciding which standard clauses are tailored (`§1.3`). |
| **§4.1.1.3–§4.1.1.8 `[M&S 41–44, 9, 51]`** — Plans, Metrics, Acceptance Criteria, Reviews & Defects | Record lifecycle plan, technical metrics, acceptance criteria (`[M&S 43]`: V&V, UQ, sensitivity, assessment thresholds), technical reviews (`[M&S 9]`), and known defects (`[M&S 51]`). | `validation_report.json` `checks` (`metrics`, `thresholds`, `comparators`); `manifest.yaml` `lineage`; `model_card.md` `## Known failure modes`, `## Disclosure`, `## Open questions`, `## Version history` | `V004`–`V013` (`comparators` formalize `[M&S 43]` acceptance bars), `C003`, `C004`, `C006`, `M018` | Programme acquisition/retirement schedules (`[M&S 41]`), formal peer-review governance (`[M&S 9]`), and live defect-tracker closure (`[M&S 51]`). |
| **§4.2.1.1–§4.2.1.2 `[M&S 10, 45]` & HDBK §4.5.1** — Development Data Pedigree & Software | Maintain RWS characteristics, development datasets, data pedigree, and supporting software/environment. | `manifest.yaml` `provenance.artifacts[]`, `provenance.dataset` (`sha256`, `n_samples`, `generator_version`, `solver_version`), `provenance.code`, `provenance.environment`, `licence`; `model_card.md` `## Training data`, `## Provenance`; `opencontractml.corpus_gate` (`G1.1`–`G1.7`) | `M011`–`M017`, `M020`, `M021`, `V002`, `V003` | Traceability of upstream experimental or COTS solver data to physical metrology standards. |
| **§4.2.1.3 `[M&S 46]` & HDBK §5.2.1.3.4** — Units & Vector Coordinate Frames | Maintain a record of physical units and vector coordinate frames for all quantities and input/output variables. | `manifest.yaml` `inputs[].units`, `canonical_units`, `outputs[].units`, `outputs[].field` (`units`, `coordinate_ref`); `check --smoke` field artifact metadata | `M004` (float inputs state units), `M005` (float outputs state units), `M018`, `M019` (`field` block), `S003` | Verifying consistent coordinate-frame transformations across multi-model interfaces. |
| **§4.2.1.4–§4.2.1.7 `[M&S 11–14]` & §4.2.1.9 `[M&S 47]`** — Assumptions, Math, Limits, Permissible Uses & User Guidance | Record conceptual abstractions/assumptions, mathematical structure, M&S limits (`[M&S 13]`), permissible uses (`[M&S 14]`), and setup/execution/interface/obsolescence guidance (`[M&S 47]`). | `manifest.yaml` `when_to_use`, `when_not_to_use`, `inputs[].range` (`[min, max]`, `min < max`), `invocation`, `lineage.retrain_cadence`, `examples[]`; `model_card.md` `## Intended use`, `## Out of scope`, `## Architecture`, `## Training configuration` | `M003`, `M004`, `M008`, `M018`, `C003`, `C004`, `S001`–`S003` | Engineering adequacy of the physical abstractions (`[M&S 11–12]`) and coupled-model interface testing (`HDBK §4.5.2`). |
| **§4.2.3 `[M&S 15, 16]`** — M&S Verification & Domain of Verification | Verify code and numerical solution accuracy and record the domain of verification. | `validation_report.json` `A5_reproducibility`, `B3_residual`, `B5_invariance`, `C2_serve_parity`, `C3_provenance_integrity`; `check --smoke` | `M012`, `M013`, `V004`, `V006`, `V011` (`bitwise` requires tolerance `0`), `V012`, `V013`, `S001`–`S003` | Upstream PDE solver mesh/time-step discretization convergence ($u_{\text{num}}$, `§4.2.4b`). |
| **§4.2.5 `[M&S 17, 18]` & HDBK §4.5.2–§4.5.3** — M&S Validation & Domain of Validation | Validate conceptual and computational M&S against a referent and record the domain of validation (including AI/ML surrogates trained on simulation or empirical data). | `validation_report.json` `A1_accuracy`, `A2_extrapolation`, `A4_baseline_beat`, `B1_monotonicity`, `B2_bounds`, `B4_conservation`, `B6_integrated_quantities`; `model_card.md` `## Performance` | `V004`–`V009` (`B4_conservation` measured, not declared), `V012`, `V013` | Closeness of the referent (physical RWS experiment vs. higher-fidelity solver) to the operational environment (`Table 9`). |
| **§4.2.7 `[M&S 19, 21]` & §4.3.3 `[M&S 28, 29]`** — Uncertainty Characterization (Development & Use) | Record processes, rationale, and quantitative/qualitative uncertainties in referent data, inputs, M&S results, and derived quantities. | `manifest.yaml` `uncertainty` (`form`, `per_output`, `calibration`); `model_card.md` `## Uncertainty quantification`; `validation_report.json` `A3_uq_calibration` | `M007` (every output covered, or `form: none`), `C005` (names a method and states a number), `V010` (`nominal`, `empirical`, `n`, `method`), `V012`, `V013` | Separating epistemic model-form error from aleatory variation and quantifying referent measurement error (`[M&S 19]`). |
| **§4.3.1 `[M&S 22–27]` & §4.3.5 `[M&S 30]`** — Proposed Use, Use Assessment, Placarding & Sensitivity | Compare proposed use against permissible use (`[M&S 22–23]`), record run inputs/setup/warnings (`[M&S 24–25, 27]`), enforce or placard excursions outside V&V domains (`[M&S 26]`), and record sensitivity analyses (`[M&S 30]`). | `manifest.yaml` `inputs[].range`, `when_to_use`, `when_not_to_use`; `validation_report.json` `A2_extrapolation`, `B1_monotonicity`, `B5_invariance`, `C1_ood_guard`; `check --json` conformance record | `M004`, `M018`, `V006`–`V008`, `V012`, `V013`, `S001`–`S003` | Operational placarding when a user deliberately runs outside the validated envelope (`[M&S 26b]`, `HDBK Fig. 13`). |
| **§4.3.6 `[M&S 31, 49]` & §4.3.8 `[M&S 32–39, 50]`** — Results/Risk Assessment & Decision-Maker Reporting | Report explicit warnings for unachieved criteria or violated limits (`[M&S 32]`), uncertainty estimates/processes (`[M&S 33–34]`), capability and results assessments (`[M&S 50, 35]`), review findings (`[M&S 36]`), practitioner qualifications (`[M&S 37]`), records (`[M&S 38]`), and M&S risk acceptance rationale (`[M&S 39, 49]`). | `validation_report.json` `overall`, `checks`, `comparators`; `manifest.yaml` `owner`; `model_card.md` `## Performance`, `## Uncertainty quantification`, `## Known failure modes`, `## Disclosure`, `## Open questions`; `check --json` conformance record | `V005`, `V008` (any `FAIL` or `NOT_RUN` blocks `overall: PASS`), `V013`, `M003`, `C003`–`C006` | Assessing the eleven `0`–`4` credibility levels (`[M&S 48, 31]`), practitioner training/qualification records (`[M&S 37]`), and programme risk sign-off (`[M&S 39]`). |

### 3.2 NASA-STD-7009B Appendix E (Tables 5–20) & NASA-HDBK-7009B Appendix D — Eleven-Factor Credibility Assessment (`0`–`4` Scale)

NASA-STD-7009B replaces the single end-point 8-factor (`1`–`4`) scale of
NASA-STD-7009A with **two separate assessments** in **Appendix E**, graded on a
five-tier ordinal step scale from **`0` (*Insufficient evidence*)** to **`4`**
(no partial credit; factor scores are not summed or averaged):

- **M&S Capability Assessment (`§E.3`, `[M&S 48]`, `[M&S 50]`, Tables 5–11)** —
  **five (`5`) factors** evaluated at or prior to model release (`Phase D`);
- **M&S Results Assessment (`§E.4`, `[M&S 31]`, `[M&S 35]`, Tables 12–20)** —
  **six (`6`) factors** evaluated on the specific operational run (`Phase E`).

The Contract does not assign `0`–`4` factor scores; instead, a conformant
Contract 1.2 package supplies the structured, machine-checked evidence an
assessor inspects when grading each of the eleven factors:

| Assessment (`Appendix E`) | Factor & Primary Table (`NASA-STD-7009B`) | Evidence supplied by a conformant Contract 1.2 package | Rules enforcing the evidence |
|---|---|---|---|
| **Capability (`§E.3`, `[M&S 48]`)** | **1. M&S Data Pedigree** (`§E.3.2`, `Table 7`; `HDBK §D.3`) | `provenance.dataset` (`sha256`, `n_samples`, `generator_version`, `solver_version`), `licence.training_data`, `model_card.md` `## Training data`, dataset hash match (`V003`), and `opencontractml.corpus_gate` (`G1.1`–`G1.7`). | `M014`, `M020`, `C003`, `C004`, `V003` |
| **Capability (`§E.3`, `[M&S 48]`)** | **2. M&S Verification** (`§E.3.3`, `Table 8`; `HDBK §D.4`) | Re-hashed artifact digests (`M013`), recomputed comparator verdicts (`V013`), `A5_reproducibility` determinism class and tolerance (`V011`), `B3_residual`, `B5_invariance`, `C2_serve_parity`, `C3_provenance_integrity`, and isolated smoke runs (`S001`–`S003`). | `M012`, `M013`, `V011`–`V013`, `S001`–`S003` |
| **Capability (`§E.3`, `[M&S 48]`)** | **3. M&S Validation** (`§E.3.4`, `Table 9`; `HDBK §D.5`) | Conceptual scope (`## Intended use`, `## Architecture`) plus quantitative comparator records across `A1_accuracy`, `A2_extrapolation`, `A4_baseline_beat`, `B1_monotonicity`, `B2_bounds`, `B4_conservation`, and `B6_integrated_quantities`. | `C003`, `C004`, `V004`–`V009`, `V012`, `V013` |
| **Capability (`§E.3`, `[M&S 48]`)** | **4. M&S Development Technical Review** (`§E.3.5`, `Table 10`; `HDBK §D.6`) | Reproducible third-party offline check (`open-contract-ml check --smoke --json`), `owner` attribution, and reserved `## Disclosure` / `## Open questions` sections (independent human peer review remains organizational). | `M003`, `C006`, `V008`, `S001`–`S003` |
| **Capability (`§E.3`, `[M&S 48]`)** | **5. M&S Development Process/Product Management** (`§E.3.6`, `Table 11`; `HDBK §D.7`) | Content-addressed `provenance` (`artifacts[]`, `dataset`, `code`, `environment`, `signature`), `spec_version` & `version` identity binding across manifest/card/report, `licence` block, and `taxonomy_registry` pin. | `E001`–`E004`, `M002`, `M011`–`M024`, `C001`, `C002`, `V001`–`V003` |
| **Results (`§E.4`, `[M&S 31]`)** | **6. M&S Use Assessment** (`§E.4.2`, `Tables 14–15`; `HDBK §D.8`) | `manifest.yaml` `domain`, `modality`, `purpose`, `when_to_use`, `when_not_to_use`, `inputs[].range`, `lineage`, `taxonomy_cell`; `model_card.md` `## Intended use`, `## Out of scope`, `## Version history`. | `M003`, `M004`, `M018`, `M022`, `C003`, `C004` |
| **Results (`§E.4`, `[M&S 31]`)** | **7. M&S Input Pedigree** (`§E.4.3`, `Table 16`; `HDBK §D.9`) | Typed `inputs[]` (`name`, `type`, `required`, `units`, `[min, max]` `range`), `examples[]` smoke inputs, and runtime `C1_ood_guard` out-of-envelope detection. | `M004`, `M006`, `M018`, `V004`, `S001` |
| **Results (`§E.4`, `[M&S 31]`)** | **8. M&S Uncertainty Characterization** (`§E.4.4`, `Table 17`; `HDBK §D.10`) | Per-output `uncertainty` contract (`M007`), quantitative `## Uncertainty quantification` prose (`C005`), empirical interval coverage in `A3_uq_calibration` (`V010`), and uncertainty keys in `stdio_json` smoke responses (`S001`, `S003`). | `M007`, `C005`, `V010`, `V012`, `V013`, `S001`, `S003` |
| **Results (`§E.4`, `[M&S 31]`)** | **9. M&S Results Robustness** (`§E.4.5`, `Table 18`; `HDBK §D.11`) | Directional parameter sensitivity (`B1_monotonicity`), boundary/tail degradation (`A2_extrapolation`), discretization/frame invariance (`B5_invariance`), and `## Known failure modes`. | `C003`, `C004`, `V004`, `V006`, `V012`, `V013` |
| **Results (`§E.4`, `[M&S 31]`)** | **10. M&S Use/Analysis Technical Review** (`§E.4.6`, `Table 19`; `HDBK §D.12`) | Machine-verifiable `conformance-record.schema.json` (`check --json`), non-masking rollup (`V008`), and explicit `NOT_APPLICABLE` rationales (`V007`) for independent review inspection. | `V007`, `V008`, `V012`, `V013` |
| **Results (`§E.4`, `[M&S 31]`)** | **11. M&S Use Process/Product Management** (`§E.4.7`, `Table 20`; `HDBK §D.13`) | Deterministic `stdio_json` invocation protocol (`M008`), `C2_serve_parity`, `C4_deployment_readiness`, and content-addressed field output artifacts (`S003`). | `M008`, `M012`, `M013`, `V004`, `S001`–`S003` |

---

## 4. Clause-by-clause crosswalk: DNV-RP-0513 (June 2021) and DNV-RP-0671 (September 2023)

DNV separates first-principles simulation assurance (**DNV-RP-0513**, *Assurance
of simulation models*, June 2021, Sections 1–4 and Appendices A–D; referencing
**DNV-RP-0510**, *Framework for assurance of data-driven algorithms and models*,
and **DNV-RP-0497**, *Data quality assessment framework*) from AI-enabled system
assurance (**DNV-RP-0671**, *Assurance of AI-enabled systems*, September 2023,
Sections 1–6 and Appendices A–I). In particular, **DNV-RP-0513 §2.3.4 and §4.4
(Table 4-3, items `1.1`–`3.6`)** define a formal machine-readable **Design
contract** for reusable black-box component models, and **DNV-RP-0671 §4.4.2
and Appendix E** generalize this into modular **Assurance contracts** connecting
assumptions and guarantees across subsystems.

| DNV-RP-0513 / DNV-RP-0671 Section | Assurance requirement | Contract 1.2 implementation | Enforced rules (`opencontractml.verify` & `corpus_gate`) |
|---|---|---|---|
| **RP-0513 §2.5 (Tables 2-1, 2-2) & §3.3.2; RP-0671 §4.2 & §5.3** — Conceptual Model Qualification, Modelling Taxonomy, System Boundaries (`CESM`) & `ODD` | Categorize the simulation/AI component, define system boundaries, intended usage, assumptions, limitations, and Operational Design Domain (`ODD`). | `manifest.yaml` `domain`, `modality`, `purpose`, `when_to_use`, `when_not_to_use`, `inputs[].range`, `taxonomy_cell`, `taxonomy_registry`; `model_card.md` `## Intended use`, `## Out of scope`, `## Architecture`, `## Known failure modes`. | `E004`, `M003`, `M004`, `M018`, `M022`–`M024`, `C003`, `C004` |
| **RP-0513 §2.6 (§2.6.2–§2.6.5, Table 2-3, Fig. 2-6); RP-0671 §4.3.6 & §4.5** — Risk-Based Assurance, Strength of Knowledge, Confidence Levels (`CL0`–`CL4`) & Maturity Levels (`ML0`–`ML4`) | Evaluate uncertainty-shaping factors and consequence severity (`0`–`4`), establish required Model Confidence Level (`CL0`–`CL4`) and Supplier Maturity Level (`ML >= CL`), and substantiate claims via V&V intensity and rigour. | Explicit per-check `thresholds` and recomputed `comparators` (`{metric, op, bar}`) in `validation_report.json` (`V006`, `V012`, `V013`), non-masking `overall` rollup (`V008`), and versioned artifact/code/dataset provenance (`M011`–`M017`). | `M011`–`M017`, `V006`–`V013` *(choosing the target `CL0`–`CL4` / `ML0`–`ML4` tier is a programme/assurer judgement)* |
| **RP-0513 §3.2 & App. A (`A.7`, `A.9`, `A.16`); RP-0510; RP-0671 §3.2.2.3(4)** — Data Quality, Units, Configuration Management & Split Independence | Ensure input/validation data quality, measurement-unit consistency (`A.16`), configuration control (`A.9`), and train/calibration vs. test independence (`§3.3.4`). | `manifest.yaml` `inputs[].units`, `outputs[].units`, `provenance.dataset` (`sha256`, `n_samples`, `generator_version`, `solver_version`); `V003` dataset hash match; `opencontractml.corpus_gate` (`G1.1` schema/units, `G1.2` convergence, `G1.3` coverage, `G1.4` bounds, `G1.5` duplicates, `G1.6` group-aware split integrity, `G1.7` provenance). | `M004`, `M005`, `M014`, `M019`, `V003`; corpus gate checks `G1.1`–`G1.7` |
| **RP-0513 §3.3.3, §3.3.4, §3.4 (Tables 3-7, 3-8), App. B (Table B-1) & App. D; RP-0671 §3.2.2.3(1–2, 5) & App. F/H** — Model Verification, Validation, Conserved/Dissipative Quantities & UQ | Verify symmetry (`B.1.1`), parameter/boundary coverage (`B.1.3.2`, `B.1.6`), conserved and dissipative quantities (`Table 3-7`), repeatable random seeds (`Table 3-8`), referent comparison (`B.2.1`), consistency in non-referent regimes (`B.2.3–B.2.4`), and calibrated uncertainty (`Table D-2`, `RP-0671 App. F/H`). | `validation_report.json` Tier A (`A1_accuracy`, `A2_extrapolation`, `A3_uq_calibration`, `A4_baseline_beat`, `A5_reproducibility`) and Tier B (`B1_monotonicity`, `B2_bounds`, `B3_residual`, `B4_conservation`, `B5_invariance`, `B6_integrated_quantities`), plus `uncertainty.per_output`. | `M007`, `C005`, `V004`–`V013` |
| **RP-0513 §2.3.4, §4.2 (Table 4-1), §4.3 (Table 4-2) & §4.4 (Table 4-3 items `1.1`–`3.6`); RP-0671 §4.4.2 & App. E** — Component Black-Box Interface, Design Contract & Modular Assurance Contracts | Publish a machine-readable *Design contract* covering identifier/version (`1.2`), confidence level (`1.3`), description/intended usage (`1.4`), licences (`1.5`), execution tools (`1.6`), assumptions (`1.7`), assurance record (`1.8`), typed I/O & parameters with units/ranges (`2.2–2.4`), and array dimensions (`2.5`). | `manifest.yaml` (`id`, `version`, `purpose`, `when_to_use`, `when_not_to_use`, `licence`, `invocation`, `provenance`, `inputs[]`, `outputs[]`, `outputs[].field`, `examples[]`), `model_card.md`, `validation_report.json`, and `check --smoke --json` conformance record. | `E001`–`E004`, `M001`–`M024`, `C001`–`C006`, `V001`–`V013`, `S001`–`S003` *(multi-component system-graph wiring `Table 4-3` items `3.1–3.4` is listed in §9 Gap 9)* |
| **RP-0671 §4.6.2.3–§4.6.2.4 & App. G.3.1; RP-0513 App. A (`A.21`)** — Regression Testing & Post-Deployment Drift Monitoring | Automate regression re-verification upon model updates (`A.21`) and monitor post-deployment performance, data drift, and concept drift (`RP-0671 §4.6.2.4`, `App. G.3.1`). | Offline deterministic regression gate (`open-contract-ml check --smoke`), runtime `C1_ood_guard` validation check, and `lineage.retrain_cadence` declaration. | `M018`, `V004`, `S001`–`S003` *(continuous in-service telemetry/drift logging is outside static package checking; see §9 Gap 4)* |

---

## 5. Companion marine ML and defense VV&A crosswalks: Bureau Veritas NI 692 R00 (2025) and MIL-STD-3022 w/ Change 1 (2012)

### 5.1 Bureau Veritas Guidance Note NI 692 R00 (*Guidelines for Machine Learning Systems*, October 2025)

Bureau Veritas NI 692 R00 specifies an eighteen-item assessment dossier
(**Section 2, Article 1, Table 1**) across six lifecycle areas for marine and
offshore machine-learning systems, together with twenty failure/risk definitions
in **Section 1, Article 6.3** (including `6.3.6` *Data drift*, `6.3.7` *Data
leakage*, `6.3.13` *Model drift*, `6.3.15` *Out-of-distribution input*, `6.3.16`
*Overfit*, and `6.3.18` *Silent failure*):

| BV NI 692 R00 Assessment Area (Sec. 2, Table 1) | Dossier & evaluation guidance | Contract 1.2 coverage and boundary |
|---|---|---|
| **1. Operational Description** (`Sec. 1 Art. 3.2`, `Sec. 2 Art. 2`, `Tables 2–9`) | Document `ConOps` (tasks, intended domain, foreseeable misuses, limits), Operational Envelope (`OE`), Operational Design Domain (`ODD`), automation/oversight degrees (`A0`–`A4`, `H1`–`H4`), and provider/deployer roles. | `manifest.yaml` `owner`, `domain`, `modality`, `purpose`, `when_to_use`, `when_not_to_use`, `inputs[].range` (`M003`, `M004`, `M018`); `model_card.md` `## Intended use`, `## Out of scope`, `## Known failure modes` (`C003`, `C004`). System-level `A0`–`A4` / `H1`–`H4` operator control loops sit above the model package. |
| **2. Risk Management** (`Sec. 2 Art. 3`) | Hazard/cause/consequence analysis, mitigation layers, bias assessment, impact assessment, and reassessment triggers. | `model_card.md` `## Known failure modes`, `## Disclosure`, `## Open questions` (`C003`, `C004`, `C006`) and `lineage.retrain_cadence`; quantitative threshold bars in `validation_report.json` (`V006`, `V012`, `V013`). |
| **3. Data Quality & Governance** (`Sec. 1 Art. 4`, `Sec. 2 Art. 4`, `Tables 10–11`) | Dataset metadata (`Table 10`: provenance, selection rationale, data rights, modalities, types, size), data quality dimensions (`Table 11`: completeness, validity, uniqueness, unit consistency), and leak-free partitioning (`Art. 4.2.5`). | `manifest.yaml` `provenance.dataset`, `licence.training_data` (`M014`, `M020`, `V003`), `inputs[]`/`outputs[]` types and units (`M004`, `M005`), `## Training data`, and `opencontractml.corpus_gate` (`G1.1`–`G1.7`, including `G1.5` duplicates and `G1.6` group-aware split leakage check). |
| **4. Model Development & Evaluation** (`Sec. 2 Art. 5`, `Tables 12–13`) | Model characteristics (`Table 12`: task, architecture, origin, training config, capabilities/limits, versioning) and thresholded evaluation report (`Table 13`: metric, justification, score range, acceptable criteria, scores across performance, robustness/OOD, reproducibility, confidence/UQ, complexity). | Directly enforced by `model_card.md` (`## Architecture`, `## Training configuration`, `## Performance`, `## Uncertainty quantification`, `## Version history`), `uncertainty.per_output` (`M007`, `C005`), and `validation_report.json` Tiers A & B (`A1`–`A5`, `B1`–`B6`) with recomputed `comparators` (`V006`–`V013`), preventing `Sec. 1 Art. 6.3.18` silent evaluation passes. |
| **5. ML System Development & Safeguards** (`Sec. 2 Art. 6`, `Tables 14–15`) | System validation report (`Table 14`), technical prerequisites (`Table 15`: OS, software/library versions, data interfaces), and automated runtime safeguards (`Art. 6.3.1`: OOD/quality/threshold triggers). | `provenance.environment` (`M016`), `provenance.artifacts[]` (`M012`, `M013`), `invocation` (`stdio_json`, `timeout_s`, `M008`), `C1_ood_guard`, `C2_serve_parity`, `C3_provenance_integrity`, `C4_deployment_readiness`, and `check --smoke` (`S001`–`S003`). |
| **6. ML System Operation** (`Sec. 2 Art. 7`, `Tables 16–18`) | Continuous operation logs (`Table 16`), significant event reports (`Table 17`), and maintenance/retraining reports (`Table 18`). | Static package checker covers pre-deployment and post-retraining package re-verification; live vessel/plant telemetry logs (`Tables 16–17`) belong to the operational runtime (§9 Gap 4). |

### 5.2 MIL-STD-3022 w/ Change 1 (*Documentation of VV&A for Models and Simulations*, 5 April 2012)

MIL-STD-3022 establishes four DoD VV&A Data Item Descriptions (`§6.3`:
`DI-MSSM-81750` *Accreditation Plan* in Appendix A, `DI-MSSM-81751` *V&V Plan*
in Appendix B, `DI-MSSM-81752` *V&V Report* in Appendix C, and `DI-MSSM-81753`
*Accreditation Report* in Appendix D) sharing a common core structure (`§5.2`
Table I) and explicitly encouraging automated production and digital archiving
of reusable VV&A records (`§5.4`):

| MIL-STD-3022 Shared Section (`§5.2` Table I & Appendices A–D) | VV&A documentation content | Contract 1.2 counterpart |
|---|---|---|
| **1. Problem Statement** (`A.6`/`B.6`/`C.6`/`D.6`) | Intended use, M&S overview, M&S application, V&V and accreditation scope. | `manifest.yaml` `id`, `name`, `version`, `domain`, `modality`, `purpose`, `taxonomy_cell`; `model_card.md` `## TL;DR`, `## Intended use`, `## Out of scope` (`M003`, `M022`, `C003`, `C004`). |
| **2. M&S Requirements & Acceptability Criteria** (`A.7`/`B.7`/`C.7`/`D.7`, `Tables A-I..D-I`) | Quantitative/qualitative metrics and acceptability criteria tied to requirements. | `validation_report.json` `checks.<key>.metrics`, `thresholds`, and `comparators` (`{metric, op, bar}`), mechanically re-evaluated by `V006`, `V012`, `V013`. |
| **3. M&S Assumptions, Capabilities, Limitations & Risks/Impacts** (`A.8`/`B.8`/`C.8`/`D.8`) | Known modelling/data assumptions, capabilities, constraints, and risk impacts. | `manifest.yaml` `when_to_use`, `when_not_to_use`, `inputs[].range`, `uncertainty`; `model_card.md` `## Architecture`, `## Uncertainty quantification`, `## Known failure modes`, `## Open questions` (`M004`, `M007`, `C003`–`C006`). |
| **4–5. V&V Task Analysis & Recommendations (`App. C.9–C.10`: Data, Conceptual, Design, Implementation & Results V&V)** | Executed test results, anomalies/discrepancies against acceptability criteria, and V&V/accreditation recommendations. | `validation_report.json` (`A1`–`A5`, `B1`–`B6`, `C1`–`C4`, `overall` via `V008`), `opencontractml.corpus_gate` (`G1.1`–`G1.7` for Data V&V `§3.1.6`), `check --smoke` (`S001`–`S003` for Implementation Verification `C.9.4`), and `check --json` conformance record (`§5.4` automation & archiving). |
| **6. Key Participants (`A.11`..`D.11`) & Accreditation Authority (`§3.1.1–§3.1.3`, `§3.1.18`)** | M&S Developer, V&V Agent, SMEs, and Accreditation Authority roles and sign-off. | `manifest.yaml` `owner` (`team`, `contact`) and `provenance.signature` declaration (`M003`, `M017`); formal organizational separation between Developer, V&V Agent, and Accreditation Authority remains a programme governance boundary (§9 Gap 7). |
| **Suggested Appendices A–C (`M&S Description`, `Traceability Matrix`, `Basis of Comparison`)** | Hardware/software config, input/output definitions with units/ranges, CM inventory (`App. A`), requirement-to-evidence matrix (`App. B`), and validation referent (`App. C`). | `manifest.yaml` `inputs[]`, `outputs[]`, `provenance` (`artifacts[]`, `dataset`, `code`, `environment`), `taxonomy_registry` (`M004`–`M024`), and this rule/check crosswalk. |

---

## 6. Conceptual crosswalk: ASME V&V 40-2018 and ASME V&V 20-2009 (R2021)

> **Verification boundary (`STANDARDS-ALIGNMENT.md` §Sources / Unverified).**
> `ASME V&V 40-2018`, `ASME V&V 20-2009 (R2021)`, `ASME V&V 10-2019 (R2025)`, and
> `ASME VVUQ 1-2022` are paywalled ASME standards whose full clause texts were
> not read directly in preparing this repository. The table below maps Contract
> 1.2 to their published scopes and public methodology elements (Question of
> Interest, Context of Use, Model Risk, Code/Solution Verification, Validation
> Comparison Error $E = S - D$ and Validation Uncertainty $u_{\text{val}}$, and
> Applicability) without asserting verbatim ASME clause numbering.

| ASME V&V 40 / V&V 20 Framework Element | Credibility concept | Contract 1.2 mapping | Enforced rules and scope note |
|---|---|---|---|
| **Question of Interest (QoI)** (`V&V 40`, `VVUQ 1`) | The specific engineering question or decision the model informs. | `model_card.md` `## Intended use`; `manifest.yaml` `purpose` and `outputs[]` (`name`, `type`, `units`, `viewer`, `field`). | `M003`, `M005`, `M019`, `C003`, `C004` |
| **Context of Use (CoU)** (`V&V 40`, `VVUQ 1`) | The role and scope of the computational or surrogate model relative to full-order simulation or physical testing. | `model_card.md` `## Intended use`, `## Out of scope`, `## Alternatives considered`; `manifest.yaml` `domain`, `modality`, `when_to_use`, `when_not_to_use`, `taxonomy_cell`. | `M003`, `M022`, `C003`, `C004`, `C006` |
| **Model Risk Assessment** (`V&V 40`) | Combination of *Model Influence* and *Decision Consequence* setting the required credibility rigor. | The numerical threshold bars (`thresholds` and `comparators[].bar`) recorded in `validation_report.json`. | `V006`, `V012`, `V013` verify that every `PASS` or `FAIL` check states its bar and satisfies its comparator; the risk level itself is chosen by the engineering programme (§9 Gap 1). |
| **Code & Calculation Verification** (`V&V 40`, `V&V 20`, `V&V 10`) | Software quality assurance, numerical determinism, and discretization sensitivity. | `provenance` (`M011`–`M017`), `licence` (`M020`, `M021`), `A5_reproducibility` (`V011`), `B3_residual`, `B5_invariance`, `C2_serve_parity`, `C3_provenance_integrity`, and `check --smoke` (`S001`–`S003`). | `M011`–`M017`, `M020`, `M021`, `V011`, `S001`–`S003` (upstream solver mesh-refinement `GCI` / $u_{\text{num}}$ is §9 Gap 8). |
| **Validation Comparator ($E = S - D$, $u_{\text{val}}$)** (`V&V 20`, `V&V 40`) | Quantitative comparison of model outputs ($S$) against a referent ($D$) with explicit comparison error and uncertainty. | `provenance.dataset.sha256` (`M014`, `V003`), `validation_report.json` Tiers A & B (`A1_accuracy`, `A2_extrapolation`, `A3_uq_calibration`, `A4_baseline_beat`, `B1`–`B6`). | `M014`, `V003`, `V006`, `V009`, `V010`, `V012`, `V013`. **V&V 20 scope boundary:** as detailed in [STANDARDS-ALIGNMENT.md](../STANDARDS-ALIGNMENT.md) §3, a surrogate evaluated on a solver split measures surrogate-to-solver error, not $u_{\text{val}} = \sqrt{u_{\text{num}}^2 + u_{\text{input}}^2 + u_D^2}$ against physical experiment (§9 Gap 2). |
| **Applicability** (`V&V 40`) | Relevance of the validation dataset and test envelope to the Context of Use. | `manifest.yaml` `inputs[].range` (`M004`), `when_to_use`, `when_not_to_use`, `taxonomy_cell` (`M022`), `taxonomy_registry` (`M023`, `M024`), and `C1_ood_guard`. | `M004`, `M022`–`M024`, `V006`, `V012`, `V013` |

---

## 7. Complete rule-to-standard reference matrix (all 50 rules)

Every rule in `opencontractml.verify.RULES` (`python -m opencontractml.verify rules`)
is listed below with its severity, the Contract version from which it applies,
its exact title, and the corresponding clauses in NASA-STD-7009B, DNV-RP-0513 /
DNV-RP-0671, and the ASME VVUQ framework:

| Rule ID | Severity | Contract version | Exact rule title (`opencontractml.verify`) | NASA-STD-7009B (`2024`) | DNV-RP-0513 (`2021`) / RP-0671 (`2023`) | ASME VVUQ Element |
|---|---|---|---|---|---|---|
| `E001` | `ERROR` | 1.0+ | `package directory exists and is readable` | `§4.2.1.2 [M&S 45]`, `§E.3.6` | RP-0513 `§4.4 Table 4-3`, `A.9` | Code Verification |
| `E002` | `ERROR` | 1.0+ | `a YAML parser is available for a .yaml artifact` | `§4.2.1.2 [M&S 45]`, `§E.3.6` | RP-0513 `Table 4-3 (1.1)`, `A.6` | Code Verification |
| `E003` | `ERROR` | 1.0+ | `the contract-v1 manifest schema loads and the checker applies every keyword it uses` | `§4.2.3.1 [M&S 15]`, `§E.3.6` | RP-0513 `§3.3.3.1`, `A.26` | Code Verification |
| `E004` | `ERROR` | 1.2 | `the pinned cell vocabulary loads and holds together, wherever a manifest declares a taxonomy key` | `§4.1.1.1 [M&S 40]`, `§E.3.6` | RP-0513 `§2.5`, `A.9` | Context of Use |
| `M001` | `ERROR` | 1.0+ | `manifest present and parses to a mapping` | `§4.3.8.8 [M&S 38]`, `§E.3.6` | RP-0513 `§2.3.4`, `Table 4-3 (1.1)` | Code Verification |
| `M002` | `ERROR` | 1.0+ | `spec_version present, MAJOR.MINOR, major supported` | `§4.2.2d`, `§E.3.6` | RP-0513 `Table 4-3 (1.2)`, `A.9` | Code Verification |
| `M003` | `ERROR` | 1.0+ | `identity block complete (id, name, version, owner, domain, modality, purpose)` | `[M&S 40]`, `[M&S 37]`, `§E.4.2` | RP-0513 `Table 4-3 (1.2, 1.4)` | QoI & CoU |
| `M004` | `ERROR` | 1.0+ | `inputs declared and well formed (float inputs state units; a range is [min, max], min < max)` | `[M&S 46]`, `[M&S 13]`, `§E.4.3` | RP-0513 `Table 4-3 (2.2, 2.3)`, `A.16` | CoU & Applicability |
| `M005` | `ERROR` | 1.0+ | `outputs declared and well formed (float outputs state units)` | `[M&S 40]`, `[M&S 46]` | RP-0513 `Table 4-3 (2.4)`, `A.16` | QoI |
| `M006` | `ERROR` | 1.0+ | `no duplicate input or output names` | `[M&S 46]`, `§E.3.3` | RP-0513 `§3.3.3.1`, `Table C-1 (1.4)` | Code Verification |
| `M007` | `ERROR` | 1.0+ / 1.1+ | `every output is covered by an uncertainty.per_output block; uncertainty.form none (from contract 1.1) declares no block and no calibration` | `[M&S 21, 29, 33]`, `§E.4.4` | RP-0513 `Table 3-8`; RP-0671 `§3.2.2.3(5)` | Validation UQ |
| `M008` | `ERROR` | 1.0+ | `invocation block complete and protocol is supported` | `[M&S 47]`, `[M&S 25]`, `§E.4.7` | RP-0513 `Table 4-3 (1.6, 3.5)` | Code Verification |
| `M009` | `ERROR` | 1.0+ | `model_card path declared, inside the package, and the file exists` | `[M&S 38]`, `§E.3.6` | RP-0513 `§2.9`, `A.1` | CoU Documentation |
| `M010` | `ERROR` | 1.0+ | `validation.report path declared, inside the package, and the file exists` | `[M&S 15, 17, 38]` | RP-0513 `§2.9`, `Table 4-3 (1.8)`, `A.1` | Validation Record |
| `M011` | `ERROR` | 1.0+ | `provenance block present` | `[M&S 10, 45]`, `§E.3.2`, `§E.3.6` | RP-0513 `A.7`, `A.9` | Code Verification |
| `M012` | `ERROR` | 1.0+ | `provenance.artifacts entries well formed (a path inside the package, a role, a sha256, an integer byte count)` | `[M&S 45]`, `§E.3.6` | RP-0513 `A.9` | Code Verification |
| `M013` | `ERROR` | 1.0+ | `every declared artifact exists and its sha256 matches the file on disk` | `[M&S 15, 45]`, `§E.3.3`, `§E.3.6` | RP-0513 `A.9`; RP-0671 `App. D.5` | Code Verification |
| `M014` | `ERROR` | 1.0+ | `provenance.dataset carries a well formed sha256` | `[M&S 10, 45]`, `§E.3.2` | RP-0513 `A.7`; RP-0510 | Data Pedigree |
| `M015` | `ERROR` | 1.0+ | `provenance.code carries repo and commit` | `[M&S 45]`, `§4.2.2g`, `§E.3.6` | RP-0513 `A.9` | Code Verification |
| `M016` | `WARN` | 1.0+ | `provenance.environment names the interpreter` | `[M&S 45, 47d]` | RP-0513 `Table 4-3 (1.6)`, `A.6` | Code Verification |
| `M017` | `WARN` | 1.1+ | `a declared provenance.signature is {format: oms, path} naming a file in the package that is not a pinned artifact (the checker verifies no signature)` | `§E.3.6` | RP-0513 `Table 4-3 (1.8)` | Provenance Integrity |
| `M018` | `ERROR` | 1.0+ | `the manifest conforms to the contract-v1 manifest schema (required keys, types, enumerations, patterns, bounds)` | `[M&S 13, 38, 46]`, `§E.3.6` | RP-0513 `§3.3.3.1`, `Table 4-3`, `A.26` | Code Verification |
| `M019` | `ERROR` | 1.1+ | `a type: field output declares its field block (kind, units, support, media_type) from contract 1.1, and a declared block is complete and sits on a field output` | `[M&S 46]`, `[M&S 12]` | RP-0513 `Table 4-3 (2.4, 2.5)`, `A.16` | QoI & Field Layout |
| `M020` | `ERROR` | 1.1+ | `a declared licence block names the model, the weights and the training data, each by an SPDX license expression with its text or URL, or by NOASSERTION with a note` | `HDBK §4.5.3` (IP/openness) | RP-0513 `Table 4-3 (1.5)` | Supply-Chain Provenance |
| `M021` | `WARN` | 1.1+ | `a package declaring contract 1.1 or later declares a licence block` | `HDBK §4.5.3` | RP-0513 `Table 4-3 (1.5)` | Supply-Chain Provenance |
| `M022` | `ERROR` | 1.2 | `a declared taxonomy_cell is an id the pinned cell vocabulary lists as live (well formed, listed, not retired)` | `[M&S 40, 12]`, `§E.4.2` | RP-0513 `§2.5 (Tables 2-1, 2-2)`, `A.20` | CoU & Applicability |
| `M023` | `ERROR` | 1.2 | `a declared taxonomy_registry comes with a taxonomy_cell and pins the cell vocabulary the checker carries: registry, version, sha256, document_sha256, bytes and cells, each well formed` | `§4.2.2g`, `§E.3.6` | RP-0513 `A.2`, `A.9` | Code Verification |
| `M024` | `WARN` | 1.2 | `a declared taxonomy_registry pins the content of the cell vocabulary the checker carries (sha256, document_sha256, bytes, cells); another version is warned, never failed` | `§4.2.2d`, `§E.3.6` | RP-0513 `A.9`, `A.21` | Applicability |
| `C001` | `ERROR` | 1.0+ | `model card parses with a flat scalar front-matter` | `[M&S 38]`, `§E.3.6` | RP-0513 `§2.9`, `A.1` | CoU Documentation |
| `C002` | `ERROR` | 1.0+ | `card front-matter identity matches the manifest` | `§4.2.2d`, `§E.3.6` | RP-0513 `Table 4-3 (1.2)`, `A.1`, `A.9` | Configuration Control |
| `C003` | `ERROR` | 1.0+ | `the eleven required card sections are present, first, in order` | `§4.1–§4.3`, `HDBK App. C` | RP-0513 `§2.9`, `Table 4-3`, `A.1` | CoU & V&V Dossier |
| `C004` | `ERROR` | 1.0+ | `no required card section is a stub` | `[M&S 38]`, `§E.3.6` | RP-0513 `§3.3.3.1`, `A.1` | CoU & V&V Dossier |
| `C005` | `ERROR` | 1.0+ | `the uncertainty section states a method and a number, or, under uncertainty.form none, that the model reports no uncertainty` | `[M&S 28, 29, 33, 34]`, `§E.4.4` | RP-0513 `Table 3-8`; RP-0671 `§3.2.2.3(5)` | Validation UQ |
| `C006` | `WARN` | 1.0+ | `extra H2 sections use reserved names` | `[M&S 9, 36, 44, 51]` | RP-0513 `A.1` | CoU Documentation |
| `V001` | `ERROR` | 1.0+ | `validation report parses and declares its identity` | `[M&S 15, 17, 38]` | RP-0513 `§3.3.3–§3.3.4`, `A.1` | Validation Record |
| `V002` | `ERROR` | 1.0+ | `validation report identity (model_id, model_version, spec_version) matches the manifest` | `§4.2.2d`, `§E.3.6` | RP-0513 `Table 4-3 (1.2, 1.8)`, `A.9` | Configuration Control |
| `V003` | `ERROR` | 1.0+ | `validation report dataset hash matches the manifest provenance` | `[M&S 10, 45]`, `§E.3.2` | RP-0513 `A.7`, `A.9` | Data Pedigree |
| `V004` | `ERROR` | 1.0+ | `every ladder key is present` | `[M&S 42, 43, 15, 17]` | RP-0513 `A.24`, `A.25`, `App. B` | V&V Completeness |
| `V005` | `ERROR` | 1.0+ | `every check declares a known status` | `[M&S 32a, 43]` | RP-0513 `§D.3`, `A.10` | Validation Reporting |
| `V006` | `ERROR` | 1.0+ | `a PASS carries a numeric measurement and a numeric threshold` | `[M&S 42, 43]` | RP-0513 `§3.3.3` (pre-defined bars), `Table D-2` | Agreed Accuracy Bars |
| `V007` | `ERROR` | 1.0+ | `NOT_APPLICABLE states a reason` | `§1.3`, `§4` (`App. A` rationale) | RP-0513 `§2.6.4` (omission argument) | Tailoring Rationale |
| `V008` | `ERROR` | 1.0+ | `the declared overall verdict matches the recomputed one` | `[M&S 32a, 43]` | RP-0513 `§3.3.3` (`Fig. 3-5` gate), `§D.8` | Credibility Rollup |
| `V009` | `ERROR` | 1.0+ | `B4 conservation is measured, not declared (a NOT_RUN check declares applicable: true and carries no measurement)` | `[M&S 15, 17]`, `§E.3.3–§E.3.4` | RP-0513 `Table 3-7` (conserved quantities) | Physics Conservation |
| `V010` | `ERROR` | 1.0+ | `A3 uq_calibration reports nominal, empirical coverage, n and method` | `[M&S 29, 33, 34]`, `§E.4.4` | RP-0513 `Table 3-8`; RP-0671 `App. F/H` | UQ Calibration |
| `V011` | `ERROR` | 1.0+ | `A5 reproducibility declares a determinism class and a tolerance (bitwise means tolerance 0, from contract 1.1)` | `[M&S 15]`, `§E.3.3` | RP-0513 `Table 2-1`, `Table 3-8` (seeds) | Numerical Reproducibility |
| `V012` | `ERROR` | 1.1+ | `comparators are well formed, and every PASS or FAIL check has one from contract 1.1` | `[M&S 43]` | RP-0513 `§D.8`; RP-0671 `§5.3.1.6` | Model Risk & Bars |
| `V013` | `ERROR` | 1.1+ | `each measured check's declared status agrees with the status its comparators give` | `[M&S 32a, 43]` | RP-0513 `§3.3.3`, `§D.8` | Comparator Verification |
| `S001` | `ERROR` | 1.0+ | `check --smoke: the entrypoint answers each example, and a batch of them where batch is supported, in the stdio_json frame: exit 0 within its timeout, a frame per row, every declared output and uncertainty key (and, from contract 1.1, status and run_id)` | `[M&S 15, 47]`, `§4.2.2e`, `§E.3.3` | RP-0513 `§4.3 (Table 4-2)`, `A.6`, `A.21` | Executable Verification |
| `S002` | `WARN` | 1.0+ | `check --smoke: the smoke test could run (examples declared, the entrypoint verified and launchable here)` | `§4.2.2e`, `[M&S 47]` | RP-0513 `Table 4-3 (1.5, 1.6)` | Executable Verification |
| `S003` | `ERROR` | 1.0+ | `check --smoke: every artifact reference an answer carries, and every declared field and *_artifact value, names a file in the run's working directory with its declared bytes, sha256 and media type` | `[M&S 15, 46]`, `§E.3.3`, `§E.4.7` | RP-0513 `Table 4-2 (5, 6)`, `Table 4-3 (2.4, 2.5)` | Payload Integrity |

---

## 8. Field, section, and ladder-key reference tables

### 8.1 `manifest.yaml` fields (`schemas/contract-v1/manifest.schema.json`)

| `manifest.yaml` field path | Enforced by | NASA-STD-7009B (`2024`) / HDBK-7009B (`2026`) | DNV-RP-0513 (`2021`) / RP-0671 (`2023`) |
|---|---|---|---|
| `spec_version` (`"1.0"`, `"1.1"`, `"1.2"`) | `M002`, `M018`, `C002`, `V002` | `§4.2.2d`, `§E.3.6` (CM & Product Mgmt) | RP-0513 `Table 4-3 (1.1, 1.2)`, `A.9` |
| `id` (`^[a-z][a-z0-9_]*$`) | `M003`, `M018`, `C002`, `V002` | `§4.2.2d` (Unique Identifier), `HDBK App. C.3(2)` | RP-0513 `Table 4-3 (1.2)` (Machine Identifier) |
| `name` | `M003`, `M018` | `HDBK App. C.3(2a)` (Official Model Name) | RP-0513 `Table 4-3 (1.2)` (Human-Readable Name) |
| `version` | `M003`, `M018`, `C002`, `V002` | `§4.2.2d`, `§4.3.2b,f`, `§E.3.6`, `§E.4.2` | RP-0513 `Table 4-3 (1.2, 3.3)`, `A.1`, `A.9` |
| `owner` (`team`, `contact`) | `M003`, `M018` | `§4` (Responsible Party), `[M&S 37]`, `HDBK App. C.3(12)` | RP-0513 `Table 4-3 (1.2)` (Maker), `§2.7`, `A.3` |
| `domain`, `analysis_type`, `tags[]` | `M003`, `M018` | `[M&S 40]`, `§4.1.3b(6)`, `§E.4.2 Table 14` | RP-0513 `§2.5 (Table 2-2)`, `Table 4-3 (1.4)` |
| `modality` (`scalar_in_scalar_out` .. `field_in_field_out`) | `M003`, `M018` | `[M&S 12]`, `HDBK §5.3.2c` | RP-0513 `Table 2-1` (Spatial), `Table 4-3 (2.2–2.5)` |
| `purpose`, `when_to_use`, `when_not_to_use` | `M003`, `M018` | `[M&S 40]` Intended Use, `[M&S 13]` Limits, `[M&S 14]` Permissible Use | RP-0513 `Table 4-3 (1.4, 1.7)`, `B.2.8`; RP-0671 `App. I.9` (`CONOPS`/`ODD`) |
| `taxonomy_cell` (`A.<d>.<n>/B<k>/<m>`, Contract 1.2) | `E004`, `M018`, `M022` | `[M&S 40, 12]`, `HDBK §4.5.2–§4.5.3` | RP-0513 `§2.5 (Tables 2-1, 2-2)`, `A.20` |
| `taxonomy_registry` (`registry`, `version`, `sha256`, `document_sha256`, `bytes`, `cells`, Contract 1.2) | `E004`, `M018`, `M023`, `M024` | `§4.2.2g`, `§E.3.6` (Controlled Vocabulary CM) | RP-0513 `A.2`, `A.9` |
| `inputs[].name`, `type`, `required`, `description`, `file_kind`, `choices` | `M004`, `M006`, `M018` | `[M&S 24]`, `§E.4.3`, `HDBK App. C.3(7d)` | RP-0513 `§4.2 (Table 4-1)`, `Table 4-3 (2.2, 2.3)` |
| `inputs[].units`, `canonical_units` | `M004`, `M018` | **`§4.2.1.3 [M&S 46]`** (Units & Coordinate Frames) | RP-0513 `Table 4-3 (2.2, 2.3)`, `A.16`, `§D.5(3)` |
| `inputs[].range` (`[min, max]`, `min < max`) | `M004`, `M018` | `[M&S 13, 16, 18, 26]`, `HDBK App. C.3(7d.ii)` | RP-0513 `Table 4-1 (3, 4)`, `B.1.3.2`, `B.2.8` |
| `outputs[].name`, `type`, `viewer`, `units`, `choices` | `M005`, `M006`, `M018` | `[M&S 40, 46]` | RP-0513 `Table 4-3 (2.4)`, `A.16` |
| `outputs[].field` (`kind`, `units`, `support`, `media_type`, `shape`, `coordinate_ref`, Contract 1.1+) | `M018`, `M019` | `[M&S 46]` (Units & Vector Coordinate Frames), `[M&S 12]` | RP-0513 `Table 4-3 (2.4, 2.5)` (Arrays & Units), `§D.5(3)` |
| `uncertainty` (`form`, `per_output`, `calibration`) | `M007`, `M018`, `C005` | `[M&S 21, 28, 29, 33, 34]`, `§E.4.4` | RP-0513 `Table 3-8` (Variance); RP-0671 `§3.2.2.3(5)`, `App. F/H` |
| `invocation` (`executable`, `protocol: "stdio_json"`, `timeout_s`, `expected_runtime_s`, `batch_supported`) | `M008`, `M018`, `S001` | `[M&S 47a,d]`, `[M&S 25]` | RP-0513 `§4.3`, `Table 4-3 (1.6, 3.5)`, `A.11` |
| `lineage` (`training_data_version`, `training_date`, `metrics`, `retrain_cadence`) | `M018` | `[M&S 47b]` (Obsolescence), `§4.3.2g` (Use History), `§E.4.2` | RP-0513 `A.1`, `A.21`; RP-0671 `§4.6` |
| `model_card` | `M009`, `M018` | `[M&S 38, 47]`, `HDBK App. C` | RP-0513 `§2.9`, `A.1` |
| `validation` (`report`, `overall`) | `M010`, `M018` | `[M&S 15, 17, 32a, 38]` | RP-0513 `§2.9`, `Table 4-3 (1.8)`, `A.1`, `A.24–A.25` |
| `provenance.artifacts[]` (`path`, `role`, `sha256`, `bytes`) | `M011`, `M012`, `M013`, `M018` | `[M&S 45]`, `§4.2.2g,h`, `§E.3.6` | RP-0513 `A.9`; RP-0671 `App. D.5` |
| `provenance.dataset` (`sha256`, `n_samples`, `generator_version`, `solver_version`) | `M011`, `M014`, `M018`, `V003` | `[M&S 10, 45]`, `§E.3.2`, `HDBK §4.5.1–§4.5.3` | RP-0513 `A.7`, `§D.5`; RP-0510 |
| `provenance.code` (`repo`, `commit`, `version`) | `M011`, `M015`, `M018` | `[M&S 45]`, `§4.2.2d,g`, `§E.3.6` | RP-0513 `A.9` |
| `provenance.environment` (`python`, `packages`) | `M016`, `M018` | `[M&S 45, 47d]` | RP-0513 `Table 4-3 (1.6)`, `A.6`, `A.9` |
| `provenance.signature` (`{format: "oms", path}`, Contract 1.1+) | `M017` | `§E.3.6` (Controlled Product Release) | RP-0513 `Table 4-3 (1.8)` |
| `licence` (`model`, `weights`, `training_data`, Contract 1.1+) | `M018`, `M020`, `M021` | `HDBK §4.5.3` (Open-Weights / Data Rights Note) | RP-0513 `Table 4-3 (1.5)` (License) |
| `examples[]` | `M018`, `S001`–`S003` | `§4.2.2e` (Benchmark I/O Test Cases in CM), `HDBK App. C.3(8a)` | RP-0513 `§4.3 (Table 4-2)`, `A.6`, `A.21` |

### 8.2 `model_card.md` H2 sections (11 required, 4 reserved optional)

| `model_card.md` section | Status | Enforced by | NASA-STD-7009B (`2024`) / HDBK-7009B (`2026`) | DNV-RP-0513 (`2021`) / RP-0671 (`2023`) |
|---|---|---|---|---|
| **YAML Front-Matter** (`model_id`, `version`, `spec_version`) | Required | `C001`, `C002` | `§4.2.2d`, `§E.3.6` | RP-0513 `Table 4-3 (1.2)`, `A.1`, `A.9` |
| `## TL;DR` | Required (#1) | `C003`, `C004` | `§4.3.8`, `HDBK §5.6.3.4` (High-Level Synopsis) | RP-0513 `Table 4-3 (1.4)` |
| `## Intended use` | Required (#2) | `C003`, `C004` | `[M&S 40]`, `[M&S 14]`, `HDBK App. C.3(3a,b) & App. F` | RP-0513 `§3.3.2(2)`, `Table 4-3 (1.4)`; RP-0671 `App. I.9` |
| `## Out of scope` | Required (#3) | `C003`, `C004` | `[M&S 11, 13, 32b,c]`, `HDBK App. C.3(3c)` | RP-0513 `§3.3.2(1, 3)`, `Table 4-3 (1.7)`, `B.2.8` |
| `## Training data` | Required (#4) | `C003`, `C004` | `[M&S 10, 45]`, `§E.3.2`, `HDBK §4.5.1 & §4.5.3` | RP-0513 `A.7`, `§D.5`; RP-0510 |
| `## Architecture` | Required (#5) | `C003`, `C004` | `[M&S 11, 12]`, `HDBK §4.5.3` & `App. C.3(4–5)` | RP-0513 `§3.3.2(4, 5)` |
| `## Training configuration` | Required (#6) | `C003`, `C004` | `[M&S 45, 47c]`, `§4.3.2c` | RP-0513 `§3.3.4` (Calibration), `A.9` |
| `## Performance` | Required (#7) | `C003`, `C004` | `[M&S 17, 18, 42]`, `§E.3.4` | RP-0513 `§3.3.4`, `A.25`; RP-0671 `§3.2.2.3(1)` |
| `## Uncertainty quantification` | Required (#8) | `C003`, `C004`, `C005` | `[M&S 19, 21, 28, 29, 33, 34]`, `§E.4.4` | RP-0513 `Table 3-8`; RP-0671 `§3.2.2.3(5)`, `App. F/H` |
| `## Known failure modes` | Required (#9) | `C003`, `C004` | `[M&S 27, 32, 51]`, `§4.2.2c`, `§4.3.2h`, `§E.4.5` | RP-0513 `Table 3-7` (unstable regions), `A.19` |
| `## Provenance` | Required (#10) | `C003`, `C004` | `[M&S 10, 45]`, `§E.3.2`, `§E.3.6`, `HDBK §4.5.1` | RP-0513 `A.1`, `A.9` |
| `## Version history` | Required (#11) | `C003`, `C004` | `§4.2.2d`, `§4.3.2f,g`, `§E.4.2`, `HDBK App. C.3(1b, 9b.iv)` | RP-0513 `A.1` (Model Version Log), `A.9` |
| `## Alternatives considered` | Optional (Reserved) | `C006` | `HDBK §5.1.1.4 (Table 5)` & `§5.2.1.2` | RP-0513 `B.1.7.2`, `B.2.9` |
| `## Disclosure` | Optional (Reserved) | `C006` | `[M&S 9, 36, 37]`, `§4.3.9d,e` | RP-0513 `§2.7`, `A.3`; RP-0671 `§3.2.2.3(8)` |
| `## Open questions` | Optional (Reserved) | `C006` | `[M&S 32, 39, 49, 51]`, `§4.2.4d`, `§4.2.6d` | RP-0513 `A.12` (Risk Log); RP-0671 `§5.4.1.2` |
| `## References` | Optional (Reserved) | `C006` | `§4.1.3a`, `Appendix C`, `HDBK App. C.3(1e)` | RP-0513 `§1.5`, `§4.5`; RP-0671 `§6` |

### 8.3 `validation_report.json` fifteen-key ladder (`V001`–`V013`)

| Ladder key (`opencontractml.verify`) | Legacy aliases (`verify.LEGACY_ALIASES`) | Tier | What the check grades | NASA-STD-7009B (`2024`) | DNV-RP-0513 (`2021`) / RP-0671 (`2023`) |
|---|---|---|---|---|---|
| `A1_accuracy` | `V1.1`, `FG1` | Tier A (Statistical) | Held-out test accuracy (relative $L_2$, MAE, RMSE) against the referent | `[M&S 17, 42, 43]`, `§E.3.4` | RP-0513 `§3.3.4`, `B.2.1`, `Table D-2`; RP-0671 `§3.2.2.3(1)` |
| `A2_extrapolation` | `V1.2`, `FG2` | Tier A (Statistical) | Held-out boundary, corner, or tail regime degradation | `[M&S 13, 18, 30]`, `§E.4.5` | RP-0513 `B.1.3.2` (Boundary value), `B.2.3`, `§D.4`; RP-0671 `§3.2.2.3(2)` |
| `A3_uq_calibration` | `V1.3`, `FG3` | Tier A (Statistical) | Empirical interval coverage vs. nominal (`nominal`, `empirical`, `n`, `method` required by `V010`) | `[M&S 29, 33, 34]`, `§E.4.4` | RP-0513 `Table 3-8` (Variance); RP-0671 `§3.2.2.3(5)`, `App. F/H` |
| `A4_baseline_beat` | `V1.4`, `FG4` | Tier A (Statistical) | Superiority over simple baseline estimators | `[M&S 17, 43]`, `HDBK §5.2.1.2` | RP-0513 `B.1.7.2` (Simplified model), `B.2.9` |
| `A5_reproducibility` | `V1.5`, `FG5` | Tier A (Statistical) | Determinism class (`bitwise` requires tolerance `0`) and seed stability (`V011`) | `[M&S 15]`, `§E.3.3` | RP-0513 `Table 2-1`, `Table 3-8` (Repeatable random sequences) |
| `B1_monotonicity` | `V2.1` | Tier B (Physics) | Preservation of known physical monotonicity trends | `[M&S 30]`, `§E.3.4`, `§E.4.5` | RP-0513 `B.1.5` (Essential parameters), `B.1.6`, `B.2.4` |
| `B2_bounds` | `V2.2` | Tier B (Physics) | Satisfaction of hard physical bounds (positivity, absolute temperature, mass fractions) | `[M&S 13, 15, 17]` | RP-0513 `B.1.3.2`, `B.2.4` (Physical principles) |
| `B3_residual` | `FG6` | Tier B (Physics) | Interior governing PDE or operator residual magnitude | `[M&S 12, 15]`, `§4.2.4b`, `§E.3.3` | RP-0513 `§3.4.2`, `B.1.2`, `B.2.4` |
| `B4_conservation` | `V2.3`, `FG7` (grid/mesh) | Tier B (Physics) | Measured global conservation imbalance (`relative_imbalance`, enforced by `V009`) | `[M&S 12, 15, 17]`, `§E.3.3–§E.3.4` | RP-0513 `Table 3-7` (Conserved quantities), `B.2.4` |
| `B5_invariance` | `V2.4`, `FG10` | Tier B (Physics) | Frame/galilean/permutation and discretization (remesh/resample/regrid) invariance | `[M&S 15, 30, 46]`, `§E.3.3`, `§E.4.5` | RP-0513 **`Table B-1 (B.1.1 Symmetry)`** & `B.1.2` |
| `B6_integrated_quantities` | `FG11` | Tier B (Physics) | Surface- or volume-integrated engineering quantities of interest ($C_D, C_L$, net flux) | `[M&S 17, 40, 42, 43]`, `§E.3.4` | RP-0513 `§3.3.2(10)`, `B.2.1`, `§D.8` |
| `C1_ood_guard` | `FG8` | Tier C (Deployment) | Runtime out-of-distribution detector separation between in-envelope and corrupted inputs | `[M&S 13, 26, 32c]`, `§4.1.3b(10)` | RP-0513 `Table 4-1 (4)`, `A.19`, `B.2.8`; RP-0671 `§3.2.2.3(2)` |
| `C2_serve_parity` | `FG9` | Tier C (Deployment) | Numerical agreement between training evaluation and packaged `stdio_json` entrypoint | `[M&S 15]`, `§E.3.3` (Deployment platform parity) | RP-0513 `A.6`, `A.21`; RP-0671 `App. G.2.2` |
| `C3_provenance_integrity` | — | Tier C (Deployment) | End-to-end digest verification across weights, dataset, and code | `[M&S 45]`, `§E.3.6` | RP-0513 `A.9`; RP-0671 `App. D.5` |
| `C4_deployment_readiness` | `V3` | Tier C (Deployment) | Single-call and batch inference latency, memory footprint, and dispatch readiness | `[M&S 47a,d]`, `§E.4.7` | RP-0513 `A.11` (System model performance), `Table 4-3 (1.6, 3.5)` |

---

## 9. Known gaps between Contract 1.2 and the standards (candidates for future revisions)

Consistent with [STANDARDS-ALIGNMENT.md](../STANDARDS-ALIGNMENT.md), the nine
rows below record where NASA-STD-7009B, DNV-RP-0513 / DNV-RP-0671, Bureau
Veritas NI 692 R00, MIL-STD-3022, or the ASME VVUQ framework call for structured
information or operational processes that Contract 1.2 either leaves to prose in
`model_card.md` or deliberately stops short of claiming:

| # | Standard requirement | What Contract 1.2 does today | Candidate extension or permanent scope boundary |
|---|---|---|---|
| 1 | **NASA-STD-7009B `§4.1.1.2 [M&S 6]` & Appendix D; DNV-RP-0513 `§2.6` (`CL0`–`CL4`); ASME V&V 40** — structured criticality / model-risk classification | Leaves criticality and risk grading to `model_card.md` `## Intended use` and `## Out of scope`. | Optional `risk_profile: {model_influence, decision_consequence, criticality_tier}` block in `manifest.yaml`. |
| 2 | **NASA-STD-7009B `§4.2.5` & `§4.2.7 [M&S 19]`; HDBK-7009B `App. B`; MIL-STD-3022 `App. C`; ASME V&V 20** — distinguishing a numerical solver referent ($u_{\text{num}}$) from a physical experiment ($D \pm u_D$) | `provenance.dataset` records `solver_version` and `generator_version`, without typing the referent kind or experimental uncertainty $u_D$. | Optional `provenance.referent` block typing `"numerical_solver" | "physical_experiment" | "hybrid"` and referent uncertainty metadata; physical experimentation itself remains outside software scope. |
| 3 | **NASA-STD-7009B `§4.2.1.8 [M&S 48]`, `§4.3.6.1 [M&S 31]` & Appendix E (Tables 5–20)** — achieved vs. threshold `0`–`4` scores across the 5 Capability and 6 Results factors | Supplies the underlying evidence for all 11 factors; carries no structured `0`–`4` factor score vector. | Optional `credibility_assessment` block in `validation_report.json` recording `{achieved, threshold, rationale}` across the 5 Capability and 6 Results factors. |
| 4 | **DNV-RP-0671 `§4.6.2.4` & `App. G.3.1`; BV NI 692 `Sec. 2 Art. 7.1 (Tables 16–17)`** — continuous post-deployment runtime monitoring, data drift, and concept drift logs | `C1_ood_guard` tests static OOD separation and `lineage.retrain_cadence` is free text; static package verification inspects no live telemetry stream. | Optional structured `recalibration_triggers` block plus a separate offline telemetry-log drift checker. |
| 5 | **OpenSSF Model Signing (`oms`) & DNV-RP-0513 `Table 4-3 (1.8)`** — cryptographic verification of detached authorship signatures | `M017` validates the declaration shape `provenance.signature: {format: "oms", path}` and verifies no signature ([PROVENANCE-SIGNING.md](../spec/PROVENANCE-SIGNING.md)). | Optional signature verification once a zero-mandatory-dependency verification path is ratified in a future version. |
| 6 | **NASA-STD-7009B `[M&S 10]` & `§E.3.2`; DNV-RP-0513 `A.7`; BV NI 692 `Sec. 2 Art. 4`** — binding the manifest to a machine-verified dataset gate report | `M014` and `V003` verify `provenance.dataset.sha256`, without pinning the digest of a `corpus_gate` (`G1.1`–`G1.7`) report. | Optional `provenance.dataset.corpus_gate_report_sha256` field and standalone corpus-check CLI entrypoint. |
| 7 | **NASA-STD-7009B `[M&S 9, 36, 37]`, `§E.3.5` & `§E.4.6`; DNV-RP-0513 `§2.7` & `A.3`; MIL-STD-3022 `§3.1.3` & `§3.1.18`** — independent peer review, V&V Agent separation, and Accreditation Authority sign-off | `manifest.yaml` records `owner`, and any third party can re-run `open-contract-ml check --smoke` offline. | Organizational independence, practitioner qualification audits, and statutory/class-society approval remain human governance acts outside a static checker. |
| 8 | **NASA-STD-7009B `§4.2.4b` & `§E.3.3`; DNV-RP-0513 `Table 3-7` & `B.1.2`; ASME V&V 20** — upstream PDE solver mesh/time-step discretization error ($u_{\text{num}}$) and multi-baseline benchmarking | `V012`–`V013` require `>= 1` satisfied comparator on `A4_baseline_beat` and do not require upstream solver mesh-convergence (`GCI`) metadata. | Optional upstream discretization-verification metadata on `provenance.dataset` and a multi-baseline comparator check on `A4_baseline_beat`. |
| 9 | **NASA-HDBK-7009B `§4.5.2`; DNV-RP-0513 `§2.4` & `Table 4-3 (3.1–3.4)`; DNV-RP-0671 `§4.4.2` & `App. E`; MIL-STD-3022 `§3.1.7`; ASME V&V 10** — multi-model coupling DAGs and modular assurance contracts | Each Contract 1.2 directory packages a single model; cross-link unit/range compatibility and uncertainty propagation across chained models are not yet expressed in `manifest.yaml`. | Optional `coupled_system` / modular assurance-contract manifest checking upstream output ranges and units against downstream input contracts. |
