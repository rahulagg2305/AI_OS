"""Drift check for the committed OpenAPI artifact (`P06-S01-M36-T01`).

`docs/process/api_contract_boundary.md`: "Drift is a build failure, per
ADR-0018 — enforced by `--check` in CI, exactly like the roadmap
generated docs." Mirrors
`tests/roadmap/test_generated_docs_are_current.py::test_generated_docs_are_current`'s
own shape: call the exporter's own `--check` mode and assert it exits 0,
rather than re-implementing the comparison here.

Found genuinely stale before this ticket: the committed
`docs/07_api/openapi.json` predated the role-administration routes
(`P03-S05-M14-T07`/`T08`) — two routes and their schemas were silently
missing, with nothing to catch it. This test is that catch.
"""

from __future__ import annotations

from scripts.export_openapi import main


def test_the_committed_openapi_artifact_is_not_stale() -> None:
    assert main(["--check"]) == 0, (
        "docs/07_api/openapi.json is stale — run `python -m scripts.export_openapi`. "
        "Per ADR-0018, contract drift is a build failure."
    )
