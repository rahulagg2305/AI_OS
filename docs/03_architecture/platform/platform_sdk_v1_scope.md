# Platform SDK v1.0.0 — Scope and Build Sequence

**Project:** AI_OS (AI Operating System)
**Document:** Platform SDK v1.0.0 Scope and Build Sequence
**Version:** 1.0
**Status:** Approved — Step 1 of 15 complete (packaging scaffold), Step 2 next
**Last Updated:** 2026-07-28 (Step 1 complete: `platform_sdk/` scaffolded as a real, installable `ai-os-sdk` distribution — see `platform_sdk.md` §1a and `implementation_status.md` §2 for verification evidence)

---

## 1. Purpose

`implementation_status.md` §6 and `feature_inventory.md` module 27 both hand off the same instruction: scope the Platform SDK v1.0.0 build as its own dedicated step before starting it. This document is that scoping. It is a **plan, not code** — no `ai_os_sdk` package exists yet, and none is created by this step.

It answers, with evidence from the real, current codebase (not from `platform_sdk.md`'s specification alone):

1. Which of the 15 documented Protocol interfaces the one real pack actually needs right now.
2. Whether the 5 real agents migrate onto the SDK in the same step it's built, or a fast-following one.
3. Whether `pack_contract_suite` ships with the SDK or after.
4. What goes in `platform_sdk/`'s empty subdirectories, file by file.
5. The ordered sequence of small, individually-approvable steps this becomes.
6. What v1.0.0 deliberately does not do.

This document is subordinate to:

1. Project Constitution
2. `platform_sdk.md` (the specification this document sequences the build of)
3. `capability_pack_contract.md` (the growth gate this build closes)
4. `docs/process/standing_rules.md` (the Platform SDK growth gate and scope-discipline rules)

---

## 2. Real usage evidence: what the one real pack actually imports today

`grep -rn "^from ai_os_kernel\|^import ai_os_kernel" capability_packs/software-engineering/src/` on 2026-07-28 returns **57 import statements across 7 files**, covering **24 unique Kernel modules**. Full command output, deduplicated by module:

```
ai_os_kernel.capability_manager.pack_contract      <- pack.py
ai_os_kernel.context_manager.manager               <- pipeline.py
ai_os_kernel.context_manager.models                <- agents/documentation.py, agents/verification.py, pipeline.py
ai_os_kernel.context_manager.resolvers             <- pipeline.py
ai_os_kernel.llm_gateway.adapters.anthropic_adapter <- agents/architecture.py, agents/build.py, agents/documentation.py, agents/requirements_analyst.py
ai_os_kernel.llm_gateway.adapters.model_config      <- (same 4 agent files)
ai_os_kernel.llm_gateway.router                     <- (same 4 agent files)
ai_os_kernel.persistence.engine                     <- (same 4 agent files)
ai_os_kernel.persistence.settings                   <- (same 4 agent files)
ai_os_kernel.prompted_completion                    <- (same 4 agent files)
ai_os_kernel.sandbox.default_executor               <- agents/build.py, agents/documentation.py, agents/verification.py, pipeline.py
ai_os_kernel.sandbox.executor                       <- agents/build.py, agents/documentation.py, agents/verification.py
ai_os_kernel.secrets_manager.env_provider           <- (same 4 agent files as LLM Gateway)
ai_os_kernel.workflow_engine.advance_runner         <- pipeline.py
ai_os_kernel.workflow_engine.definition_catalog     <- pipeline.py
ai_os_kernel.workflow_engine.lease                  <- pipeline.py
ai_os_kernel.workflow_engine.loader                 <- pipeline.py
ai_os_kernel.workflow_engine.models                 <- pipeline.py
ai_os_kernel.workflow_engine.prompted_agent         <- (same 4 agent files as LLM Gateway)
ai_os_kernel.workflow_engine.registry               <- pipeline.py
ai_os_kernel.workflow_engine.repository             <- pipeline.py
ai_os_kernel.workflow_engine.sandboxed_tool          <- agents/build.py, agents/documentation.py, agents/verification.py
ai_os_kernel.workflow_engine.service                <- pipeline.py
ai_os_kernel.workflow_engine.step_executor           <- pipeline.py
```

### 2.1 A finding that changes the shape of this plan: `pipeline.py`'s imports are not pack-facing

11 of the 24 modules are imported **only** by `pipeline.py`, never by an agent: both `context_manager.manager`/`resolvers`, and all 8 `workflow_engine.{advance_runner,definition_catalog,lease,loader,models,registry,repository,service,step_executor}` modules.

`pipeline.py`'s own docstring states plainly what it is: a composition script that chains the 4 real agents into `se.delivery_pipeline`, built "the identical shape `ai_os_kernel.bootstrap._build_workflow_trigger` already establishes for the Kernel's own demo workflow, reused here for a real pack-owned one." It constructs the Workflow Engine's own lease service, repository, instance service, and step executors by hand — work a real Capability Manager would do once, generically, for every pack, handing each pack a `PackContext` instead. That generic "activate a pack's declared workflow through the real engine" mechanism does not exist yet (Capability Manager is a minimal slice — see `feature_inventory.md` module 8), so this reprioritization step's test harness had to do it by hand.

**Consequence for this plan:** `pipeline.py` is not a pack-boundary violation the SDK should fix. It plays the platform's own composition-root role, physically located inside the pack's source tree for lack of anywhere else to put it. Migrating its 11 imports onto SDK Protocols would be modeling platform-internal orchestration as if it were pack-facing capability — wrong shape. **This plan's SDK surface and migration scope is therefore driven only by the 13 modules the 5 agents and `pack.py` actually use**, not all 24. Closing `pipeline.py`'s own gap (a real, generic pack-activation path) is Capability Manager work, out of scope here and named explicitly in §7 non-goals.

### 2.2 The 13 agent/pack-facing modules, mapped to §5's interfaces

| Kernel module (real import) | Used by | Maps to (`platform_sdk.md` §) | Needed now? |
|---|---|---|---|
| `llm_gateway.adapters.anthropic_adapter` (`PROVIDER_NAME`) | architecture, build, documentation, requirements_analyst | §5.1 `LLMGateway` | **Yes** |
| `llm_gateway.adapters.model_config` (`load_provider_config`) | same 4 | §5.1 `LLMGateway` | **Yes** |
| `llm_gateway.router` (`RoutingDecision`, `StaticRouter`) | same 4 | §5.1 `LLMGateway` | **Yes** |
| `prompted_completion` (`PromptedCompletionService`, `build_anthropic_prompted_completion_service`) | same 4 | §5.1 `LLMGateway` + §5.2 `PromptRegistry` (combined) | **Yes** |
| `persistence.engine` (`build_engine`) | same 4 | §5.2 `PromptRegistry` (DB access needed only to construct the SQL-backed prompt catalog underneath it; the SDK hides this entirely) | **Yes** |
| `persistence.settings` (`DatabaseSettings`) | same 4 | §5.2 `PromptRegistry` | **Yes** |
| `secrets_manager.env_provider` (`EnvSecretProvider`) | same 4 | §5.9 `SecretResolver` | **Yes** |
| `workflow_engine.prompted_agent` (`PromptedAgent` base class) | same 4 | §4.2 `Agent` Protocol — needs a new SDK-provided convenience base, not one of the 15 numbered interfaces itself | **Yes** (as a helper, see §5 of this doc) |
| `sandbox.default_executor` (`build_default_sandbox_executor`) | build, documentation, verification | §5.6 `ToolInvoker` | **Yes** |
| `sandbox.executor` (`SandboxExecutor`) | build, documentation, verification | §5.6 `ToolInvoker` | **Yes** |
| `workflow_engine.sandboxed_tool` (`SandboxedCommandTool`) | build, documentation, verification | §5.6 `ToolInvoker` + §4.3 `Tool` Protocol | **Yes** |
| `context_manager.models` (`AssembledContext`) | documentation, verification | §5.3 `ContextService` — **boundary model only**, see note below | **Yes (model only)** |
| `capability_manager.pack_contract` (`HealthReport`, `PackContext`, `PackRegistration`) | pack.py | §6 `PackContext` + §7 `CapabilityPack`/`PackRegistration`/`HealthReport` | **Yes** |

**Note on `ContextService`:** no agent calls `.assemble()` themselves — `AgentStepExecutor` (Workflow Engine) already assembles context and hands it to the agent via `AgentRequest.context` (per `agent_architecture.md`'s Invocation Lifecycle, already real — see `step_executor.py`'s `AgentStepExecutor._invocation_inputs`). The two agents above only import the **model** (`AssembledContext`) to type-annotate what they receive, never the assembly path. v1.0.0 therefore needs `ContextService`'s boundary models (`AssembledContext`, `ContextItem`, `SourceRef`) but not a working `.assemble()` implementation behind the Protocol — the Protocol method is declared for future callers, unused by real code today.

### 2.3 Answer to Question 1: which of the 15 interfaces does the pack need right now

**5 of 15**, by direct evidence: `LLMGateway` (§5.1), `PromptRegistry` (§5.2), `SecretResolver` (§5.9), `ToolInvoker` (§5.6), and `ContextService` (§5.3, models only, not the live method). Plus the two entry-point contracts that are not among the 15 but are equally load-bearing: `PackContext` (§6) and `CapabilityPack`/`PackRegistration`/`HealthReport` (§7).

**10 of 15 have zero real usage today** and stay deferred: `RetrievalService`, `MemoryService`, `EventBus`, `ConfigService`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`. This is not an oversight — every subsystem behind these 10 is itself 0%-built or a docstring-only stub (`feature_inventory.md` confirms this for each), so building the pack-facing Protocol first would mean shipping an interface with nothing real to route to.

This matches and sharpens `platform_sdk.md` §11's own "Concrete next gap" paragraph (which named `LLMGateway`, `PromptRegistry`, `ContextService`, plus `AiOsError`) — this evidence pass adds `SecretResolver` and `ToolInvoker`, found by exact import count, and confirms `PackContext`/`CapabilityPack` are needed too (they're literally how a pack receives every other interface).

---

## 3. Migration plan: same step or fast-following?

**Recommendation: fast-following, not the same step — but with no other work permitted to land between the two.**

**Reasoning:**

- **Size and risk.** Building 5 Protocols + their boundary models + `AiOsError` + `PackContext`/`CapabilityPack` is already a multi-step body of work by this project's own established cadence (see §6). Bundling 5-agent migration into the same step roughly doubles the diff size and the number of things that can break in one commit — this project's standing rule is small, individually-approvable steps, and a combined step would be the largest single step in the project's history.
- **The agents are currently proven and passing** (803/803 real tests, per the last two audits). Migrating them is a mechanical, verifiable, per-agent change (swap an import, swap a constructor argument, re-run that agent's existing tests) — exactly the shape of change this project has always done one-at-a-time (`015_architecture_agent.md` through `018_documentation_agent.md` each built one agent in its own step; there is no reason migration should be coarser than construction was).
- **But the task's own concern is real and must be bounded**: shipping the SDK and *not* migrating promptly would leave the hard gate satisfied in letter (an SDK exists) but not in spirit (the flagship pack still violates it) — an even worse state than today's honestly-documented exception, because it would look closed while staying open. **The fix is sequencing discipline, not step-merging**: the migration steps (§6, steps 9–14) are treated as mandatory, adjacent next steps once the SDK-build steps (1–8) land — no unrelated feature work, and specifically no 6th agent or new pack, is approved in between. This is recorded as a standing-rules addition in this same step (see the commit for this plan).

---

## 4. `pack_contract_suite` timing

**Recommendation: split it.** Check 7 (forbidden imports) ships **with** the SDK, as its own small step (step 8, §6). The remaining 8 checks ship **after** migration, as their own dedicated step (step 15, §6).

**Reasoning:**

- The task's own framing is exactly right: check 7 is the mechanism that would have caught the current, months-long, hand-recorded violation. Every day it doesn't exist is another day the same blind spot is live. **Check 7 has zero dependency on anything else in this plan** — it's a pure AST import-scanner over a pack's own source tree (`ast.walk` for `Import`/`ImportFrom` nodes naming `ai_os_kernel`, `ai_os_services`, or another pack's package), needing no `PackContext`, no `CapabilityPack` semantics, no activation lifecycle. It can be built the moment the SDK package exists to hold it, independent of everything else.
- Checks 2, 3, 4, and 9 (entry-point resolution, I/O-model matching, workflow step resolution, clean activation/deactivation) **do** depend on `PackContext`/`CapabilityPack` being real and on the SE pack actually being migrated onto them — running them before migration would mean testing against the soon-to-be-replaced Kernel-internal `capability_manager.pack_contract` shapes, work that would be partly thrown away. Checks 5, 6, 8 (trust-tier consistency, permission vocabulary, prompt existence) are cheap and could ship early, but splitting the suite into "check 7 now, 5/6/8 early, 2/3/4/9 late" fragments one document's own coherent 9-check contract for a marginal gain; shipping the full remaining 8 together, once there's a real migrated pack to run them against, keeps the suite itself simple and the "does this pack pass" answer meaningful the first time it's asked.

---

## 5. `platform_sdk/` subdirectories: file-by-file plan

Verified current state (`find platform_sdk -type d`): `contracts/`, `models/`, `prompts/`, `sdk/`, `utilities/` all exist and are empty; `schemas/` holds the one real file. `errors/` and `testing/` **do not exist at all** (not even as empty directories) — `platform_sdk.md` §3 already flags this precisely.

*(Note: the handoff in `implementation_status.md` §6 said "4 empty subdirectories" — the real count, re-verified this step, is 5 empty directories on disk, plus 2 that don't exist yet. `prompts/` is the one this plan doesn't otherwise mention — see below.)*

```
platform_sdk/
├── pyproject.toml                    NEW — PEP 621 distribution, name="ai-os-sdk", package ai_os_sdk
├── src/ai_os_sdk/
│   ├── __init__.py
│   ├── errors/
│   │   ├── __init__.py
│   │   └── taxonomy.py               AiOsError, TransientError, PermanentError, QualityError,
│   │                                  InfrastructureError, BudgetExceededError, SecurityError,
│   │                                  StructuredError (§4.4)   [directory does not exist — create it]
│   ├── models/
│   │   ├── __init__.py
│   │   ├── common.py                 ArtifactRef, TraceContext, SecurityContext, StepBudget (§4.1)
│   │   ├── agent.py                  AgentRequest, AgentResult (§4.2)
│   │   ├── tool.py                   ToolRequest, ToolResult (§4.3)
│   │   ├── llm.py                    LLMRequest, LLMResponse, UsageRecord, ProviderCapabilities,
│   │                                  Message, ContentBlock, CacheHint (§5.1)
│   │   ├── prompt.py                 RenderedPrompt, PromptDefinition (§5.2)
│   │   ├── context.py                ContextRequest, AssembledContext, ContextItem, SourceRef (§5.3)
│   │   ├── secret.py                 SecretValue (§5.9)
│   │   └── pack.py                   PackContext, PackRegistration, HealthReport (§6, §7)
│   ├── contracts/
│   │   ├── __init__.py
│   │   ├── agent.py                  Agent (Protocol) (§4.2)
│   │   ├── tool.py                   Tool (Protocol) (§4.3)
│   │   ├── llm_gateway.py            LLMGateway (Protocol) (§5.1)
│   │   ├── prompt_registry.py        PromptRegistry (Protocol) (§5.2)
│   │   ├── context_service.py        ContextService (Protocol) (§5.3) — declared, unimplemented caller
│   │   ├── secret_resolver.py        SecretResolver (Protocol) (§5.9)
│   │   ├── tool_invoker.py           ToolInvoker (Protocol) (§5.6)
│   │   └── capability_pack.py        CapabilityPack (Protocol) (§7)
│   ├── sdk/
│   │   ├── __init__.py
│   │   └── prompted_agent.py         PROPOSED (see below) — a concrete, non-Protocol Agent base
│   │                                  built on LLMGateway + PromptRegistry, mirroring
│   │                                  ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent's
│   │                                  real shape. 4 of 5 real agents already depend on the
│   │                                  Kernel-internal equivalent of exactly this class.
│   └── utilities/
│       └── __init__.py               EMPTY beyond this — see reasoning below
└── testing/
    ├── __init__.py
    └── forbidden_imports.py          pack_contract_suite check #7 only, v1.0.0
                                        [directory does not exist — create it]
```

**Two things flagged rather than silently decided, per this project's own standing rule to stop and report a genuine gap:**

1. **`platform_sdk/sdk/` has no description anywhere** — `platform_sdk.md` §3's own layout tree doesn't list it at all (only `contracts/`, `models/`, `errors/`, `testing/`, `utilities/`, `prompts/`, `schemas/` have a stated purpose). This plan **proposes** `sdk/` as the home for concrete, opinionated helper implementations built *on top of* the Protocols (starting with a `PromptedAgent` base) — Protocols are abstractions a pack could implement differently; `sdk/` is where the SDK saves a pack the boilerplate of doing so, the same role `ai_os_kernel.workflow_engine.prompted_agent.PromptedAgent` plays inside the Kernel today. Approving this plan is this proposal's approval; if the product owner intends something else for `sdk/`, say so before step 1 starts.
2. **`platform_sdk/prompts/` stays untouched.** `platform_sdk.md` §3 marks it "(present on disk, undocumented)" and nothing in this plan's real-usage evidence needs it — the real pack's prompts already live in `capability_packs/software-engineering/prompts/`. Left empty pending a product-owner decision on what it's for; not addressed by any step in §6.

**`utilities/` stays a bare `__init__.py` in v1.0.0.** Checked directly: `grep -rn "ulid\|hashlib\|sha256\|canonical" capability_packs/software-engineering/src/` finds no pack code generating its own IDs, hashes, or canonical JSON — the Kernel does all of that internally today. Per this project's coding standard ("fields exist only once something reads them"), building out `ids.py`/`hashing.py`/`canonical_json.py` speculatively, with no current caller, is exactly the premature scaffolding the standards forbid. Revisit when a real pack need appears.

---

## 6. Ordered step sequence

Each step below is scoped to become its own future prompt, in this order, each individually approved before it starts — matching this project's established cadence (one agent per step for the original 5, one fix per step in the two most recent audits).

**SDK build:**

1. **Scaffold `platform_sdk` as a real `ai-os-sdk` PEP 621 distribution.** `pyproject.toml`, `src/ai_os_sdk/__init__.py`, add to `[tool.uv.workspace] members` and `[tool.uv.sources]` in the root `pyproject.toml`, extend `[tool.mypy].files`. No interfaces yet — prove `import ai_os_sdk` works and CI checks it.
2. **`AiOsError` hierarchy + `StructuredError` + shared boundary models** (`ArtifactRef`, `TraceContext`, `SecurityContext`, `StepBudget` — §4.1, §4.4). Dependency-free foundation everything else builds on.
3. **`Agent`/`Tool` Protocols + their request/result models** (`AgentRequest`/`AgentResult`, `ToolRequest`/`ToolResult` — §4.2, §4.3).
4. **`LLMGateway` Protocol + full model set** (§5.1) — the single highest-usage real interface.
5. **`PromptRegistry` Protocol + models** (§5.2) — pairs with step 4 since `prompted_completion` already combines both today.
6. **`SecretResolver` Protocol + `SecretValue`** (§5.9) **and `ToolInvoker` Protocol** (§5.6, built on `Tool` from step 3).
7. **`ContextService` boundary models** (`AssembledContext`/`ContextItem`/`SourceRef`, §5.3, models only) **and the entry-point contract**: `PackContext` (§6), `CapabilityPack`/`PackRegistration`/`HealthReport` (§7).
8. **`pack_contract_suite` check #7 only** (forbidden-import AST scanner), wired into CI. Closes the historical blind spot immediately, independent of migration.

**Migration (fast-following, no other feature work interleaved — see §3):**

9. **Migrate `requirements-analyst`** onto the real SDK (`LLMGateway`, `PromptRegistry`, `SecretResolver`). Simplest of the 4 prompted agents; no sandbox/tool usage to complicate the first proof.
10. **Migrate `architecture`** onto the real SDK (same shape as step 9).
11. **Migrate `build`** onto the real SDK — adds `ToolInvoker`/sandbox migration on top of the pattern proven in 9–10.
12. **Migrate `documentation`** onto the real SDK (same shape as step 11).
13. **Migrate `qa-test` (`verification.py`)** onto the real SDK — the one non-`PromptedAgent` agent; proves the bare `Agent` Protocol + `ToolInvoker` path with no `LLMGateway` involvement.
14. **Migrate `pack.py`'s entry point** onto the real `CapabilityPack`/`PackContext`/`PackRegistration`/`HealthReport` SDK types; remove the dated direct-Kernel-import exception language from `capability_pack_contract.md` now that it's closed for the agents (note: `pipeline.py` is explicitly untouched — see §2.1).

**Compliance completion:**

15. **Build the remaining 8 `pack_contract_suite` checks**, run them against the now-migrated SE pack end to end, and formally record the gate as satisfied (not just built) in `feature_inventory.md`, `capability_pack_contract.md`, and `standing_rules.md`.

**Gate semantics:** the Platform SDK growth gate (`standing_rules.md`) lifts only after step 15, not after step 1 or step 8. An SDK existing (steps 1–8 done) without a migrated, verified pack is still "no compliant pack exists" — the gate's purpose is a compliant pack, not merely an importable SDK.

---

## 7. Explicit non-goals for v1.0.0

Deferred, deliberately, so scope doesn't creep mid-build:

- **The 10 Protocol interfaces with zero real usage today** (`RetrievalService`, `MemoryService`, `EventBus`, `ConfigService`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`). Each sits on a 0%-built or docstring-only Kernel subsystem — building the pack-facing contract first would ship an interface nothing implements.
- **`pipeline.py`'s 11 composition-root imports.** Not a pack-boundary problem; a real Capability Manager "activate a pack's declared workflow" mechanism is the actual missing piece, tracked separately (`feature_inventory.md` module 8), not Platform SDK scope.
- **SDK semantic-versioning enforcement in the Manifest Loader** (§8 of `platform_sdk.md`) — requires a real SDK version to exist first; a small follow-on once v1.0.0 itself is versioned and shipped.
- **The full 9-check `pack_contract_suite`** in the SDK-build phase — only check 7 ships early (§4); checks 2/3/4/9 need a migrated pack to test against meaningfully.
- **`platform_sdk/prompts/`.** Purpose undocumented anywhere in the source spec; left untouched pending a product-owner decision, not invented here.
- **Migrating `kernel/bootstrap.py` or any other Kernel-internal composition onto `ai_os_sdk` types.** The Kernel *implements* these Protocols; it does not consume them. Only pack code (steps 9–14) migrates.
- **Any 6th SE-pack agent, or any new Capability Pack.** Still blocked by the existing hard gate until step 15 completes — building the SDK does not itself lift the gate (see §6's gate semantics note).

---

## 8. Final Authority

Order of precedence:

1. Project Constitution
2. AI Governance Framework
3. `platform_sdk.md` (Platform SDK Specification)
4. `capability_pack_contract.md`
5. This document
6. Source Code

---

## 9. Related Documents

- [`platform_sdk.md`](platform_sdk.md) — the specification this document sequences the build of
- [`../capability_framework/capability_pack_contract.md`](../capability_framework/capability_pack_contract.md) — the growth gate this build closes, and the dated exception steps 9–14 retire
- [`../../process/standing_rules.md`](../../process/standing_rules.md) — the Platform SDK growth gate and scope-discipline rules this plan's step sequence is designed to satisfy
- [`../../19_roadmap/implementation_status.md`](../../19_roadmap/implementation_status.md) §6 — the handoff this document answers
- [`../../19_roadmap/feature_inventory.md`](../../19_roadmap/feature_inventory.md) — module 27 (Platform SDK), module 29 (SE Pack — Agents), module 8 (Capability Manager, the real owner of `pipeline.py`'s gap)
- [`../agents/agent_architecture.md`](../agents/agent_architecture.md) — the Invocation Lifecycle that already assembles context before an agent runs (§2.2's `ContextService` note)
- [`../../../capability_packs/software-engineering/`](../../../capability_packs/software-engineering/) — the one real pack this plan migrates
