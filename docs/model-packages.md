# A model registry directory

What a dispatching GUI's runtime model registry — a `models/` directory —
holds, and how the GUI validates it.

Each subdirectory is **one model** and must contain:

- `manifest.yaml` conforming to
  [the package-v1 manifest schema](../src/opencontractml/schemas/package-v1/manifest.schema.json)
- `model_card.md` with the 11 mandatory H2 sections (see
  [the model-card template](../src/opencontractml/templates/model_card.template.md))
- The model executable referenced by `invocation.executable` in the
  manifest

## Validation

The GUI scans the directory at startup and on filesystem change.
For each subdirectory it:

1. Loads `manifest.yaml`
2. Validates against `manifest.schema.json`
3. Verifies `invocation.executable` exists and is executable
4. Loads `model_card.md`, parses front-matter, confirms `model_id`
   matches the manifest
5. Verifies the 11 mandatory H2 sections are present in the card
6. Verifies the `uncertainty.per_output` block covers every output

Any failure → the model is **rejected**, appears on a rejected-models
page with the validation error, and does
NOT appear in the catalog. This is deliberate: better to fail loud
at startup than serve a model whose UQ block is missing.

## Field outputs and what a run answers

The Contract's 1.1 amendment, which 0.2.0 is the first release to implement,
has a `type: field` output carry a `field` block — `kind`, `units`, `support`
and `media_type`, with `shape` and `coordinate_ref` where the node layout is
fixed — and the package-v1 schema defines the block exactly as the Contract's
manifest schema does. The field's band is named by `lower_artifact` and
`upper_artifact` in its `uncertainty.per_output` block. A run answers in the
`stdio_json` frame of [the Contract's section 12](spec/CONTRACT-v1.md): the
entrypoint writes the field into the working directory made for the run and
answers with a reference giving the file's path, media type, sha256 and size,
and the field's name, units, value range and node count. The file must be
exactly that size with that digest, so a dispatcher can verify it before reading
it; `opencontractml.verify.reference_problems` is that check, and
`open-contract-ml check --smoke` applies it to every reference an entrypoint
returns.

## Adding a model

Drop a folder into the directory matching the structure above. The
registry hot-reloads on filesystem change; the new model appears in
the catalog within seconds.

## Removing a model

Delete the folder. Existing runs against that model are preserved
in the SQLite store and remain viewable in History (their
`manifest_snapshot` is frozen at run time), but the model no longer
appears in the catalog.

## Updating a model

Replace the `.exe` and bump `version` in the manifest. Past runs keep
their old version's `manifest_snapshot` intact; new runs use the new
version. The catalog card shows the current version; history rows
show the version that ran.

## Worked example

A non-runnable illustrative example lives at
[../examples/brake_disc_tmf_v1/](../examples/brake_disc_tmf_v1/) — it
shows what a complete `manifest.yaml` + `model_card.md` pair looks
like. Once a real `.exe` is built, copying that folder into a
registry directory would make it discoverable.

Two runnable contract packages are worked examples as well:
[../examples/reference-package/](../examples/reference-package/), whose
outputs are scalars, and
[../examples/reference-field-package/](../examples/reference-field-package/),
whose output is a field answered by artifact reference. Both pass
`open-contract-ml check --smoke`.
