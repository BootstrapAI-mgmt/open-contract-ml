# Model onboarding — packaging a trained model for a dispatching GUI

> How a trained model becomes a package that a model-agnostic dispatching GUI
> can load and run: the repeatable workflow, and the package format behind it.
> The gate it documents is `opencontractml.manifest` — the same validators a
> consumer runs when it loads a package — so onboarding never diverges from what
> is enforced at load.

---

## Why this exists

A model-agnostic runner carries no per-model code: a model docks by adding a
folder, with no rebuild of the runner. For that to scale to every model as it
is built, two things must be stable and public: **what a package looks like**
(the format, §1) and **how you prove a package is admissible before shipping
it** (the pre-publish gate, §3). Catching a malformed manifest or card at
authoring time — not silently at a colleague's startup — is the whole point.

---

## 1. The model-package format

A model package is a single directory, conventionally `models/<id>/` in the
consumer's model registry, containing exactly:

```
models/<id>/
├── manifest.yaml      # the machine-checkable contract (the package-v1 manifest schema)
├── model_card.md      # the human-prose companion (11 mandatory H2 sections)
└── <executable>       # the stdio_json model binary named by invocation.executable
```

Rules that make the package self-describing and relocatable:

- **`manifest.yaml`** validates against
  [the package-v1 manifest schema](../src/opencontractml/schemas/package-v1/manifest.schema.json)
  and satisfies the semantic invariants `opencontractml.manifest` checks — above
  all that `uncertainty.per_output` covers **every** output.
- **Paths are relative to the manifest.** `invocation.executable` (e.g.
  `./model.exe`) and `model_card: ./model_card.md` resolve against the package
  directory, so the folder moves as a unit (USB stick, network share, bundled
  release).
- **`model_card.md`** carries front-matter (`model_id`, `version`) that matches
  the manifest, then the eleven mandatory H2 sections in order
  ([the model-card template](../src/opencontractml/templates/model_card.template.md)).
- **`spec_version`** (optional, `MAJOR.MINOR`) declares the manifest-spec the
  package targets; absent ⇒ `1.0`. A consumer loads any package whose MAJOR is ≤
  its supported major and rejects a higher MAJOR loudly. This is what lets one
  consumer build keep loading models authored against a later same-major spec
  without a rebuild.

A worked, conformant package: [examples/brake_disc_tmf_v1/](../examples/brake_disc_tmf_v1/)
(it ships no `.exe` — see §3 on why that is still gate-valid). A package that
also carries the Contract's `provenance` and `validation` blocks is a contract
package; [examples/reference-package/](../examples/reference-package/) is the
worked one, graded by `open-contract-ml check`.

---

## 2. The onboarding workflow

From a trained model to a docked one:

1. **Train / export** the model and wrap it behind the `stdio_json` wire format:
   read one JSON object on stdin, write `{status, outputs|error}` on stdout,
   progress JSON on stderr.
2. **Author `manifest.yaml`** — identity, inputs, outputs, the `uncertainty`
   block (form + `per_output` for every output + calibration), `invocation`,
   `lineage`, and discoverability metadata.
3. **Author `model_card.md`** from the template — the eleven sections, with the
   `model_id`/`version` front-matter matching the manifest.
4. **Build the executable** and place it in the package folder; point
   `invocation.executable` at it.
5. **Validate the package** with the pre-publish gate (§3). Fix every reported
   error — the gate is the same contract a consumer enforces at load.
6. **Publish** — drop the folder into the consumer's model registry, or include
   it in a bundled release. A consumer that reloads its registry picks the model
   up with no code change.

---

## 3. The pre-publish validation gate

Run the validators a consumer runs at load, against a candidate package,
*before* it is published:

```bash
python -m opencontractml.manifest path/to/package-dir     # one package
python -m opencontractml.manifest models/*                # many at once
```

Exit code `0` = admissible; non-zero = at least one package failed, with each
problem printed and attributed to its file. Run it in the producer's CI against
every candidate package; a green run is the signal to publish.

**What the gate checks** (via `opencontractml.manifest.validate_package`,
reusing `collect_manifest_errors` + `collect_model_card_errors`):

- manifest JSON-Schema structure, the typed model, and every semantic invariant
  — name uniqueness, categorical `choices`, file `file_kind`, `primary_*`
  references, the **`uncertainty.per_output` coverage keystone**, and the
  **`spec_version` major policy**;
- the model card's front-matter id/version match and the **eleven mandatory H2
  sections in order**.

**What it deliberately does not check:** that `invocation.executable` exists on
disk. That is the dispatcher's check at load time; skipping it here lets a
contract-only worked example (no `.exe`) pass the gate. A real package's
executable is verified when the model is loaded for dispatch.

For a contract package, run `open-contract-ml check <package>` as well: it adds
the provenance hashes, the validation report and the rest of the Contract's
rules.

---

## 4. Ownership and cadence

- **Ownership.** The model's authoring team owns its `manifest.yaml` +
  `model_card.md` and keeps them in sync with each retrain (bump `version`,
  update the card's Version history).
- **"Model ready" handshake.** A model is ready to onboard when its package
  passes the gate (§3) green.
- **Cadence.** Models onboard as they are built — there is no consumer release
  tied to a model add. Adding or updating a model never requires re-versioning
  the consumer; only a breaking manifest-spec major bump would.

---

## 5. See also

- [the package-v1 manifest schema](../src/opencontractml/schemas/package-v1/manifest.schema.json) — the manifest format
- [the model-card template](../src/opencontractml/templates/model_card.template.md) — the card template
- [docs/spec/CONTRACT-v1.md](spec/CONTRACT-v1.md) — the Contract, which adds provenance and validation to the package format
