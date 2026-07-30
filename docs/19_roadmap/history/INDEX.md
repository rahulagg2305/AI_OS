# AI_OS Implementation History — Index

**Status:** Active | **Last Updated:** 2026-07-28

This folder holds the full, detailed, chronological implementation history that used to live entirely inside `docs/19_roadmap/implementation_status.md`. That document is now short by design — current stage, what exists, current blockers, next step — and links here for detail. Nothing from the original document was deleted; it was split by logical milestone/subsystem (not by date) and, as an absolute safety net, also preserved in full in `000_full_snapshot_pre_split_2026-07-28.md`.

Files are numbered in roughly the order the work happened, grouped by subsystem where a milestone's own entries were contiguous in the source. Two subsystems (Context Manager) were deliberately pulled out of an otherwise-contiguous LLM Gateway block to keep them together — see `011`/`012` below.

| File | Covers |
|---|---|
| `000_full_snapshot_pre_split_2026-07-28.md` | Complete, unmodified, verbatim copy of the original `implementation_status.md`, as an absolute backstop — not a milestone file. |
| `001_project_bootstrap_and_configuration.md` | Stage A Steps 1–2: `uv` workspace, composition root, Configuration Manager, Observability skeleton, Manifest Loader, Health & Lifecycle, template pack. |
| `002_persistence_foundation.md` | Stage B: first Postgres schema (`workflow_instances`/`workflow_events`/`workflow_leases`), Alembic, Docker Compose dev environment. |
| `003_workflow_engine_core.md` | Definition loading/validation, instance creation, state transitions, multi-step progression, Agent/Tool contracts and step executors, lease acquire/renew/reap, run-to-completion, `workflow_steps`/`approvals`/`list_events`. |
| `004_stage_a_cross_cutting_infrastructure.md` | CI pipeline realignment, minimal Secrets Resolution (ADR-0024), real OpenTelemetry spans and metrics (ADR-0017). |
| `005_catalog_and_evaluation_schema_buildout.md` | Governance/platform/trace schemas, and the full `catalog`/`evaluation` schema buildout (workflow_definitions, prompts, tools, agents, packs, run_manifests, experiments, gate_results, metrics, llm_calls, pack_state_transitions) plus retrofitted FKs. |
| `006_llm_gateway_and_prompt_engine_foundation.md` | First LLM Gateway slice + `llm_calls` writer; first Prompt Engine slice, `PromptedCompletionService`, `SqlPromptCatalog`; `catalog.prompts` composite-PK/FK retrofit. |
| `007_workflow_step_contract_and_registries.md` | Step Contract documentation, `WorkflowStep` validation, `workflow_steps` writer extensions, minimal `AgentRegistry`/`ToolRegistry` and their SQL-backed implementations, `EntrypointLoader`. |
| `008_first_real_llm_integration_and_prompted_agent.md` | Minimal Capability Manager slice, `AnthropicAdapter`, first end-to-end Prompt→LLM→`llm_calls` path, `PromptedAgent`/`AgentStepExecutor`, bootstrap wiring. |
| `009_security_manager_and_http_routes.md` | Minimal Security Manager slice, first authenticated HTTP routes, paginated `GET /api/v1/workflows`. |
| `010_capability_manager_pack_lifecycle.md` | Pack lifecycle writer, bootstrap wiring, `pack:manage`-gated HTTP surface. |
| `011_llm_gateway_advanced_router_retry_budget.md` | Router, `DispatchingLLMGateway`, second provider (`LocalAdapter`), Retry & Fallback chain, Circuit Breaker, Backoff, Error Taxonomy, Policy & Budget Enforcer, `TraceContext`, Capability Negotiator. |
| `012_context_manager.md` | Context Manager first real slice and the Size & Token Budget Enforcer (pulled out of the LLM Gateway block above). |
| `013_retrieval.md` | Knowledge schema/migration, knowledge writer, keyword-search reader. |
| `014_sandbox_and_tool_execution.md` | Minimal Tier 1 Sandbox Executor (`LocalSubprocessSandbox`), `tier1_sandboxed` Tool + `ToolStepExecutor` guard. |
| `015_architecture_agent.md` | Software Engineering pack's Architecture Agent. |
| `016_build_agent.md` | Software Engineering pack's Build Agent (real sandboxed file write). |
| `017_test_agent.md` | Software Engineering pack's Test Agent (no LLM call). |
| `018_documentation_agent.md` | Software Engineering pack's Documentation Agent. |
| `019_delivery_pipeline.md` | Architecture → Build → Test → Documentation chained via `WorkflowStepOutputResolver` into one real workflow. |
| `020_docker_sandbox.md` | Real ADR-0016 Tier 1 `DockerSandbox` backend, including the Windows npipe/`detach=True` stdin-EOF bug fix. |
| `021_documentation_reconciliation_and_verification.md` | Health-audit doc-drift closure, agent-catalog rename (`architect`→`architecture`, `test`→`qa-test`), shared Postgres fixture fix, first full green integration run (218 passed, 10 skipped). |
| `022_gap_analysis_and_blockers_snapshot.md` | Point-in-time (2026-07-28) snapshot of the old document's full `## 4. What Remains`, `## 5. Blockers / Risks`, and `## 6. Recommended Next Small Step` sections, preserved verbatim before `implementation_status.md` was shortened. |
| `023_docker_sandbox_default_wiring.md` | Deleted the stale `capability_packs/analytics/` folder; resolved the `sys.executable` portability gap (`python_command` on `SandboxExecutor`); wired `DockerSandbox` in as the Software Engineering pack's real default backend (`AIOS_SANDBOX_BACKEND`); new real, Docker-gated end-to-end pipeline test proving network isolation and filesystem containment during an actual generated-code run. |
| `024_docker_verification_and_requirements_analyst.md` | First real (not collect-only) run of the Docker-gated integration suite — passed; two real bugs found and fixed (`pipeline.py`'s own independent `python_command` re-derivation, `test_verification_agent_pack.py`'s hardcoded `sys.executable`); fifth real Software Engineering agent, Requirements Analyst, proven independently. |
| `025_documentation_consolidation_audit.md` | Full documentation/architecture/folder-structure consolidation audit (100 files, docs only). Discovered ~70 documented directories have **zero tracked files** and are absent from a fresh clone; corrected badly stale stage status in `PROJECT_INDEX.md`/`README.md`/`implementation_roadmap.md`; added honest Implementation Status sections to 82 documents; appended implementation-status notes to all 25 ADRs (append-only); resolved every TBD found; removed the dead `capability_packs/software_engineering/` duplicate. |
| `026_platform_sdk_gate_and_audit_completion.md` | Recorded the Platform SDK growth gate as a hard product-owner blocker in 4 places (`capability_pack_contract.md`, `implementation_status.md`, `feature_inventory.md`, `standing_rules.md`); closed the remaining 16-document audit gap left by `025`'s session-limited subagents — documentation is now 100% audited. Found: only 3/9 workflow states and 2/7 step types ever execute; the monotonic-narrowing authorization chain only computes its first term; Context Manager has no `trust` field at all; `tests/security/` is empty; only 1 of 5 secrets backends exists; the forbidden-import CI check the coding standards document claims does not exist. |
| `027_platform_sdk_v1_scope_plan.md` | **Archived 2026-07-30, not a milestone written directly into this folder** — a verbatim copy of the now-closed `docs/03_architecture/platform/platform_sdk_v1_scope.md` (the full 18-step-plus-2-inserted-steps Platform SDK v1.0.0 build plan, all steps complete), moved here per the new file-splitting standing rule since it exceeded the 500-line threshold and is a completed plan, not an active/growing document. The live document at its original path keeps a short, permanent summary and points here for full step-by-step detail. |

For the current, live state (short), see `docs/19_roadmap/implementation_status.md`.
