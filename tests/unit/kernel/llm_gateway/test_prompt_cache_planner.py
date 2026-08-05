"""Unit tests for the Prompt Cache Planner: pure logic, no I/O, no
provider-specific wire shape (see anthropic_adapter's own tests for
that real translation)."""

import pytest

from ai_os_kernel.llm_gateway.errors import LLMPromptCacheError
from ai_os_kernel.llm_gateway.prompt_cache_planner import (
    PromptCacheSegment,
    plan_prompt_cache_segments,
)


def test_splits_into_a_cacheable_stable_segment_and_a_volatile_suffix() -> None:
    segments = plan_prompt_cache_segments("stable partvolatile part", len("stable part"))

    assert segments == [
        PromptCacheSegment(content="stable part", cacheable=True),
        PromptCacheSegment(content="volatile part", cacheable=False),
    ]


def test_a_boundary_at_zero_produces_only_a_volatile_segment() -> None:
    segments = plan_prompt_cache_segments("everything is volatile", 0)

    assert segments == [PromptCacheSegment(content="everything is volatile", cacheable=False)]


def test_a_boundary_at_the_end_produces_only_a_cacheable_segment() -> None:
    content = "everything is stable"
    segments = plan_prompt_cache_segments(content, len(content))

    assert segments == [PromptCacheSegment(content=content, cacheable=True)]


def test_rejects_a_boundary_index_beyond_the_content_length() -> None:
    with pytest.raises(LLMPromptCacheError, match="out of range"):
        plan_prompt_cache_segments("short", 100)


def test_rejects_a_negative_boundary_index() -> None:
    with pytest.raises(LLMPromptCacheError, match="out of range"):
        plan_prompt_cache_segments("short", -1)


def test_rejects_blank_content() -> None:
    with pytest.raises(LLMPromptCacheError, match="must not be blank"):
        plan_prompt_cache_segments("", 0)
