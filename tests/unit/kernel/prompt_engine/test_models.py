"""Unit tests for the minimal PromptRenderRequest/PromptRenderResponse
shapes: validation only — no engine, no I/O."""

import pytest
from pydantic import ValidationError

from ai_os_kernel.prompt_engine.models import PromptRenderRequest


def test_a_well_formed_request_is_accepted() -> None:
    request = PromptRenderRequest(
        prompt_id="prompt_greeting",
        version="1.0.0",
        variables={"name": "Ada"},
    )

    assert request.prompt_id == "prompt_greeting"
    assert request.version == "1.0.0"
    assert request.variables == {"name": "Ada"}


def test_variables_defaults_to_empty() -> None:
    request = PromptRenderRequest(prompt_id="prompt_greeting", version="1.0.0")

    assert request.variables == {}


def test_blank_prompt_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="prompt_id must not be blank"):
        PromptRenderRequest(prompt_id="   ", version="1.0.0")


def test_blank_version_is_rejected() -> None:
    with pytest.raises(ValidationError, match="version must not be blank"):
        PromptRenderRequest(prompt_id="prompt_greeting", version="   ")


def test_request_is_frozen() -> None:
    request = PromptRenderRequest(prompt_id="prompt_greeting", version="1.0.0")

    with pytest.raises(ValidationError):
        request.version = "2.0.0"  # type: ignore[misc]
