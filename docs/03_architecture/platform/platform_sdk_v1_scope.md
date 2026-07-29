# Platform SDK v1.0.0 — Scope and Build Sequence

**Project:** AI_OS (AI Operating System)
**Document:** Platform SDK v1.0.0 Scope and Build Sequence
**Version:** 2.6
**Status:** Approved — 18 steps; **Steps 1, 2, 2a, 3, 4, 5, 6, and 6a complete**, Step 6b next (`PackContext` construction + the `EntrypointLoader` zero-argument injection blocker — the actual unlock for every migration step)
**Last Updated:** 2026-07-29 (v2.6: **Step 6a complete** — real Kernel-side adapters (`kernel/src/ai_os_kernel/sdk_adapters/`) genuinely implementing `LLMGateway`, `PromptRegistry`, and `ToolInvoker` over `DispatchingLLMGateway`, the Prompt Engine, and `LocalSubprocessSandbox` — the first step to touch real Kernel code, resolving P1 in full. The `ToolInvoker` adapter also resolves the timeout-precedence nuance step 6 left open (`min()` of the two timeouts) and surfaces one new, documented gap (the Protocol carries no trace parameter, resolved with a fresh, uncorrelated per-invocation `TraceContext`). Record in §6g. Prior, v2.5: **Step 6 complete** — `ToolInvoker` Protocol, `ToolDescriptor`, `ToolResult`, and the `platform.sandbox.run_command` tool built at the from-scratch shape decided in 2a. Proven against the **real, actually-executed** `LocalSubprocessSandbox` (clean/timed-out/truncated runs), which found and corrected two real bugs before they could reach step 6a: a too-strict `ToolResult` validator, and a circular import between `ai_os_sdk.errors` and `ai_os_sdk.models`. Record in §6f. Prior, v2.4: **Step 5 complete** — `PromptRegistry` Protocol built at the documented keyword call style (the one reversal decision from 2a), `RenderedPrompt` narrowed to 3 fields, conversion to/from the real Kernel prompt models proven lossless. Record in §6e. Prior, v2.3: **Step 4 complete** — `LLMGateway` Protocol narrowed to `complete()`/`capabilities()`, `ProviderCapabilities` extended to 13 fields, proven against the real `DispatchingLLMGateway`. Record in §6d. Prior, v2.2: **Step 3 complete** — `Agent`/`Tool` Protocols proven against all five real pack agents and both real tools. Record in §6c. Prior, v2.1: **Step 2a complete** — all five reconciliation decisions recorded; summary in §6b. Prior, v2.0: an independent architecture review found 7 real problems in v1.0's 15-step sequence; revised to 18 steps. Findings: §6a.)

**Previously:** 2026-07-28 (v1.0 — original 15-step sequence, Step 1 complete)

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

11 of the 24 modules are imported **only** by `pipeline.py`, never by an agent: both `context_manager.manager`/`resolvers`, and all **nine** `workflow_engine.{advance_runner,definition_catalog,lease,loader,models,registry,repository,service,step_executor}` modules. *(v1.0 of this document said "8" here while listing nine — corrected per finding P7; 2 + 9 = 11, and 13 + 11 = 24.)*

`pipeline.py`'s own docstring states plainly what it is: a composition script that chains the 4 real agents into `se.delivery_pipeline`, built "the identical shape `ai_os_kernel.bootstrap._build_workflow_trigger` already establishes for the Kernel's own demo workflow, reused here for a real pack-owned one." It constructs the Workflow Engine's own lease service, repository, instance service, and step executors by hand — work a real Capability Manager would do once, generically, for every pack, handing each pack a `PackContext` instead. That generic "activate a pack's declared workflow through the real engine" mechanism does not exist yet (Capability Manager is a minimal slice — see `feature_inventory.md` module 8), so this reprioritization step's test harness had to do it by hand.

**Consequence for this plan:** `pipeline.py` is not a pack-boundary violation the SDK should fix. It plays the platform's own composition-root role, physically located inside the pack's source tree for lack of anywhere else to put it. Migrating its 11 imports onto SDK Protocols would be modeling platform-internal orchestration as if it were pack-facing capability — wrong shape. **This plan's SDK surface and migration scope is therefore driven only by the 13 modules the 5 agents and `pack.py` actually use**, not all 24.

**Revised in v2.0 (finding P4):** v1.0 concluded from this that `pipeline.py` should simply be left alone until a future Capability Manager arrives, and listed it as a permanent non-goal. That was wrong in one important respect — leaving a Kernel-importing, `sqlalchemy`-importing module inside the pack's **shipped package** means `pack_contract_suite` check 7 can never pass on this pack, at any point, ever. Since **no pack source module imports `pipeline.py`** (only two Kernel-side tests do), relocating it into `tests/` resolves both problems at once and costs far less than a Capability Manager. It is now **step 7** — see §4.1.

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

### 2.3 Answer to Question 1: which interfaces does the pack need right now

**Revised 2026-07-28 (v2.0) from "5 of 15" to "3 capability Protocols of 15."** v1.0 of this document answered 5 (`LLMGateway`, `PromptRegistry`, `SecretResolver`, `ToolInvoker`, `ContextService`-models). The architecture review found the derivation flawed — see §2.4 and finding **P5** in §6a. The corrected answer:

**3 capability Protocols**, and they map exactly onto the pack's two **declared** permissions (`capability_packs/software-engineering/manifest.yaml` lines 71–73: `llm:invoke`, `sandbox:execute`):

| Declared permission | Protocols required to serve it |
|---|---|
| `llm:invoke` | `LLMGateway` (§5.1), `PromptRegistry` (§5.2) |
| `sandbox:execute` | `ToolInvoker` (§5.6), + the `Tool` contract (§4.3) |

**Plus the non-capability contracts**, which are not permission-gated because they are the shape of a pack itself rather than something granted to it: `Agent` (§4.2), `PackContext` (§6), `CapabilityPack`/`PackRegistration`/`HealthReport` (§7), and `ContextService`'s **boundary models only** (§5.3 — `AssembledContext`/`ContextItem`/`SourceRef`, imported for type annotation; no agent calls `.assemble()`).

**`SecretResolver` (§5.9) is dropped from v1.0.0.** Its only real use is constructing the pack's *own* LLM Gateway (`architecture.py:161`: `secret_provider=EnvSecretProvider(), api_key_secret_reference=...`). Once a constructed gateway is injected (step 6b), the pack resolves no secrets at all. Decisively: **the manifest declares no secret permission**, and `platform_sdk.md` §6 states PackContext attributes are present *"only if the manifest declared the corresponding capability and it was granted."* Putting `secrets` on this pack's `PackContext` would grant an undeclared capability — a contract violation, not a convenience. Re-add it in the step that first onboards a pack declaring a secret permission.

**11 of 15 stay deferred** (was 10; `SecretResolver` joins them): `RetrievalService`, `MemoryService`, `EventBus`, `ConfigService`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`, `SecretResolver`. For the first ten, the reason is unchanged and still correct: every subsystem behind them is 0%-built or a docstring-only stub, so shipping the pack-facing Protocol first would mean an interface with nothing to route to.

**One correction to v1.0's deferral reasoning.** v1.0 deferred `ConfigService` (§5.8) on the stated grounds of *"zero real usage."* That is factually wrong, and the review caught it (**P5**): all four prompted agents read platform configuration directly off disk and out of the environment — `_CONFIG_PATH = Path.cwd() / "config" / "llm.yaml"` plus `load_provider_config(...)`, and `DatabaseSettings()` for `AIOS_DATABASE_URL` (`architecture.py:112,152,161`; identically in `build.py`, `documentation.py`, `requirements_analyst.py`). Both are prohibited by `platform_sdk.md` §10 today ("direct… filesystem access outside `WorkspaceService`/`StorageService`", "literal absolute paths"). `ConfigService` still stays deferred — but for the *correct* reason: the need disappears entirely once step 6b injects a fully-constructed gateway, so no pack-facing config Protocol is required to close it.

### 2.4 Why v1.0's count was wrong: construction vs. consumption (finding P5)

v1.0 mapped each imported Kernel module 1:1 onto a Protocol. That conflates two different things:

- **Imports the pack needs to *construct* its own dependencies** — `anthropic_adapter` (`PROVIDER_NAME`), `model_config` (`load_provider_config`), `router` (`StaticRouter`/`RoutingDecision`), `persistence.engine` (`build_engine`), `persistence.settings` (`DatabaseSettings`), `secrets_manager.env_provider` (`EnvSecretProvider`), `sandbox.default_executor` (`build_default_sandbox_executor`). **Seven of the thirteen.**
- **Capabilities the pack actually *consumes*** — completing a prompted LLM call, and executing a command in a sandbox.

All seven construction imports exist for one reason: **nothing injects anything, so each agent builds its own object graph.** They do not each need a corresponding Protocol; they all disappear together the moment a `PackContext` carries constructed services (step 6b). Mapping them 1:1 to Protocols overstated the required surface by roughly a factor of two and, worse, produced a Protocol (`SecretResolver`) the pack has no declared right to.

The corrected derivation starts from **declared permissions**, not from imports — because permissions are what `platform_sdk.md` §6 actually gates `PackContext` attributes on.

---

## 3. Migration plan: same step or fast-following?

**Recommendation: fast-following, not the same step — but with no other work permitted to land between the two.**

**Reasoning:**

- **Size and risk.** Building 5 Protocols + their boundary models + `AiOsError` + `PackContext`/`CapabilityPack` is already a multi-step body of work by this project's own established cadence (see §6). Bundling 5-agent migration into the same step roughly doubles the diff size and the number of things that can break in one commit — this project's standing rule is small, individually-approvable steps, and a combined step would be the largest single step in the project's history.
- **The agents are currently proven and passing** (803/803 real tests, per the last two audits). Migrating them is a mechanical, verifiable, per-agent change (swap an import, swap a constructor argument, re-run that agent's existing tests) — exactly the shape of change this project has always done one-at-a-time (`015_architecture_agent.md` through `018_documentation_agent.md` each built one agent in its own step; there is no reason migration should be coarser than construction was).
- **But the task's own concern is real and must be bounded**: shipping the SDK and *not* migrating promptly would leave the hard gate satisfied in letter (an SDK exists) but not in spirit (the flagship pack still violates it) — an even worse state than today's honestly-documented exception, because it would look closed while staying open. **The fix is sequencing discipline, not step-merging**: the migration steps (§6, steps 9–14) are treated as mandatory, adjacent next steps once the SDK-build steps land — no unrelated feature work, and specifically no 6th agent or new pack, is approved in between. This is recorded as a standing-rules addition (see `../../process/standing_rules.md`).

**Migration order reversed in v2.0 (finding P6).** v1.0 ordered the migrations `requirements-analyst` → `architecture` → `build` → `documentation` → `qa-test`, describing `requirements-analyst` as "simplest." It is not. `qa-test` (`verification.py`) is: it **makes no LLM call at all**, imports only 4 Kernel modules, and constructs no gateway, no router, no database engine, and no secret provider. `requirements-analyst` needs that entire construction chain replaced at once. Migrating `qa-test` first validates the `Agent` Protocol and the new injection path **in isolation from any gateway complexity** — if it breaks, exactly one thing is new. The corrected order is `qa-test` → `requirements-analyst` → `architecture` → `build` → `documentation` → `pack.py`.

---

## 4. `pack_contract_suite` timing

**Recommendation: split it.** Check 7 (forbidden imports) ships **with** the SDK, as its own small step (step 8, §6). The remaining 8 checks ship **after** migration, as their own dedicated step (step 15, §6).

**Reasoning:**

- The task's own framing is exactly right: check 7 is the mechanism that would have caught the current, months-long, hand-recorded violation. Every day it doesn't exist is another day the same blind spot is live. **Check 7 has zero dependency on anything else in this plan** — it's a pure AST import-scanner over a pack's own source tree (`ast.walk` for `Import`/`ImportFrom` nodes naming `ai_os_kernel`, `ai_os_services`, or another pack's package), needing no `PackContext`, no `CapabilityPack` semantics, no activation lifecycle. It can be built the moment the SDK package exists to hold it, independent of everything else.
- Checks 2, 3, 4, and 9 (entry-point resolution, I/O-model matching, workflow step resolution, clean activation/deactivation) **do** depend on `PackContext`/`CapabilityPack` being real and on the SE pack actually being migrated onto them — running them before migration would mean testing against the soon-to-be-replaced Kernel-internal `capability_manager.pack_contract` shapes, work that would be partly thrown away. Checks 5, 6, 8 (trust-tier consistency, permission vocabulary, prompt existence) are cheap and could ship early, but splitting the suite into "check 7 now, 5/6/8 early, 2/3/4/9 late" fragments one document's own coherent 9-check contract for a marginal gain; shipping the full remaining 8 together, once there's a real migrated pack to run them against, keeps the suite itself simple and the "does this pack pass" answer meaningful the first time it's asked.

### 4.1 What v1.0 got wrong about check 7 (finding P4)

v1.0 said check 7 would be "wired into CI" at step 8 and left it there. The review established that this **breaks CI and cannot ever pass on this pack** without two additions:

1. **It fails immediately, not trivially.** At step 8 the Software Engineering pack still has **57 `ai_os_kernel` imports**. Check 7 run against it *fails*. With no waiver mechanism, **CI goes red at step 8 and stays red through step 13** — six steps of a knowingly-broken pipeline, which this project's own zero-regression rule forbids. Step 8 therefore must ship the check **together with an explicit, documented, expiring waiver** for the not-yet-migrated pack, removed at step 14.
2. **`pipeline.py` can never pass, under v1.0's own rules.** It is inside the shipped wheel (`packages = ["src/ai_os_pack_software_engineering"]`), it imports 11 Kernel modules **and** `sqlalchemy.ext.asyncio` (`pipeline.py:107` — also check-7-forbidden as a database driver), and v1.0 declared it a **permanent** non-goal. So check 7 would fail on this pack forever, even after step 14 completed every migration.

**The fix the review found, which v1.0 missed entirely: relocate `pipeline.py` into `tests/`.** Verified: **zero pack source modules import it** — its only importers are two Kernel-side tests (`tests/integration/workflow_engine/test_delivery_pipeline.py`, `tests/integration/sandbox/test_delivery_pipeline_docker.py`). It is a test harness sitting in shipped-package space. Moving it makes check 7 pass **honestly** rather than by exemption, and dissolves §2.1's "11 composition-root imports" problem — **without** building a Capability Manager first. This is now step 7.

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
│   │   └── pack.py                   PackContext, PackRegistration, HealthReport (§6, §7)
│   │                                 (secret.py / SecretValue dropped in v2.0 — see §2.3)
│   ├── contracts/
│   │   ├── __init__.py
│   │   ├── agent.py                  Agent (Protocol) (§4.2)
│   │   ├── tool.py                   Tool (Protocol) (§4.3)
│   │   ├── llm_gateway.py            LLMGateway (Protocol) (§5.1)
│   │   ├── prompt_registry.py        PromptRegistry (Protocol) (§5.2)
│   │   ├── context_service.py        ContextService (Protocol) (§5.3) — declared, unimplemented caller
│   │   ├── tool_invoker.py           ToolInvoker (Protocol) (§5.6)
│   │   └── capability_pack.py        CapabilityPack (Protocol) (§7)
│   │                                 (secret_resolver.py dropped in v2.0 — see §2.3)
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

## 6. Ordered step sequence (revised v2.0 — 18 steps)

Each step below is scoped to become its own future prompt, in this order, each individually approved before it starts — matching this project's established cadence (one agent per step for the original 5, one fix per step in the two most recent audits).

**Net change from v1.0's 15 steps:** three insertions (**2a**, **6a**, **6b**), one repurposed step (**7**, now the `pipeline.py` relocation), one deletion (`SecretResolver`, per §2.3), and the migration order reversed (§3). Reasoning for every change: §6a.

**Reconciliation & foundation**

| # | Scope | Status |
|---|---|---|
| 1 | Scaffold `platform_sdk` as a real `ai-os-sdk` PEP 621 distribution — packaging only, six stub subpackages, workspace member. | **Done** (`fc0973a`) |
| 2 | `AiOsError` hierarchy + `StructuredError` + shared boundary models (`ArtifactRef`, `TraceContext`, `SecurityContext`, `StepBudget` — §4.1, §4.4). Dependency-free foundation everything else builds on. | **Done** |
| **2a** | **Protocol/reality reconciliation decision (docs only).** All five decisions made and recorded as dated blocks in `platform_sdk.md` §4.2/§4.3/§5.1/§5.2/§5.6 — see §6b below for the summary. Resolves P1 + P3. | **Done** |
| 3 | `Agent` + `Tool` Protocols **only** — the narrowed, dict-based shapes decided in 2a, plus the SDK's own `TrustTier`. `AgentRequest`/`AgentResult`/`ToolRequest` out of scope (deferred past v1.0.0); `ToolResult` moved to step 6 with its consumer. **Structural compatibility proven against real classes**, not mocks: all 5 pack agents + `EchoAgent` satisfy `Agent`, and `EchoTool` + `SandboxedCommandTool` satisfy `Tool`, with **zero modification to any Kernel or pack source** (`tests/unit/platform_sdk/test_kernel_satisfies_sdk_contracts.py`, 13 assertions). | **Done** |

**Contracts**

| # | Scope | Status |
|---|---|---|
| 4 | `LLMGateway` Protocol narrowed to `complete()` + `capabilities()` (the two methods `DispatchingLLMGateway` implements); `ProviderCapabilities` extended to the real 13 fields; `LLMRequest`/`Message`/`MessageRole`/`StopReason`/`UsageRecord`/`LLMResponse` as field-for-field mirrors of the real Kernel models. **Structural compatibility proven against the real `DispatchingLLMGateway`**, not a mock, constructed with an empty `StaticRouter` and no providers — zero I/O, zero Kernel/pack source modified. `EchoLLMGateway` correctly does *not* satisfy the SDK Protocol (it implements only `complete()`), which is itself evidence the narrowing is exact, not accidentally loose. | **Done** |
| 5 | `PromptRegistry` Protocol at the documented keyword call style (`render(prompt_id, variables, *, version)`) — the one reversal decision from 2a, kept over the Kernel's own request-object envelope; `version` required. `RenderedPrompt` narrowed to 3 fields. **No real Kernel class satisfies this Protocol** (it is a from-scratch call convention, not a narrowing), so instead of an `isinstance` proof, the conversion to/from the real `PromptRenderRequest`/`PromptRenderResponse` is proven **lossless in both directions** (`tests/unit/platform_sdk/test_prompt_registry_adapter_conversion.py`, 7 assertions) — the reference conversion functions are test-local, illustrative only, not production code. | **Done** |
| 6 | `ToolInvoker` Protocol (from-scratch, signature kept from 2a) + `ToolDescriptor` + `ToolResult` (moved here from step 3) + the `platform.sandbox.run_command` tool contract, grounded in `PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR`. **`SecretResolver` removed** — see §2.3. **No Kernel class satisfies `ToolInvoker` directly** (from-scratch design), so proven instead against the **real, executed** `LocalSubprocessSandbox` (clean/timed-out/truncated runs) — which found and fixed two real bugs: an over-strict `ToolResult` validator (§6f), and a circular import between `errors` and `models` (§6f). | **Done** |
| **6a** | **NEW — Kernel-side adapters implementing the SDK Protocols**, over `DispatchingLLMGateway`, the Prompt Engine, and the sandbox. Without this, the Protocols from 4–6 have no conforming implementation anywhere. Resolves P1. Proven with real, non-mocked underlying objects (Echo-backed `DispatchingLLMGateway`, `InMemoryPromptEngine`, `LocalSubprocessSandbox`); the timeout-precedence nuance step 6 left open is resolved via `min()` ("more restrictive wins"). Record in §6g. | **Done** |
| **6b** | **NEW — `PackContext` construction + injection path.** Build a real `PackContext` in the composition root, and resolve the zero-argument blocker (`EntrypointLoader`/`SqlAgentRegistry`, or a real `activate()` call path). **This is the actual unlock for every migration step.** Resolves P2. **Next.** | |
| 7 | **REPURPOSED — relocate `pipeline.py` out of the shipped package into `tests/`** (§4.1), and land `ContextService` boundary models (§5.3) + the entry-point contract `PackContext`/`CapabilityPack`/`PackRegistration`/`HealthReport` (§6, §7). Resolves P4's permanent-failure half. | |

**Compliance gate**

| # | Scope |
|---|---|
| 8 | `pack_contract_suite` check 7 (forbidden-import AST scanner) + **an explicit, documented, expiring waiver** for the still-unmigrated pack, so CI stays green through steps 9–13 and the waiver is removed at step 14. Resolves P4's red-CI half. |

**Migration** (fast-following, no other feature work interleaved — §3; order reversed per P6)

| # | Scope |
|---|---|
| 9 | Migrate **`qa-test`** (`verification.py`) — simplest: no LLM call, 4 Kernel imports, no gateway construction. Proves `Agent` + `ToolInvoker` + the new injection path in isolation. |
| 10 | Migrate **`requirements-analyst`** — the first gateway-injection migration. |
| 11 | Migrate **`architecture`**. |
| 12 | Migrate **`build`**. |
| 13 | Migrate **`documentation`**. |
| 14 | Migrate **`pack.py`**'s entry point onto the real SDK types; **remove the step-8 check-7 waiver**; retire the dated direct-Kernel-import exception in `capability_pack_contract.md`. |

**Completion**

| # | Scope |
|---|---|
| 15 | Build the remaining 8 `pack_contract_suite` checks, run them end to end against the migrated pack, and formally record the gate as **satisfied** (not merely built) in `feature_inventory.md`, `capability_pack_contract.md`, and `standing_rules.md`. |

*(18 steps total: 1, 2, 2a, 3, 4, 5, 6, 6a, 6b, 7, 8, 9, 10, 11, 12, 13, 14, 15.)*

**Gate semantics (unchanged):** the Platform SDK growth gate (`standing_rules.md`) lifts only after step 15 — not after step 1, and not after step 8. An SDK existing without a migrated, verified pack is still "no compliant pack exists"; the gate's purpose is a compliant pack, not merely an importable SDK.

---

## 6a. Architecture review findings (2026-07-28) — what changed and why

An independent architecture review of v1.0 of this document, conducted against real source rather than against `platform_sdk.md`'s specification, found seven problems. All were accepted in full. The v1.0 sequence was **not executable as written**: it defined Protocols (2–8) then migrated packs onto them (9–14), with nothing in between making the Kernel able to *supply* those Protocols — and with the mechanism that would have listed as a non-goal.

| # | Severity | Finding | Evidence | Resolution |
|---|---|---|---|---|
| **P1** | **Blocking** | **No step made the Kernel satisfy the SDK Protocols.** Protocols are structural, so v1.0 implicitly assumed existing Kernel classes would conform. Three of the needed ones do not. | `LLMGateway` (§5.1) specifies `complete`/`stream`/`embed`/`count_tokens`/`capabilities`; real `DispatchingLLMGateway` has `complete()` (`gateway.py:358`) and `capabilities()` (`:337`) **only** — 3 of 5 absent. `PromptRegistry` (§5.2) specifies `render(prompt_id, variables, version)` + `get(...)`; real `PromptEngine` (`renderer.py:79`) is `render(request: PromptRenderRequest)` with **no `get()`**. `ToolInvoker` (§5.6) has **no counterpart at all**. Only `SecretResolver` matched exactly (`provider.py:34`) — and it is now dropped anyway. | New step **2a** (decide narrow-vs-extend, amend the spec) + new step **6a** (build the adapters). |
| **P2** | **Blocking** | **The injection path does not exist, and v1.0 listed fixing it as a non-goal** — so the migration steps depended on a mechanism their own plan excluded. | `EntrypointLoader.load()` line 95 is `return cls()` — hardcoded zero-argument; its docstring (lines 21–27) states *"Passing manifest-declared configuration into an entrypoint's constructor is real Capability Manager design work, not attempted here."* `PackContext` (`pack_contract.py:56`) is identity-only (`pack_id`, `pack_version`); its docstring confirms all 14 service attributes are deferred. `pack_contract.py:30`: *"Nothing in this codebase calls `CapabilityPack.activate()` yet."* The only `PackContext(...)` construction anywhere is `capability_packs/software-engineering/tests/test_pack.py:50` — a test. | New step **6b**; the corresponding non-goal in §7 is withdrawn. |
| **P3** | **Blocking** | **The SDK `Agent`/`Tool` Protocols are incompatible with the Workflow Engine's real calling convention**, and a migrated agent would fail to load. | Kernel `Agent` (`agent.py:71,73`): `output_schema: dict`, `execute(inputs: dict) -> dict`. SDK `Agent` (§4.2): `agent_id`, `version`, `input_model`, `output_model`, `execute(AgentRequest) -> AgentResult`. `SqlAgentRegistry` (`registry.py:222`) does `isinstance(loaded, Agent)` against the **Kernel** Protocol → an SDK-shaped agent lacking `output_schema` **fails to load** with *"missing output_schema/execute"*. `AgentStepExecutor._validate_output` (`step_executor.py:165-172`) reads `agent.output_schema`. `Tool` is worse: the method **name** differs (`execute` vs SDK `invoke`). | Step **2a** decides; step **3** builds to that decision, not to §4.2/§4.3 as written. |
| **P4** | High | **Check 7 at step 8 fails loudly rather than trivially, and one target could never pass.** | 57 `ai_os_kernel` imports remain at step 8 → check fails → **CI red for six steps**, violating the zero-regression rule. `pipeline.py` is inside the shipped wheel, imports 11 Kernel modules **and** `sqlalchemy.ext.asyncio` (`:107`, also forbidden), and was a *permanent* non-goal → permanent failure. **Missed cheap fix:** zero pack source modules import `pipeline.py`; only two Kernel-side tests do. | Step **8** gains an expiring waiver; new step **7** relocates `pipeline.py` into `tests/`. |
| **P5** | Medium | **The "5 needed / 10 deferred" split was right in outcome but wrong in derivation**, and two entries were misclassified. | `SecretResolver` was included, but its only use is constructing the pack's own gateway, and the manifest (lines 71–73) declares **no secret permission** — `platform_sdk.md` §6 grants PackContext attributes only for declared capabilities. `ConfigService` was deferred as *"zero real usage"*, but all four prompted agents read `config/llm.yaml` via `Path.cwd()` and `AIOS_DATABASE_URL` via `DatabaseSettings()`. Root cause: 7 of 13 imports are **construction-only**, not consumed capabilities. | §2.3 rewritten (3 capability Protocols, derived from declared permissions); §2.4 added; `SecretResolver` dropped from step 6. |
| **P6** | Low | **Migration order was inverted.** v1.0 called `requirements-analyst` "simplest"; it needs the whole construction chain replaced. `qa-test` makes no LLM call at all. | `verification.py` imports 4 Kernel modules, constructs no gateway/router/engine/secret provider. | Order reversed: `qa-test` first (step 9). |
| **P7** | Low | Documentation arithmetic slip. | §2.1 says *"all 8 `workflow_engine.{…}`"* then lists **nine** modules. The 11 pipeline-only modules are 2 `context_manager` + 9 `workflow_engine`. (The 13 + 11 = 24 total is correct.) | Corrected in §2.1. |

**Two findings reduced scope rather than adding it:** dropping `SecretResolver` (P5) and relocating `pipeline.py` instead of waiting on a Capability Manager (P4).

## 6b. Step 2a — the five reconciliation decisions (2026-07-29)

Each decision is recorded in full, with its evidence, as a dated **v1.0.0 Reconciliation Decision** block in the corresponding section of `platform_sdk.md`. Summary:

| Interface | Decision | Core evidence | Consequence |
|---|---|---|---|
| **`Agent`** (§4.2) | **NARROW** to the dict-based `output_schema` + `execute(inputs) -> outputs` shape | 5 real agents on it (`agent.py:71-73`); `AgentStepExecutor` calls `execute(dict)` and validates against `output_schema` (`step_executor.py:165-172`); `SqlAgentRegistry` gates on `isinstance` (`registry.py:222`) | `AgentRequest`/`AgentResult` deferred past v1.0.0 — **step 3 shrinks** |
| **`Tool`** (§4.3) | **NARROW** the Protocol; **MIXED** on `ToolResult`; **DEFER** `ToolRequest` | `tool.py:65-68` — and the method is named `execute`, not the spec's `invoke`; `SqlToolRegistry` also cross-checks `trust_tier` against `catalog.tools` (`registry.py:277-284`) | `ToolResult`: `stdout_ref`/`stderr_ref` narrowed to inline strings (no `StorageService`), `artifacts` deferred, **and extended with `timed_out`/`truncated`** — two real outcomes the spec cannot express (`sandbox/models.py:63-68`) |
| **`LLMGateway`** (§5.1) | **NARROW** methods 5 → 2 (`complete`, `capabilities`); **EXTEND** `ProviderCapabilities` 10 → 13 fields | `DispatchingLLMGateway` has `complete()` (`gateway.py:358`) and `capabilities()` (`:337`) only; real `ProviderCapabilities` carries 13 fields and its own docstring names this document as the discrepancy it "implements past" (`capability_negotiator.py:98-109`) | `stream`/`embed`/`count_tokens` deferred (additive later = minor bump) |
| **`PromptRegistry`** (§5.2) | **KEEP the documented keyword call style** (reject the Kernel's request-object envelope); **NARROW** `version` to required; **DEFER** `get()` and 2 `RenderedPrompt` fields | Real `PromptEngine.render(request)` (`renderer.py:79`); `models.py:56-63` requires `version` and its docstring states *"nothing here silently picks a version on the caller's behalf"*; `SqlPromptCatalog` exposes only `render()` (`catalog.py:65`) | **The one deliberate "documented shape wins" decision** — a pack-facing Protocol is shaped for its caller, not its implementer (ADR-0004); adapter conversion is ~3 lines |
| **`ToolInvoker`** (§5.6) | **DESIGN** — signature KEPT, grounded in a platform-provided tool id `platform.sandbox.run_command` | The pack declares **zero** tools (`manifest.yaml:71-73`); `SandboxedCommandTool.execute(inputs)` **ignores `inputs`** entirely (`sandboxed_tool.py:110-118`), so agents construct a fresh tool per call (`build.py:324`, `verification.py:265`) | Moving the command into `inputs` makes `invoke(tool_id, inputs)` genuinely meaningful and **fixes** the ignored-inputs wart; step 6a's adapter is built directly over `SandboxExecutor`, not over the dict-based `Tool` |

**Net direction:** four narrowings, two targeted extensions where the real Kernel is richer than the specification, one deliberate reversal in the specification's favour (`PromptRegistry`'s call style), and one from-scratch design. **Every extension is a case where the spec could not express a real, materially-different outcome** — not scope creep.

**Effect on the remaining plan:** step 3 gets *smaller* (two Protocols, no models); step 6 gets one model (`ToolResult`) and one tool contract; steps 4, 5, 6a, 6b, 7, 8, 9–15 are unchanged in scope. **No new step is needed**, and nothing else blocks step 3.

---

## 6c. Step 3 — `Agent`/`Tool` Protocols built and proven (2026-07-29)

Two `Protocol` definitions in `platform_sdk/src/ai_os_sdk/contracts/`, plus the SDK's own `TrustTier`. Both are `@runtime_checkable`, matching the Kernel's own convention so a loader can reject a structurally unrelated entrypoint.

**The claim step 2a's narrowing rested on is now proven against real code, not a mock.** `tests/unit/platform_sdk/test_kernel_satisfies_sdk_contracts.py` imports the actual shipped classes and asserts `isinstance` against the new SDK Protocols — 13 assertions, all passing:

- **`Agent`:** all five Software Engineering pack agents (`ArchitectureAgentEntrypoint`, `BuildAgentEntrypoint`, `DocumentationAgentEntrypoint`, `RequirementsAnalystAgentEntrypoint`, `TestAgentEntrypoint`) plus the Kernel's `EchoAgent`. Each is constructed exactly as `EntrypointLoader` constructs it — `cls()`, zero arguments — so the test exercises the real construction path, and none performs I/O before first `execute`.
- **`Tool`:** the Kernel's `EchoTool` and the one real non-trivial tool, `SandboxedCommandTool`, constructed the way `agents/build.py` and `agents/verification.py` construct it.
- **Negative controls:** an object missing `output_schema` is not an `Agent`; a real agent is not a `Tool` (the tier is what separates them, and an agent passing as a tool could bypass ADR-0016's sandbox guard).

**Three decisions and findings worth recording:**

1. **The SDK defines its own `TrustTier` rather than importing the Kernel's**, because §2 rule 1 makes this SDK the dependency floor. Both enums independently mirror `manifest.schema.json`'s `tools[].trustTier` enum — verified to be exactly `["tier1_sandboxed", "tier2_trusted"]` — and a test asserts the two carry identical values, since nothing else would catch them drifting apart. **Consequence, recorded rather than hidden:** because they are distinct Python types, a Kernel-typed tool is *not statically assignable* to the SDK `Tool` Protocol even though it satisfies it at runtime. Bridging that is step 6a's adapter, exactly as §4.3's decision block anticipated.
2. **`mypy --strict` rejects enum-to-string and cross-enum equality as non-overlapping**, even where it is true at runtime for a `StrEnum`. Four such comparisons were written and then corrected to compare `.value` explicitly — which is also the more precise claim, since what must agree with the schema is the wire value, not member identity.
3. **The cross-boundary test lives in the root suite, not in `platform_sdk/tests/`.** A test importing `ai_os_kernel`, a pack, *and* `ai_os_sdk` is inherently a cross-boundary assertion, and `platform_sdk/tests/` deliberately imports nothing from the Kernel or any pack — holding the dependency-floor discipline in the SDK's own test suite, not only in its source.

**Also asserted: the limit of what the runtime check proves.** A test constructs an object whose `execute` is not async, takes no arguments, and whose `output_schema` is a plain string — and confirms it still passes `isinstance`. This makes §4.2's precision correction executable: a `runtime_checkable` Protocol verifies *member presence only*, never signatures, so the check converts "this is not remotely an agent" into a clear error but never certifies the contract.

---

## 6d. Step 4 — `LLMGateway` Protocol built and proven (2026-07-29)

One `Protocol` in `platform_sdk/src/ai_os_sdk/contracts/llm_gateway.py`, at the narrowed shape decided in 2a (`complete()` + `capabilities()` only), plus its full model set in `platform_sdk/src/ai_os_sdk/models/llm.py`: `Message`, `MessageRole`, `LLMRequest`, `StopReason`, `UsageRecord`, `LLMResponse` (field-for-field mirrors of the real, working Kernel models — narrowed exactly as far as the Kernel's own models are narrowed, no further), and `ProviderCapabilities` (extended to the real 13 fields, per 2a).

**Proven against the real `DispatchingLLMGateway`, not a mock.** Added to `tests/unit/platform_sdk/test_kernel_satisfies_sdk_contracts.py`: `DispatchingLLMGateway(router=StaticRouter(routes={}), gateways={})` — constructed with an empty routing table and no providers, so zero I/O and zero network occur — satisfies the new SDK `LLMGateway` Protocol via `isinstance`. **A negative control worth keeping:** `EchoLLMGateway`, which implements only `complete()`, does *not* satisfy the SDK Protocol. This is itself evidence the narrowing is exact rather than accidentally loose — the Kernel's own internal `LLMGateway` Protocol requires only `complete()`, so it is narrower than this SDK Protocol; only the real, production `DispatchingLLMGateway` (which also implements `capabilities()`) conforms.

**One thing worth recording:** `LLMRequest.metadata` uses the SDK's own canonical, seven-field `TraceContext` (`ai_os_sdk.models.common`, built in step 2), not the Kernel's own two-field reduced `TraceContext` (`llm_gateway/models.py:107`). The two are structurally different models serving the same field name in different packages — not a bug, since the SDK is the dependency floor and cannot reference the Kernel's type, but worth a future adapter author's attention when step 6a builds the real conversion between a pack-facing `LLMRequest` and whatever the Kernel's `DispatchingLLMGateway.complete()` actually consumes.

**Verified:** `platform_sdk/tests/` 109 → 124 passed (15 new: `test_llm_models.py`, `test_llm_gateway_contract.py`); cross-boundary proof 13 → 15 passed; `mypy --strict` clean across 304 files; `ruff check`/`format` clean; root suite 816 → 818 passed, 11 skipped (unchanged); SE pack suite unchanged at 46; zero Kernel/pack source modified (`git status -- kernel/ capability_packs/` reports nothing).

---

## 6e. Step 5 — `PromptRegistry` Protocol built and proven by conversion, not identity (2026-07-29)

One `Protocol` in `platform_sdk/src/ai_os_sdk/contracts/prompt_registry.py`, at the shape 2a kept from the specification: `async def render(prompt_id, variables, *, version) -> RenderedPrompt`, `version` keyword-only and required. `RenderedPrompt` in `platform_sdk/src/ai_os_sdk/models/prompt.py`, narrowed to `prompt_id`/`version`/`content` — the real `PromptRenderResponse`'s exact three fields.

**Why this step's proof is shaped differently from steps 3 and 4's.** `Agent`, `Tool`, and `LLMGateway` were each narrowed *to* a shape a real Kernel class already has, so a single `isinstance` call proved compatibility. `PromptRegistry` is the opposite case: 2a deliberately *kept* the documented call style specifically because it is a better pack-facing API than the Kernel's own `PromptRenderRequest` envelope. No real class implements this signature, and building one would be step 6a's job, not this one's. What this step proves instead — the claim the 2a decision block's "the adapter conversion in step 6a is three lines" rests on — is that converting between the two shapes loses nothing in either direction.

**The proof:** `tests/unit/platform_sdk/test_prompt_registry_adapter_conversion.py`, 7 assertions, all passing. Two small, deliberately test-local functions (not shipped in `ai_os_sdk` — building the real adapter is step 6a's) perform the conversion:

- `sdk call → PromptRenderRequest`: every field maps one to one with no transformation (`prompt_id=prompt_id, version=version, variables=variables`); an empty `variables` mapping survives as empty on both sides; a value as rich as a nested dict inside `variables` survives untouched; the Kernel's own blank-`prompt_id` validator still fires after conversion, proving the conversion doesn't bypass existing validation.
- `PromptRenderResponse → RenderedPrompt`: every field maps one to one; a full request→(simulated real engine)→response→`RenderedPrompt` round trip preserves `prompt_id`/`version` exactly; no field is fabricated, defaulted, or silently drawn from the request instead of the response.

**Also proven, at the Protocol level (`platform_sdk/tests/test_prompt_registry_contract.py`):** the documented keyword call style itself — `await registry.render("requirements.analyze", {"requirement": "x"}, version="0.1.0")`, the exact one-line call the decision block cites as the reason this shape was kept — and that `version` is genuinely keyword-only: calling with it positional raises `TypeError` before any implementation code runs.

**Verified:** `platform_sdk/tests/` 124 → 142 passed (18 new: `test_prompt_models.py`, `test_prompt_registry_contract.py`); cross-boundary suite 15 → 22 passed (7 new); `mypy --strict` clean across 309 files (two `type: ignore` mismatches found and corrected — one now-unneeded, one pointing at the wrong error code); `ruff check`/`format` clean; root suite 818 → 825 passed, 11 skipped (unchanged skips); SE pack suite unchanged at 46; zero Kernel/pack source modified.

---

## 6f. Step 6 — `ToolInvoker` Protocol built and proven against real execution (2026-07-29)

One `Protocol` (`ToolInvoker`) in `platform_sdk/src/ai_os_sdk/contracts/tool_invoker.py`, plus `ToolDescriptor`/`ToolStatus`/`ToolResult` in `platform_sdk/src/ai_os_sdk/models/tool.py`, and the `platform.sandbox.run_command` tool concept (id constant + input/output JSON Schemas + a real `ToolDescriptor` instance, `PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR`) grounding `available_tools()` in a genuine, non-empty answer — all at the from-scratch shape 2a designed.

**Why this step's proof runs real commands through a real sandbox, not just constructed models.** `ToolInvoker` is a from-scratch design like `PromptRegistry` — no Kernel class satisfies it, so there's no `isinstance` proof. But unlike `PromptRegistry`, the whole point of `ToolResult`'s extension (`timed_out`/`truncated`) is to preserve a distinction a **real, executing** sandbox produces — proving that with hand-constructed `SandboxResult` values would only show the model accepts three different inputs, not that the real execution path genuinely produces three different outcomes. `tests/unit/platform_sdk/test_tool_invoker_sandbox_conversion.py` therefore runs the real `LocalSubprocessSandbox` three times — a clean `print('hello')`, a `time.sleep(5)` against a 0.3s timeout, and a 100,000-byte print against a 16-byte cap — and converts each real `SandboxResult` through a test-local reference function into a `ToolResult`.

**This real execution found two genuine bugs before they could reach step 6a — exactly what running the design was for.**

1. **The `ToolResult` model's own validator was wrong.** It required `exit_code` to be set whenever `timed_out` was `False`, on the assumption that only a real timeout leaves a process without a confirmed exit code. Running the truncation case disproved this: `sandbox/executor.py`'s own cap-breach path (`cap_exceeded` branch, `_finished_result(wait_task, None)`) kills the process as soon as the output cap is hit, and on this platform that kill consistently outraces the process's own exit — confirmed by direct probing across `max_output_bytes` values from 16 down to 1 byte, every run producing `exit_code=None` with `timed_out=False`. The validator was corrected to one direction only: `exit_code` must be `None` when `timed_out` is `True`; the reverse is not enforced, because it is false.
2. **A real circular import between `ai_os_sdk.errors` and `ai_os_sdk.models`.** `ToolResult.error` needs `StructuredError`, which lived in `ai_os_sdk.errors` — but `ai_os_sdk.errors.taxonomy` itself imports `ai_os_sdk.models.common.TraceContext`. Importing `ai_os_sdk.errors` first (as the sandbox-conversion test originally did) triggered `ai_os_sdk.models` package init, which reached `models.tool`, which needed `ai_os_sdk.errors` again, mid-initialization — `ImportError`. Fixed by relocating `ErrorCategory`/`StructuredError` into a new `ai_os_sdk.models.error` module (both remain fully public via `ai_os_sdk.errors.ErrorCategory`/`ai_os_sdk.errors.StructuredError`, re-exported unchanged) — the same fix shape already applied to `TrustTier` one step earlier, for the identical reason: a lower layer cannot import a higher one.

**A related, smaller layering fix, found while adding `ToolDescriptor`:** `TrustTier` was relocated from `ai_os_sdk.contracts.tool` (where step 3 first defined it) into `ai_os_sdk.models.tool`, since `ToolDescriptor` — a model — needed it too, and a model depending on a contract would invert the package's own layering. `ai_os_sdk.contracts.tool` re-exports it unchanged.

**Verified after both fixes:** `platform_sdk/tests/` 142 → 170 total across the two directories (26 in the cross-boundary suite, including the corrected truncation test, which now correctly asserts `FAILURE`/`exit_code=None` for the truncated case — not the originally-assumed `SUCCESS`); `mypy --strict` clean across 315 files (two more `type: ignore` issues found and fixed, plus a genuine `attr-defined` error from the `taxonomy.py` re-export requiring explicit `as`-import syntax under `--strict`); `ruff check`/`format` clean; root suite 825 → 829 passed, 11 skipped (unchanged skips); SE pack suite unchanged at 46; zero Kernel/pack source modified.

**One documented, deliberately unresolved nuance:** `ToolInvoker.invoke`'s own `timeout_seconds` keyword and `platform.sandbox.run_command`'s required `inputs["timeout_seconds"]` are two different timeouts — an outer, tool-agnostic ceiling and the specific sandboxed command's own required timeout. §5.6's decision block documents both; how a step 6a adapter reconciles the two when both are supplied is explicitly left to that step, not decided here.

---

## 6g. Step 6a — real Kernel-side SDK adapters built and proven against real underlying objects (2026-07-29)

Three adapter classes in the new `kernel/src/ai_os_kernel/sdk_adapters/` package (explicitly **not** inside `platform_sdk/`, since the SDK cannot depend on the Kernel — this is the boundary where the Kernel implements the SDK, the reverse dependency direction): `LLMGatewayAdapter` wraps `DispatchingLLMGateway`, `PromptRegistryAdapter` wraps `PromptEngine`, `ToolInvokerAdapter` wraps `SandboxExecutor`. `kernel/pyproject.toml` gained its first and only dependency change this entire initiative — `ai-os-sdk` — since the Kernel now genuinely *implements* SDK Protocols rather than merely resembling them.

**Every field mapping was verified against real source before writing, not assumed** — continuing the discipline of steps 4–6. `UsageRecord` and `ProviderCapabilities` are field-identical on both sides (by step 4's own design); `MessageRole`/`StopReason` map by `.value` between independent enum classes, matching the `TrustTier` precedent from step 6. `TraceContext` is a real, one-directional, documented narrowing: the SDK's 7-field canonical shape reduces to the Kernel `llm_gateway.models.TraceContext`'s 2 fields (`workflow_id`/`step_id`) — flagged as a discrepancy to resolve exactly here in step 4's own record (§6d), now resolved honestly rather than silently.

**A new, real gap surfaced while building `ToolInvokerAdapter`, not assumed in advance:** v1.0.0's `ToolInvoker.invoke(tool_id, inputs, *, timeout_seconds)` Protocol carries no trace or correlation parameter at all, yet a failing `ToolResult.error: StructuredError` requires a `TraceContext` (§4.4, required). Resolved by generating a fresh, real, per-invocation `TraceContext` via the Kernel's existing `ai_os_kernel.observability.trace.generate_trace_id()` (called twice, once per field, since no dedicated span-id generator exists) — explicitly **not** correlated with whatever workflow or step actually invoked the tool, since the Protocol provides nothing to correlate against. Recorded here as a concrete, evidenced input for whichever future step revisits §5.6's signature.

**The timeout-precedence decision step 6 explicitly left open (§6f) is resolved: the more restrictive of the two timeouts always wins.** `invoke()`'s own `timeout_seconds` and the tool's own required `inputs["timeout_seconds"]` can both be supplied; the effective timeout is `min(timeout_seconds, inputs["timeout_seconds"])` when an outer bound is supplied, or `inputs["timeout_seconds"]` directly otherwise (`None` means "no outer ceiling," not "no timeout at all" — the tool's own timeout is always required and always real). Chosen over "one is authoritative, reject on conflict" because it never rejects a call over a disagreement with an obvious safe resolution, and because it composes correctly with the Protocol's own stated intent for the outer parameter as "a generic, tool-agnostic ceiling" (`ai_os_sdk.contracts.tool_invoker`) — a ceiling is a `min()`, never an equality requirement. Proven with four real-execution tests measuring genuine `time.monotonic()` elapsed wall-clock time around real `time.sleep(5)` subprocess commands through `LocalSubprocessSandbox`, not by inspecting internal variable state: a tighter outer bound governs, a tighter inputs bound governs, no outer bound falls through to the inputs bound, and two generous bounds do not falsely trigger a timeout.

**Proven against real underlying objects, not mocks**, matching this initiative's established convention: `LLMGatewayAdapter` against a real `DispatchingLLMGateway` (`StaticRouter` + `StaticCapabilityNegotiator` + `EchoLLMGateway`, 8 tests) — including discovering, by real test failure rather than assumption, that `EchoLLMGateway` hardcodes its own `provider`/`model_id` self-description (`"echo"`/`"echo-1"`) regardless of registration key; `PromptRegistryAdapter` against a real `InMemoryPromptEngine` (5 tests); `ToolInvokerAdapter` against a real `LocalSubprocessSandbox` running genuine subprocesses (10 tests, including the 4 timeout-precedence tests above). None of the three are wired into `bootstrap.py`, `EntrypointLoader`, or any pack — that is step 6b (injection path) and steps 9–14 (migration); this step proves the adapters exist and work in isolation.

**Verified:** 23 new tests, all passing (`tests/unit/kernel/sdk_adapters/`); root suite 829 → 852 passed, 11 skipped (unchanged skips); SE pack suite unchanged at 46; `mypy --strict` clean across 323 files; `ruff check`/`format` clean; `git status` confirms only `kernel/pyproject.toml` and `uv.lock` modified among pre-existing tracked files, everything else strictly additive.

---

### 6a.1 Additional observations recorded during Step 2 (not review findings)

Two things found while building step 2, recorded here because they are inputs to step 2a rather than problems with this plan:

- **Three `TraceContext` definitions will now coexist.** `ai_os_kernel.observability.trace.TraceContext` (`trace_id` required; no `span_id`, no `run_id`) and `ai_os_kernel.llm_gateway.models.TraceContext` (`workflow_id`/`step_id` only) already exist, and **both docstrings explicitly name `platform_sdk.md` §4.1 as the canonical shape they are reduced slices of**. Step 2 creates that canonical version. Consolidating the two Kernel partials onto it is Kernel-side work for step 2a/6a to schedule — it is not in scope for step 2, which adds a type and changes no existing code.
- **`StructuredError.trace` is required by §4.4 but no raise site can supply one yet.** §4.4 marks `retry_after_seconds` and `details` as `| None` but *not* `trace`, so required is the faithful reading. Step 2 therefore keeps `AiOsError.trace` optional (a raise site deep in a library genuinely may not know it) while `StructuredError.trace` is required, with the conversion demanding a trace explicitly at the boundary. Whether that boundary discipline is workable in practice is a step-2a question.

---

## 7. Explicit non-goals for v1.0.0

Deferred, deliberately, so scope doesn't creep mid-build:

- **The 11 Protocol interfaces with no consumed usage today** (`RetrievalService`, `MemoryService`, `EventBus`, `ConfigService`, `StorageService`, `WorkspaceService`, `Telemetry`, `TraceabilityService`, `QualityGateRegistry`, `SpeechGateway`, and — added in v2.0 — **`SecretResolver`**). For the first ten, each sits on a 0%-built or docstring-only Kernel subsystem, so building the pack-facing contract first would ship an interface nothing implements. For `SecretResolver` and `ConfigService` specifically, the need disappears once step 6b injects a constructed gateway; and `SecretResolver` would additionally grant a capability the pack's manifest never declared (§2.3).
- **SDK semantic-versioning enforcement in the Manifest Loader** (§8 of `platform_sdk.md`) — requires a real SDK version to exist first; a small follow-on once v1.0.0 itself is versioned and shipped.
- **The full 9-check `pack_contract_suite`** in the SDK-build phase — only check 7 ships early (§4, §4.1); checks 2/3/4/9 need a migrated pack to test against meaningfully.
- **`platform_sdk/prompts/`.** Purpose undocumented anywhere in the source spec; left untouched pending a product-owner decision, not invented here.
- **Consolidating the Kernel's two partial `TraceContext` classes** onto the SDK's canonical one (§6a.1). A real Kernel change with its own regression surface; scheduled by step 2a/6a, not smuggled into a model-definition step.
- **Any 6th SE-pack agent, or any new Capability Pack.** Still blocked by the existing hard gate until step 15 completes — building the SDK does not itself lift the gate (see §6's gate semantics note).

**Two non-goals from v1.0 are now withdrawn**, because the architecture review showed they were load-bearing rather than deferrable:

- ~~"`pipeline.py`'s 11 composition-root imports"~~ — withdrawn. It is now **step 7**. v1.0 deferred this to a future Capability Manager; the review found a far cheaper resolution (relocate it into `tests/`, since nothing in the pack's own source imports it) which is also required for check 7 to ever pass. See §4.1.
- ~~"Migrating `kernel/bootstrap.py` or any other Kernel-internal composition"~~ — withdrawn. v1.0 justified this as *"the Kernel implements these Protocols; it does not consume them,"* which is true but beside the point: **something must construct the adapters and the `PackContext` and inject them, and `bootstrap.py` is the composition root** (ADR-0010, no DI container). That work is now **steps 6a and 6b**. It remains true that no Kernel code is migrated to *depend on* `ai_os_sdk` types for its own internal use.

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
