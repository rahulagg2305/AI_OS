"""Quality Gate Engine — executes gates and returns structured results.

Executes only; it never decides workflow consequence — that belongs to
the Workflow Engine's Gate Coordinator (ADR-0006). An LLM-as-judge gate
may only be `warning` severity, never the sole blocking gate for a
stage.

See docs/03_architecture/kernel/quality_gate_engine.md, ADR-0006.
Not yet implemented — Implementation Roadmap Stage B/C.
"""
