# Worked Instance — Brake-Disc TMF Chain (A.8.1)
## Link 1 — A.3.2 Transient Thermal · Bucket B4 (FNO)
### Model Card v0.1

> Companion artifact to `WORKED-INSTANCE-A81-link1-thermal-contract.md`.
> The contract sheet covers what the model produces and consumes; this
> model card covers what the model *is* — topology, hyperparameters,
> training configuration, loss specification, UQ approach, and
> alternatives considered.
>
> **Disclosure** inherits from the contract sheet §8 in full. Specific
> hyperparameter values, network depth, channel widths, and λ-weight
> defaults below are *illustrative configurations*; the FNO family choice
> and the operator-learning framing are *anchored* to Q-ml-op-01
> [Kovachki2023]. The architecture topology is *contractual* in the sense
> that any re-tune of these defaults bumps `model_version` and triggers
> chain re-validation per the contract sheet's §3.3 metadata schema.

---

## 1. Identity

| Field | Value |
|---|---|
| Chain link | 1 of 3 |
| CAE analysis | A.3.2 — FEA Thermal: Transient (`tasks/TASK-1-cae-analysis-catalog.md` §6) |
| Architecture bucket | B4 — Operator / parameter-to-function surrogate (`tasks/TASK-4-architecture-buckets.md` §3) |
| Architecture family | FNO (Fourier Neural Operator) (`tasks/TASK-2-ml-model-catalog.md` §5) |
| Reference paper | Li et al. 2021, *Fourier Neural Operator for Parametric PDEs* (arXiv:2010.08895) |
| Survey anchor | Q-ml-op-01 [Kovachki2023] — operator-learning framing, verified-true |
| Contract sheet | `WORKED-INSTANCE-A81-link1-thermal-contract.md` |
| Methodology anchors (physics) | [Bergman2017] (Fourier conduction; Bi/Fo); [Patankar1980] (FV discretization for CHT) |

---

## 2. Architecture topology

### 2.1 Network diagram

```
Input tensor X: [B, T=200, N_x=64, N_y=64, N_z=24, F_in=10]
                where B = batch size, F_in channels enumerated in §2.2
   │
   ├── Lifting layer: 1×1×1×1 conv, F_in=10 → F_h=32
   │
   ├── Fourier blocks × N_blocks=4
   │     each block:
   │       ├── Spectral conv (4-D FFT, modes (m_t, m_x, m_y, m_z) = (16,12,12,6))
   │       ├── Linear bypass (1×1×1×1 conv, F_h → F_h)
   │       └── Residual sum + GELU activation
   │
   ├── Projection MLP: F_h=32 → 128 → F_out=1
   │
Output tensor Y: [B, T=200, N_x=64, N_y=64, N_z=24, 1]   (T_norm)
```

Discretization invariance — the spectral-conv layers are FFT-based, so the model accepts grid resolutions different from training. This is the core property the deck slide 8 names as load-bearing for the family choice.

### 2.2 Input-channel enumeration (F_in = 10)

| Channel index | Content | Static / time-varying | Source (contract sheet §3.1) |
|---|---|---|---|
| 0 | Occupancy mask | static | `geometry_grid` channel 3 |
| 1 | Thermal conductivity k (normalized) | static | `material_field` channel 0 |
| 2 | Specific heat cp (normalized) | static | `material_field` channel 1 |
| 3 | Density ρ (normalized) | static | `material_field` channel 2 |
| 4 | Emissivity ε (normalized) | static | `material_field` channel 3 |
| 5 | D_outer (normalized, broadcast) | static | `disc_design` channel 0 |
| 6 | D_inner (normalized, broadcast) | static | `disc_design` channel 1 |
| 7 | Brake torque τ(t) (normalized) | time-varying | `descent_profile` channel 1 |
| 8 | Ambient T(t) (normalized) | time-varying | `descent_profile` channel 2 |
| 9 | Time t/T_total | time-varying | derived from `descent_profile` channel 0 |

Static channels broadcast across the time axis; time-varying channels broadcast spatially. This collation step is the bridge between the contract sheet's storage-native row tensors (§3.1) and the FNO's input tensor.

---

## 3. Hyperparameters (illustrative defaults)

| Hyperparameter | Value | Notes |
|---|---|---|
| Hidden channels F_h | 32 | Per-block; scale to 64 if validation L² plateaus above target |
| Fourier blocks N_blocks | 4 | FNO-canonical default per Li2021 |
| Spectral modes (m_t, m_x, m_y, m_z) | (16, 12, 12, 6) | z-mode count smaller — disc thickness has fewer spatial frequencies |
| Activation | GELU | Smooth; FNO-preferred over ReLU per Li2021 |
| Normalization | Per-channel z-score on input; no batch/layer norm inside Fourier blocks (FNO-canonical) | |
| Parameter count | ~2.5 M | Small relative to typical CV networks; FNO is parameter-efficient |
| Float precision | FP32 throughout | Mixed-precision training is a future optimization |

---

## 4. Training configuration (illustrative)

| Element | Value |
|---|---|
| Optimizer | AdamW, lr=1e-3, weight_decay=1e-4 |
| LR schedule | Cosine decay over total epochs, 5% warmup |
| Batch size | 8 design-points / batch (memory-bound on a single 24 GB GPU) |
| Epochs | 200 with early stopping on validation L² plateau |
| Deep-ensemble count | N=5 — five independent models, different seeds, for UQ (§6) |
| Compute (per ensemble member) | ~10²–10³ GPU-h (deck slide 13); ensemble cost = 5× single-model |
| Hardware (training) | NVIDIA A100 / H100 single-GPU sufficient at this network scale |
| Inference latency | ~10 ms per query on A100; ~200 ms CPU (deck slide 13) |

---

## 5. Loss specification (consolidated)

```
L_link1 = L_data + λ_int R_int + λ_conv R_conv + λ_bc L_bc

where
  L_data  = ||T_pred − T_true||²  in spectral L² (Parseval-equivalent to MSE on T_norm)
  R_int   = ||ρ cp ∂T/∂t − ∇·(k ∇T) − q̇||²  at sampled interior collocation points
  R_conv  = ||−k ∂T/∂n − h(T − T_∞)||²       at exterior surface points
                                              (h from Bergman2017 correlation tier)
  L_bc    = Dirichlet-BC enforcement at ambient interfaces

Default (pure-data FNO):           λ_int = λ_conv = λ_bc = 0
Ablation (physics-informed FNO):   λ_int = 0.1, λ_conv = 0.1, λ_bc = 1.0
```

The physics-residual terms are an *optional ablation lever*, not the default training. Pure-data FNO is the §3 / §4 default per the operator-learning framing of Q-ml-op-01 [Kovachki2023]. Q-ml-pinn-02 [Karniadakis2021] framing applies when the ablation is run.

The chain-composite `L_endpoint` term is added during chain-level fine-tuning; specified in the chain-level contract sheet.

---

## 6. UQ approach

| Element | Value |
|---|---|
| Method | Deep ensembles, N=5 independently-trained models, different seeds |
| Per-cell uncertainty | `epistemic_sigma_K[t, x, y, z]` = ensemble standard deviation of T_norm, denormalized to K |
| Aleatoric component | Not modelled at link 1 (heat equation is deterministic given inputs); aleatoric inherited from upstream input distribution |
| Output to chain | `epistemic_sigma_K` full tensor `[T, N_x, N_y, N_z]` per contract sheet §4.2 |
| Calibration check | Hold-out coverage: 95 %-prediction-interval should contain ground-truth ≥ 95 % of voxel-time samples; reported in dataset card |

---

## 7. Alternatives considered

| Alternative | Rejected because |
|---|---|
| DeepONet (also B4) | Branch–trunk separation natural when input is a function and queries are scattered; for our regular-grid output FNO is more natural and faster at inference |
| 3-D U-Net (B2 family) | Discretization-bound — locks training and inference to a fixed grid; loses the discretization-invariance property the deck slide 8 names as load-bearing |
| MeshGraphNet (B3 family) | Required when mesh topology varies across the design space; here we accept lossy regular-grid voxelization in exchange for FNO's spectral efficiency. If the disc family expands to topologically-varying ventilation patterns the bucket flips to B3 |
| PINN (residual-loss only) | Demonstrated to struggle on stiff / multi-scale problems (ROADMAP B.2); descent thermal couples fast surface heating to slow bulk diffusion — exactly the multi-scale regime PINNs struggle with. Available as an *ablation* via §5 physics-residual terms |
| Pure 3-D CNN regressor | No discretization invariance; no operator framing; rejected for the same reasons as 3-D U-Net |

---

## 8. Disclosure (inherits contract sheet §8)

| Element | Status | Anchor |
|---|---|---|
| FNO family choice | **Anchored** | Q-ml-op-01 [Kovachki2023] |
| Operator-learning framing | **Anchored** | Q-ml-op-01 [Kovachki2023] |
| Architecture topology pattern (lifting → Fourier blocks → projection) | **Anchored** | Li2021 |
| Specific hyperparameter values (F_h=32, N_blocks=4, modes (16,12,12,6)) | **Illustrative configuration** | Defaults; tune against held-out validation |
| λ-weight defaults (0.1 / 0.1 / 1.0) for physics ablation | **Illustrative** | Tune against ablation study; no anchored values |
| Training-config values (lr, batch size, epochs) | **Illustrative** | Standard AdamW defaults; tune per project |
| Compute / latency estimates | **Illustrative** | Deck slide 12 framing range |

A re-tune of any *illustrative* element bumps `model_version`; per the contract sheet §3.3 metadata schema this propagates to `composite_version` and triggers chain re-validation.

---

## 9. Open questions

None at v0.1. All v0.2 contract-sheet questions resolved at user review (Q1: detailed-in-card → this document; Q2: loss consolidated here in §5; Q3–Q5: no excessive detail). This card surfaces no new format questions.
