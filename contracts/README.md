# contracts/ — inter-stage contracts (frozen assets)

Every pipeline artifact is a JSON document validated against one of the schemas in this directory (the artifact's `schema_version` field names the schema). The schemas are frozen: any change is a breaking change that requires an explicit decision record. Each schema has a minimal example instance under `examples/`.

## Convention: extension keywords discoverable on the contracts side

| Keyword | Location | Meaning | Defined by |
|---|---|---|---|
| `x-carverflow-counts` | schema property objects inside `initial_oas` | `{n_present, n_total}`: how often the field occurred over all observations of the operation (the evidence for required/optional decisions) | decision record 003, addendum A, ruling 2; promoted to a checkable definition when the knowledge base is merged |

The `x-carverflow-*` extension keywords carry the implementation's earlier internal name; they are part of the frozen artifact format and are kept as they are.

## Known debts (recorded when approved; repaid at the next approved contract change)

| Id | Content | Origin | Status |
|---|---|---|---|
| KD-1 | The `app_profile` shape embedded in `run_config.schema.json` was a looser version frozen before `app_profile.schema.json`; to be tightened to `$ref: app_profile.schema.json` at the next approved change. | app_profile schema review (2026-06-10); option (a) chosen: keep as is and record the debt | **repaid** (2026-06-10, tightened to `$ref` with decision record 002 §7.3; the run_config example follows) |
| KD-2 | `augmented_oas.schema.json#/$defs/ui_observation` and `initial_oas.schema.json#/$defs/observation` are **duplicate definitions** (the former = the latter's shape + a `source` const). Not expressed as a `$ref` because probe observations reference a different object (probe_id vs run_id+entry_index) and the initial_oas observation is `additionalProperties:false`, so `source` cannot be added. **Coupling:** a field change on either side must be mirrored on the other. | contract-change review of decision record 004 §7 (2026-06-10) | open (the duplication is accepted; to be removed if a shared `$defs` file is introduced) |
