# Worked Instance — Brake-Disc TMF Chain
## Link 3 — Fatigue Post-Process · Bucket B1 (Tabular, GBM + GP)
### Model Card v0.1

> This model card covers what the link-3 model *is* — GBM ensemble + GP
> companion, hyperparameters, training configuration, full loss
> specification, UQ decomposition, and alternatives considered. What the
> model produces and consumes is fixed by the link's data contract, a
> companion sheet that is not published here; the fixture package
> `tests/fixtures/producer_packages/brake_disc_link3_fatigue_gbm_gp/` carries
> the part of that signature Contract v1.0 can express.
>
> **Two-model setup.** This card describes both the GBM (primary
> regression head) and the GP (calibrated-UQ companion) as a single
> two-model B1 surrogate, not as two separate models. Both share inputs,
> outputs, training data, and provenance — they differ in inductive bias
> and UQ semantics.
>
> **Disclosure.** Specific hyperparameter values and kernel choices below
> are *illustrative configurations*; the GBM + GP family choice is
> anchored to an unpublished analysis-to-bucket mapping.

---

## 1. Identity

| Field | Value |
|---|---|
| Chain link | 3 of 3 (terminal) |
| CAE analysis | Fatigue: stress-life and strain-life |
| Architecture bucket | B1 — Tabular surrogate over integral / scalar outputs |
| Architecture family | Two-model B1: GBM (primary) + GP (UQ companion) |
| Reference papers | Chen & Guestrin 2016, *XGBoost: A Scalable Tree Boosting System* (KDD); Ke et al. 2017, *LightGBM* (NeurIPS); Rasmussen & Williams 2006, *Gaussian Processes for Machine Learning* (textbook); [Miner1945] cumulative-damage rule |
| Survey-level anchor | [Miner1945] — log-life target framing and Miner-scatter motivation |
| Data contract | companion sheet, not published here; fixture: `tests/fixtures/producer_packages/brake_disc_link3_fatigue_gbm_gp/` |
| Methodology anchors (physics) | [Stephens2001] (Marin factors, mean-stress correction families, multiaxial criteria); [Suresh1998] (mechanism framing); [Paris1963] (crack-growth boundary) |

---

## 2. Architecture topology

### 2.1 Two-model setup

```
Input feature vector x ∈ ℝ^F (F=12 per hot-spot; mixed continuous + categorical)
   │
   ├──── GBM ENSEMBLE (PRIMARY) ────────────────────────────────────────────
   │     N_ens = 5 LightGBM models, independent seeds
   │     Each: gradient-boosted tree ensemble, log-MAE objective in log10(N_f)
   │     Native categorical handling per LightGBM
   │     Output: log10_N_f_gbm_mean (ensemble mean), log10_N_f_gbm_sigma (std)
   │
   ├──── GP COMPANION (UQ) ─────────────────────────────────────────────────
   │     Single GP with separable kernel:
   │       k(x, x') = k_continuous(x_cont, x_cont') · k_categorical(x_cat, x_cat')
   │     Continuous kernel: Matérn 5/2 RBF with ARD length-scales
   │     Categorical kernel: per-categorical-axis independent block
   │     Mean function: linear in continuous features (z-score-normalized)
   │     Noise: learned, with Miner-scatter floor σ²_floor (see §6)
   │     Output: log10_N_f_gp_mean (posterior mean),
   │             log10_N_f_gp_sigma (posterior std combining epistemic + aleatoric)
   │
Output assembly:
   log10_N_f_min        = min over hot-spots of log10_N_f_gbm_mean
   p5_log10_N_f         = log10_N_f_gp_mean − 1.645 · log10_N_f_gp_sigma
   epistemic_sigma_log10 = max(log10_N_f_gbm_sigma, log10_N_f_gp_sigma − σ_aleatoric)
   aleatoric_sigma_log10 = σ_aleatoric (from GP noise variance, floored at σ²_floor)
```

### 2.2 Why two models, not one

| Concern | GBM alone is insufficient | GP alone is insufficient | Pair resolves |
|---|---|---|---|
| Epistemic UQ from training-data coverage | Weak — GBM ensembles are not principled UQ | Reasonable but expensive | GBM ensemble for fast point + epistemic; GP for principled posterior |
| Aleatoric UQ (Miner-scatter floor) | None — GBM has no noise model | Native — GP noise variance learned | GP carries the irreducible scatter |
| Production-deployment maturity | Strongest in deployment | Less common at OEM scale | GBM is the design-iteration deliverable; GP is the certification companion |
| Inference latency | Sub-ms on CPU | ~ms on CPU; O(n) prediction at posterior | GBM for fast inner loops; GP only at certification scans |
| Calibration on long-tail life | Poor | Good (separates epistemic / aleatoric) | GP for RBDO 5th-percentile life |

This pair structure follows an unpublished analysis-to-bucket mapping (GBM as production-default, GP as the calibrated-UQ companion; both are members of B1).

---

## 3. Hyperparameters (illustrative defaults)

### 3.1 GBM (LightGBM, per ensemble member)

| Hyperparameter | Value | Notes |
|---|---|---|
| Objective | regression with custom log-MAE in log10(N_f) | Robust to outliers; matches Miner-scatter motivation |
| Number of leaves | 63 | Standard for ~10³–10⁴ row corpora |
| Max depth | -1 (leaves-driven) | LightGBM default |
| Min data in leaf | 20 | Higher than default; corpus is small |
| Feature fraction | 0.8 | Per-iteration feature subsample |
| Bagging fraction | 0.8 | Per-iteration row subsample |
| Bagging frequency | 5 | Resample every 5 iterations |
| Number of estimators | up to 2000 with early stopping | Stop at 100-iter no-improvement on validation |
| Learning rate | 0.03 | Slow; corpus is small, want over-fit defense |
| L1 / L2 leaf regularization | 0.1 / 0.1 | Mild |
| Categorical features | declared natively (`categorical_feature` arg) | LightGBM optimal-split for categoricals; no one-hot needed |
| Ensemble count N_ens | 5 | Independent seeds; mean ensemble for point, std for epistemic UQ |
| Inference latency | < 1 ms per query on CPU | Sub-ms typical |

### 3.2 GP (companion)

| Hyperparameter | Value | Notes |
|---|---|---|
| Kernel — continuous | Matérn 5/2 with ARD length-scales | One length-scale per continuous feature; learned by marginal likelihood |
| Kernel — categorical | Per-axis independent diagonal blocks | Each categorical class gets its own variance |
| Kernel composition | k(x,x') = k_cont · k_cat (separable) | |
| Mean function | linear in continuous features | Stabilizes posterior away from training data |
| Noise model | iid Gaussian, learned variance σ²_noise | |
| Noise floor σ²_floor | (log10(2.0) − log10(0.6))²/4 ≈ 0.072 (so σ_floor ≈ 0.27) | Anchored to the [Miner1945] Miner-scatter range |
| Optimizer (kernel hyperparam) | L-BFGS-B with multiple restarts | Standard for GP marginal-likelihood |
| Inducing points | None (exact GP up to ~3000 rows; switch to sparse-GP / SVGP if corpus grows) | |
| Inference latency | ~10 ms per query (full posterior) on CPU | Linear in corpus size for prediction |

---

## 4. Training configuration (illustrative)

### 4.1 GBM ensemble

| Element | Value |
|---|---|
| Training corpus | 806 rows (per the link's dataset card splits; the dataset card is not published here) |
| Validation corpus | 173 rows for early-stopping criterion |
| Per-row weighting | Up-weight rare categorical classes by inverse-class-frequency |
| Per-ensemble-member seed | 5 distinct seeds (e.g. 17, 42, 137, 1729, 31337) |
| Total compute | < 10 minutes on a single CPU node, all 5 ensembles together (GBM trains on CPU in minutes for typical 10³ – 10⁴ row corpora) |
| Hardware | Single-CPU-node sufficient |

### 4.2 GP companion

| Element | Value |
|---|---|
| Training corpus | Same 806 rows |
| Kernel hyperparameter optimization | L-BFGS-B with 10 random restarts; pick max marginal-likelihood |
| Noise floor enforcement | Constrained optimization: σ²_noise ≥ σ²_floor |
| Cross-validation for kernel structure | 5-fold CV to pick between separable-kernel variants (Matérn 5/2 vs RBF vs Matérn 3/2 on continuous side) |
| Total compute | < 30 minutes on single CPU; bottleneck is the marginal-likelihood evaluations during multi-restart optimization |
| Hardware | Single-CPU-node sufficient |

---

## 5. Loss specification (consolidated)

### 5.1 GBM (per ensemble member)

```
L_gbm = Σ_i  w_i · |log10(N_f_pred_i) − log10(N_f_true_i)|

where
  w_i = inverse-frequency weight for the row's rarest categorical class

Robustness:
  Custom log-MAE objective (not log-MSE) — robust to long-tail outliers
  in the high-life regime (log10_N_f ∈ [7, 8]) where data is scarce.
```

### 5.2 GP (companion)

```
L_gp = − log p(y | X, θ)
     = − [ −1/2 (y − m)ᵀ K⁻¹ (y − m) − 1/2 log |K| − N/2 log(2π) ]

where
  K = K(X, X; θ) + σ²_noise · I,    σ²_noise ≥ σ²_floor (Miner-scatter floor)
  m = mean function evaluation at X (linear in continuous features)
  θ = (length-scales, per-categorical-block variances, σ²_noise, mean coefficients)

Constrained optimization: σ²_noise floor anchored to (log10(2.0) − log10(0.6))²/4
                          per the [Miner1945] Miner-scatter range.
```

### 5.3 Combined-output assembly (deterministic, no learnable parameters)

```
log10_N_f_min = min over hot-spots of log10_N_f_gbm_mean
              # engineering deliverable for design-iteration

p5_log10_N_f_min = log10_N_f_gp_mean[hotspot_min] − 1.645 · log10_N_f_gp_sigma[hotspot_min]
              # RBDO / certification deliverable

epistemic_sigma_log10 = sqrt( max(log10_N_f_gbm_sigma², log10_N_f_gp_sigma² − σ²_aleatoric_learned) )
              # training-coverage uncertainty, conservative max across two sources

aleatoric_sigma_log10 = sqrt( max(σ²_aleatoric_learned, σ²_floor) )
              # Miner-scatter, with floor protection
```

The chain-composite `L_endpoint` term — special-case treatment because GBM does not gradient-fine-tune cleanly — is addressed in the chain-level contract (not published here). Likely treatment: freeze link-3 weights during chain-level joint fine-tune; back-propagate `L_endpoint` only through links 1 and 2.

---

## 6. UQ approach

| Element | Value |
|---|---|
| Method | Two-source: GBM deep ensemble for epistemic; GP for combined epistemic + aleatoric |
| Per-hot-spot output | (log10_N_f_gbm_mean, log10_N_f_gbm_sigma, log10_N_f_gp_mean, log10_N_f_gp_sigma, p5_log10_N_f) |
| Decomposition | aleatoric_sigma_log10 (Miner-scatter floor) + epistemic_sigma_log10 (training coverage) — exposed separately in the output dataclass per the data contract |
| Aleatoric floor | σ²_floor = (log10(2.0) − log10(0.6))²/4 ≈ 0.072² per the [Miner1945] Miner-scatter range |
| Calibration check | Hold-out coverage at 95 % prediction interval should be ≥ 95 % AND ≤ 99 %. Over-coverage means UQ is too conservative |
| Long-life extrapolation | log10_N_f_gp_mean > 7 raises explicit `long_life_extrapolation_flag` per the data contract — coupon endurance limit data only, no component-level test cycles |
| Cross-source consistency check | If log10_N_f_gbm_mean and log10_N_f_gp_mean differ by > 0.5 log-decades, raise an internal warning (one of the two is mis-calibrated for this row) |

---

## 7. Alternatives considered

| Alternative | Rejected because |
|---|---|
| GBM only (no GP) | Lacks calibrated UQ; Miner-scatter aleatoric floor cannot be modeled; RBDO 5th-pctile life unavailable. *Demonstrated-only-deliverable* alternative for design-iteration but insufficient for certification |
| GP only (no GBM) | GP scales O(n³) for kernel hyperparameter optimization — fine at 10³ rows but uncomfortable at 10⁴. GBM is faster at inference and dominant in deployment; using GBM as the production point estimate matches industrial practice |
| MLP regressor | Less inductive-bias-fit for tabular data than GBM — GBM/GP/MLP are alternative B1 family members, but GBM is the production default for this analysis |
| Conformal prediction wrapper around GBM | Provides distribution-free coverage guarantees but does not decompose into epistemic / aleatoric. Useful as a *calibration check* on the GP posterior; out of scope for the primary architecture |
| Bayesian-NN | Heavyweight for tabular data with this corpus size; does not match production-deployment pattern |
| Pure rainflow + Miner post-processor (no ML) | The thing we replace; not an ML alternative. Remains the *ground-truth* via the dataset card's solver provenance |

---

## 8. Disclosure

| Element | Status | Anchor |
|---|---|---|
| GBM family choice | **Anchored** | An unpublished analysis-to-bucket mapping and its deployment evidence |
| GP companion for calibrated UQ | **Anchored** | An unpublished bucket roster (calibrated-UQ certification tier) |
| log10(N_f) target | **Anchored** | [Miner1945] |
| Marin factor product feature | **Anchored** | [Stephens2001] |
| Aleatoric noise floor formula | **Anchored** | [Miner1945] Miner-scatter range |
| Mean-stress correction enumeration | **Anchored** | [Stephens2001] |
| GBM hyperparameters (num_leaves, lr, regularization) | **Illustrative** | Standard LightGBM defaults |
| GP kernel choice (Matérn 5/2 ARD + per-categorical-axis blocks) | **Illustrative (informed)** | Standard engineering-surrogate default per Rasmussen2006 |
| Categorical class-balance minimums (≥ 30 rows) | **Illustrative** | Engineering rule of thumb |
| Compute / latency estimates | **Illustrative** | Order-of-magnitude framing range |
| **Deployment maturity (this link)** | **DEMONSTRATED** | Unpublished industry-context and deployment-evidence notes |

---

## 9. Open questions

None at v0.1. The data contract flags five format questions (two-model architecture granularity, aleatoric component disclosure, categorical-heavy schema, terminal-link asymmetry, deployment-maturity disclosure rows). This model card surfaces no new format questions: the link-1 and link-2 model card structure (identity → topology → hyperparameters → training → loss → UQ → alternatives → disclosure) extrapolates to two-model B1 cleanly.

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../docs/REFERENCES.md).*
