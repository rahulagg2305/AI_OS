"""Unit tests for the Context Assembler
(ai_os_kernel.context_manager.manager.DefaultContextManager) — fake
resolvers throughout, isolating assembly logic from any real source
(ADR-0004: interface-driven, so fake Protocol implementations are
legitimate substitutes)."""

import pytest

from ai_os_kernel.context_manager.manager import DefaultContextManager
from ai_os_kernel.context_manager.models import ContextItem, ContextRequest, SourceRef, SourceType

_REQUEST = ContextRequest(workflow_id="wf_1", step_id="step_1")


def _item(content: str, token_count: int, source_type: SourceType) -> ContextItem:
    return ContextItem(
        content=content,
        provenance=SourceRef(source_type=source_type, identifier="fake"),
        relevance_score=1.0,
        token_count=token_count,
        trust="untrusted",
    )


class _FakeResolver:
    def __init__(self, source_type: SourceType, items: list[ContextItem]) -> None:
        self.source_type = source_type
        self._items = items
        self.requests: list[ContextRequest] = []

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        self.requests.append(request)
        return self._items


@pytest.mark.asyncio
async def test_assembling_with_no_resolvers_returns_an_empty_context() -> None:
    manager = DefaultContextManager(resolvers=[])

    assembled = await manager.assemble(_REQUEST)

    assert assembled.items == []
    assert assembled.total_tokens == 0
    assert assembled.sources_queried == []
    assert assembled.items_excluded_count == 0
    assert assembled.assembly_id


@pytest.mark.asyncio
async def test_assembling_with_one_resolver_returns_its_items() -> None:
    item = _item("hello", 2, SourceType.WORKFLOW_STATE)
    resolver = _FakeResolver(SourceType.WORKFLOW_STATE, [item])
    manager = DefaultContextManager(resolvers=[resolver])

    assembled = await manager.assemble(_REQUEST)

    assert assembled.items == [item]
    assert assembled.total_tokens == 2
    assert assembled.sources_queried == [SourceType.WORKFLOW_STATE]
    assert resolver.requests == [_REQUEST]


@pytest.mark.asyncio
async def test_concatenates_items_from_every_resolver_in_order() -> None:
    first = _FakeResolver(SourceType.WORKFLOW_STATE, [_item("a", 1, SourceType.WORKFLOW_STATE)])
    second = _FakeResolver(SourceType.WORKFLOW_STATE, [_item("b", 3, SourceType.WORKFLOW_STATE)])
    manager = DefaultContextManager(resolvers=[first, second])

    assembled = await manager.assemble(_REQUEST)

    assert [item.content for item in assembled.items] == ["a", "b"]
    assert assembled.total_tokens == 4
    assert assembled.sources_queried == [SourceType.WORKFLOW_STATE, SourceType.WORKFLOW_STATE]


@pytest.mark.asyncio
async def test_a_resolver_returning_no_items_still_counts_as_queried() -> None:
    empty_resolver = _FakeResolver(SourceType.WORKFLOW_STATE, [])
    manager = DefaultContextManager(resolvers=[empty_resolver])

    assembled = await manager.assemble(_REQUEST)

    assert assembled.items == []
    assert assembled.sources_queried == [SourceType.WORKFLOW_STATE]


@pytest.mark.asyncio
async def test_items_excluded_count_is_always_zero_with_no_budget_enforcer() -> None:
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE, [_item("x", 999999, SourceType.WORKFLOW_STATE)]
    )
    manager = DefaultContextManager(resolvers=[resolver])

    assembled = await manager.assemble(_REQUEST)

    assert assembled.items_excluded_count == 0


@pytest.mark.asyncio
async def test_each_call_gets_a_distinct_assembly_id() -> None:
    manager = DefaultContextManager(resolvers=[])

    first = await manager.assemble(_REQUEST)
    second = await manager.assemble(_REQUEST)

    assert first.assembly_id != second.assembly_id


@pytest.mark.asyncio
async def test_assembling_the_same_request_twice_is_deterministic_apart_from_assembly_id() -> None:
    # ADR-0022: "context assembly ... is deterministic given the same
    # inputs" — everything except the per-call identity must match.
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE, [_item("stable", 2, SourceType.WORKFLOW_STATE)]
    )
    manager = DefaultContextManager(resolvers=[resolver])

    first = await manager.assemble(_REQUEST)
    second = await manager.assemble(_REQUEST)

    assert first.items == second.items
    assert first.total_tokens == second.total_tokens
    assert first.sources_queried == second.sources_queried
    assert first.assembly_id != second.assembly_id


# --- Size & Token Budget Enforcer -----------------------------------------


def _item_scored(content: str, token_count: int, relevance_score: float) -> ContextItem:
    return ContextItem(
        content=content,
        provenance=SourceRef(source_type=SourceType.WORKFLOW_STATE, identifier="fake"),
        relevance_score=relevance_score,
        token_count=token_count,
        trust="untrusted",
    )


@pytest.mark.asyncio
async def test_no_budget_at_all_includes_every_item_unfiltered() -> None:
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE, [_item_scored("a", 100, 1.0), _item_scored("b", 100, 1.0)]
    )
    manager = DefaultContextManager(resolvers=[resolver])

    assembled = await manager.assemble(_REQUEST)

    assert [item.content for item in assembled.items] == ["a", "b"]
    assert assembled.items_excluded_count == 0


@pytest.mark.asyncio
async def test_a_request_level_budget_excludes_items_that_do_not_fit() -> None:
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE, [_item_scored("a", 6, 1.0), _item_scored("b", 6, 1.0)]
    )
    manager = DefaultContextManager(resolvers=[resolver])
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=6)

    assembled = await manager.assemble(request)

    assert [item.content for item in assembled.items] == ["a"]
    assert assembled.total_tokens == 6
    assert assembled.items_excluded_count == 1


@pytest.mark.asyncio
async def test_the_assemblers_default_budget_applies_when_the_request_specifies_none() -> None:
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE, [_item_scored("a", 6, 1.0), _item_scored("b", 6, 1.0)]
    )
    manager = DefaultContextManager(resolvers=[resolver], default_token_budget=6)

    assembled = await manager.assemble(_REQUEST)

    assert [item.content for item in assembled.items] == ["a"]
    assert assembled.items_excluded_count == 1


@pytest.mark.asyncio
async def test_a_request_level_budget_overrides_the_assemblers_default() -> None:
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE, [_item_scored("a", 6, 1.0), _item_scored("b", 6, 1.0)]
    )
    manager = DefaultContextManager(resolvers=[resolver], default_token_budget=6)
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=12)

    assembled = await manager.assemble(request)

    assert [item.content for item in assembled.items] == ["a", "b"]
    assert assembled.items_excluded_count == 0


@pytest.mark.asyncio
async def test_higher_relevance_items_are_admitted_before_lower_relevance_ones() -> None:
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE,
        [_item_scored("low", 6, 0.1), _item_scored("high", 6, 0.9)],
    )
    manager = DefaultContextManager(resolvers=[resolver])
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=6)

    assembled = await manager.assemble(request)

    # "high" is admitted despite appearing second — rank governs
    # admission, not input position.
    assert [item.content for item in assembled.items] == ["high"]
    assert assembled.items_excluded_count == 1


@pytest.mark.asyncio
async def test_surviving_items_are_returned_in_rank_order_not_resolver_order() -> None:
    # P02-S03-M08-T09: a deliberate reversal of this test's own prior
    # name/assertion (then "..._not_rank_order") — the real Filter/
    # Ranker now presents survivors by relevance_score, not arrival
    # order, matching this ticket's own "by relevance, not order" Goal.
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE,
        [_item_scored("low", 3, 0.1), _item_scored("high", 3, 0.9)],
    )
    manager = DefaultContextManager(resolvers=[resolver])
    # Budget fits both — admission is not in question here, only order.
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=100)

    assembled = await manager.assemble(request)

    assert [item.content for item in assembled.items] == ["high", "low"]


@pytest.mark.asyncio
async def test_tied_relevance_scores_preserve_original_order_when_truncating() -> None:
    # ADR-0022 determinism: a stable sort on equal keys must not
    # reorder or arbitrarily pick among ties.
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE,
        [_item_scored("first", 6, 1.0), _item_scored("second", 6, 1.0)],
    )
    manager = DefaultContextManager(resolvers=[resolver])
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=6)

    assembled = await manager.assemble(request)

    assert [item.content for item in assembled.items] == ["first"]


@pytest.mark.asyncio
async def test_a_smaller_lower_ranked_item_fills_room_a_skipped_item_left_unused() -> None:
    # First-fit continues past a skip, rather than stopping at the
    # first item that doesn't fit.
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE,
        [
            _item_scored("big_high_rank", 10, 0.9),
            _item_scored("small_low_rank", 2, 0.1),
        ],
    )
    manager = DefaultContextManager(resolvers=[resolver])
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=5)

    assembled = await manager.assemble(request)

    assert [item.content for item in assembled.items] == ["small_low_rank"]
    assert assembled.total_tokens == 2
    assert assembled.items_excluded_count == 1


@pytest.mark.asyncio
async def test_an_item_larger_than_the_entire_budget_is_excluded_not_partially_included() -> None:
    resolver = _FakeResolver(SourceType.WORKFLOW_STATE, [_item_scored("too_big", 1000, 1.0)])
    manager = DefaultContextManager(resolvers=[resolver])
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=10)

    assembled = await manager.assemble(request)

    assert assembled.items == []
    assert assembled.total_tokens == 0
    assert assembled.items_excluded_count == 1


@pytest.mark.asyncio
async def test_budget_enforcement_is_deterministic_across_repeated_calls() -> None:
    resolver = _FakeResolver(
        SourceType.WORKFLOW_STATE,
        [_item_scored("a", 6, 0.5), _item_scored("b", 6, 0.5), _item_scored("c", 6, 0.9)],
    )
    manager = DefaultContextManager(resolvers=[resolver])
    request = ContextRequest(workflow_id="wf_1", step_id="step_1", token_budget=12)

    first = await manager.assemble(request)
    second = await manager.assemble(request)

    assert [item.content for item in first.items] == [item.content for item in second.items]
    assert first.items_excluded_count == second.items_excluded_count == 1


@pytest.mark.asyncio
async def test_ranking_reorders_across_multiple_sources_even_with_no_budget() -> None:
    # The Filter/Ranker is its own real step, not merely a side effect
    # of budget truncation -- two different sources, no budget at all,
    # and the low-relevance source's item still moves after the
    # high-relevance one.
    workflow_state = _FakeResolver(
        SourceType.WORKFLOW_STATE, [_item_scored("workflow-item", 5, 0.2)]
    )
    knowledge = _FakeResolver(SourceType.KNOWLEDGE, [_item_scored("knowledge-item", 5, 0.8)])
    manager = DefaultContextManager(resolvers=[workflow_state, knowledge])

    assembled = await manager.assemble(_REQUEST)

    # workflow_state resolved first (arrival order), yet knowledge-item
    # outranks it and is presented first -- genuine cross-source
    # reordering, not a trivial pass-through.
    assert [item.content for item in assembled.items] == ["knowledge-item", "workflow-item"]
    assert assembled.items_excluded_count == 0
