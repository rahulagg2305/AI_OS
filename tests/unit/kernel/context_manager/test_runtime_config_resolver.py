"""Unit tests for RuntimeConfigResolver — real YAML files (tmp_path)
and a real ConfigurationManager/RuntimeOverrideStore, no database.
ConfigChangeWriter is faked here for the identical reason
test_runtime_overrides.py already fakes it: this ticket is about the
Context Manager's own resolver, not re-proving RuntimeOverrideStore's
own already-covered real Postgres audit persistence
(tests/integration/configuration_manager/test_runtime_overrides_audit.py).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_os_kernel.configuration_manager.loader import ConfigurationManager
from ai_os_kernel.configuration_manager.runtime_overrides import RuntimeOverrideStore
from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import ContextRequest, SourceType
from ai_os_kernel.context_manager.resolvers import (
    RuntimeConfigKeyUnknownError,
    RuntimeConfigResolver,
)

_REQUEST = ContextRequest(workflow_id="wf_1", step_id="step_1")


class _FakeConfigChangeWriter:
    """The identical fake test_runtime_overrides.py already
    establishes for the one real seam RuntimeOverrideStore.apply
    depends on."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def record(
        self,
        *,
        config_key: str,
        old_value: Any,
        new_value: Any,
        changed_by: str,
        reason: str,
    ) -> None:
        self.calls.append(
            {
                "config_key": config_key,
                "old_value": old_value,
                "new_value": new_value,
                "changed_by": changed_by,
                "reason": reason,
            }
        )


def _write_yaml(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def _manager(tmp_path: Path) -> ConfigurationManager:
    _write_yaml(tmp_path / "platform.yaml", {"kernel": {"log_level": "WARNING"}})
    return ConfigurationManager(
        environment="local",
        platform_config_path=tmp_path / "platform.yaml",
        environments_dir=tmp_path / "environments",
    )


@pytest.mark.asyncio
async def test_resolve_exposes_real_config_values_as_context_items(tmp_path: Path) -> None:
    resolver = RuntimeConfigResolver(
        configuration_manager=_manager(tmp_path),
        runtime_override_store=RuntimeOverrideStore(),
        role="api",
        config_keys=["log_level", "host"],
    )

    items = await resolver.resolve(_REQUEST)

    assert len(items) == 2
    by_key = {item.provenance.identifier: item for item in items}
    assert by_key["config_key:log_level"].content == f"log_level: {json.dumps('WARNING')}"
    assert by_key["config_key:host"].content == f"host: {json.dumps('127.0.0.1')}"
    for item in items:
        assert item.provenance.source_type == SourceType.CONFIGURATION
        assert item.trust == "trusted"
        assert item.relevance_score == 1.0


@pytest.mark.asyncio
async def test_a_live_runtime_override_is_reflected_without_reconstructing_the_resolver(
    tmp_path: Path,
) -> None:
    override_store = RuntimeOverrideStore()
    resolver = RuntimeConfigResolver(
        configuration_manager=_manager(tmp_path),
        runtime_override_store=override_store,
        role="api",
        config_keys=["log_level"],
    )

    before = await resolver.resolve(_REQUEST)
    assert before[0].content == f"log_level: {json.dumps('WARNING')}"

    # A real runtime override, applied through the real store -- the
    # identical live mechanism P01-S02-M01-T04 built specifically so a
    # change takes effect without a process restart.
    await override_store.apply(
        _FakeConfigChangeWriter(),
        config_key="log_level",
        new_value="DEBUG",
        changed_by="test-admin",
        reason="test override",
    )

    after = await resolver.resolve(_REQUEST)
    assert after[0].content == f"log_level: {json.dumps('DEBUG')}"


def test_construction_rejects_an_unknown_config_key(tmp_path: Path) -> None:
    with pytest.raises(RuntimeConfigKeyUnknownError, match="not_a_real_field"):
        RuntimeConfigResolver(
            configuration_manager=_manager(tmp_path),
            runtime_override_store=RuntimeOverrideStore(),
            role="api",
            config_keys=["log_level", "not_a_real_field"],
        )


@pytest.mark.asyncio
async def test_runtime_config_flows_into_a_real_context_assembly(tmp_path: Path) -> None:
    resolver = RuntimeConfigResolver(
        configuration_manager=_manager(tmp_path),
        runtime_override_store=RuntimeOverrideStore(),
        role="api",
        config_keys=["log_level"],
    )
    context_manager = DefaultContextManager([resolver])

    assembled = await context_manager.assemble(_REQUEST)

    assert assembled.sources_queried == [SourceType.CONFIGURATION]
    assert len(assembled.items) == 1
    assert assembled.items[0].content == f"log_level: {json.dumps('WARNING')}"
    assert assembled.items[0].provenance.source_type == SourceType.CONFIGURATION
