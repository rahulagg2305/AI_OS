"""Unit tests for InMemoryAgentRegistry/InMemoryToolRegistry — no
database, no real capability discovery (ADR-0004: interface-driven, so
a plain in-process mapping is a legitimate substitute at this stage)."""

import pytest

from ai_os_kernel.workflow_engine.agent import EchoAgent
from ai_os_kernel.workflow_engine.errors import AgentNotRegisteredError, ToolNotRegisteredError
from ai_os_kernel.workflow_engine.registry import InMemoryAgentRegistry, InMemoryToolRegistry
from ai_os_kernel.workflow_engine.tool import EchoTool


@pytest.mark.asyncio
async def test_resolve_agent_returns_the_registered_instance() -> None:
    agent = EchoAgent()
    registry = InMemoryAgentRegistry({"se.software_engineering/analyst": agent})

    resolved = await registry.resolve_agent("se.software_engineering/analyst")

    assert resolved is agent


@pytest.mark.asyncio
async def test_resolve_agent_raises_for_an_unregistered_id() -> None:
    registry = InMemoryAgentRegistry({})

    with pytest.raises(AgentNotRegisteredError, match="se.software_engineering/analyst"):
        await registry.resolve_agent("se.software_engineering/analyst")


@pytest.mark.asyncio
async def test_resolve_tool_returns_the_registered_instance() -> None:
    tool = EchoTool()
    registry = InMemoryToolRegistry({"se.build": tool})

    resolved = await registry.resolve_tool("se.build")

    assert resolved is tool


@pytest.mark.asyncio
async def test_resolve_tool_raises_for_an_unregistered_id() -> None:
    registry = InMemoryToolRegistry({})

    with pytest.raises(ToolNotRegisteredError, match="se.build"):
        await registry.resolve_tool("se.build")


@pytest.mark.asyncio
async def test_registries_do_not_share_state_with_the_dict_passed_in() -> None:
    """The constructor copies its argument — mutating the caller's dict
    afterward must not affect what the registry resolves."""
    original_agent = EchoAgent()
    agents = {"se.software_engineering/analyst": original_agent}
    registry = InMemoryAgentRegistry(agents)

    agents["se.software_engineering/analyst"] = EchoAgent()
    agents.clear()

    resolved = await registry.resolve_agent("se.software_engineering/analyst")
    assert resolved is original_agent
