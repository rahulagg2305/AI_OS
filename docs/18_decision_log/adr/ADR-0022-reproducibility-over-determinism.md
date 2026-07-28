# ADR-0022: Reproducibility over Determinism

**Status:** Accepted
**Date:** 2026-07-25
**Decision Makers:** Chief Architect, Project Owner
**Related Documents:** `docs/00_constitution/ai_governance_framework.md`, `docs/03_architecture/kernel/evaluation_engine.md`

---

## Context

The AI Governance Framework required that "given identical inputs and configuration, AI should produce consistent engineering outputs", and the requirement was echoed as a design goal in the Workflow, Agent, Context Manager, and Knowledge Manager documents. LLM inference is not deterministic. Current frontier models additionally reject the sampling parameters that were historically used to reduce variance, and several perform adaptive internal reasoning whose depth varies per request. The requirement as written is therefore unachievable, and an unachievable governance requirement is worse than none: it is either quietly ignored — which teaches contributors that governance is decorative — or it blocks progress on a technicality.

The underlying need is real, though. It is not identical output; it is the ability to explain a run, repeat it under the same conditions, and compare two runs fairly.

## Decision

**Replace determinism with reproducibility, defined as three obligations.**

**1. Configuration reproducibility (required).** For every workflow run and every experiment run, the platform records the complete set of inputs that determine behaviour: workflow definition ID and version, agent IDs and versions, prompt IDs and versions, tool IDs and versions, pack IDs and versions, model alias → resolved provider/model/version, all model parameters actually sent, context-pack IDs and versions, retrieval index generation and embedding model version, the resolved configuration set, and Kernel version. This bundle — the **run manifest** — is durable and queryable. Any run can be re-launched under exactly the same conditions.

**2. Deterministic platform behaviour (required).** Everything the platform itself does is deterministic given the same inputs: context assembly, retrieval ranking, chunking, prompt rendering, gate evaluation, and cost computation. Non-determinism is confined to the model call. This is the harder engineering requirement and it is not relaxed.

**3. Recorded non-determinism (required).** Model responses, token counts, latency, cache hits, tool-call sequences, and gate outcomes are recorded per run. Where a metric is compared across models, comparison uses **repeated runs with reported variance**, never a single run.

**Fairness rule for experiments.** Within an experiment, everything except the deliberately varied dimension is pinned by the run manifest. Prompts are held **byte-identical across models** by default; if a provider requires an adapted prompt, the adaptation is recorded as a declared variable of the experiment and reported alongside results, because an unrecorded per-model prompt tweak silently invalidates the comparison.

The Governance Framework's "Deterministic Engineering" principle is reworded accordingly, and the Constitution's "replayable whenever practical" language is satisfied by obligations 1–3.

## Alternatives Considered

- **Keep the determinism requirement and interpret it loosely** — Rejected: an unenforceable rule corrodes the credibility of every other rule in the Governance Framework.
- **Require `temperature=0` for determinism** — Rejected on fact: it never guaranteed identical outputs, and current models reject the parameter outright.
- **Cache model responses so replay returns the original output** — Useful for debugging and supported by the caching strategy, but rejected as the definition of reproducibility: it replays a recording rather than reproducing the conditions, and would make a re-run of an experiment meaningless as evidence.
- **Drop reproducibility claims entirely** — Rejected: it would remove the basis for the benchmarking product goal.

## Consequences

### Positive
- The governance requirement becomes verifiable, so it can actually be enforced.
- Multi-LLM comparison rests on a defensible methodology (pinned conditions, repeated runs, reported variance).
- Debugging improves: any run can be re-launched under identical conditions.

### Negative
- The run manifest is a substantial data structure that must be captured completely; an omitted field silently weakens reproducibility, so its schema is validated.
- Repeated runs to establish variance cost real money; experiment definitions must declare run counts, and the Dashboard must show variance rather than single-run point values.

### Neutral
- Several documents are reworded from "deterministic" to "reproducible"; no architectural component changes.

## Compliance

Amends the AI Governance Framework's Deterministic Engineering principle. Consistent with the Constitution's Observability by Default.

## References

- `docs/03_architecture/kernel/evaluation_engine.md`
- `docs/06_capability_packs/benchmarking/overview.md`

---

## Implementation Status (appended 2026-07-28 — not part of the Accepted decision)

**Status in code:** Partially implemented

Obligation 2 (deterministic platform behaviour) holds for what is built — context assembly, prompt rendering, and cost computation are deterministic — and obligation 3 is partially met: the `llm_calls` recorder captures resolved model, token counts, and cost per call. Obligation 1 is not built: there is no run manifest, no experiment concept, and no replicate or variance machinery, because `ai_os_kernel.evaluation_engine` is a docstring-only stub (the `evaluation` schema tables exist but have no writer).

Live status: [`feature_inventory.md`](../../19_roadmap/feature_inventory.md) · Build history: [`history/INDEX.md`](../../19_roadmap/history/INDEX.md)
