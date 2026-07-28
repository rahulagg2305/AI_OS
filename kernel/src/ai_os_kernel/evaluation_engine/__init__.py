"""Evaluation Engine — metrics, run manifests, and comparison statistics.

Records the run manifest for every workflow run (ADR-0022), collects
cost/quality/performance/process metrics, and computes comparison
statistics (mean + variance over replicates, excluding cache-served
runs) for multi-LLM experiments. Experiment *definition* belongs to the
Benchmarking Capability Pack, not here — see
docs/03_architecture/kernel/evaluation_engine.md §5.1 for the boundary.

See docs/03_architecture/kernel/evaluation_engine.md, ADR-0022.
Not yet implemented — Implementation Roadmap Stage D.
"""
