"""Semantic manifest validation — the rules genuinely buildable today
against this repository's real, current data model
(docs/03_architecture/capability_framework/manifest_schema.md's
Validation Rules; ``P01-S03-M02-T04``). Runs only once a manifest has
already passed schema validation (this ticket's own Input) — every
function here assumes required fields are present exactly as the JSON
Schema guarantees.

**Rule 13 (SDK version range).** ``dependencies.sdkVersion`` must
include the real, running ``ai-os-sdk`` version. Genuinely enforceable
as of this step — manifest_schema.md's own prior caveat ("no SDK
distribution and therefore no running SDK version") is stale, corrected
in this same step: ``ai-os-sdk`` is real and installed (the Platform
SDK initiative).

**Rule 16 (workflow-definition existence + step-reference
resolution).** Every ``workflows[]`` entry's ``definition`` file must
exist, parse, and structurally validate — reused directly through the
real :class:`~ai_os_kernel.workflow_engine.loader.WorkflowDefinitionLoader`
(ADR-0004: don't reinvent an existing seam), not reimplemented here.
Every step's ``agentId``/``toolId``/``promptId`` must then resolve
within this manifest's own declared ``agents[]``/``tools[]``/``prompts[]``
— cross-pack references are rejected (ADR-0009 prohibits pack-to-pack
dependencies; the one real example in this repository always uses the
``<pack-id>/<agent-id>`` form with its own pack id).

**Rule 20 (circular dependency among workflows and sub-workflows) is
NOT implemented here — confirmed, not assumed, currently
*unenforceable* rather than merely unbuilt.**
:class:`~ai_os_kernel.workflow_engine.models.WorkflowStep`'s own
docstring states plainly: "sub-workflow linkage remain[s] genuinely
undocumented — no document defines a field-level contract for them
yet." A ``sub_workflow``-typed step declares none of the five
invocation fields, so there is no field anywhere in the real data model
today naming *which* workflow a ``sub_workflow`` step would call —
nothing to build a cycle detector against. The identical "currently
unenforceable, not merely unimplemented" category rule 13 was in before
this step (manifest_schema.md's own established distinction); disclosed
here and in that document rather than force-built as a permanent no-op.
"""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from ai_os_kernel.manifest_loader.errors import ManifestError
from ai_os_kernel.workflow_engine.errors import WorkflowDefinitionError
from ai_os_kernel.workflow_engine.loader import WorkflowDefinitionLoader
from ai_os_kernel.workflow_engine.models import WorkflowStep

_SDK_DISTRIBUTION_NAME = "ai-os-sdk"


def validate_sdk_version_range(raw: dict[str, Any]) -> None:
    """Rule 13: ``dependencies.sdkVersion`` must include the real,
    running ``ai-os-sdk`` version.

    Raises :class:`ManifestError` if the range is not a valid PEP 440
    specifier, if ``ai-os-sdk`` is not installed in this environment, or
    if the installed version falls outside the declared range.
    """
    spec_str = raw["dependencies"]["sdkVersion"]
    try:
        specifier = SpecifierSet(spec_str)
    except InvalidSpecifier as exc:
        raise ManifestError(
            f"dependencies.sdkVersion {spec_str!r} is not a valid PEP 440 range: {exc}"
        ) from exc

    try:
        running_version = metadata.version(_SDK_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError as exc:
        raise ManifestError(
            f"cannot verify dependencies.sdkVersion {spec_str!r}: "
            f"'{_SDK_DISTRIBUTION_NAME}' is not installed in this environment"
        ) from exc

    if not specifier.contains(running_version, prereleases=True):
        raise ManifestError(
            f"dependencies.sdkVersion {spec_str!r} does not include the running "
            f"'{_SDK_DISTRIBUTION_NAME}' version {running_version!r}"
        )


def validate_workflow_definitions(raw: dict[str, Any], manifest_path: Path) -> None:
    """Rule 16: every ``workflows[]`` entry's definition file must
    exist, parse, and structurally validate, and every step's
    ``agentId``/``toolId``/``promptId`` must resolve within this
    manifest's own declared components.

    Raises :class:`ManifestError` naming the workflow and step on any
    failure.
    """
    manifest_dir = manifest_path.parent
    pack_id = raw["metadata"]["id"]
    declared_agent_ids = {agent["id"] for agent in raw.get("agents", [])}
    declared_tool_ids = {tool["id"] for tool in raw.get("tools", [])}
    declared_prompts = {(p["id"], p["version"]) for p in raw.get("prompts", [])}

    loader = WorkflowDefinitionLoader()
    for workflow in raw.get("workflows", []):
        definition_path = manifest_dir / workflow["definition"]
        try:
            definition = loader.load(definition_path)
        except WorkflowDefinitionError as exc:
            raise ManifestError(f"workflow '{workflow['id']}': {exc}") from exc

        for step in definition.steps:
            _validate_step_references(
                step,
                workflow_id=workflow["id"],
                pack_id=pack_id,
                declared_agent_ids=declared_agent_ids,
                declared_tool_ids=declared_tool_ids,
                declared_prompts=declared_prompts,
            )


def _validate_step_references(
    step: WorkflowStep,
    *,
    workflow_id: str,
    pack_id: str,
    declared_agent_ids: set[str],
    declared_tool_ids: set[str],
    declared_prompts: set[tuple[str, str]],
) -> None:
    if step.agent_id is not None:
        reason = _unresolved_agent_id_reason(step.agent_id, pack_id, declared_agent_ids)
        if reason is not None:
            raise ManifestError(f"workflow '{workflow_id}' step '{step.id}': {reason}")

    if step.tool_id is not None and step.tool_id not in declared_tool_ids:
        raise ManifestError(
            f"workflow '{workflow_id}' step '{step.id}': toolId {step.tool_id!r} does "
            "not resolve to any tool declared in this manifest"
        )

    # A step declaring promptId also declares promptVersion together
    # (WorkflowStep's own rule 5) — both are matched as one pair against
    # prompts[], never promptId alone, since a manifest may declare
    # multiple versions of the same prompt id.
    prompt_ref = (step.prompt_id, step.prompt_version)
    if step.prompt_id is not None and prompt_ref not in declared_prompts:
        raise ManifestError(
            f"workflow '{workflow_id}' step '{step.id}': promptId {step.prompt_id!r} "
            f"version {step.prompt_version!r} does not resolve to any prompt "
            "declared in this manifest"
        )


def _unresolved_agent_id_reason(
    agent_id_ref: str, pack_id: str, declared_agent_ids: set[str]
) -> str | None:
    """Returns ``None`` if ``agent_id_ref`` resolves cleanly; otherwise
    a human-readable reason it does not."""
    if "/" not in agent_id_ref:
        return f"agentId {agent_id_ref!r} is not in '<pack-id>/<agent-id>' form"
    ref_pack_id, _, agent_id = agent_id_ref.partition("/")
    if ref_pack_id != pack_id:
        return (
            f"agentId {agent_id_ref!r} references pack {ref_pack_id!r}, not this "
            f"pack ({pack_id!r}) — cross-pack workflow references are not supported "
            "(ADR-0009 prohibits pack-to-pack dependencies)"
        )
    if agent_id not in declared_agent_ids:
        return f"agentId {agent_id_ref!r} does not resolve to any agent declared in this manifest"
    return None
