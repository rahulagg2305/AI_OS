"""SqlContextAuditLogger against real Postgres (ADR-0015 — no mocking
the database). Proves a real context assembly is genuinely persisted
to ``context.context_assemblies`` and read back at full fidelity —
enabling exact replay of a past assembly, not merely a summary.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from ai_os_kernel.context_manager.audit_logger import SqlContextAuditLogger
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import ContextItem, ContextRequest, SourceRef, SourceType
from ai_os_kernel.persistence.engine import build_engine
from tests.integration._postgres_fixture import postgres_container

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture(scope="module")
def database_url() -> Generator[str, None, None]:
    with postgres_container() as postgres:
        url = postgres.get_connection_url()
        previous = os.environ.get("AIOS_DATABASE_URL")
        os.environ["AIOS_DATABASE_URL"] = url
        try:
            command.upgrade(Config(str(ALEMBIC_INI)), "head")
            yield url
        finally:
            if previous is None:
                os.environ.pop("AIOS_DATABASE_URL", None)
            else:
                os.environ["AIOS_DATABASE_URL"] = previous


def _item(content: str, token_count: int, source_type: SourceType, score: float) -> ContextItem:
    return ContextItem(
        content=content,
        provenance=SourceRef(source_type=source_type, identifier=f"fake:{content}"),
        relevance_score=score,
        token_count=token_count,
        trust="untrusted" if source_type == SourceType.WORKFLOW_STATE else "trusted",
    )


class _FakeResolver:
    def __init__(self, source_type: SourceType, items: list[ContextItem]) -> None:
        self.source_type = source_type
        self._items = items

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        return self._items


def test_a_real_assembly_is_persisted_and_readable_back_at_full_fidelity(
    database_url: str,
) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_logger = SqlContextAuditLogger(engine)
            workflow_item = _item("workflow-content", 5, SourceType.WORKFLOW_STATE, 1.0)
            knowledge_item = _item("knowledge-content", 5, SourceType.KNOWLEDGE, 0.42)
            manager = DefaultContextManager(
                [
                    _FakeResolver(SourceType.WORKFLOW_STATE, [workflow_item]),
                    _FakeResolver(SourceType.KNOWLEDGE, [knowledge_item]),
                ],
                audit_logger=audit_logger,
            )
            request = ContextRequest(
                workflow_id="wf_audit_test", step_id="step_audit_test", agent_id="agent_audit_test"
            )

            assembled = await manager.assemble(request)

            record = await audit_logger.get_by_assembly_id(assembled.assembly_id)
            assert record is not None
            assert record.assembly_id == assembled.assembly_id
            assert record.workflow_id == "wf_audit_test"
            assert record.step_id == "step_audit_test"
            assert record.agent_id == "agent_audit_test"
            assert record.sources_queried == [SourceType.WORKFLOW_STATE, SourceType.KNOWLEDGE]
            assert record.items_excluded_count == 0
            assert record.total_tokens == assembled.total_tokens

            # Exact replay: the read-back items reconstruct byte-for-byte
            # what the real assembly actually returned, in rank order.
            assert record.items == assembled.items
            assert [item.content for item in record.items] == [
                "workflow-content",
                "knowledge-content",
            ]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_a_budget_trimmed_assembly_persists_its_real_excluded_count(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_logger = SqlContextAuditLogger(engine)
            big_item = _item("big", 10, SourceType.WORKFLOW_STATE, 0.9)
            small_item = _item("small", 2, SourceType.KNOWLEDGE, 0.1)
            manager = DefaultContextManager(
                [
                    _FakeResolver(SourceType.WORKFLOW_STATE, [big_item]),
                    _FakeResolver(SourceType.KNOWLEDGE, [small_item]),
                ],
                audit_logger=audit_logger,
            )
            request = ContextRequest(
                workflow_id="wf_audit_trim_test",
                step_id="step_audit_trim_test",
                token_budget=12,
            )

            assembled = await manager.assemble(request)
            assert assembled.items_excluded_count == 0  # both fit within 12

            record = await audit_logger.get_by_assembly_id(assembled.assembly_id)
            assert record is not None
            assert record.items_excluded_count == 0
            assert record.total_tokens == 12

            # A tighter budget genuinely excludes the smaller, lower-ranked
            # item -- and that real exclusion is what gets persisted.
            tight_request = ContextRequest(
                workflow_id="wf_audit_trim_test_2",
                step_id="step_audit_trim_test_2",
                token_budget=12,
            )
            manager_with_extra_item = DefaultContextManager(
                [
                    _FakeResolver(SourceType.WORKFLOW_STATE, [big_item]),
                    _FakeResolver(
                        SourceType.KNOWLEDGE,
                        [small_item, _item("excluded", 5, SourceType.KNOWLEDGE, 0.05)],
                    ),
                ],
                audit_logger=audit_logger,
            )
            trimmed = await manager_with_extra_item.assemble(tight_request)
            assert trimmed.items_excluded_count == 1

            trimmed_record = await audit_logger.get_by_assembly_id(trimmed.assembly_id)
            assert trimmed_record is not None
            assert trimmed_record.items_excluded_count == 1
            assert [item.content for item in trimmed_record.items] == ["big", "small"]
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_reading_back_an_unknown_assembly_id_returns_none(database_url: str) -> None:
    async def _run() -> None:
        engine = build_engine(database_url)
        try:
            audit_logger = SqlContextAuditLogger(engine)
            assert await audit_logger.get_by_assembly_id("asm_does_not_exist") is None
        finally:
            await engine.dispose()

    asyncio.run(_run())
