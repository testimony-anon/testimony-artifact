# Vendored official meta-schemas (frozen copies)

The contracts define only the pipeline's own constraints precisely; full validity of external standard formats is checked against the frozen copies of the official meta-schemas kept here (usable offline).

| Directory | Content | Source | Retrieved |
|---|---|---|---|
| `openapi-3.1/schema.json` | OpenAPI 3.1 official meta-schema (2022-10-07 edition, JSON Schema 2020-12 dialect) | https://spec.openapis.org/oas/3.1/schema/2022-10-07 | 2026-06-10 |
| `har-1.2/*.json` (18 files) | HAR 1.2 schema (draft-06 dialect; the member files reference each other by `$ref`) | https://github.com/ahmadnassri/har-schema (MIT License) | 2026-06-10 |

Note: the HAR 1.2 specification (a W3C draft) has no official machine-readable schema; the community de-facto standard ahmadnassri/har-schema is used instead.

This directory is a frozen asset: do not edit by hand; upgrading a version is a breaking contract change that requires a decision record.
