# models/

Runtime model registry.

Each subdirectory is **one model** and must contain:

- `manifest.yaml` conforming to
  [../schemas/manifest.schema.json](../schemas/manifest.schema.json)
- `model_card.md` with the 9 mandatory H2 sections (see
  [../templates/model_card.template.md](../templates/model_card.template.md))
- The model executable referenced by `invocation.executable` in the
  manifest

## Validation

The server scans this directory at startup and on filesystem change.
For each subdirectory it:

1. Loads `manifest.yaml`
2. Validates against `manifest.schema.json`
3. Verifies `invocation.executable` exists and is executable
4. Loads `model_card.md`, parses front-matter, confirms `model_id`
   matches the manifest
5. Verifies the 9 mandatory H2 sections are present in the card
6. Verifies the `uncertainty.per_output` block covers every output

Any failure → the model is **rejected**, appears in the
`/admin/rejected-models` page with the validation error, and does
NOT appear in the catalog. This is deliberate: better to fail loud
at startup than serve a model whose UQ block is missing.

## Adding a model

Drop a folder into this directory matching the structure above. The
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
like. Once a real `.exe` is built, copying that folder into this
directory would make it discoverable.
