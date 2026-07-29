"""Step 5 of ``platform_sdk_v1_scope.md``: the ``RenderedPrompt`` model
(``platform_sdk.md`` §5.2, narrowed to 3 fields)."""

import pytest
from pydantic import ValidationError

from ai_os_sdk.models import RenderedPrompt


def _rendered(**overrides: object) -> RenderedPrompt:
    fields: dict[str, object] = {
        "prompt_id": "requirements.analyze",
        "version": "0.1.0",
        "content": "Analyze the following requirement: ...",
    }
    fields.update(overrides)
    return RenderedPrompt(**fields)


class TestRenderedPrompt:
    def test_accepts_a_well_formed_result(self) -> None:
        rendered = _rendered()
        assert rendered.prompt_id == "requirements.analyze"
        assert rendered.version == "0.1.0"

    def test_defines_exactly_the_three_narrowed_fields(self) -> None:
        """v1.0.0 drops variables_used and cache_boundary_index —
        neither has a producer; see the model's own docstring."""
        assert set(RenderedPrompt.model_fields) == {"prompt_id", "version", "content"}

    @pytest.mark.parametrize("field", ["prompt_id", "version"])
    def test_rejects_a_blank_identifier(self, field: str) -> None:
        with pytest.raises(ValidationError):
            _rendered(**{field: "  "})

    def test_content_may_be_empty(self) -> None:
        """An empty rendered result is a real (if unusual) outcome, not
        an invalid one — the prompt engine doesn't forbid it, so this
        boundary model shouldn't either."""
        assert _rendered(content="").content == ""

    def test_is_frozen(self) -> None:
        rendered = _rendered()
        with pytest.raises(ValidationError):
            rendered.content = "changed"  # type: ignore[misc]
