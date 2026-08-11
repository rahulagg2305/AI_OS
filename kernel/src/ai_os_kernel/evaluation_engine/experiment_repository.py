"""The ``evaluation.experiments`` writer and reader (``P04-S01-M12-T12``,
FR-070) — this table's first real writer, and the create/read half of
api_architecture.md §6.3's own documented Experiments endpoint group.

**Why this lives in the Kernel, not the Benchmarking pack.** Experiment
*validation rules* exist in that pack too (`ai_os_pack_benchmarking.
experiment_definition.validate_experiment_spec`), and it would be
tempting to reuse them — but the Kernel is deliberately pack-agnostic
(the whole point of the manifest/registry system is that the Kernel
hard-codes no pack knowledge), the ``evaluation.experiments`` table and
the ``POST /api/v1/experiments`` route are both platform-level (a Kernel
table, a documented platform API), and the rules themselves (``>= 2``
variants to compare, ``>= 3`` replicates for variance) are generic
statistical truths, not Benchmarking-specific. So the platform owns its
own experiment validation here; the pack's version is a legitimate
independent mirror across the Kernel/pack boundary — the identical
precedent ``ai_os_sdk.models.tool.TrustTier`` and the Project
Intelligence pack's own ``provenance.py`` already establish. Reconciling
the two into one shared source of truth is real, separate, later work.

**The data model follows data_model.md §6 literally, resolving a real
mismatch found while building.** The Benchmarking pack's own
``ExperimentSpec`` carries an explicit ``variants`` list (each
``{variant_key, model_alias}``) — but data_model.md §6 is authoritative,
and it puts ``variant_key``/``model_alias`` in ``evaluation.
experiment_runs`` (the *materialised* variants, one row per run), while
``evaluation.experiments`` stores only ``variables`` ("what is
deliberately varied"). So a platform *experiment definition* records
what varies (``variables``: each key a varied dimension, each value the
list of alternatives to compare) plus the reproducibility/statistics
parameters; the concrete per-variant runs are a *run-time* concern
(``POST /experiments/{id}/run``, a later ticket), never stored here.
``pinned_conditions`` is empty at definition time — those are pinned
into the run manifest when the experiment actually runs (ADR-0022) — and
``status`` starts at ``defined``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.persistence.evaluation_schema import experiments
from ai_os_kernel.workflow_engine.definition_catalog import WorkflowDefinitionCatalog
from ai_os_kernel.workflow_engine.ids import new_experiment_id

# The two documented rules a definition can be checked against at
# definition time (Benchmarking `overview.md` §5/§7, elevated here to the
# platform's own — see this module's docstring): a comparison needs at
# least two variants, and variance across replicates needs at least three
# runs of each. The per-variant enumeration is a run-time concern, so at
# definition time "at least two variants" is checked as "the declared
# `variables` yield at least two distinct variants" (their combinatorial
# product), which a real run will materialise.
_MIN_VARIANTS = 2
_MIN_RUNS_PER_VARIANT = 3
_INITIAL_STATUS = "defined"


class ExperimentValidationError(ValueError):
    """A caller-supplied experiment definition failed one or more real
    rules — carries every failure found, not just the first, so a caller
    can fix all of them at once (the identical shape the Benchmarking
    pack's own ``ExperimentValidationError`` already uses)."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class ExperimentDefinitionNotFoundError(Exception):
    """``POST /experiments`` named a ``definition_id``/``definition_version``
    that no real ``catalog.workflow_definitions`` row matches — reported
    before any insert, so a caller gets a clear error rather than a raw
    foreign-key ``IntegrityError``."""


class ExperimentDefinitionInput(BaseModel):
    """The raw, caller-supplied experiment definition — the body
    ``POST /api/v1/experiments`` accepts. ``created_by`` is deliberately
    absent: it is the authenticated principal's own id, never a
    client-declared field (the "who did this comes from authentication"
    convention ``start_workflow``/pack-lifecycle already establish)."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    definition_id: str
    definition_version: str
    variables: dict[str, list[str]]
    runs_per_variant: int
    pinned_conditions: dict[str, Any] = Field(default_factory=dict)


class ExperimentRecord(BaseModel):
    """One real, persisted ``evaluation.experiments`` row — the read model
    ``GET /experiments``/``GET /experiments/{id}`` return."""

    model_config = ConfigDict(frozen=True)

    experiment_id: str
    name: str
    description: str
    definition_id: str
    definition_version: str
    variables: dict[str, Any]
    pinned_conditions: dict[str, Any]
    runs_per_variant: int
    status: str
    created_by: str


def _variant_count(variables: dict[str, list[str]]) -> int:
    """The number of distinct variants the declared ``variables`` yield —
    the combinatorial product of each varied dimension's own alternatives.
    An empty ``variables`` (nothing varied) yields zero, not one: an
    experiment that varies nothing is not a real experiment."""
    if not variables:
        return 0
    count = 1
    for alternatives in variables.values():
        count *= len(alternatives)
    return count


def validate_experiment_definition(definition: ExperimentDefinitionInput) -> None:
    """Every documented, checkable-at-definition-time rule, collecting all
    failures. Raises :class:`ExperimentValidationError` if any fail."""
    errors: list[str] = []
    if not definition.name.strip():
        errors.append("name must not be empty")
    if not definition.description.strip():
        errors.append("description must not be empty")
    for dimension, alternatives in definition.variables.items():
        if len(alternatives) < 1:
            errors.append(f"varied dimension {dimension!r} declares no alternatives")
    if _variant_count(definition.variables) < _MIN_VARIANTS:
        errors.append(
            f"an experiment must compare at least {_MIN_VARIANTS} variants — the declared "
            f"`variables` yield {_variant_count(definition.variables)}"
        )
    if definition.runs_per_variant < _MIN_RUNS_PER_VARIANT:
        errors.append(
            f"runs_per_variant must be >= {_MIN_RUNS_PER_VARIANT} (replicate count for "
            f"variance) — got {definition.runs_per_variant}"
        )
    if errors:
        raise ExperimentValidationError(errors)


class SqlExperimentRepository:
    """The only implementation at this stage: SQLAlchemy 2.0 Core against
    Postgres (ADR-0011). Reuses the Kernel's own
    :class:`~ai_os_kernel.workflow_engine.definition_catalog.
    WorkflowDefinitionCatalog` to confirm the referenced workflow
    definition really exists — a pure-Kernel collaborator, no pack
    involved — before writing, so the composite foreign key can never be
    the thing that surfaces a bad reference."""

    def __init__(
        self, engine: AsyncEngine, *, definition_catalog: WorkflowDefinitionCatalog
    ) -> None:
        self._engine = engine
        self._definition_catalog = definition_catalog

    async def create(
        self, definition: ExperimentDefinitionInput, *, created_by: str
    ) -> ExperimentRecord:
        validate_experiment_definition(definition)
        existing = await self._definition_catalog.get(
            definition_id=definition.definition_id, version=definition.definition_version
        )
        if existing is None:
            raise ExperimentDefinitionNotFoundError(
                f"no workflow definition {definition.definition_id!r} "
                f"version {definition.definition_version!r} exists to experiment on"
            )
        record = ExperimentRecord(
            experiment_id=new_experiment_id(),
            name=definition.name,
            description=definition.description,
            definition_id=definition.definition_id,
            definition_version=definition.definition_version,
            variables=dict(definition.variables),
            pinned_conditions=dict(definition.pinned_conditions),
            runs_per_variant=definition.runs_per_variant,
            status=_INITIAL_STATUS,
            created_by=created_by,
        )
        async with self._engine.begin() as connection:
            await connection.execute(sa.insert(experiments).values(**record.model_dump()))
        return record

    async def update_status(self, experiment_id: str, status: str) -> None:
        """Transition an experiment's lifecycle ``status`` — e.g.
        ``defined`` -> ``running`` -> ``complete`` as
        ``POST /experiments/{id}/run`` drives it (``P04-S01-M12-T13``).
        A row-count-agnostic ``UPDATE``: an ``experiment_id`` matching no
        row updates nothing rather than raising, since the only caller
        (the run orchestrator) has already confirmed the row exists via
        :meth:`get`. ``status`` has no ``CHECK`` constraint (§6 gives the
        column no closed value list — see ``evaluation_schema.py``)."""
        async with self._engine.begin() as connection:
            await connection.execute(
                sa.update(experiments)
                .where(experiments.c.experiment_id == experiment_id)
                .values(status=status)
            )

    async def get(self, experiment_id: str) -> ExperimentRecord | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(experiments).where(experiments.c.experiment_id == experiment_id)
                    )
                )
                .mappings()
                .one_or_none()
            )
        return ExperimentRecord.model_validate(dict(row)) if row is not None else None

    async def list_all(self) -> list[ExperimentRecord]:
        """Every real experiment, newest first — deliberately unpaginated,
        the same "genuinely small, bounded collection" reasoning
        ``GET /workflow_definitions``/``GET /approvals`` already use (an
        experiment is defined by a human, rarely, not once per run)."""
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(experiments).order_by(experiments.c.experiment_id.desc())
                    )
                )
                .mappings()
                .all()
            )
        return [ExperimentRecord.model_validate(dict(row)) for row in rows]
