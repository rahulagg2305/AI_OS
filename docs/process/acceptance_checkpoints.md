# Acceptance and Demo Checkpoints

**Status:** Active · **Introduced:** Phase R2 (2026-07-31)

Task-level "done" is proven by tests (`docs/process/ticket_templates.md`).
**Stage-level "done" must be something the product owner can see or run
themselves** — not a report claiming it works.

## The rule

A Stage is complete only when its **acceptance demo** has been executed
and its output shown. The demo must be:

1. **A single command** the product owner can run, copy-pasteable.
2. **Real end to end** — real database, real sandbox, no mocks standing
   in for the thing being demonstrated.
3. **Self-evident** — the output shows the claim is true without needing
   the code explained.
4. **Recorded** in the Stage's final report with its real output pasted.

A Stage whose demo cannot be run is not complete, regardless of how many
of its Tasks are `done`.

## Demo per Stage (current, real)

| Stage | Acceptance demo | Runnable today? |
|---|---|---|
| P01-S04 Health and Lifecycle | `curl localhost:8000/health/ready` against a started Kernel; shows per-pack real state | Yes |
| P01-S06 CI and Test Infrastructure | A pushed commit produces a green Actions run | Partly — R-003 |
| P02-S01 Workflow Execution Core | `pytest tests/integration/workflow_engine/test_delivery_pipeline.py -v` — a real 8-step run completes | Yes |
| P02-S05 Capability Manager and SDK | `pytest tests/contract -v` — 9-check contract suite, zero waivers | Yes |
| P02-S06 Quality Gate Engine | Run the pipeline with a deliberately failing test; show it halts and a real `evaluation.gate_results` row exists | Yes |
| P03-S01 Sandboxed Tool Execution | `pytest tests/integration/sandbox/test_docker_sandbox_live.py -v` — live container, no network | Yes (needs Docker) |
| P03-S05 Security and Human Approval | Start a workflow, see it pause at an approval, decide it, see it resume | **No — not built** |
| P04-S01 Evaluation Engine | Run the same workflow twice; show a comparison with mean and variance | **No — not built** |
| P06-S03 Dashboard | Open the dashboard, decide an approval from it, watch the workflow resume live | **No — not built** |

## Convention for new Stages

When a Stage is defined, its demo is written **at the same time as its
first Task ticket**, not at the end. If nobody can state the demo up
front, the Stage is not well-scoped yet.
