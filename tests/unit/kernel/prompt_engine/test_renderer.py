"""Unit tests for InMemoryPromptEngine: the one trivial in-process
implementation of PromptEngine — no I/O, no catalog, nothing to mock."""

import pytest

from ai_os_kernel.prompt_engine.errors import PromptNotFoundError, PromptVariableMissingError
from ai_os_kernel.prompt_engine.models import PromptRenderRequest
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine


@pytest.mark.asyncio
async def test_renders_a_template_by_substituting_variables() -> None:
    engine = InMemoryPromptEngine(
        {("prompt_greeting", "1.0.0"): "Hello, {{name}}! Welcome to {{place}}."}
    )

    response = await engine.render(
        PromptRenderRequest(
            prompt_id="prompt_greeting",
            version="1.0.0",
            variables={"name": "Ada", "place": "AI_OS"},
        )
    )

    assert response.content == "Hello, Ada! Welcome to AI_OS."
    assert response.prompt_id == "prompt_greeting"
    assert response.version == "1.0.0"


@pytest.mark.asyncio
async def test_a_template_with_no_placeholders_needs_no_variables() -> None:
    engine = InMemoryPromptEngine({("prompt_static", "1.0.0"): "You are a helpful assistant."})

    response = await engine.render(PromptRenderRequest(prompt_id="prompt_static", version="1.0.0"))

    assert response.content == "You are a helpful assistant."


@pytest.mark.asyncio
async def test_extra_variables_not_referenced_by_the_template_are_ignored() -> None:
    engine = InMemoryPromptEngine({("prompt_greeting", "1.0.0"): "Hello, {{name}}!"})

    response = await engine.render(
        PromptRenderRequest(
            prompt_id="prompt_greeting",
            version="1.0.0",
            variables={"name": "Ada", "unused": "ignored"},
        )
    )

    assert response.content == "Hello, Ada!"


@pytest.mark.asyncio
async def test_unknown_prompt_id_or_version_raises() -> None:
    engine = InMemoryPromptEngine({("prompt_greeting", "1.0.0"): "Hello, {{name}}!"})

    with pytest.raises(PromptNotFoundError, match="prompt_missing"):
        await engine.render(
            PromptRenderRequest(prompt_id="prompt_missing", version="1.0.0", variables={})
        )

    with pytest.raises(PromptNotFoundError, match="version='2.0.0'"):
        await engine.render(
            PromptRenderRequest(prompt_id="prompt_greeting", version="2.0.0", variables={})
        )


@pytest.mark.asyncio
async def test_missing_required_variable_raises_and_names_it() -> None:
    engine = InMemoryPromptEngine(
        {("prompt_greeting", "1.0.0"): "Hello, {{name}}! Welcome to {{place}}."}
    )

    with pytest.raises(PromptVariableMissingError, match="name, place"):
        await engine.render(
            PromptRenderRequest(prompt_id="prompt_greeting", version="1.0.0", variables={})
        )


@pytest.mark.asyncio
async def test_no_rendering_is_attempted_when_a_variable_is_missing() -> None:
    engine = InMemoryPromptEngine({("prompt_greeting", "1.0.0"): "Hello, {{name}}!"})

    with pytest.raises(PromptVariableMissingError):
        await engine.render(
            PromptRenderRequest(
                prompt_id="prompt_greeting",
                version="1.0.0",
                variables={"place": "AI_OS"},
            )
        )
