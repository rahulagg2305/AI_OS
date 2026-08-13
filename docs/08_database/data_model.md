# Data Model – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Data Model
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-26 (§5 catalog.agents/catalog.tools: added required entrypoint column, closing a gap against the Agent/Tool Contracts)

---

## 1. Purpose

This document defines the persistent data model of AI_OS: the tables, their purpose, the invariants they enforce, and the rules governing their evolution. It is the reference for Alembic migrations.

Governing decisions: [ADR-0011](../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md), [ADR-0013](../18_decision_log/adr/ADR-0013-search-and-vector-store.md), [ADR-0017](../18_decision_log/adr/ADR-0017-observability-stack.md).

---

## Implementation Status (2026-07-28)

**This document is unusually accurate already** — most non-obvious gaps (the `EchoAgent`/`EchoTool` dispatch note in §4.3, the schema-only `entrypoint` column in §5, the deferred/retrofitted foreign keys in §5–§6) are already documented inline at the point they matter, a pattern this audit did not need to correct. Two things verified this step are worth stating explicitly because they are not yet inline:

- **All 29 Alembic migrations are real** (`kernel/alembic/versions/0001…0029`) and every schema in §3 (`workflow`, `catalog`, `evaluation`, `trace`, `governance`, `platform`) has a corresponding migration. **`knowledge` (§7) is the newest**, added by migration `0029_knowledge_schema` (2026-07-27) — schema and tables only, per that migration's own docstring: no reader, no Retrieval Service, and no Knowledge/Memory Manager exist to query them. A narrow, real write path exists for two of the four tables — `persistence/knowledge_writer.py` writes `knowledge.documents` and `knowledge.chunks` only (already-chunked input, no chunking/hashing/fetching of its own) — but `embeddings` and `memory_items` have no writer at all yet, and the documented HNSW index on `embeddings.embedding` is deliberately not created (no fixed vector dimension has been decided).
- **§13's SQLite development mode is not real.** A repo-wide, case-insensitive search for `sqlite` inside `kernel/` returns **zero matches** — there is no SQLite dialect wiring, no conditional repository implementation, and no test fixture using it anywhere. Every real repository and every integration test targets PostgreSQL only (via `tests/integration/_postgres_fixture.py`). This section's capability-gap table is accurate in spirit (Postgres-only features would indeed be absent) but the premise — that SQLite is "supported... through the same repository interfaces" today — is not true; it describes a target, not a working mode.
- **§11 Retention is policy only, exactly as its own text says** ("Retention values are configuration, not code") — but no archival or pruning job exists for any listed table yet (`workflow_events`, `audit_log`, `llm_calls`, etc. all grow unbounded today); this is a documented future capability, not a gap this document was overstating.

Authoritative, always-current status: `../19_roadmap/feature_inventory.md`.

---

## 2. Conventions

| Rule | Detail |
|---|---|
| Database | PostgreSQL 16 |
| Identifiers | `snake_case` tables (plural), `snake_case` columns |
| Primary keys | Prefixed ULID text, for example `wf_01HQ…`, `stp_01HQ…`. Sortable, opaque, safe in URLs and logs. |
| Timestamps | `TIMESTAMPTZ NOT NULL`, UTC, database-generated |
| Money | `NUMERIC(14,6)` for USD. Never floating point. |
| Structured payloads | `JSONB` with a `schema_version` column alongside |
| Deletes | Soft delete (`archived_at`) for user-facing entities. Event and audit tables are never deleted by the application. |
| Enums | Text with a `CHECK` constraint, not PostgreSQL `ENUM` — adding a value stays a data-only migration |
| Content addressing | Artifacts referenced as `sha256:<hex>`, never stored inline |

---

## 3. Schemas

| Schema | Contents |
|---|---|
| `workflow` | Workflow definitions, instances, events, steps, leases, approvals |
| `catalog` | Packs, agents, tools, prompts, workflow definitions registry |
| `evaluation` | Experiments, runs, metrics, gate results, run manifests |
| `knowledge` | Documents, chunks, embeddings, memory items |
| `trace` | Traceability artifacts and links |
| `governance` | Audit log, configuration change history |
| `security` | Role grants (`P03-S05-M14-T07`) |
| `context` | Context assembly audit records (`P02-S03-M08-T10`) |
| `platform` | Outbox, idempotency keys, schema metadata |

---

## 4. Workflow State

The core of the design: an append-only event log plus a materialised snapshot, written in **one transaction** so they can never disagree.

### 4.1 `workflow.workflow_instances`

| Column | Type | Notes |
|---|---|---|
| `workflow_id` | text PK | `wf_…` |
| `definition_id` | text NOT NULL | Stable across every version of a definition (never changes once assigned). Together with `definition_version`, a composite FK → `catalog.workflow_definitions` (`definition_id`, `version`) |
| `definition_version` | text NOT NULL | Pinned at start. See `definition_id` — the pair jointly forms the composite FK |
| `status` | text NOT NULL | `created`, `running`, `waiting_for_human`, `waiting_for_retry`, `quality_gate_failed`, `compensating`, `completed`, `failed`, `cancelled` — **the canonical state list** |
| `current_step_id` | text NULL | |
| `inputs` | jsonb NOT NULL | |
| `outputs` | jsonb NULL | |
| `experiment_id` | text NULL | FK → `evaluation.experiments` |
| `run_manifest_id` | text NULL | FK → `evaluation.run_manifests` |
| `principal_id` | text NOT NULL | Who started it |
| `principal_permissions` | jsonb NULL | The triggering principal's real, computed `SecurityContext.permissions`, captured once at trigger time (`P03-S05-M14-T09`, migration `0031`) — `NULL` means no real `SecurityContext` reached the trigger call, so the principal term of ADR-0023's monotonic-narrowing chain is unenforced for this instance, never an empty-array "holds nothing" claim. Read back at every later agent/tool resolution (`ai_os_kernel.workflow_engine.registry`) |
| `scheduled_at` | timestamptz NULL | The Scheduler's own data (`P02-S01-M05-T13`, migration `0032`) — `NULL` means no scheduled start was requested (must be started by an explicit `start()` call); a real timestamp means "start no earlier than this," read by `ai_os_kernel.workflow_engine.scheduler.WorkflowScheduler` |
| `retried_at` | timestamptz NULL | The **retry epoch** (`P06-S01-M36-T05`, migration `0039`) — `NULL` means this instance has never been retried by an operator, which is every row predating `POST /workflows/{id}/retry`; a real timestamp means only step failures at or after it count against the definition's `retryPolicy`. Read by `SqlWorkflowInstanceRepository.step_failure_stats`, which joins this table rather than taking the value as an argument, so the repository Protocol signature is unchanged and no caller can silently skip the filter. Without it a retry would be near-useless: a `failed` instance has already spent both retry bounds, so the first new failure would re-fail it immediately |
| `last_event_seq` | bigint NOT NULL | Sequence of the last applied event |
| `error` | jsonb NULL | `StructuredError` |
| `total_cost_usd` | numeric(14,6) NOT NULL DEFAULT 0 | |
| `total_tokens` | bigint NOT NULL DEFAULT 0 | |
| `created_at`, `updated_at`, `completed_at` | timestamptz | |

Indexes: `status`, `definition_id`, `experiment_id`, `created_at DESC`.

### 4.2 `workflow.workflow_events` — append-only

| Column | Type | Notes |
|---|---|---|
| `event_id` | text PK | `evt_…` |
| `workflow_id` | text NOT NULL | FK |
| `seq` | bigint NOT NULL | **UNIQUE (`workflow_id`, `seq`)** — per-instance ordering |
| `event_type` | text NOT NULL | `workflow.started`, `step.started`, `step.completed`, `agent.invoked`, `tool.invoked`, `llm.called`, `gate.evaluated`, `approval.requested`, `approval.decided`, `state.transitioned`, `workflow.completed`, … |
| `schema_version` | int NOT NULL | |
| `payload` | jsonb NOT NULL | |
| `trace_id` | text NULL | |
| `step_id`, `agent_id` | text NULL | |
| `occurred_at` | timestamptz NOT NULL | |

`UPDATE` and `DELETE` are **revoked for the application role**. Corrections are new compensating events. This table is the replay and forensic substrate; folding it reconstructs any instance's history exactly.

Indexes: `(workflow_id, seq)`, `event_type`, `occurred_at DESC`, `trace_id`.

### 4.3 `workflow.workflow_steps`

Materialised per-step state: `step_id` PK, `workflow_id`, `step_name`, `step_type`, `status`, `attempt`, `agent_id`, `tool_id`, `prompt_id`, `prompt_version`, `model_alias`, `inputs`, `outputs`, `error`, `idempotency_key`, `usage` (jsonb), `started_at`, `completed_at`.

`UNIQUE (workflow_id, step_name, attempt)` — makes retries explicit and countable rather than overwriting history.

`agent_id`/`tool_id`/`prompt_id`/`prompt_version`/`model_alias` record all five of workflow_architecture.md's Step Contract fields (`agentId`/`toolId`/`promptId`/`promptVersion`/`modelAlias`) exactly as the executed step *declared* them, copied straight from the step at write time. This is not yet which agent or tool a step *actually ran through*, nor which prompt/model an agent actually used: every step still dispatches to the same `EchoAgent`/`EchoTool` regardless of what it declares, and nothing calls the Prompt Engine or LLM Gateway from a step — resolving a declared id to a different real implementation needs a Capability Manager registry that does not exist yet. All five columns are nullable (a step may declare none, some, or all of them, per the Step Contract's own rules) and carry no foreign key: `prompt_id`/`prompt_version` are typed `text`, matching `evaluation.llm_calls.prompt_id`/`prompt_version` exactly (§6), but unlike that table's own composite foreign key to `catalog.prompts (prompt_id, version)`, no such constraint exists here — no writer exists yet for `catalog.prompts` (only a reader), so a real foreign key would make it impossible to ever record a declared `prompt_id` that has no matching catalog row, the same reasoning `agent_id`/`tool_id` were already exempted under.

### 4.4 `workflow.workflow_leases`

| Column | Type | Notes |
|---|---|---|
| `lease_id` | text PK | |
| `workflow_id` | text NOT NULL UNIQUE | One lease per instance |
| `worker_id` | text NOT NULL | |
| `acquired_at` | timestamptz NOT NULL | |
| `expires_at` | timestamptz NOT NULL | Reclaimed after expiry |
| `heartbeat_at` | timestamptz NOT NULL | |

Claimed with `SELECT … FOR UPDATE SKIP LOCKED`. This table is what lets multiple workers run without a broker; expiry is what makes a crashed worker's work recoverable ([ADR-0020](../18_decision_log/adr/ADR-0020-deployment-topology-and-scaling.md)).

### 4.5 `workflow.approvals`

`approval_id` PK, `workflow_id`, `step_id`, `approval_class`, `title`, `description`, `context_digest` (sha256 of exactly what was shown at decision time), `options` (jsonb), `status` (`pending`/`approved`/`rejected`/`changes_requested`/`timed_out`/`cancelled`), `decided_by`, `decision_comment`, `requested_at`, `expires_at`, `decided_at`.

`context_digest` exists so that "what did the approver actually see?" is answerable months later.

---

## 5. Catalog

| Table | Purpose |
|---|---|
| `catalog.packs` | `pack_id` PK, `version`, `state` (`discovered`/`validated`/`installed`/`configured`/`activated`/`deactivated`/`failed`/`uninstalled` — the canonical pack lifecycle), `manifest` (jsonb), `sdk_version`, `min_kernel_version`, `installed_at`, `activated_at`, `health` (jsonb) |
| `catalog.pack_state_transitions` | `transition_id` PK, `pack_id` (FK → `catalog.packs.pack_id`), `from_state`, `to_state`, `reason`, `actor`, `occurred_at` — append-only lifecycle history |
| `catalog.agents` | `agent_id` PK (fully qualified `pack_id/agent_slug`), `pack_id`, `version`, `entrypoint`, `input_schema`, `output_schema`, `required_permissions`, `required_tools` |
| `catalog.tools` | `tool_id` PK, `pack_id`, `version`, `entrypoint`, `trust_tier`, `input_schema`, `output_schema`, `required_permissions` |
| `catalog.prompts` | `prompt_id` (stable across versions, never changes), `version`, **PRIMARY KEY (`prompt_id`, `version`)**, `pack_id`, `content`, `input_schema`, `content_hash` — versions are immutable |
| `catalog.workflow_definitions` | `definition_id` (stable across versions, never changes), `version`, **PRIMARY KEY (`definition_id`, `version`)**, `pack_id`, `graph` (jsonb), `inputs_schema`, `outputs_schema`, `declared_permissions`, `validated_at` |

Prompt and workflow-definition versions are immutable: a change creates a new version row sharing the same `definition_id`/`prompt_id` as every other version, distinguished by `version`. Both `catalog.workflow_definitions` and `catalog.prompts` reflect this directly: neither `definition_id` nor `prompt_id` alone is unique (every version of one definition or prompt shares it), so each primary key is a composite (`definition_id`, `version`) / (`prompt_id`, `version`) pair. `workflow.workflow_instances`' `definition_id` + `definition_version` columns (§4.1) form a composite foreign key against `catalog.workflow_definitions`' pair, and `evaluation.llm_calls`' `prompt_id` + `prompt_version` columns (§6) form a composite foreign key against `catalog.prompts`' pair — resolving what was previously an open ambiguity between each pair of tables' treatment of the shared id. This is what makes run manifests meaningful.

`catalog.agents`/`catalog.tools` both carry `entrypoint` (text, not null) — a real, pre-existing gap discovered while building a `catalog`-backed `AgentRegistry`/`ToolRegistry`: the Agent Contract and Tool Contract have always required an entrypoint, and `platform_sdk/schemas/manifest.schema.json`'s own `agents[]`/`tools[]` entries already require and validate one (pattern `^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$`, "Python import path, `module.path:ClassName`"), but neither catalog table had ever recorded it. No `CHECK` constraint mirrors that pattern — format validation for it is the Manifest Loader's job at manifest-load time, the same convention `agent_id`/`tool_id`'s own documented id shapes already follow without a Postgres-level format constraint either. Schema only: nothing reads this column yet, and no entrypoint-loading mechanism (dynamic import, construction) exists — that remains Capability Manager territory (Stage C).

`catalog.prompts` originally shipped with `prompt_id` alone as its primary key (before this composite-key resolution), which made it impossible to store two versions of the same prompt as separate rows — discovered while building a second `PromptEngine` implementation against it. The migration to the composite key is safe by construction: a value already unique on `prompt_id` alone is trivially still unique on `prompt_id` plus `version`, so no existing row could violate the new, strictly broader constraint — the identical reasoning already applied to `catalog.workflow_definitions`' own composite-key migration.

**`catalog.packs`' primary key is `pack_id`** — one row per pack, holding its current installed state; version history of a pack's own state (not a workflow definition's) is separately captured, append-only, in `pack_state_transitions`. **`catalog.pack_state_transitions`' primary key is `transition_id`**, with `pack_id` a required foreign key back to `catalog.packs.pack_id` — every transition row belongs to exactly one existing pack; a transition row does not, and cannot, outlive or precede the pack it describes.

---

## 6. Evaluation

| Table | Purpose |
|---|---|
| `evaluation.experiments` | `experiment_id` PK, `name`, `description`, `definition_id` + `definition_version` (**composite FK → `catalog.workflow_definitions` (`definition_id`, `version`)**), `variables` (jsonb — what is deliberately varied), `pinned_conditions` (jsonb), `runs_per_variant` int NOT NULL, `status`, `created_by` |
| `evaluation.experiment_runs` | `run_id` PK, `experiment_id`, `workflow_id`, `variant_key`, `model_alias`, `resolved_model_id`, `replicate_index`, `served_from_cache` bool NOT NULL, `status` |
| `evaluation.run_manifests` | `run_manifest_id` PK, `workflow_id`, `manifest` (jsonb), `manifest_hash` — the complete pinned-conditions bundle required by [ADR-0022](../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) |
| `evaluation.metrics` | `metric_id` PK, `workflow_id`, `run_id` (FK → `evaluation.experiment_runs.run_id`), `metric_name`, `metric_value` numeric(20,6), `unit`, `source_component`, `recorded_at` |
| `evaluation.gate_results` | `result_id` PK, `workflow_id`, `step_id`, `gate_id`, `gate_version`, `status`, `severity`, `metrics` (jsonb), `messages` (jsonb), `duration_ms`, `created_at` (added 2026-08-13, migration `0038_gate_results_created_at`, server-defaulted `now()` and indexed — this table had no timestamp at all, which is what blocked `GET /gates/trends`; existing rows were backfilled with the migration's own execution time rather than a fabricated history, the identical honest choice `0035` records for `llm_calls`) |
| `evaluation.llm_calls` | `call_id` PK, `workflow_id`, `step_id`, `agent_id` (FK → `catalog.agents.agent_id`), `prompt_id` + `prompt_version` (**composite FK → `catalog.prompts` (`prompt_id`, `version`)**), `model_alias`, `provider`, `model_id`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `cost_usd` numeric(18,6), `latency_ms`, `stop_reason`, `retries`, `fallback_used`, `degradations` (jsonb), `created_at` (timestamptz, `server_default now()`) |

`evaluation.llm_calls` is the single authoritative record of model spend. `replicate_index` and `runs_per_variant` exist because comparisons must report variance across repeated runs, not a single point value. `created_at` (`P07-S03-M42-T02`) was added retroactively — every prior row from before this step has no real recorded time, backfilled by Postgres's own `server_default` at migration time, not a fabricated value — added because Cost Anomaly Alerting (NFR-045) needs a genuine per-call timestamp to bucket spend by hour, which nothing in this table previously carried.

`metrics.metric_value` and `llm_calls.cost_usd` intentionally use wider precision (`NUMERIC(20,6)` and `NUMERIC(18,6)` respectively) than this document's general `NUMERIC(14,6)` money convention (§2) — approved exceptions for these two columns specifically, not an inconsistency: `metric_value` is not always USD-denominated (it holds whatever a metric measures — latency, accuracy, a count, a cost), and `cost_usd` is given its own wider precision independent of the general convention. `llm_calls.agent_id` is a real foreign key because `catalog.agents` already exists and uses exactly the id shape that column stores. `llm_calls.prompt_id`/`prompt_version` were originally a single-column foreign key to `catalog.prompts.prompt_id` alone; once `catalog.prompts` gained its own composite primary key (`prompt_id`, `version` — see §5), a single-column foreign key on `prompt_id` alone was no longer possible (Postgres requires the referenced columns to carry a unique constraint or primary key of the exact same shape), so it was retrofitted to a composite foreign key against the pair. This also closes a latent correctness gap: before the retrofit, `prompt_version` was not checked against `catalog.prompts` at all, so an `llm_calls` row could reference a real `prompt_id` with a `prompt_version` that did not match any actual row.

`experiments.definition_id`/`definition_version` and `metrics.run_id` were both deliberately deferred, undocumented-as-foreign-keys, until their blockers resolved: the former needed the same `definition_id`/`version` composite-key resolution `catalog.workflow_definitions` itself needed (§5) plus a real writer to safely reference (`SqlWorkflowDefinitionCatalog`); the latter simply was not part of any approved step's scope until now. Both are now real foreign keys — `experiments.definition_id`/`definition_version` a composite FK against `catalog.workflow_definitions (definition_id, version)`, mirroring `workflow_instances`' identical retrofit; `metrics.run_id` a single-column FK against `experiment_runs.run_id`, already indexed since `metrics` was created.

---

## 7. Knowledge and Retrieval

| Table | Purpose |
|---|---|
| `knowledge.documents` | `document_id` PK, `source_uri`, `content_hash`, `media_type`, `project_id` NULL, `trust` (`trusted`/`untrusted`), `ingested_at`, `archived_at` |
| `knowledge.chunks` | `chunk_id` PK, `document_id`, `ordinal`, `content` text, `token_count`, `chunk_strategy_version`, `content_tsv` tsvector (generated), `metadata` jsonb |
| `knowledge.embeddings` | `embedding_id` PK, `chunk_id`, `embedding vector(N)`, `embedding_model_id`, `embedding_model_version`, `dimensions`, `index_generation` |
| `knowledge.memory_items` | `memory_id` PK, `memory_type` (`workflow`/`engineering`/`asset`), `content`, `source_workflow_id`, `quality_signal` numeric NULL, `promoted_at` NULL, `expires_at` NULL, `provenance` jsonb |

Indexes: GIN on `chunks.content_tsv`; HNSW on `embeddings.embedding` (cosine).

**Two rules that make retrieval reproducible.** A query only compares embeddings sharing the same `embedding_model_id` + `embedding_model_version`. `index_generation` is pinnable in a search request, so an experiment can retrieve against a fixed index even as ingestion continues. `trust` propagates from document to chunk to `ContextItem`, which is how the injection controls in the Security Architecture stay enforceable.

---

## 8. Traceability

| Table | Purpose |
|---|---|
| `trace.artifacts` | `artifact_key` PK, `artifact_type` (`requirement`/`architecture_element`/`adr`/`design_element`/`module`/`source_file`/`test_case`/`documentation`/`release`/`workflow_run`), `external_id`, `title`, `location`, `version` |
| `trace.links` | `link_id` PK, `source_key`, `relationship` (`implements`/`verifies`/`realizes`/`affects`/`contains`/`produced`/`applies_to`), `target_key`, `confidence` (`confirmed`/`inferred`/`provisional`), `created_by`, `created_by_type` (`agent`/`user`/`process`), `created_at`, `closed_at` NULL |

`UNIQUE (source_key, relationship, target_key)` where `closed_at IS NULL`. Impact analysis uses recursive CTEs over `trace.links` — no graph database is required at this scale ([ADR-0011](../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)).

---

## 9. Governance

### 9.1 `governance.audit_log` — append-only, hash-chained

| Column | Type | Notes |
|---|---|---|
| `audit_id` | text PK | |
| `seq` | bigserial NOT NULL UNIQUE | Global ordering |
| `event_type` | text NOT NULL | `auth.success`, `auth.failure`, `authz.denied`, `approval.decided`, `secret.accessed`, `config.changed`, `pack.state_changed`, `sandbox.executed`, `git.write`, … |
| `principal_id`, `principal_type` | text | |
| `resource_type`, `resource_id` | text NULL | |
| `outcome` | text NOT NULL | `allowed` / `denied` / `success` / `failure` |
| `detail` | jsonb NOT NULL | Never contains secret values |
| `trace_id` | text NULL | |
| `prev_hash` | text NULL | SHA-256 of the previous row's canonical form |
| `row_hash` | text NOT NULL | SHA-256 of this row's canonical form including `prev_hash` |
| `occurred_at` | timestamptz NOT NULL | |

`UPDATE`/`DELETE` revoked. A scheduled job verifies the chain and alerts on a break ([ADR-0017](../18_decision_log/adr/ADR-0017-observability-stack.md)).

### 9.2 `governance.config_changes`

`change_id` PK, `config_key`, `old_value_digest`, `new_value_digest`, `changed_by`, `reason`, `changed_at`. Digests rather than values, so a secret reference change never leaks a value.

---

## 9a. Security (`P03-S05-M14-T07`)

Its own bounded context, distinct from `governance` — a real, previously-undocumented gap: role *administration* (granting/revoking a role for a principal) had no schema at all before this table, since every role before it came solely from a bearer token's own `roles` claim (`security_manager.token_verifier`), never from persisted state. Inserted here (not renumbering `10. Platform` onward) to avoid invalidating every existing cross-reference to a numbered section below it.

### 9a.1 `security.role_grants`

| Column | Type | Notes |
|---|---|---|
| `grant_id` | text PK | |
| `principal_id` | text NOT NULL | The principal the role is granted to — a bearer token's own `sub` claim |
| `role` | text NOT NULL | The exact role string, e.g. `approver:approve-git-push` — the same closed-vocabulary-family ADR-0023 §4.2 documents, not validated against a fixed list here (the `approver:<class>` family is open-ended by class name, matching `approval_class`'s own unconstrained shape in `workflow.approvals`) |
| `status` | text NOT NULL | `active` / `revoked` |
| `granted_by`, `granted_reason`, `granted_at` | text, text, timestamptz NOT NULL | Attributable, per this table's own "every grant/revoke is audited" requirement — mirrored again in `governance.audit_log` (`security.role_granted`/`security.role_revoked`), never only here |
| `revoked_by`, `revoked_reason`, `revoked_at` | text, text, timestamptz NULL | `NULL` until revoked; a row is never deleted, only transitioned |

A partial unique index (`principal_id`, `role`) `WHERE status = 'active'` prevents two simultaneously-active grants of the identical role to the identical principal — a real, enforced invariant, not merely a convention. `UPDATE` is real and expected here (unlike `governance.audit_log`'s own append-only rule) — a grant transitions `active` -> `revoked` in place, its own real audit trail living in `governance.audit_log`, not in row history.

Real, disclosed, narrower-than-full-RBAC scope: only the `admin`-gated grant/revoke this ticket's own Input/Output asks for is built — no self-service request flow, no expiring grants, no bulk operations.

---

## 9b. Context Assembly Audit (`P02-S03-M08-T10`)

Its own bounded context, distinct from `governance` — the same "genuinely distinct concern, not a security control" reasoning `9a`'s own header gives for `security`. `context_manager.md` §9 names the fields a real audit record needs; this section is the first place any of them get a documented schema (§3's schema list had no `context` row before this table). Inserted here (not renumbering `10. Platform` onward), the same convention `9a` itself established.

### 9b.1 `context.context_assemblies`

| Column | Type | Notes |
|---|---|---|
| `assembly_id` | text PK | `asm_<ULID>` (`ai_os_kernel.context_manager.ids.new_assembly_id`), already generated per call before this table existed |
| `workflow_id`, `step_id` | text NOT NULL | From the originating `ContextRequest` — "exactly what context *each step* actually received" (this ticket's own Goal) needs both, not only `workflow_id` |
| `agent_id` | text NULL | From `ContextRequest.agent_id` — optional there, so optional here |
| `sources_queried` | jsonb NOT NULL | `AssembledContext.sources_queried`, a JSON array of `SourceType` values |
| `included_items` | jsonb NOT NULL | `AssembledContext.items`, full fidelity per item (`content`, `provenance`, `relevance_score`, `token_count`, `trust`) — enables §9's own "exact replay," not only a summary |
| `items_excluded_count` | integer NOT NULL | `AssembledContext.items_excluded_count` |
| `total_tokens` | integer NOT NULL | `AssembledContext.total_tokens` |
| `recorded_at` | timestamptz NOT NULL | Database-generated at insert — §9's own "Timestamp" |

Two of §9's five named fields are real, disclosed gaps, not silently omitted: **Trace ID** has no column, because no `TraceContext` (`llm_gateway.models.TraceContext`) is threaded into context assembly anywhere in this codebase — `ContextRequest` carries no trace identifier to record. **Which specific items were excluded** is not recoverable beyond the count: `AssembledContext` itself (§6) only ever carries a count, not the excluded items' own identities — a pre-existing limitation of the Filter/Ranker's own return shape (`P02-S03-M08-T09`), not something this table invents. Both are recorded here exactly as they are, not fabricated to appear complete.

No foreign key to `workflow.workflow_instances`: an assembly record should outlive and stay insertable independent of that row's own lifecycle, the same "loose pointer, not a hard dependency" reasoning `governance.audit_log` already gives for referencing no single table.

---

## 10. Platform

| Table | Purpose |
|---|---|
| `platform.event_outbox` | `outbox_id` PK, `event_type`, `schema_version`, `payload` jsonb, `trace_id`, `created_at`, `dispatched_at` NULL, `attempts` int. Written **in the same transaction as the state change that produced the event** ([ADR-0012](../18_decision_log/adr/ADR-0012-event-bus.md)). |
| `platform.idempotency_keys` | `key` PK, `principal_id`, `request_digest`, `response` jsonb, `status_code`, `created_at`, `expires_at` (24 h) |
| `platform.schema_metadata` | Alembic revision plus `index_generation` counters for retrieval |

---

## 11. Retention

| Data | Retention | Then |
|---|---|---|
| `workflow_events` | 180 days hot | Archived to object storage in a replayable format, then pruned |
| `workflow_instances` | Indefinite (metadata only) | — |
| `audit_log` | 7 years | Archived, never deleted while the chain must verify |
| `llm_calls` | 2 years | Aggregated, then pruned |
| `knowledge.documents` for ingested third-party repositories | Per project policy, default 90 days after last use | Purged |
| Idempotency keys | 24 hours | Deleted |
| Artifacts (blob storage) | Per project policy | Lifecycle rules |

Retention values are configuration, not code. Archival of `workflow_events` must preserve replayability, so the archive format is the event rows themselves, not a summary.

---

## 12. Migration Rules

1. Every change is an Alembic migration, reviewed like code.
2. **Expand → migrate → contract** for anything backward-incompatible: add the new shape, dual-write, backfill, switch reads, then remove the old shape in a later release. Never a single destructive migration.
3. Adding a column requires a default or nullability; no table rewrite on a large table without a plan.
4. Production schema changes require human approval ([ADR-0007](../18_decision_log/adr/ADR-0007-human-governance-for-critical-decisions.md)).
5. Every migration is tested against a seeded database in CI, and downgrade paths are tested for the current and previous release.
6. Changing `JSONB` payload structure requires incrementing the row's `schema_version` and keeping a reader for the previous version until the retention window for that version has passed.

---

## 13. SQLite Development Mode — Capability Gap

SQLite is supported for single-process local development through the same repository interfaces, with these documented absences ([ADR-0011](../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md)):

| Feature | SQLite |
|---|---|
| `FOR UPDATE SKIP LOCKED` leasing | Absent — single worker only |
| pgvector / vector search | Absent — retrieval work requires Postgres |
| Full-text search | Reduced (FTS5, different ranking) |
| `JSONB` operators | Reduced |
| Concurrent writers | Not supported |

SQLite is **not a supported production configuration**. Any work touching retrieval, leasing, or concurrency must use a Postgres container.

---

## 14. Final Authority

Order of precedence:

1. Project Constitution
2. Architecture Decision Records
3. Data Model (this document)
4. Alembic migrations
5. Source Code

---

## 15. Related Documents

- [`../03_architecture/workflow/state_management.md`](../03_architecture/workflow/state_management.md) — the §4 workflow-state design this table set implements; only 3 of the 9 `status` values are ever written
- [`../03_architecture/kernel/knowledge_manager.md`](../03_architecture/kernel/knowledge_manager.md) — the intended owner of §7's tables, currently an untouched stub
- [ADR-0011](../18_decision_log/adr/ADR-0011-persistence-and-workflow-state.md) · [ADR-0013](../18_decision_log/adr/ADR-0013-search-and-vector-store.md) · [ADR-0017](../18_decision_log/adr/ADR-0017-observability-stack.md) — the three decisions this document implements
- [`../19_roadmap/feature_inventory.md`](../19_roadmap/feature_inventory.md) — live build status
