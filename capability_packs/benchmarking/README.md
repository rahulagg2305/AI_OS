# Benchmarking Capability Pack

Controlled, repeatable multi-LLM experiments over the same software
engineering work (`docs/06_capability_packs/benchmarking/overview.md`).

## Status: one real component — experiment definition and validation

**First real increment (`P04-S03-M34-T01`, 2026-08-07).** This pack
declares no agents, tools, or workflows yet, and has no `manifest.yaml`
— nothing here needs pack activation. It contains one real, pure
component: [`experiment_definition.py`](src/ai_os_pack_benchmarking/experiment_definition.py),
which validates a raw experiment spec (pinned workflow, model
variants, replicate count) against the overview's own real, decided
rules (§7) — no sampling-parameter variables, no fewer than 2 variants
or 3 replicates, no duplicate variant keys — and, via an injected
`WorkflowDefinitionExistenceCheck`, confirms the pinned workflow
definition genuinely exists.

The real, Postgres-backed implementation of that check
(`ai_os_kernel.sdk_adapters.workflow_definition_existence_adapter`)
lives in the Kernel, wrapping the already-real `SqlWorkflowDefinitionCatalog`
— proven end to end in `tests/integration/evaluation_engine/test_experiment_definition_validation.py`.
Not yet wired into any real submission/execution path — that is a
later ticket's own scope.
