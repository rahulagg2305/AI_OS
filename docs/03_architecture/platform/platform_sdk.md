# Platform SDK Specification – AI_OS

**Project:** AI_OS (AI Operating System)
**Document:** Platform SDK Specification
**Version:** 1.0
**Status:** Approved
**Last Updated:** 2026-07-25

---

## 1. Purpose

The Platform SDK (`ai-os-sdk`, package `ai_os_sdk`) is the **only** interface between Capability Packs and the AI_OS platform. It defines every contract a pack may depend on, every data model crossing the boundary, and the testing suite that proves compliance.

This document specifies that surface. It is the contract the Kernel must implement and packs must code against.

This document is subordinate to:

1. Project Constitution
2. AI Governance Framework
3. System Architecture
4. Capability Pack Contract
5. Kernel Architecture

Governing decisions: [ADR-0001](../../18_decision_log/adr/ADR-0001-modular-capability-pack-architecture.md), [ADR-0004](../../18_decision_log/adr/ADR-0004-interface-driven-and-configuration-over-code.md), [ADR-0008](../../18_decision_log/adr/ADR-0008-primary-language-and-runtime.md), [ADR-0010](../../18_decision_log/adr/ADR-0010-composition-and-dependency-injection.md).

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

```text
platform_sdk/
├── contracts/          # Protocol definitions (the interfaces below)
├── models/             # Pydantic boundary models
├── errors/             # AiOsError hierarchy
├── testing/            # pack_contract_suite, fakes, fixtures
└── utilities/          # ids, hashing, canonical JSON, time
```

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

One taxonomy for the whole platform, matching `docs/03_architecture/workflow/error_handling_retry.md`:

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

---

## 5. Platform Interfaces

Every interface below is a `Protocol` in `ai_os_sdk.contracts`. These are the **complete** set of capabilities available to a Capability Pack.

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

`ai_os_sdk.testing.pack_contract_suite` is a pytest suite every pack must run and pass ([ADR-0015](../../18_decision_log/adr/ADR-0015-testing-and-ci.md)). It verifies:

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

Each of these is checked by the contract suite, by lint rules, or by the loader.

---

## 11. Current Status

This specification defines the SDK surface for v1. Concrete signatures live in `platform_sdk/contracts/`; this document and the ADRs it cites govern them. Any change to a Protocol here requires an SDK version increment and, where behaviour changes, an ADR.

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
