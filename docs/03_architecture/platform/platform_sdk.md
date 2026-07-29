# Platform SDK Specification – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Platform SDK Specification
**Version:** 1.1
**Status:** Approved as a specification — **not implemented** (see §1a)
**Last Updated:** 2026-07-28 (added Implementation Status and Related Documents; every claim that this surface exists in code corrected — it does not)

**Previously:** 2026-07-25 (v1.0)

---

## 1. Purpose

The Platform SDK (`ai-os-sdk`, package `ai_os_sdk`) is intended to be the **only** interface between Capability Packs and the AI_OS platform. It defines every contract a pack may depend on, every data model crossing the boundary, and the testing suite that proves compliance.

This document specifies that surface. It is the contract the Kernel must implement and packs must code against.

> **⚠ Read §1a before treating anything below as existing code.** Every Protocol, model, error class, and test suite in this document is a **design specification with no implementing package**. Nothing described here can be imported today.

This document is subordinate to:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Capability Pack Contract
5. Kernel Architecture

Governing decisions: [ADR-0001](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md), [ADR-0004](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md), [ADR-0008](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md), [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md).

---

## 1a. Implementation Status (2026-07-28)

**Built:** one file. `../../../platform_sdk/schemas/manifest.schema.json` — the machine-readable Capability Pack manifest schema (JSON Schema draft 2020-12), which is real, versioned, and actively enforced by the Manifest Loader.

**That is the entirety of `platform_sdk/` on disk.** There is **no `ai-os-sdk` distribution and no importable `ai_os_sdk` package**. It is not a workspace member in `../../../pyproject.toml` (it is listed there under "Planned, not yet scaffolded"), has no `pyproject.toml` of its own, and contains no Python file whatsoever. `platform_sdk/contracts/`, `platform_sdk/models/`, `platform_sdk/sdk/`, `platform_sdk/utilities/`, and `platform_sdk/prompts/` are all **empty directories**. `platform_sdk/errors/` and `platform_sdk/testing/` — both named in §3, §4.4, and §9 — **do not exist at all**, not even as empty directories.

**Not built — i.e. everything else in this document:**

- **All 15 Protocol interfaces in §5** (`LLMGateway`, `PromptRegistry`, `ContextService`, `RetrievalService`, `MemoryService`, `ToolInvoker`, `EventBus`, `ConfigService`, `SecretResolver`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`). None exists as an SDK Protocol. Several have *unrelated, narrower, Kernel-internal* counterparts that are **not** this interface and are **not** pack-facing — for example `ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` (no `stream()`, no `embed()`, no `count_tokens()`), `ai_os_kernel.prompt_engine.catalog`, `ai_os_kernel.context_manager.manager.ContextManager`, `ai_os_kernel.secrets_manager.provider`. Five of the fifteen have no counterpart at any layer, because their whole subsystem is an empty stub package: `MemoryService`, `EventBus`, `TraceabilityService`, `QualityGateRegistry`, and `StorageService`. `SpeechGateway` has no code anywhere. **`ToolInvoker` does not exist in any form** — the closest real thing is the workflow-engine-internal `ToolStepExecutor` + `SandboxedCommandTool`, which is not a pack-facing interface.
- **All §4 boundary models** (`ArtifactRef`, `TraceContext`, `SecurityContext`, `AgentRequest`, `AgentResult`, `StepBudget`, `ToolRequest`, `ToolResult`, `StructuredError`, and the `LLMRequest`/`LLMResponse`/`UsageRecord`/`ProviderCapabilities` shapes in §5.1). The Kernel has its own internal Pydantic models under `ai_os_kernel.llm_gateway.models` and a `TraceContext` in `ai_os_kernel.observability.trace`; these are Kernel types, not SDK boundary types, and no pack contract is defined in terms of them.
- **The `AiOsError` exception hierarchy** (§4.4) — `AiOsError`, `TransientError`, `PermanentError`, `QualityError`, `InfrastructureError`, `BudgetExceededError`, `SecurityError`. **None of these classes exists anywhere in the codebase.** The LLM Gateway defines its own local `LLMProviderError`/`LLMRefusalError` in `ai_os_kernel/llm_gateway/errors.py` which inherit from nothing shared; the same is true of every other subsystem's `errors.py`. The `error_code` catalogue this document places in `platform_sdk/errors/` does not exist.
- **`PackContext` (§6)** — the object a pack is "handed". No such object exists; nothing constructs one.
- **The `CapabilityPack` Protocol and `PackRegistration` (§7)** as SDK types. The real `software-engineering` pack does expose an entry-point class, but it is typed against Kernel internals, not against an SDK Protocol.
- **SDK semantic versioning enforcement (§8).** Nothing has an SDK version to check, so the Manifest Loader cannot enforce `dependencies.sdkVersion`; that semantic rule is currently unenforceable rather than merely unimplemented.
- **`pack_contract_suite` (§9).** The 9-check compliance suite **does not exist**. No pack runs it, and no pack could. Today the only real validation of a pack is the manifest JSON Schema plus a handful of semantic rules in `ai_os_kernel/manifest_loader/`. In particular, checks 2–9 — entry-point resolution, I/O-model matching, workflow step resolution, `trust_tier` consistency, permission vocabulary, **the forbidden-import check**, prompt existence, and clean activation — are all unenforced.
- **The §10 prohibitions.** They remain the binding rules, but the sentence "Each of these is checked by the contract suite, by lint rules, or by the loader" is currently **false**: there is no contract suite, and no lint rule enforces the import boundary. They are honour-system rules today.

**This is exactly why Capability Packs currently import Kernel internals directly.** The `software-engineering` pack — the platform's own flagship pack — imports `ai_os_kernel.*` in every agent module and in its pipeline composition, because there is no SDK package for it to depend on instead and it genuinely needs a real LLM Gateway, Prompt Engine, and database connection. That is a live, knowing violation of §2 rule 1, §10, and the Capability Pack Contract's "Direct Kernel access is prohibited", recorded as a dated exception in `../capability_framework/capability_pack_contract.md` § Platform Interaction Rules and in each affected module's own docstring. **Scaffolding this document into a real `ai-os-sdk` package is what closes it** — and closing it is the single highest-leverage item this document implies.

Authoritative, always-current status: `../../19_roadmap/feature_inventory.md` (per-module completion table — see rows 18, 27, and 44) and `../../19_roadmap/implementation_status.md`. Build history: `../../19_roadmap/history/INDEX.md`.

---

## 2. Design Rules

1. **The SDK is the dependency floor.** `ai-os-sdk` depends on no other AI_OS distribution. A pack depending on `ai-os-kernel`, `ai-os-services`, or another pack fails CI ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)).
2. **Interfaces are `Protocol`s.** Structural typing, so adapters need no inheritance from SDK classes.
3. **Every boundary model is a Pydantic v2 model.** Validated on construction, at both ends.
4. **Packs receive capabilities, not the Kernel.** A pack is handed a `PackContext` carrying only what its manifest declared and was granted; anything else is not reachable because the object is absent ([ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md)).
5. **SDK versioning is semantic and enforced.** Packs declare `sdkVersion`; the loader refuses incompatible packs.
6. **No provider SDK, database driver, or HTTP client is re-exported.** Packs never gain transitive access to a provider.

---

## 3. Package Layout

The **intended** layout. None of these packages exists yet — see §1a.

```text
platform_sdk/
├── contracts/          # Protocol definitions (the interfaces below)   — empty directory
├── models/             # Pydantic boundary models                      — empty directory
├── errors/             # AiOsError hierarchy                           — DOES NOT EXIST
├── testing/            # pack_contract_suite, fakes, fixtures          — DOES NOT EXIST
├── utilities/          # ids, hashing, canonical JSON, time            — empty directory
├── prompts/            # (present on disk, undocumented)               — empty directory
└── schemas/
    └── manifest.schema.json    ← the ONLY real file in platform_sdk/
```

Any other document citing `platform_sdk/contracts/<x>.py`, `platform_sdk/errors/`, or `ai_os_sdk.<anything>` is citing a path that does not exist; treat such a citation as a specification reference, not a source reference.

---

## 4. Core Boundary Models

Presented as field contracts. Field names are normative.

### 4.1 Identity and provenance

```text
ArtifactRef        artifact_id: "sha256:<hex>"; media_type; size_bytes; uri
TraceContext       trace_id; span_id; workflow_id?; step_id?; agent_id?;
                   experiment_id?; run_id?
SecurityContext    principal_id; principal_type: user|service_account|agent;
                   roles[]; permissions[] (effective, already narrowed);
                   tenant_id (reserved, always "default" in v1)
                   -- immutable; may only be narrowed, never widened
```

### 4.2 Agent contract

```text
AgentRequest       agent_id; workflow_id; step_id; inputs (schema-validated);
                   context: AssembledContext; security: SecurityContext;
                   trace: TraceContext; budget: StepBudget; deadline: datetime

AgentResult        status: success|failure|partial;
                   outputs (schema-validated) | error: StructuredError;
                   artifacts: ArtifactRef[]; usage: UsageRecord;
                   traceability_links: TraceabilityLink[]

StepBudget         max_tokens?; max_cost_usd?; max_tool_calls?;
                   max_wall_seconds?
```

An agent implements:

```text
Agent (Protocol)
    agent_id: str
    version: str
    input_model:  type[BaseModel]
    output_model: type[BaseModel]
    async def execute(request: AgentRequest) -> AgentResult
```

Agents are stateless between invocations. Any state persists via Workflow State.

### 4.3 Tool contract

```text
ToolRequest        tool_id; inputs; workspace: WorkspaceHandle;
                   security: SecurityContext; trace: TraceContext;
                   timeout_seconds
ToolResult         status: success|failure; outputs | error: StructuredError;
                   artifacts: ArtifactRef[]; stdout_ref?; stderr_ref?;
                   exit_code?; duration_ms

Tool (Protocol)
    tool_id: str
    version: str
    trust_tier: Literal["tier1_sandboxed", "tier2_trusted"]
    required_permissions: frozenset[str]
    input_model / output_model
    async def invoke(request: ToolRequest) -> ToolResult
```

`trust_tier` is validated at pack load. Any tool that executes a command string, compiles, runs tests, installs dependencies, or processes untrusted repository content **must** be `tier1_sandboxed` ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

### 4.4 Error model

One taxonomy for the whole platform, matching `../workflow/error_handling_retry.md` §3/§8:

```text
StructuredError    error_code: str            # stable, catalogued
                   category: transient | permanent | quality |
                             infrastructure | budget | security
                   message: str               # human-readable, no secrets
                   retriable: bool
                   retry_after_seconds: float | None
                   details: dict | None
                   trace: TraceContext
```

Exception hierarchy: `AiOsError` → `TransientError`, `PermanentError`, `QualityError`, `InfrastructureError`, `BudgetExceededError`, `SecurityError`. Every exception carries an `error_code` and maps 1:1 onto `StructuredError`.

*Specification only; not yet implemented.* No class in that hierarchy exists in the codebase, and neither does the `error_code` catalogue. Each subsystem currently defines unrelated local exceptions in its own `errors.py` (for example `ai_os_kernel/llm_gateway/errors.py`), inheriting from nothing shared. Introducing the shared hierarchy is tracked as its own module (`../../19_roadmap/feature_inventory.md` row 44).

---

## 5. Platform Interfaces

Every interface below is **specified** as a `Protocol` in `ai_os_sdk.contracts`. These are the intended **complete** set of capabilities available to a Capability Pack.

*Specification only; not yet implemented.* `ai_os_sdk` is not an importable package (§1a). **No interface in this section exists as an SDK Protocol.** The table below records what, if anything, exists one layer down — a Kernel-internal type that is narrower, differently shaped, and not pack-facing. It is provided so a reader does not mistake a partial Kernel component for a delivered SDK contract.

| § | Interface | Nearest real code today | Gap |
|---|---|---|---|
| 5.1 | `LLMGateway` | `ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway` | `complete()` only — no `stream()`, `embed()`, `count_tokens()`; `capabilities()` exists separately as `CapabilityNegotiator` |
| 5.2 | `PromptRegistry` | `ai_os_kernel.prompt_engine.catalog` (`InMemoryPromptEngine`, `SqlPromptCatalog`) | No version resolution, no `cache_boundary_index` |
| 5.3 | `ContextService` | `ai_os_kernel.context_manager.manager.ContextManager` | 1 of 6 documented sources; no `trust` tagging, no filter/ranker |
| 5.4 | `RetrievalService` | `ai_os_kernel.persistence.knowledge_keyword_search` | Keyword mode only — no `vector`, no `hybrid`, no `index_generation` pinning, no permission predicates |
| 5.5 | `MemoryService` | **Nothing.** `ai_os_kernel/memory_manager/` is a docstring-only stub | Entire subsystem |
| 5.6 | `ToolInvoker` | **Nothing pack-facing.** `workflow_engine.step_executor.ToolStepExecutor` + `workflow_engine.sandboxed_tool.SandboxedCommandTool` cover a slice internally | No `ToolInvoker` Protocol or package exists anywhere; no permission enforcement, no `available_tools()` |
| 5.7 | `EventBus` | **Nothing.** `ai_os_kernel/event_bus/` is a docstring-only stub; the `platform.event_outbox` table exists unused | Entire subsystem |
| 5.8 | `ConfigService` | `ai_os_kernel.configuration_manager.loader.ConfigurationManager` | Not namespaced per pack; 3 of 7 precedence layers; no `flag()` |
| 5.9 | `SecretResolver` | `ai_os_kernel.secrets_manager` (`EnvSecretProvider`, `SecretValue`) | `env` backend only; masking is real, broker/TTL/rotation are not |
| 5.10 | `StorageService` | **Nothing.** No content-addressed artifact store exists | Entire service |
| 5.11 | `WorkspaceService` | **Nothing.** Sandbox temp directories only, per-invocation | Per-workflow-instance isolation is not yet mandatory or enforced |
| 5.12 | `Telemetry` | `ai_os_kernel.observability` (`logging`, `metrics`, `tracing`) | Real OTel spans + 1 metric, console exporters only; not namespaced `aios.pack.*` |
| 5.13 | `TraceabilityService` | **Nothing.** `ai_os_kernel/traceability_engine/` is a docstring-only stub; `trace.artifacts`/`trace.links` tables exist with no writer | Entire subsystem |
| 5.14 | `QualityGateRegistry` | **Nothing.** `ai_os_kernel/quality_gate_engine/` is a docstring-only stub | Entire subsystem; `quality_gate` workflow steps complete as no-ops |
| 5.15 | `SpeechGateway` | **Nothing.** No Speech Gateway code exists | Entire service |

### 5.1 `LLMGateway`

The single route to any model ([ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md)).

```text
async def complete(request: LLMRequest) -> LLMResponse
async def stream(request: LLMRequest) -> AsyncIterator[LLMStreamEvent]
async def embed(request: EmbeddingRequest) -> EmbeddingResponse
async def count_tokens(request: LLMRequest) -> int
def capabilities(alias: str) -> ProviderCapabilities
```

```text
LLMRequest         model_alias: str                  # NEVER a literal model id
                   messages: Message[]
                   system: SystemBlock[] | None
                   tools: ToolDefinition[] | None
                   tool_choice: auto|any|none|{tool:name} | None
                   response_format: JsonSchemaFormat | None
                   thinking: adaptive | disabled | None
                   effort: low|medium|high|xhigh|max | None
                   max_output_tokens: int
                   cache_hints: CacheHint[] | None
                   metadata: TraceContext
                   budget: StepBudget | None
                   -- no temperature / top_p / top_k: current models reject them

LLMResponse        content: ContentBlock[]     # text | tool_call | thinking
                   stop_reason: end_turn|max_tokens|tool_use|refusal|pause_turn
                   stop_details: {category, explanation} | None
                   usage: UsageRecord
                   provider: str; model_id: str; model_version: str
                   served_from_cache: bool

UsageRecord        input_tokens; output_tokens; cache_read_tokens;
                   cache_write_tokens; cost_usd; latency_ms;
                   provider; model_id; retries; fallback_used: bool

ProviderCapabilities
                   supports_tools; supports_parallel_tool_calls;
                   supports_structured_output; supports_streaming;
                   supports_thinking; supports_effort;
                   supports_prompt_caching; max_input_tokens;
                   max_output_tokens; supports_vision
```

**Degradation rules.** If a request uses a capability the routed provider lacks, the Gateway either (a) emulates it where faithful emulation is possible — for example structured output via a forced single-tool call — or (b) fails with `PermanentError(error_code="llm.capability_unsupported")`. It never silently drops a requested capability. Every degradation is recorded on the response and in telemetry, because a silent downgrade would corrupt cross-model comparison.

**Prohibited:** literal model IDs in pack code; any direct provider import; any HTTP call to a provider endpoint.

### 5.2 `PromptRegistry`

```text
async def render(prompt_id, variables, version=None) -> RenderedPrompt
async def get(prompt_id, version=None) -> PromptDefinition

RenderedPrompt     prompt_id; version; content; variables_used;
                   cache_boundary_index?   # prefix/suffix split for caching
```

Prompts are versioned pack assets. Rendering validates variables against the prompt's declared `input_schema`. The rendered result records `prompt_id` + `version` for the run manifest ([ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md)).

### 5.3 `ContextService`

The only route to knowledge and memory. Packs never query stores directly.

```text
async def assemble(request: ContextRequest) -> AssembledContext

ContextRequest     workflow_id; step_id; agent_id;
                   required_types: ContextType[]   # requirements, architecture,
                                                   # standards, prior_outputs,
                                                   # code, patterns, memory
                   query: str | None
                   token_budget: int
                   filters: dict | None

AssembledContext   items: ContextItem[]; total_tokens; sources_queried[];
                   items_excluded_count; assembly_id; index_generation

ContextItem        content; provenance: SourceRef; relevance_score;
                   token_count;
                   trust: Literal["trusted", "untrusted"]
```

**`trust` is mandatory and load-bearing.** Repository content, ingested documents, tool output, and web content are always `untrusted`. The Prompt Engine wraps untrusted items in explicit data boundaries, and untrusted content can never confer authority ([ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md)).

Context assembly is deterministic for a given request, index generation, and embedding model version.

### 5.4 `RetrievalService`

Lower-level search for packs that need it (primarily Project Intelligence). Consolidates knowledge and memory behind one seam.

```text
async def search(request: SearchRequest) -> SearchResults

SearchRequest      query; mode: keyword|vector|hybrid;
                   sources: SourceType[]; filters; limit;
                   index_generation: str | None   # pin for reproducibility
```

Results are permission-trimmed by SQL predicate, never post-filtered.

### 5.5 `MemoryService`

```text
async def write(item: MemoryWrite) -> MemoryRef
async def recall(request: MemoryQuery) -> MemoryItem[]
```

Writes are structured and mediated; a pack cannot write free-form memory. Memory never overrides authoritative documentation. Promotion of workflow memory to engineering memory is a platform decision, not a pack decision.

### 5.6 `ToolInvoker`

```text
async def invoke(tool_id, inputs, *, timeout=None) -> ToolResult
def available_tools() -> ToolDescriptor[]
```

Enforces permissions, applies the trust tier, and records the invocation. An agent may not execute a side effect by any other means.

### 5.7 `EventBus`

```text
async def publish(event: Event) -> None
def subscribe(event_type: str, handler: EventHandler) -> Subscription

Event              event_id; event_type; schema_version; timestamp;
                   source; trace: TraceContext; payload
```

A pack may publish and subscribe only to event types declared in its manifest. Delivery is at-least-once; handlers must be idempotent on `event_id` ([ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md)).

### 5.8 `ConfigService`

```text
def get(key: str, model: type[T]) -> T          # typed and validated
def flag(name: str, default: bool = False) -> bool
```

Namespaced to the pack. A pack reads only its own namespace plus explicitly shared platform keys, and never reads a file from disk directly.

### 5.9 `SecretResolver`

```text
async def resolve(reference: str) -> SecretValue
```

Accepts only `secret://…` references the pack declared. `SecretValue.__str__` and `__repr__` return `***`; the raw value requires an explicit accessor. Never available inside a Tier 1 sandbox ([ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md)).

### 5.10 `StorageService`

```text
async def put(content: bytes | AsyncIterator[bytes], media_type) -> ArtifactRef
async def get(ref: ArtifactRef) -> AsyncIterator[bytes]
async def exists(ref: ArtifactRef) -> bool
```

Content-addressed. Artifacts are referenced from workflow state, never embedded in it.

### 5.11 `WorkspaceService`

```text
async def acquire(workflow_id) -> WorkspaceHandle
WorkspaceHandle    workspace_id; root_path; is_writable
```

Workspaces are **isolated per workflow instance** — mandatory, not best-effort. Two concurrent workflows never share a working copy, which is what prevents concurrent-write corruption in parallel and fan-out patterns.

### 5.12 `Telemetry`

```text
def logger(name: str) -> BoundLogger        # structlog, trace-context bound
def counter(name, unit, description) -> Counter
def histogram(name, unit, description) -> Histogram
def span(name, attributes=None) -> AsyncContextManager[Span]
```

Metric names are namespaced `aios.pack.<pack_id>.<metric>`. Secrets, credentials, raw prompt bodies containing customer source, and personal data must never be emitted ([ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md)).

### 5.13 `TraceabilityService`

```text
async def link(link: TraceabilityLink) -> None
async def query(request: TraceabilityQuery) -> TraceabilityResult

TraceabilityLink   source_type; source_id; relationship;
                   target_type; target_id; confidence; provenance
```

Links are created explicitly, never inferred silently.

### 5.14 `QualityGateRegistry`

```text
def register(gate: QualityGate) -> None      # at pack load only

QualityGate (Protocol)
    gate_id; version; severity: blocking|warning
    async def evaluate(context: GateContext) -> GateResult

GateResult         gate_id; status: pass|fail|warning|error;
                   metrics: dict[str, float]; messages[];
                   duration_ms; details
```

A pack-contributed gate returns a result; it never decides workflow consequence. The Workflow Engine owns that ([ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md)).

### 5.15 `SpeechGateway`

Available only to packs declaring speech permissions ([ADR-0019](../../18_decision_log/adr/ADR-0019-speech-gateway.md)).

```text
async def transcribe(audio, options) -> Transcript
async def synthesize(text, voice_alias) -> AudioRef
async def detect_wake_word(stream) -> AsyncIterator[WakeWordEvent]
```

Selection is by alias. A `local_only` policy restricts routing to local adapters.

---

## 6. `PackContext`

What a pack actually receives. Attributes are present **only** if the manifest declared the corresponding capability and it was granted.

```text
PackContext
    pack_id: str
    pack_version: str
    llm:            LLMGateway
    prompts:        PromptRegistry
    context:        ContextService
    retrieval:      RetrievalService | None
    memory:         MemoryService | None
    tools:          ToolInvoker
    events:         EventBus | None
    config:         ConfigService
    secrets:        SecretResolver | None
    storage:        StorageService | None
    workspace:      WorkspaceService | None
    telemetry:      Telemetry
    traceability:   TraceabilityService | None
    gates:          QualityGateRegistry
    speech:         SpeechGateway | None
```

There is no `kernel` attribute, no `db`, no `http`, and no escape hatch. A capability a pack did not declare is absent from the object.

---

## 7. Pack Entry Point

Every pack exposes one entry point, registered under `ai_os.capability_packs` ([ADR-0009](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md)):

```text
CapabilityPack (Protocol)
    pack_id: str
    version: str
    async def activate(context: PackContext) -> PackRegistration
    async def deactivate() -> None
    async def health() -> HealthReport

PackRegistration   agents: dict[str, Agent]
                   tools: dict[str, Tool]
                   workflows: dict[str, WorkflowDefinition]
                   gates: dict[str, QualityGate]
                   commands: dict[str, Command]
```

`activate` must be idempotent and must not perform long-running work; heavy initialisation belongs in the first invocation or a declared warm-up step. Everything returned must match the manifest declaration exactly — a mismatch fails activation.

---

## 8. Compatibility and Versioning

- The SDK follows semantic versioning. Packs declare `dependencies.sdkVersion` as a range.
- **Major** — a Protocol method is removed or its signature changes incompatibly; a required model field is added.
- **Minor** — a new Protocol, a new optional field, a new permission.
- **Patch** — documentation and non-behavioural fixes.
- Deprecations are announced one minor version before removal, emit a warning, and are listed in the SDK CHANGELOG.
- The Manifest Loader refuses a pack whose `sdkVersion` range excludes the running SDK, and refuses a pack whose `compatibility.minKernelVersion` exceeds the running Kernel.

---

## 9. Compliance Testing

`ai_os_sdk.testing.pack_contract_suite` is **specified as** a pytest suite every pack must run and pass ([ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md)). It is to verify:

1. `manifest.yaml` validates against the published JSON Schema.
2. Every declared agent, tool, workflow, gate, and command resolves and is importable.
3. Declared I/O models match the implementations' `input_model` / `output_model`.
4. Every workflow's step references resolve; the graph is acyclic where required.
5. `trust_tier` declarations are consistent with what each tool does.
6. Requested permissions are in the closed vocabulary.
7. **No forbidden imports** — no provider SDK, no `ai_os_kernel`, no other pack, no database driver, no HTTP client to a provider.
8. Prompts referenced by agents exist at the declared versions.
9. Activation and deactivation are clean (no dangling registrations).

A pack that does not pass this suite is not compliant and is not loadable.

*Specification only; not yet implemented.* **`pack_contract_suite` does not exist** — neither the module nor the `platform_sdk/testing/` directory that would hold it. No pack has ever run it. Today the only real gate on a pack is check 1 (manifest validation against `../../../platform_sdk/schemas/manifest.schema.json`, genuinely enforced by `ai_os_kernel/manifest_loader/`) plus a few of the semantic rules in `../capability_framework/manifest_schema.md` § Validation Rules. **Checks 2–9 are unenforced**, including check 7 (forbidden imports) — which is precisely why the live direct-Kernel-import exception in §1a went undetected by tooling and had to be recorded by hand. The sentence "A pack that does not pass this suite is not loadable" therefore describes the intended gate, not a gate that operates. Building this suite is the mechanism that would make §10's prohibitions enforceable rather than advisory.

---

## 10. Prohibited in Pack Code

- Importing any provider SDK, or any transitive route to one.
- Importing `ai_os_kernel`, `ai_os_services`, or another pack.
- Direct database, Redis, or filesystem access outside `WorkspaceService` and `StorageService`.
- Literal model IDs, literal secrets, or literal absolute paths.
- Agent-to-agent invocation, in any form.
- Constructing a `SecurityContext`, or mutating one.
- Registering components not declared in the manifest.
- Executing untrusted code outside a Tier 1 sandbox.

Each of these is **intended to be** checked by the contract suite, by lint rules, or by the loader.

*Specification only; not yet implemented.* None of these prohibitions is currently machine-checked. There is no contract suite (§9), no import-boundary lint rule, and the loader checks only the manifest. They remain binding rules on every pack author; they are enforced by review, not by tooling. The first of them — "Importing `ai_os_kernel`" — is knowingly violated today by the `software-engineering` pack (§1a).

---

## 11. Current Status

This document is a **specification with no implementing package**. It defines the SDK surface for v1; nothing in §4–§10 can be imported. There are no concrete signatures on disk — `platform_sdk/contracts/` is an empty directory. This document and the ADRs it cites govern the signatures when they are written.

Once the package exists, any change to a Protocol here requires an SDK version increment and, where behaviour changes, an ADR.

**Concrete next gap, and what would settle it:** scaffold `platform_sdk/` as a real `ai-os-sdk` PEP 621 distribution and add it to `../../../pyproject.toml`'s `[tool.uv.workspace] members` (where it is already noted as "Planned, not yet scaffolded"), starting with the interfaces the one real pack actually reaches through Kernel internals today — `LLMGateway`, `PromptRegistry`, `ContextService` — plus the `AiOsError` hierarchy in §4.4, which every other contract's error field depends on. That is the minimum that lets a pack depend on the SDK instead of the Kernel and closes the dated exception in `../capability_framework/capability_pack_contract.md`.

---

## 12. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Capability Pack Contract
5. Architecture Decision Records
6. Platform SDK Specification (this document)
7. Source Code

---

## 13. Related Documents

**Governing ADRs**

- [ADR-0001 — Modular Capability Pack Architecture](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md) (the pack boundary this SDK exists to enforce)
- [ADR-0004 — Interface-driven and configuration-over-code](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md)
- [ADR-0008 — Primary language and runtime](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md) (`Protocol` + Pydantic v2)
- [ADR-0009 — Packaging and dependency management](../../18_decision_log/adr/ADR-0009-packaging-and-dependency-management.md) (the dependency floor in §2, entry points in §7)
- [ADR-0010 — Composition and dependency injection](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md) (`PackContext` in §6)
- [ADR-0002](../../18_decision_log/adr/ADR-0002-llm-gateway-single-entry-point.md) (§5.1) · [ADR-0006](../../18_decision_log/adr/ADR-0006-quality-gates-are-mandatory.md) (§5.14) · [ADR-0012](../../18_decision_log/adr/ADR-0012-event-bus.md) (§5.7) · [ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md) (§9) · [ADR-0016](../../18_decision_log/adr/ADR-0016-tool-execution-sandboxing.md) (§4.3, §5.3) · [ADR-0017](../../18_decision_log/adr/ADR-0017-observability-stack.md) (§5.12) · [ADR-0019](../../18_decision_log/adr/ADR-0019-speech-gateway.md) (§5.15) · [ADR-0022](../../18_decision_log/adr/ADR-0022-reproducibility-over-determinism.md) (§5.2) · [ADR-0024](../../18_decision_log/adr/ADR-0024-secrets-management-backend.md) (§5.9)
- Full index: `../../18_decision_log/README.md`

**Architecture**

- `system_architecture.md` — where the SDK sits in the layer stack
- `../capability_framework/capability_pack_contract.md` — the pack side of this contract, and the dated direct-Kernel-import exception
- `../capability_framework/manifest_schema.md` — §8's `sdkVersion`/`minKernelVersion` rules, and the real schema this document's one implemented file holds
- `../kernel/kernel_architecture.md` — the side that must implement these Protocols
- `../workflow/error_handling_retry.md` — §4.4's taxonomy, stated once for the whole platform
- `../agents/agent_architecture.md` — the consumer of §4.2
- `../services/` — the services behind §5.10, §5.11, §5.4 (all unimplemented)
- `technology_stack.md` — the technologies these contracts are built on

**Machine-readable artifacts**

- `../../../platform_sdk/schemas/manifest.schema.json` — the only real file this document's package contains
- `../../../capability_packs/software-engineering/manifest.yaml` — the one real pack manifest, and the one real (non-compliant, documented) consumer of this surface

**Requirements traced to this document**

- `../../02_requirements/functional/functional_requirements.md` — FR-001/FR-003 (pack loading and lifecycle), FR-007 (§5.1), FR-010 (§5.3), FR-011 (§5.2), FR-012 (§5.14), FR-014 (§5.7), FR-016 (§5.8), FR-017 (§5.9), FR-018 (§4.1 `SecurityContext` narrowing), FR-019 (§5.13), FR-021 (§4.3 `trust_tier`), FR-022 (§4.2 `StepBudget`)

**Terminology**

- `../../20_glossary/glossary.md`

**Current state of the build**

- `../../19_roadmap/feature_inventory.md` — rows 18 (`ToolInvoker`), 27 (`ai-os-sdk`), 28 (Manifest Schema), 44 (`AiOsError` hierarchy)
- `../../19_roadmap/implementation_status.md`, `../../19_roadmap/history/INDEX.md`
- `platform_sdk_v1_scope.md` — the concrete, evidence-based v1.0.0 build sequence for exactly this document's surface, scoped 2026-07-28
