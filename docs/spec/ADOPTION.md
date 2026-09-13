# Contract v1 -- adoption path

Companion to [CONTRACT-v1.md](CONTRACT-v1.md). This document says
**exactly** what each repo must change, at file and field level. It is a work order,
not a discussion. Nothing here has been applied -- G1D authored the spec and the
checker only; these edits belong to whoever takes the next card.

Line numbers are as of 2026-09-12 and are given as a hint; the symbol names are the
contract. Verify before editing.

The measured starting point is [GAP-MATRIX.md](GAP-MATRIX.md), regenerated
with `python -m opencontractml.verify gap`. Work the `ABSENT` and `PARTIAL` cells; the table is
the work-list.

---

## 1. Ordering

```
  cae-ml-gui (enforce)          -- small, self-contained, unblocks everything
        |
        +--> physics-surrogates (emit)   -- the large one; needs spec v1.1 for fields
        |
        +--> CAE-ML-data-pipelines (emit + fix)
```

`cae-ml-gui` first. Its change is additive and back-compatible, and until it accepts
the contract sections nothing either producer emits can dock.

---

## 2. `cae-ml-gui` -- become the enforcer

**Two sections, one provenance block, one validation pointer.** Nothing is removed;
every existing manifest and card stays valid except for the card section count.

### 2.1 `server/model_card.py` -- the two-string change

`MANDATORY_SECTIONS` (line 44) becomes eleven entries. **Insert only** -- do not
re-order the existing nine:

```python
MANDATORY_SECTIONS: tuple[str, ...] = (
    "TL;DR",
    "Intended use",
    "Out of scope",
    "Training data",
    "Architecture",
    "Training configuration",          # <-- inserted (contract 4.2, position 6)
    "Performance",
    "Uncertainty quantification",
    "Known failure modes",
    "Provenance",                      # <-- inserted (contract 4.2, position 10)
    "Version history",
)
```

`_section_errors` already derives its count from `len(MANDATORY_SECTIONS)`, so the
logic needs no edit. The prose does:

- module docstring lines 1, 11-13 -- "nine mandatory H2 sections" / "first nine";
- line 43 comment -- "The nine mandatory H2 sections";
- line 160 message -- "(the nine mandatory sections must come first, in order)";
- `server/manifest.py` line 536 -- "the nine-mandatory-section + id/version card checks";
- `server/README.md` line 16 -- "the nine".

Prefer wording that does not hard-code a count, so the next insertion is a one-line
change: *"the mandatory H2 sections, in order, as the card's leading headings."*

### 2.2 `server/model_card.py` -- reserved extras (optional, warning-severity)

Contract 4.2 reserves four post-required section names. The GUI currently permits **any**
extra H2 after the mandatory ones. To match the contract, add a non-rejecting warning for
an unreserved extra; do **not** make it an error -- the contract grades `C006` as a warning
precisely so this stays additive.

### 2.3 `schemas/manifest.schema.json` -- two new properties

Add to `properties` and to `required`:

| key | shape |
|---|---|
| `provenance` | object; `required: [artifacts, dataset, code]` |
| `validation` | object; `required: [report]`, `report` a relative path string, optional `overall` enum `[PASS, FAIL]` |

`provenance.artifacts` is an array with `minItems: 1` of objects requiring
`path`, `role`, `sha256`, `bytes`; `role` enum `[entrypoint, weights, asset]`;
`sha256` pattern `^[0-9a-f]{64}$`. `provenance.dataset` requires `sha256` with the same
pattern. `provenance.code` requires `repo` and `commit`, `commit` pattern
`^[0-9a-f]{7,40}$`.

Making these `required` is a **MAJOR** change under the GUI's own back-compat policy
(design decision 15), because existing manifests lack them. Two options, and the choice
is the owner's:

- **(a)** add them as *optional* in manifest-spec 1.1, warn when absent, and promote to
  required in 2.0. Keeps every existing model loadable. Recommended.
- **(b)** add them as required and bump `SUPPORTED_SPEC_MAJOR` to 2. Honest, loud, and
  breaks the worked example until it is updated.

Recommend **(a)**: the GUI already has a warning channel (`manifest_warnings`) built for
exactly this kind of nudge, and `validate_package` surfaces it.

### 2.4 `server/manifest.py` -- typed mirror

The module asserts schema/model parity in its own tests, so the typed layer must move
with the schema. Add, mirroring the existing style:

```python
class Artifact(BaseModel):
    path: str
    role: ArtifactRole          # StrEnum: entrypoint | weights | asset
    sha256: str
    bytes: int

class Provenance(BaseModel):
    artifacts: list[Artifact]
    dataset: DatasetProvenance
    code: CodeProvenance
    environment: Environment | None = None

class Validation(BaseModel):
    report: str
    overall: str | None = None
```

and on `Manifest`: `provenance: Provenance | None = None`,
`validation: Validation | None = None` (both non-optional under option (b)). Export the
new names in `__all__`.

Then add to `semantic_errors` -- these are cross-field invariants the JSON Schema
cannot express, which is where the GUI already puts this kind of check:

1. `invocation.executable` must equal the `path` of the single `role: entrypoint`
   artifact (contract `M012`/`M013`). This is the one that makes the whole provenance
   block load-bearing.
2. Every `artifacts[].path` must resolve inside the package directory.

Hash **verification** (re-hashing the file on disk) belongs in the registry/runner at
load time, alongside the existing `invocation.executable`-exists check that
`load_model` deliberately defers (design section 3 step 3). Keep the contract layer
filesystem-free; the contract's `M013` is the pre-publish gate's job, and the GUI already
has that seam in `validate_package`.

### 2.5 Fixtures and docs to move with it

| file | change |
|---|---|
| `templates/model_card.template.md` | insert the two sections (currently 9 `##` at lines 13-80, plus `## References`) |
| `examples/brake_disc_tmf_v1/model_card.md` | insert the two sections |
| `examples/brake_disc_tmf_v1/manifest.yaml` | add `provenance` + `validation`; its `fake_model.py` is the entrypoint to hash |
| `server/tests/fixtures/model_packages/conformant/` | both files, same change |
| `server/tests/fixtures/model_packages/nonconformant/` | see the trap below |
| `server/tests/test_model_card.py` | lines 65, 83, 90 name "the nine"; the helpers derive from `MANDATORY_SECTIONS` and should keep doing so |

> **Trap, found by running the validator.** The `nonconformant` fixture's
> `model_card.md` currently passes `collect_model_card_errors` with **zero** errors --
> it is non-conformant at the *manifest* level only. Anyone reading the fixture name as
> "the card that fails card validation" will be wrong. Either rename it, or add a
> sibling fixture whose card genuinely fails, before relying on it in a contract test.

### 2.6 Definition of done for the GUI

`python -m server.manifest examples/brake_disc_tmf_v1` passes, **and**
`python -m opencontractml.verify check examples/brake_disc_tmf_v1` (run from data-pipelines,
pointed at the gui path) passes. Two checkers, one package, same verdict. Until both
agree, the contract is still two contracts.

---

## 3. `physics-surrogates` -- become an emitter

This is the big one. `physics-surrogates` currently emits **nothing** a consumer can
dock: no `manifest.yaml`, no `.md` card, no `stdio_json` wrapper. Verified by
`grep -rIn "stdio_json\|manifest.yaml"` over the repo -- the only hits are its own
productization prose.

What it *does* have is better than it looks, and most of the work is packaging rather
than building.

### 3.1 What already complies

| contract requirement | where it already lives |
|---|---|
| `A1`-`A5`, `B3`, `B5`, `C1`, `C2` | `physsur/gates/field_gate.py`, `mesh/gate.py`, `cloud/gate.py` |
| `B4_conservation` (the reference implementation) | `field_gate.py` FG7 -- `|source - sink - edge| / gross` vs `imbalance_max` |
| numeric metrics + thresholds on every check | every `_gate(...)` call carries `metrics=` and `thresholds=` |
| recomputable rollup | `overall = all(...)` at `field_gate.py:259` |
| `provenance.dataset.sha256` | `card["dataset"]["sha256"]` |
| artifact + split + rules hashing | `physsur/runs.py` -- `describe_run` already hashes checkpoint, exports, splits and rules |
| torch-free forward | `physsur/cloud/numpy_infer.py`, `physsur/mesh/numpy_infer.py` (`load_npz`) |

### 3.2 Changes, in order

**(1) Resolve the FG7 collision. Do this first -- it is a correctness fix, not
packaging.** `FG7` currently means conservation in `gates/field_gate.py` and
`mesh/gate.py`, and integrated quantities in `cloud/gate.py`. Rename the cloud lane's
gate string from `FG7_integrated_quantities` to a distinct id (`FG11_integrated_quantities`
is the least disruptive, since `FG1`-`FG10` are spoken for), update
`configs/rules_airfrans.json`, `allow_not_run_by_task`, and
`tests/test_cloud_gates.py`. Until this lands, any cross-lane rollup that keys on the
`FG<n>` prefix -- `runs.py:describe_run` builds exactly such a dict at
`{g["gate"].split("_")[0]: g["status"]}` -- silently conflates two different physical
claims.

**(2) Add the contract key to every gate.** Cheapest form: one extra field per gate dict.

```python
def _gate(name, passed, **detail):
    status = "NOT_RUN" if passed is None else ("PASS" if passed else "FAIL")
    return {"gate": name, "contract_key": CONTRACT_KEYS[name.split("_")[0]], "status": status, **detail}
```

with a per-lane `CONTRACT_KEYS` map. `verify.legacy_key(lane, legacy)` is the
authority for the mapping and is lane-aware for `FG7`; import it or mirror it, but do
not hand-copy the `FG7` row.

**(3) Replace `allow_not_run` with `NOT_APPLICABLE` + reason.** The cloud lane's
`allow_not_run_by_task: {"full": ["FG2"], "scarce": ["FG2"]}` becomes a
`NOT_APPLICABLE` status carrying `reason: "the full task has no extrapolation split"`.
Same verdict; the rationale stops being implicit in an allow-list.

**(4) Declare `determinism_class` on FG5.** It is `seeded_tolerance` at `rel_tol =
2e-2`. One field; makes the difference from the scalar ladder's `1e-6` legible
(contract 5.5(b)).

**(5) Add the missing Tier-B checks or declare them NOT_APPLICABLE.** `B1_monotonicity`
and `B2_bounds` have no field-lane equivalent. For a thermal field, "temperature stays
above ambient everywhere" is a real `B2` and probably cheap. Do not leave them absent:
absent is `V004`, which blocks.

**(6) Write the package emitter.** A new `physsur/package.py` plus a `physsur ... package`
subcommand in `physsur/cli.py` (which already has `generate | baselines | train | gate |
export | all | report`), taking a run directory and writing a contract package:

| output | built from |
|---|---|
| `validation_report.json` | the existing gate card, re-keyed to contract keys, plus `spec_version` / `produced_by` / `model_id` / `model_version` / `dataset_sha256` |
| `manifest.yaml` | `predictor.describe()` for the model block; `runs.py:describe_run` for `provenance`; the config for `inputs` |
| `model_card.md` | a template with the eleven sections; `Performance`, `Uncertainty quantification` and `Provenance` are generated from the report, the rest are authored once per model family |
| `predict.py` | the `stdio_json` wrapper -- read JSON on stdin, run `numpy_infer.load_npz` + forward, write JSON on stdout. Torch-free, which is why `FG9`/`C2` exists |

**Blocked on spec v1.1.** A field model cannot fully describe its outputs under contract
v1.0: `outputs[]` was designed for scalars and categoricals and has no shape, no mesh
reference and no field units (spec section 10, limitation 3). Two ways forward, and this
is a decision for the spec owner, not the emitter author:

- **(a)** extend `outputs[]` with an optional `field: {shape, coordinate_ref, units}`
  block in contract 1.1 (additive, MINOR);
- **(b)** emit field models as `modality: geometry_in_field_out` with a single
  `type: field` output and push the shape into `uncertainty.per_output` -- workable
  today, but it puts structural information in the UQ block, which is wrong.

Recommend **(a)**, and treat it as a prerequisite for step (6) rather than working
around it.

### 3.3 Definition of done for physics-surrogates

`python -m physsur package --run runs/heat64 --model fno --out dist/heat64_fno` produces
a directory that `python -m opencontractml.verify check dist/heat64_fno` accepts, whose
`predict.py` answers a `stdio_json` request, and whose `B4_conservation` carries the FG7
number it already computes.

Note that `evidence/heat64/models/fno/model_card.json` records
`FG7_conservation: FAIL` (`imbalance_abs_mean` 0.172 against a threshold of 0.05). A
conformant package is **not** the same as a passing model, and the contract is deliberately
able to express "this package is well-formed and its model fails B4". Do not weaken the
threshold to make the package green (LESSONS L18).

---

## 4. `CAE-ML-data-pipelines` -- become an emitter, and fix the vacuous gate

### 4.1 The A81 cards

The three `WORKED-INSTANCE-A81-*-model-card.md` files fail `cae-ml-gui`'s validator with
10 errors each and share no section label with the contract set. They need a restructure,
not a patch. The content maps cleanly:

| A81 section | contract section |
|---|---|
| 1. Identity | front-matter + `TL;DR` |
| 2. Architecture topology | `Architecture` |
| 3. Hyperparameters + 4. Training configuration + 5. Loss specification | `Training configuration` |
| 6. UQ approach | `Uncertainty quantification` |
| 7. Alternatives considered | `Alternatives considered` (reserved, kept as-is) |
| 8. Disclosure | `Disclosure` (reserved, kept as-is) |
| 9. Open questions | `Open questions` (reserved, kept as-is) |
| -- | `Intended use`, `Out of scope`, `Training data`, `Performance`, `Known failure modes`, `Provenance`, `Version history` **must be written; they do not exist today** |

The seven sections in the last row are the real work. `Performance` is the notable one:
**the A81 cards carry no metrics table at all.** That is not a formatting gap.

### 4.2 `examples/TASK-10-corpus-consumer/model_gate.py` -- gate G1.4, not this card

Two defects, both out of scope here and both now measurable:

1. **`V2.3` / `V2.4` are presence-of-non-empty-string tests** (line ~256:
   `all(v not in ("not declared", None, "") for v in v2decl.values())`). The shipped
   card `evidence/reports/model_card_real_pv-f1_plate.json` carries
   `"V2.3 conservation": "applicable_not_implemented_v0 (...)"` and passes. Under the
   contract that is `V009` FAIL. Fix per spec 5.4: measure a relative imbalance over a
   named control volume, or declare `applicable: false` with a reason.
2. **No `C1_ood_guard`, no `C2_serve_parity`.** The scalar ladder has neither.
   `physics-surrogates` has both (`physsur/gates/ood.py` is directly portable).

**Do not touch `model_gate.py` for the contract.** It is owned by G1.4 and was being edited
concurrently by another agent on 2026-09-12.

### 4.3 The emitter

Same shape as physics-surrogates' step (6): a package writer that turns
`model_bundle.pkl` + `model_card.json` + `data_card.json` into a contract package. The
scalar lane is *easier* than the field lane -- its outputs are genuinely scalars, so
contract v1.0 describes them fully with no v1.1 dependency. **Do this one first** to prove
the round trip end to end while the field-output extension is still being specified.

---

## 5. Acceptance for G1.2 as a whole

The gate is not "the spec exists". It is:

1. `python -m opencontractml.verify check` accepts a package from **each** of the three repos;
2. `cae-ml-gui`'s own `python -m server.manifest <pkg>` accepts the same packages;
3. the gap matrix regenerates with no `ABSENT` cell in the `M*` or `V*` rows;
4. the two `ABSENT`-everywhere rows today -- `C003:Provenance` and
   `V004:C3_provenance_integrity` -- are closed. **No producer in the ecosystem emits
   provenance integrity today.** That is the single widest hole the measurement found,
   and it is the reason the provenance block is normative rather than advisory.
