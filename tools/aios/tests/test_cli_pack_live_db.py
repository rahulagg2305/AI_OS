"""The one real, full end-to-end CLI test against a real, running
Kernel and a real, migrated Postgres (ADR-0015 — no mocking the
database): ``aios pack list/show/activate/deactivate`` against a
genuinely registered pack, proving the entire real stack (CLI ->
HTTP -> RBAC -> ``PackLifecycleRepository`` -> Postgres), not just the
degrade paths ``test_cli_live.py`` already covers.

There is no CLI "register" command (not in ``cli_design.md``'s own
documented tree) — this test seeds the one real pack directly through
:class:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository`,
the same real repository the HTTP route itself uses, then drives every
real state transition through the CLI alone.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid

import jwt
import pytest
from cli_helpers import invoke

from ai_os_kernel.capability_manager.repository import SqlPackLifecycleRepository
from ai_os_kernel.persistence.engine import build_engine

_SIGNING_KEY = "aios-cli-test-signing-key-at-least-32-bytes-long"


def _admin_token() -> str:
    claims = {
        "sub": "cli-test-admin",
        "roles": ["admin"],
        "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=5),
    }
    return jwt.encode(claims, _SIGNING_KEY, algorithm="HS256")


def test_the_real_pack_lifecycle_is_driven_entirely_through_the_cli(
    live_kernel_with_db: str, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack_id = f"cli-test-pack-{uuid.uuid4().hex}"

    async def _seed() -> None:
        engine = build_engine(database_url)
        try:
            repository = SqlPackLifecycleRepository(engine)
            await repository.register(
                pack_id=pack_id,
                version="1.0.0",
                manifest={},
                sdk_version="1.0.0",
                min_kernel_version="0.1.0",
                actor="test-seed",
                reason="seeding for a real CLI test",
            )
        finally:
            await engine.dispose()

    asyncio.run(_seed())

    monkeypatch.setenv("AIOS_API_URL", live_kernel_with_db)
    monkeypatch.setenv("AIOS_TOKEN", _admin_token())

    list_result = invoke(["--output", "json", "pack", "list"])
    assert list_result.exit_code == 0
    assert pack_id in list_result.output

    show_result = invoke(["--output", "json", "pack", "show", pack_id])
    assert show_result.exit_code == 0
    assert '"state": "installed"' in show_result.output

    activate_result = invoke(
        ["--output", "json", "pack", "activate", pack_id, "--reason", "real cli test"]
    )
    assert activate_result.exit_code == 0
    assert '"state": "activated"' in activate_result.output

    deactivate_result = invoke(
        ["--output", "json", "pack", "deactivate", pack_id, "--reason", "real cli test"]
    )
    assert deactivate_result.exit_code == 0
    assert '"state": "deactivated"' in deactivate_result.output

    # A second, real activate/deactivate genuinely fails through the CLI
    # too — the real repository's own state machine, not a CLI-side
    # shortcut: deactivating an already-deactivated pack is a real 409.
    second_deactivate = invoke(
        ["--output", "json", "pack", "deactivate", pack_id, "--reason", "should fail"]
    )
    assert second_deactivate.exit_code == 5
