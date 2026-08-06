# API Contract Boundary

**Status:** Active · **Introduced:** Phase R2 (2026-07-31)

The mechanism that lets a Dashboard-focused (or CLI-focused) session read
**only the API contract**, never Kernel internals.

## What already existed (verified, Phase R1/R2)

The boundary was **already declared, and already gated in CI** — the
missing piece was the artifact itself:

- **ADR-0018 line 27** already mandates it verbatim: *"API client and
  types generated from the published OpenAPI 3.1 document; generation
  runs in CI and drift fails the build."*
- **ADR-0018 rejects a hand-written client** explicitly: *"guarantees
  drift from the OpenAPI contract."*
- **`ci.yml` already has the gate** — the `frontend` job's
  `OpenAPI client drift check` step (`npm run check:api-client`),
  correctly no-op today because `dashboard/` does not exist.
- **FastAPI already generates the document** at runtime from the four
  registered routers (health, workflows, delivery_pipeline, packs).

What did **not** exist: any *committed* OpenAPI artifact. The document
only existed inside a running process, so nothing could consume it
without booting the Kernel and a database.

## The boundary rule

**`docs/07_api/openapi.json` is the contract.** It is a generated file.

- A **Dashboard/CLI session reads only that file.** It must not read
  `kernel/src/**`. This is the same one-way boundary
  `scripts/check_import_boundaries.py` already enforces for Capability
  Packs against the SDK.
- A **Kernel session may change the routes**, but the regenerated
  artifact must be committed in the same step — an uncommitted change to
  the HTTP surface is a defect.
- The artifact is exported by `scripts/export_openapi.py` with **no
  database required** (the app is constructed with an empty pack
  directory; route *shapes* do not depend on runtime state).
- Drift is a **build failure**, per ADR-0018 — enforced by
  `--check` in CI, exactly like the roadmap generated docs.

## Why this is the right seam

The HTTP surface is `frozen` under
`docs/process/interface_stability.md`: a breaking change needs a new path
prefix, never a silent edit to `/api/v1`. A generated artifact plus a
drift check turns that policy into a mechanism — the same move Phase R2
made for the roadmap trackers.

## Scheduled work

- `P06-S03-M39-T01` — Dashboard scaffold consuming only the generated
  client.

## Implementation Status (appended 2026-08-06, `P06-S01-M36-T01`)

The artifact and drift check described above are now real: the
committed `docs/07_api/openapi.json` had already gone stale (missing
the role-administration routes) with nothing to catch it — the "already
gated in CI" claim above was correct about the mechanism's *intent*
(ADR-0018 line 27, the `frontend` job's client-drift step) but the
Kernel side of the same rule had no enforcement of its own yet. Fixed
by `tests/contract/test_openapi_contract.py`, which `ci.yml`'s existing
`tests/contract` step already runs unconditionally.
