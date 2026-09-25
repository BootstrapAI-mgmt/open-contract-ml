# Worked Instance — Brake-Disc TMF Chain
## Link 2 — Thermo-Mechanical · Bucket B7 (Latent-Space Coupled-Dynamics ROM)
### Model Card v0.1

> This model card covers what the link-2 model *is* —
> encoder/decoder/Neural-ODE topology, hyperparameters, training
> configuration with adjoint backprop, full loss formula, UQ approach,
> and alternatives considered. What the model produces and consumes is
> fixed by the link's data contract, a companion sheet that is not
> published here; the fixture package
> `tests/fixtures/producer_packages/brake_disc_link2_thermo_mech_rom/` carries
> the part of that signature Contract v1.0 can express.
>
> **Disclosure.** Specific hyperparameter values, latent dimension, GNN
> depth/width, Neural-ODE tolerances, and λ-weights below are
> *illustrative configurations*; the autoencoder + Neural-ODE family
> choice is anchored to [Lee2020] and Chen2018.

---

## 1. Identity

| Field | Value |
|---|---|
| Chain link | 2 of 3 |
| CAE analysis | Multiphysics, thermo-mechanical |
| Architecture bucket | B7 — Reduced-order / latent-dynamics |
| Architecture family | Autoencoder + Neural-ODE (latent-space coupled-dynamics ROM) |
| Reference papers | Chen et al. 2018, *Neural Ordinary Differential Equations* (NeurIPS, arXiv:1806.07366); Battaglia et al. 2018, *Relational inductive biases, deep learning, and graph networks* (arXiv:1806.01261) |
| Survey-level anchor | [Lee2020] — nonlinear-manifold ROM via autoencoder projection, the family-fit anchor for autoencoder + Neural-ODE in continuous time |
| Data contract | companion sheet, not published here; fixture: `tests/fixtures/producer_packages/brake_disc_link2_thermo_mech_rom/` |
| Methodology anchors (physics) | [Bazilevs2013] / [HsuBazilevs2012] (coupling-scheme taxonomy); [Bathe2014], [Belytschko2014] (FE structural mech foundations); symmetric-tensor preservation (predict 6 independent components, not 9) |

---

## 2. Architecture topology

### 2.1 Network diagram

```
Mesh graph G = (mesh_node_features [N, 4], edge_index [2, N_e], edge_features [N_e, 6])
Thermal history T_history [T_snap=20, N, 1]   (from Link 1 + projection)
Static params  s = (disc_design [4], material_mech_params [6], coupling_class [3])
   │
   ├── ENCODER — Graph Neural Network
   │     stack of N_enc=4 GNN message-passing layers (GraphNet block:
   │       node_update + edge_update with sum aggregation), plus a
   │       global-pooling head (mean-pool over nodes); output is a
   │       graph-level latent z_0 ∈ ℝ^d_latent.
   │     Inputs concatenated per node:
   │       [node_features (4), T_history_at_node (interp at t=0) (1),
   │        s broadcast across nodes (13)]  → F_node_enc = 18
   │
   │     z_0 ∈ ℝ^d_latent   where d_latent = 64
   │
   ├── NEURAL-ODE — latent-space dynamics
   │     dz/dt = f_θ(z, s, t)
   │     f_θ : MLP, depth 4, width 128, GELU
   │     Solver: dopri5 (adaptive RK4(5)); rtol=1e-5, atol=1e-7
   │     Adjoint backprop (Chen2018) for memory-efficient training
   │
   │     Output: z(t_k) for t_k in {snapshot_times_s} → [T_snap, d_latent]
   │
   ├── DECODER — Graph Neural Network
   │     stack of N_dec=4 GNN layers; broadcasts z(t_k) to per-node
   │     features and reconstructs eps_p_field at each snapshot.
   │     Output projection MLP per node: F_h → 6 (symmetric tensor components)
   │
Output:
  eps_p_field_snapshots  [T_snap, N, 6]   — training supervision
  eps_p_field_peak       [N, 6]           — derived from snapshots at inference
  latent trajectory      [T_snap, d_latent] — exposed if return_latent=True
```

The encoder and decoder share GNN message-passing primitives (same edge-update / node-update functional form) but have independent weights. Latent dimension `d_latent = 64` is the load-bearing capacity decision (§3).

### 2.2 Input feature plan (encoder F_node_enc = 18)

| Block | Per-node features | Source |
|---|---|---|
| Geometry | (x_norm, y_norm, z_norm, vol_log_norm) | `mesh_node_features` |
| Thermal IC | (T_at_t0_norm) | `temperature_history[0, :, 0]` |
| Disc design (broadcast) | (D_outer_norm, D_inner_norm, thickness_norm, n_vanes_norm) | `disc_design` |
| Material (broadcast) | (E_norm, ν_norm, σ_y_norm, α_norm, K_norm, n_norm) | `material_mech_params` |
| Coupling class (broadcast, one-hot) | (one_way, loose_two_way, strong_two_way) | `coupling_strength_class` |
| Thermal history → conditioning | (handled separately as Neural-ODE input alongside z) | `temperature_history[1:, :, :]` |

The full thermal trajectory `temperature_history` is passed as a conditioning input to `f_θ` at each integration step, not encoded once at t=0 — that is what makes the dynamics *driven* by the upstream thermal evolution rather than autonomous.

---

## 3. Hyperparameters (illustrative defaults)

| Hyperparameter | Value | Notes |
|---|---|---|
| Latent dimension `d_latent` | 64 | Load-bearing capacity choice; ablation range [16, 128] |
| Encoder GNN layers `N_enc` | 4 | 4 hops of message passing capture brake-disc local-stress neighborhoods adequately |
| Decoder GNN layers `N_dec` | 4 | Same depth for symmetry |
| GNN hidden width `F_h` | 128 | Per-layer node + edge feature width |
| Neural-ODE MLP depth | 4 | `f_θ` depth |
| Neural-ODE MLP width | 128 | |
| Activation | GELU throughout | |
| Normalization | LayerNorm in GNN message passing; no normalization in Neural-ODE MLP (preserves phase-space geometry) | |
| Neural-ODE solver | Dopri5 (adaptive Runge-Kutta 4(5)) | |
| Neural-ODE rtol / atol | 1e-5 / 1e-7 | Tighter than typical ML defaults; physical dynamics need precision |
| Adjoint method | Yes (Chen2018) | Memory-efficient backprop through Neural-ODE |
| Parameter count | ~5 M (illustrative) | Larger than link-1 FNO due to dual GNN towers + dynamics MLP |
| Float precision | FP32 throughout | Mixed-precision is risky around adjoint backprop |

---

## 4. Training configuration (illustrative)

| Element | Value |
|---|---|
| Curriculum stage 1 | Encoder/decoder pretrained as a static autoencoder on snapshot data: `eps_p(t_k) → z_k → eps_p(t_k)`. ~50 epochs. Locks the latent geometry before dynamics training. |
| Curriculum stage 2 | Neural-ODE trained against snapshot rollouts with encoder/decoder frozen first 20 epochs, then unfrozen. ~150 epochs. |
| Optimizer | AdamW, lr=5e-4 (lower than link 1 — Neural-ODE training is touchier) |
| Weight decay | 1e-4 |
| LR schedule | Cosine decay; 10% warmup |
| Batch size | 4 design-points / batch (memory-bound on 24 GB; Neural-ODE checkpointing dominates memory) |
| Gradient clipping | global norm 1.0 — Neural-ODE rollouts can produce exploding gradients without |
| Epochs total | 200 (50 stage 1 + 150 stage 2) |
| Deep-ensemble count | N=5 — five independent models, different seeds, for UQ (§6) |
| Compute (per ensemble member) | ~10¹–10² GPU-h; ensemble cost = 5× single-model |
| Hardware (training) | NVIDIA A100 / H100 single-GPU sufficient at this network scale |
| Inference latency | 10–100 ms per soak-window evaluation; CPU inference ~500 ms – 2 s |

---

## 5. Loss specification (consolidated)

```
L_link2 = L_recon + λ_dyn L_dyn + λ_sym L_sym + λ_kin L_kin

where
  L_recon  = || eps_p(t_k)_pred − eps_p(t_k)_true ||²            per-snapshot
                summed over t_k ∈ {snapshot_times_s}; supervises encoder + decoder.
  L_dyn    = || z(t_k)_pred − z(t_k)_consistent ||²              latent-rollout
                where z(t_k)_consistent = encode(eps_p(t_k)_true);
                supervises Neural-ODE dynamics in latent space.
  L_sym    = symmetric-tensor preservation penalty: penalises any predicted
                tensor whose off-diagonal asymmetric component (eps_p[i,j] −
                eps_p[j,i]) deviates from zero. Avoids the asymmetric-tensor
                pitfall (predict 6 independent components, not 9).
  L_kin    = kinematic-compatibility soft penalty: ∇·(eps_p) consistency
                where applicable; off by default (λ_kin = 0).

Defaults: λ_dyn = 1.0, λ_sym = 0.1, λ_kin = 0
Ablation:  λ_dyn = 0   (autoencoder-only baseline; no rollout)
           λ_kin = 0.05 (kinematic-aware variant)
```

**Asymmetry between training and inference loss application.** L_recon and L_dyn are summed over training snapshots; at inference, a single peak-cyclic field is returned rather than a snapshot trajectory (per the data contract). The reconciliation between snapshot-level supervision and peak-level deployment is one of the format deviations the data contract flags.

The chain-composite `L_endpoint` term is added during chain-level fine-tuning per the chain-level contract (not published here).

---

## 6. UQ approach

| Element | Value |
|---|---|
| Method | Deep ensembles, N=5 independently-trained models, different seeds |
| Per-cell uncertainty | `epistemic_sigma_eps_p[node, component]` = ensemble standard deviation per symmetric-tensor component; full-tensor shape `[N_nodes, 6]` per chain UQ contract |
| Latent-disagreement scalar | `latent_disagreement` = ensemble standard deviation of z_0 (encoder output), aggregated across latent dimensions; useful for chain-level sanity check at the link-2-to-link-3 interface |
| Aleatoric component | Not modelled at link 2 (deterministic given inputs; aleatoric inherited from upstream input distribution + upstream link-1 propagation) |
| Output to chain | Full-tensor `epistemic_sigma_eps_p` + `latent_disagreement` scalar per the data contract |
| Calibration check | Hold-out coverage: 95 %-prediction-interval should contain ground-truth ≥ 95 % of (node, component) samples; reported in dataset card |

---

## 7. Alternatives considered

| Alternative | Rejected because |
|---|---|
| POD-NN (POD basis + per-mode regression) | Linear modal basis; struggles to capture highly nonlinear coupled dynamics in the strong-two-way regime where this link is most needed. POD-NN is the *low-fidelity tier* sub-variant; remains a useful baseline for the loose-two-way regime |
| DeepONet (B4 family) | Operator-learning over the coupling map is an alternative framing; rejected because the time-resolved rollout regime favors Neural-ODE's continuous-time integration over DeepONet's branch-trunk function evaluation, and because per-link physical-test validation is easier with explicit latent dynamics |
| Direct GNN regression (no latent dynamics) | Predicts ε_p directly from inputs without compressing through a latent space. Loses the slow-manifold structural inductive bias that makes B7 cheaper than B3 at inference; also forfeits the chain-level fine-tune lever (operating in latent space) |
| Pure FE-FE coupled solver | The thing we replace; not an ML alternative |
| Physics-informed Neural ODE (residual loss inside f_θ) | Available as an ablation via λ_kin > 0; rejected as default for the same reasons FNO PINN was rejected at link 1 — strong-two-way coupling spans multi-scale dynamics that residual losses struggle with |

---

## 8. Disclosure

| Element | Status | Anchor |
|---|---|---|
| Autoencoder + Neural-ODE family choice | **Anchored** | [Lee2020]; Chen2018 (Neural-ODE) |
| GNN encoder/decoder for unstructured mesh | **Anchored** | Battaglia2018 graph-network framework |
| Symmetric-tensor preservation in loss | **Anchored** | Symmetry of the plastic-strain tensor (6 independent components) |
| Coupling-class enforcement protocol | **Anchored** | [Bazilevs2013] |
| Latent dimension `d_latent = 64` | **Illustrative** | Tune against held-out validation; ablation range [16, 128] |
| GNN depth `N_enc = N_dec = 4`, width `F_h = 128` | **Illustrative** | Standard graph-network defaults |
| Neural-ODE solver choice (Dopri5) and tolerances | **Illustrative (informed)** | Tighter than typical ML defaults; tune against rollout-stability test |
| λ-weight defaults (1.0 / 0.1 / 0) | **Illustrative** | Tune against ablation study |
| Training-config values (lr, batch size, epochs, curriculum) | **Illustrative** | Standard defaults; Neural-ODE-specific gradient clipping is necessary |
| Compute / latency estimates | **Illustrative** | Order-of-magnitude framing range |

A re-tune of any *illustrative* element bumps `model_version`; under the chain's metadata schema this propagates to `composite_version` and triggers chain re-validation.

---

## 9. Open questions

None at v0.1. The data contract flags three format questions (mesh-as-graph storage, training-vs-inference output reconciliation, coupling-class enforcement protocol). This model card surfaces no new format questions: the link-1 model card structure (identity → topology → hyperparameters → training → loss → UQ → alternatives → disclosure) extrapolates cleanly even though the architecture family is structurally different (FNO → autoencoder + Neural-ODE).

---

*Citations of the form `[Key]` resolve to [`docs/REFERENCES.md`](../../docs/REFERENCES.md).*
