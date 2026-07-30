"""Documents this pack's own ``workflows[].inputsSchema``/``outputsSchema``
(manifest_schema.md's own illustrative example already names this exact
module path). **Not yet validated at runtime** — the identical, already
established "documents the contract, not a second real validation path"
scope every agent's own ``*Input``/``*Output`` model in this pack already
carries; :class:`~ai_os_kernel.workflow_engine.models.WorkflowDefinition`
already validates a real instance's own ``inputs`` against its own
declared JSON Schema (``delivery_pipeline.yaml``'s own ``inputs``/
``outputs`` keys) at instance-creation time — these two Pydantic models
mirror that same JSON Schema in the pack's own native, importable form,
for a future manifest-driven discovery/documentation consumer, not a
new or different validation boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PipelineInput(BaseModel):
    """Mirrors ``delivery_pipeline.yaml``'s own declared ``inputs`` JSON
    Schema exactly."""

    requirement: str = Field(
        ...,
        description=(
            "The raw software requirement or ask to design, build, test, and document — "
            "analyzed and refined by Requirements Analyst before Architecture ever sees it."
        ),
    )


class PipelineOutput(BaseModel):
    """Mirrors ``delivery_pipeline.yaml``'s own declared ``outputs`` JSON
    Schema exactly."""

    documentation_path: str = Field(..., alias="documentationPath")

    model_config = {"populate_by_name": True}
