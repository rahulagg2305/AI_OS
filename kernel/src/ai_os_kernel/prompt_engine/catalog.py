"""Minimal read path for ``catalog.prompts`` — a second
:class:`~ai_os_kernel.prompt_engine.renderer.PromptEngine` implementation,
backed by the database rather than an in-process map.

This is deliberately **not** a Prompt Registry, not a prompt
writing/admin API, and not a Capability Manager extension — all remain
out of scope. It is a reader/renderer path only, mirroring
:class:`~ai_os_kernel.workflow_engine.definition_catalog.
SqlWorkflowDefinitionCatalog`'s shape (a thin SQLAlchemy 2.0 Core
component, ADR-0011) as closely as a *read* mirrors that module's
*write*: look up one row by its natural key, map it onto the already-
established contract, fail cleanly if it is missing or the query itself
fails.

**Lookup key is ``(prompt_id, version)``**, matching
``catalog.prompts``' primary key exactly (data_model.md §5) and
:class:`~ai_os_kernel.prompt_engine.models.PromptRenderRequest`'s own
``prompt_id``/``version`` fields — no version resolution, no role/alias
lookup (the Version Manager/Prompt Resolver subsystems, prompt_engine.md
§5, remain out of scope; the caller still supplies an exact version, as
:class:`InMemoryPromptEngine <ai_os_kernel.prompt_engine.renderer.
InMemoryPromptEngine>` already requires).

**Only ``content`` is read.** ``catalog.prompts`` also has
``pack_id``/``input_schema``/``content_hash`` columns, but this reduced
render contract has no field for any of them yet (see
:mod:`ai_os_kernel.prompt_engine.models` for exactly which fields of the
full §6 Prompt Contract this step's contract covers) — reading columns
this contract cannot expose would be dead data, not a real feature.
Required variables continue to come from the placeholders literally
present in ``content`` (:func:`~ai_os_kernel.prompt_engine.renderer.
render_template`), not from the row's own ``input_schema`` — validating
against a declared schema is real prompt catalog loading beyond what
this step needs, the same fence :class:`InMemoryPromptEngine
<ai_os_kernel.prompt_engine.renderer.InMemoryPromptEngine>` already
draws.

No writer, no update, no delete — reading is the only operation this
step approves. Rows must already exist in ``catalog.prompts`` by
whatever process eventually owns writing them (a Capability Manager /
Manifest Loader concern, out of scope here, the same boundary already
drawn for ``catalog.workflow_definitions`` before its own minimal writer
existed).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.catalog_schema import prompts
from ai_os_kernel.prompt_engine.errors import PromptCatalogError, PromptNotFoundError
from ai_os_kernel.prompt_engine.models import PromptRenderRequest, PromptRenderResponse
from ai_os_kernel.prompt_engine.renderer import render_template


class SqlPromptCatalog:
    """The ``catalog.prompts``-backed implementation of
    :class:`~ai_os_kernel.prompt_engine.renderer.PromptEngine`: SQLAlchemy
    2.0 Core against Postgres (ADR-0011)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def render(self, request: PromptRenderRequest) -> PromptRenderResponse:
        try:
            async with self._engine.connect() as connection:
                result = await connection.execute(
                    sa.select(prompts.c.content).where(
                        prompts.c.prompt_id == request.prompt_id,
                        prompts.c.version == request.version,
                    )
                )
                row = result.one_or_none()
        except sa.exc.SQLAlchemyError as exc:
            raise PromptCatalogError(
                f"failed to load prompt '{request.prompt_id}@{request.version}': {exc}"
            ) from exc

        if row is None:
            raise PromptNotFoundError(
                f"no template registered for prompt_id={request.prompt_id!r} "
                f"version={request.version!r}"
            )

        content = render_template(row.content, request.variables)

        return PromptRenderResponse(
            prompt_id=request.prompt_id,
            version=request.version,
            content=content,
        )
