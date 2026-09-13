# Model Onboarding — packaging a trained model for the GUI

> How a trained model from
> [CAE-ML-data-pipelines](https://github.com/BootstrapAI-mgmt/CAE-ML-data-pipelines)
> becomes a model the GUI can dispatch. This is the repeatable workflow and the
> **published package-format contract** behind operator Requirement 2 (onboard
> all pipeline models as they are built) — the process half that complements the
> runtime registry described in [gui-design.md](gui-design.md) §12.
>
> Implements TC-GUI18. The gate it documents reuses the validation library
> (`server/manifest.py`, `server/model_card.py`), so onboarding never diverges
> from what the server enforces at registry load (gui-design.md §3).

---

## Why this exists

The GUI is a **model-agnostic universal runner**: it carries no per-model code,
and a model docks by adding a folder — no GUI rebuild (gui-design.md §13,
decisions 2 and 15). For that to scale to "all pipeline models as they are
built," two things must be stable and public: **what a package looks like** (the
format contract, §1) and **how you prove a package is admissible before shipping
it** (the pre-publish gate, §3). Catching a malformed manifest or card at
authoring time — not silently at a colleague's startup — is the whole point.

---

## 1. The model-package format (contract)

A model package is a single directory under `./models/<id>/` containing exactly:

```
models/<id>/
├── manifest.yaml      # the machine-checkable contract (schemas/manifest.schema.json)
├── model_card.md      # the human-prose companion (9 mandatory H2 sections)
└── <executable>       # the stdio_json model binary named by invocation.executable
```

Rules that make the package self-describing and relocatable:

- **`manifest.yaml`** validates against
  [schemas/manifest.schema.json](../schemas/manifest.schema.json) and satisfies
  the semantic invariants in gui-design.md §3 — above all that
  `uncertainty.per_output` covers **every** output.
- **Paths are relative to the manifest.** `invocation.executable` (e.g.
  `./model.exe`) and `model_card: ./model_card.md` resolve against the package
  directory, so the folder moves as a unit (USB stick, network share, bundled
  release).
- **`model_card.md`** carries front-matter (`model_id`, `version`) that matches
  the manifest, then the nine mandatory H2 sections in order
  ([templates/model_card.template.md](../templates/model_card.template.md)).
- **`spec_version`** (optional, `MAJOR.MINOR`) declares the manifest-spec the
  package targets; absent ⇒ `1.0`. The GUI loads any package whose MAJOR is ≤ its
  supported major and rejects a higher MAJOR loud (gui-design.md §13, decision
  15). This is what lets one GUI build keep loading models authored against a
  later same-major spec without a rebuild.

A worked, conformant package: [examples/brake_disc_tmf_v1/](../examples/brake_disc_tmf_v1/)
(it ships no `.exe` — see §3 on why that is still gate-valid).

---

## 2. The onboarding workflow

From a trained pipeline model to a docked GUI model:

1. **Train / export** the model in CAE-ML-data-pipelines and wrap it behind the
   `stdio_json` wire format (gui-design.md §8): read one JSON object on stdin,
   write `{status, outputs|error}` on stdout, progress JSON on stderr.
2. **Author `manifest.yaml`** — identity, inputs, outputs, the `uncertainty`
   block (form + `per_output` for every output + calibration), `invocation`,
   `lineage`, and discoverability metadata.
3. **Author `model_card.md`** from the template — the nine sections, with the
   `model_id`/`version` front-matter matching the manifest.
4. **Build the executable** and place it in the package folder; point
   `invocation.executable` at it.
5. **Validate the package** with the pre-publish gate (§3). Fix every reported
   error — the gate is the same contract the server enforces at load.
6. **Publish** — drop the folder into `./models/<id>/` (local) or include it in a
   bundled release (gui-design.md, TC-GUI21). The server hot-reloads; the model
   appears in the catalog with zero GUI code changes.

---

## 3. The pre-publish validation gate

Run the same validators the registry uses, against a candidate package, *before*
it lands in `./models/`:

```bash
python -m server.manifest path/to/package-dir          # one package
python -m server.manifest examples/* models/*          # many at once
```

Exit code `0` = admissible; non-zero = at least one package failed, with each
problem printed and attributed to its file. CI runs this over every package
under `examples/` and `models/` via
[.github/workflows/validate-model-package.yml](../.github/workflows/validate-model-package.yml);
point the identical command at a candidate package in the sibling repo to gate it
there before handoff.

**What the gate checks** (via `server.manifest.validate_package`, reusing
`collect_manifest_errors` + `collect_model_card_errors`):

- manifest JSON-Schema structure, the typed model, and every semantic invariant
  — name uniqueness, categorical `choices`, file `file_kind`, `primary_*`
  references, the **`uncertainty.per_output` coverage keystone**, and the
  **`spec_version` major policy**;
- the model card's front-matter id/version match and the **nine mandatory H2
  sections in order**.

**What it deliberately does not check:** that `invocation.executable` exists on
disk (gui-design.md §3 step 3). That is the registry/runner's check at load time;
skipping it here lets a contract-only worked example (no `.exe`) pass the gate. A
real package's executable is verified when the registry loads it.

---

## 4. Coordination with CAE-ML-data-pipelines

Onboarding is a **standing activity**, decoupled from GUI releases (gui-design.md
§13, decision 15; ROADMAP Phase 5):

- **Ownership.** The model's authoring team owns its `manifest.yaml` +
  `model_card.md` and keeps them in sync with each retrain (bump `version`,
  update the card's Version history).
- **"Model ready" handshake.** A model is ready to onboard when its package
  passes the gate (§3) green. The sibling repo runs `python -m server.manifest`
  on the candidate package in its own CI; a green run is the signal to publish.
- **Cadence.** Models onboard as they are built — there is no GUI release tied to
  a model add. Adding or updating a model never requires re-versioning or
  re-downloading the GUI (operator Requirement 4); only a breaking manifest-spec
  major bump would (gui-design.md §13, decision 15).

---

## 5. See also

- [gui-design.md](gui-design.md) §3 (validation at registry load), §8
  (`stdio_json` wire format), §12 (filesystem registry), §13 (decisions 2, 15)
- [schemas/manifest.schema.json](../schemas/manifest.schema.json) — the manifest contract
- [templates/model_card.template.md](../templates/model_card.template.md) — the card template
- [ROADMAP.md](../ROADMAP.md) Phase 5 — model onboarding & dual distribution
