"""Unit tests for PromptResolver: the Prompt Resolver subsystem
(prompt_engine.md §5), ``P02-S03-M07-T04``.

Uses a real :class:`InMemoryPromptEngine` behind the resolver rather
than a fake — the resolver's whole contract is "resolve, then render
through a real engine", so substituting the render half would test the
half that is not this Task's.
"""

import pytest

from ai_os_kernel.prompt_engine.errors import (
    PromptNotFoundError,
    PromptRoleNotBoundError,
    PromptVariableMissingError,
)
from ai_os_kernel.prompt_engine.renderer import InMemoryPromptEngine
from ai_os_kernel.prompt_engine.resolver import PromptBinding, PromptResolver

_TEMPLATES = {
    ("se.build.write_file", "1.0.0"): "Build v1: {{instruction}}",
    ("se.build.write_file", "2.0.0"): "Build v2: {{instruction}}",
    ("se.review.findings", "1.0.0"): "Review: {{code}}",
}


def _resolver(**roles: tuple[str, str]) -> PromptResolver:
    return PromptResolver(
        InMemoryPromptEngine(_TEMPLATES),
        bindings={r: PromptBinding(prompt_id=p, version=v) for r, (p, v) in roles.items()},
    )


@pytest.mark.asyncio
async def test_renders_the_prompt_a_role_is_bound_to() -> None:
    resolver = _resolver(builder=("se.build.write_file", "1.0.0"))

    response = await resolver.render_for_role("builder", {"instruction": "make it"})

    assert response.content == "Build v1: make it"


@pytest.mark.asyncio
async def test_the_response_names_the_resolved_prompt_not_the_role() -> None:
    """§7 step 5: the caller must learn which prompt and version actually
    produced the text — precisely what a role indirection would hide."""
    resolver = _resolver(builder=("se.build.write_file", "1.0.0"))

    response = await resolver.render_for_role("builder", {"instruction": "x"})

    assert response.prompt_id == "se.build.write_file"
    assert response.version == "1.0.0"
    assert "builder" not in (response.prompt_id, response.version)


@pytest.mark.asyncio
async def test_a_role_binds_to_an_exact_version_not_the_newest() -> None:
    """The ADR-0022 reproducibility property: two runs cannot silently
    differ. Both versions genuinely exist; the binding decides."""
    resolver = _resolver(builder=("se.build.write_file", "1.0.0"))

    response = await resolver.render_for_role("builder", {"instruction": "x"})

    assert response.version == "1.0.0"  # not 2.0.0, which also exists


@pytest.mark.asyncio
async def test_rebinding_a_role_changes_which_version_renders() -> None:
    """The flip side: changing a binding is a real, visible config change."""
    response = await _resolver(builder=("se.build.write_file", "2.0.0")).render_for_role(
        "builder", {"instruction": "x"}
    )

    assert response.content == "Build v2: x"


@pytest.mark.asyncio
async def test_an_unbound_role_is_refused_and_lists_what_is_bound() -> None:
    """Never falls through to treating the role as a prompt_id — that
    would surface a confusing PromptNotFoundError about an id the caller
    never named."""
    resolver = _resolver(builder=("se.build.write_file", "1.0.0"))

    with pytest.raises(PromptRoleNotBoundError, match="'reviewer' is not bound") as exc:
        await resolver.render_for_role("reviewer", {})

    assert "builder" in str(exc.value)  # names what IS bound


@pytest.mark.asyncio
async def test_an_unbound_role_error_is_readable_with_no_bindings_at_all() -> None:
    with pytest.raises(PromptRoleNotBoundError, match="<none>"):
        await _resolver().render_for_role("anything", {})


@pytest.mark.asyncio
async def test_a_role_bound_to_a_missing_prompt_raises_the_catalog_error() -> None:
    """The distinction the two error types exist for: a configuration gap
    and a catalog gap are fixed in different places."""
    resolver = _resolver(ghost=("se.does_not_exist", "1.0.0"))

    with pytest.raises(PromptNotFoundError):
        await resolver.render_for_role("ghost", {})


@pytest.mark.asyncio
async def test_variable_validation_still_applies_through_the_resolver() -> None:
    """Resolving must not weaken the render contract."""
    resolver = _resolver(builder=("se.build.write_file", "1.0.0"))

    with pytest.raises(PromptVariableMissingError, match="instruction"):
        await resolver.render_for_role("builder", {})


@pytest.mark.asyncio
async def test_variables_default_to_empty_for_a_template_needing_none() -> None:
    resolver = PromptResolver(
        InMemoryPromptEngine({("static", "1.0.0"): "no placeholders"}),
        bindings={"plain": PromptBinding(prompt_id="static", version="1.0.0")},
    )

    assert (await resolver.render_for_role("plain")).content == "no placeholders"


def test_binding_for_returns_the_binding_without_rendering() -> None:
    """For a run manifest (ADR-0022) that must record which prompt a run
    used without paying for a render."""
    binding = _resolver(builder=("se.build.write_file", "1.0.0")).binding_for("builder")

    assert (binding.prompt_id, binding.version) == ("se.build.write_file", "1.0.0")


def test_binding_for_refuses_an_unbound_role() -> None:
    with pytest.raises(PromptRoleNotBoundError):
        _resolver(builder=("se.build.write_file", "1.0.0")).binding_for("nope")


def test_a_blank_binding_field_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        PromptBinding(prompt_id="se.build.write_file", version="   ")


def test_bindings_are_copied_so_later_caller_mutation_cannot_change_resolution() -> None:
    """The same defensive-copy property InMemoryPromptEngine already has."""
    supplied = {"builder": PromptBinding(prompt_id="se.build.write_file", version="1.0.0")}
    resolver = PromptResolver(InMemoryPromptEngine(_TEMPLATES), bindings=supplied)

    supplied.clear()

    assert resolver.binding_for("builder").version == "1.0.0"
