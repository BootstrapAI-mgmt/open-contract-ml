# Worked Instance — Brake-Disc TMF Chain
## Link 1 — Transient Thermal · Bucket B4 (FNO)
### Model Card v0.1

> This model card covers what the link-1 model *is* — topology,
> hyperparameters, training configuration, loss specification, UQ
> approach, and alternatives considered. What the model produces and
> consumes is fixed by the link's data contract, a companion sheet that
> is not published here; the fixture package
> `tests/fixtures/producer_packages/brake_disc_link1_thermal_fno/` carries the
> part of that signature Contract v1.0 can express.
>
> **Disclosure.** Specific hyperparameter values, network depth, channel
> widths, and λ-weight defaults below are *illustrative configurations*;
> the FNO family choice and the operator-learning framing are *anchored*
> to [Kovachki2023]. The architecture topology is *contractual* in the
> sense that any re-tune of these defaults bumps `model_version` and
> triggers chain re-validation.

---

## 1. Identity

| Field | Value |
|---|---|
| Chain link | 1 of 3 |
| CAE analysis | FEA thermal, transient |
| Architecture bucket | B4 — Operator / parameter-to-function surrogate |
| Architecture family | FNO (Fourier Neural Operator) |
| Reference paper | Li et al. 2021, *Fourier Neural Operator for Parametric PDEs* (arXiv:2010.08895) |
| Survey anchor | [Kovachki2023] — operator-learning framing |
| Data contract | companion sheet, not published here; fixture: `tests/fixtures/producer_packages/brake_disc_link1_thermal_fno/` |
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

Discretization invariance — the spectral-conv layers are FFT-based, so the model accepts grid resolutions different from training. This is the core property the family choice rests on.

### 2.2 Input-channel enumeration (F_in = 10)

| Channel index | Content | Static / time-varying | Source (data contract) |
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

Static channels broadcast across the time axis; time-varying channels broadcast spatially. This collation step is the bridge between the data contract's storage-native row tensors and the FNO's input tensor.

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
| Compute (per ensemble member) | ~10²–10³ GPU-h; ensemble cost = 5× single-model |
| Hardware (training) | NVIDIA A100 / H100 single-GPU sufficient at this network scale |
| Inference latency | ~10 ms per query on A100; ~200 ms CPU |

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

The physics-residual terms are an *optional ablation lever*, not the default training. Pure-data FNO is the §3 / §4 default per the operator-learning framing of [Kovachki2023]. The [Karniadakis2021] physics-informed framing applies when the ablation is run.

The chain-composite `L_endpoint` term is added during chain-level fine-tuning; it is specified in the chain-level contract (not published here).

---

## 6. UQ approach

| Element | Value |
|---|---|
| Method | Deep ensembles, N=5 independently-trained models, different seeds |
| Per-cell uncertainty | `epistemic_sigma_K[t, x, y, z]` = ensemble standard deviation of T_norm, denormalized to K |
| Aleatoric component | Not modelled at link 1 (heat equation is deterministic given inputs); aleatoric inherited from upstream input distribution |
| Output to chain | `epistemic_sigma_K` full tensor `[T, N_x, N_y, N_z]` per the data contract |
| Calibration check | Hold-out coverage: 95 %-prediction-interval should contain ground-truth ≥ 95 % of voxel-time samples; reported in dataset card |

---

## 7. Alternatives considered

| Alternative | Rejected because |
|---|---|
| DeepONet (also B4) | Branch–trunk separation natural when input is a function and queries are scattered; for our regular-grid output FNO is more natural and faster at inference |
| 3-D U-Net (B2 family) | Discretization-bound — locks training and inference to a fixed grid; loses the discretization-invariance property the family choice rests on |
| MeshGraphNet (B3 family) | Required when mesh topology varies across the design space; here we accept lossy regular-grid voxelization in exchange for FNO's spectral efficiency. If the disc family expands to topologically-varying ventilation patterns the bucket flips to B3 |
| PINN (residual-loss only) | Known to struggle on stiff / multi-scale problems; descent thermal couples fast surface heating to slow bulk diffusion — exactly the multi-scale regime PINNs struggle with. Available as an *ablation* via §5 physics-residual terms |
| Pure 3-D CNN regressor | No discretization invariance; no operator framing; rejected for the same reasons as 3-D U-Net |

---

## 8. Disclosure

| Element | Status | Anchor |
|---|---|---|
| FNO family choice | **Anchored** | [Kovachki2023] |
| Operator-learning framing | **Anchored** | [Kovachki2023] |
| Architecture topology pattern (lifting → Fourier blocks → projection) | **Anchored** | Li2021 |
| Specific hyperparameter values (F_h=32, N_blocks=4, modes (16,12,12,6)) | **Illustrative configuration** | Defaults; tune against held-out validation |
| λ-weight defaults (0.1 / 0.1 / 1.0) for physics ablation | **Illustrative** | Tune against ablation study; no anchored values |
| Training-config values (lr, batch size, epochs) | **Illustrative** | Standard AdamW defaults; tune per project |
| Compute / latency estimates | **Illustrative** | Order-of-magnitude framing range |

A re-tune of any *illustrative* element bumps `model_version`; under the chain's metadata schema this propagates to `composite_version` and triggers chain re-validation.

---

## 9. Open questions

None at v0.1. This card surfaces no new format questions.

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../docs/REFERENCES.md).*
