"""Quality Gate Engine — executes gates and returns structured results.

Executes only; it never decides workflow consequence — that belongs to
the Workflow Engine's Gate Coordinator (ADR-0006). An LLM-as-judge gate
may only be `warning` severity, never the sole blocking gate for a
stage.

**The Gate Registry is now real (`P02-S06-M15-T05`)** —
:mod:`ai_os_kernel.quality_gate_engine.registry` resolves a declared
``gateId`` to a real, manifest-derived :class:`~ai_os_kernel.
quality_gate_engine.registry.GateDefinition`. See that module's own
docstring for the full design. Gate Executor, Result Evaluator, and
Policy Enforcer remain unbuilt.

See docs/03_architecture/kernel/quality_gate_engine.md, ADR-0006.
"""
