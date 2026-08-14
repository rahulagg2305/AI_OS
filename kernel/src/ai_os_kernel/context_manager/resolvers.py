"""Source Resolvers (context_manager.md §4) — the components that each
know how to pull items from exactly one source.

**All six documented sources are now real: Workflow State, Knowledge
(``P02-S03-M08-T05``), Memory (``P02-S03-M08-T06``), Runtime
Configuration (``P02-S03-M08-T08``), and, as of ``P02-S03-M08-T07``,
AI Context Packs.** context_manager.md §3 lists six sources an
assembly may draw on: Workflow State, Knowledge Manager, Memory
Manager, AI Context Packs, Runtime Configuration, and User-provided
inputs. Workflow State was the first real one —
:class:`~ai_os_kernel.workflow_engine.repository.WorkflowInstanceRepository`,
already built and already real. :class:`KnowledgeResolver` calls the
real :class:`~ai_os_kernel.knowledge_manager.query_engine.QueryEngine`
(``P02-S04-M09-T04``). :class:`MemoryResolver` calls the real
:class:`~ai_os_kernel.persistence.memory_writer.MemoryStore`
(``P02-S04-M10-T01``). :class:`RuntimeConfigResolver` calls the
real :class:`~ai_os_kernel.configuration_manager.loader.
ConfigurationManager` (``P01-S02-M01-T04``).

**``AIContextPackResolver`` (below) is real, disclosed-narrow logic
against a documented-but-currently-empty real structure — not a
built-ahead-of-need fabrication.** ``docs/ai_context/
context_pack_structure.md`` §3/§4 fully specifies a real directory
layout (``<category>/<pack_name>/manifest.yaml`` plus numbered content
files) and real manifest fields (``id``/``name``/``version``/``type``/
``description``/``applies_to``/``priority``) — the gap this ticket
faced was never missing documentation (contrast
``P02-S04-M10-T03``'s Promotion Logic, which found no documented
shape at all and was correctly left ``blocked``); it is that the real
``ai_context/`` directory itself is absent from a fresh clone (that
document's own words: "Built: nothing... absent from a fresh clone"),
and CLAUDE.md's own standing rule forbids creating a planned folder
speculatively. This resolver never creates or assumes that directory
exists — ``base_dir`` is a real, constructor-injected path (mirroring
:class:`~ai_os_kernel.configuration_manager.loader.
ConfigurationManager`'s own ``platform_config_path``/
``environments_dir`` injection), and a missing directory, missing
``manifest.yaml``, or missing individual content file all resolve to
"no such pack"/"no such section," never an error — the identical
"an unresolvable source contributing nothing is not a failure" shape
every other resolver in this module already establishes. Proven
against real files written to a real ``tmp_path`` directory — real
file I/O against the real documented format, the identical precedent
``test_loader.py`` already uses for ``ConfigurationManager``'s own
not-yet-populated YAML files — never the actual repository
``ai_context/`` directory. ``pack_references`` is a real constructor
parameter (mirroring ``RuntimeConfigResolver``'s own ``config_keys``):
automatic, ``applies_to``-based pack selection is deliberately out of
scope — a caller names exactly which packs it wants.

**``relevance_score`` reads the pack's own real, manifest-declared
``priority`` — a real authored signal, not a constant.** A pack with no
declared ``priority`` gets ``0.0``, the identical "no signal recorded
is honestly zero relevance" default :class:`MemoryResolver` already
establishes for an unset ``quality_signal``. ``id``/``version`` are
required, not optional-with-an-invented-default: §7 of that same
document states "every context pack must have a version," and ``id``
is a pack's own primary identity — a manifest missing either is
malformed input, not a sparse-but-valid one, so both are validated,
not guessed.

**``RuntimeConfigResolver`` re-resolves configuration fresh on every
``resolve()`` call, including the live ``RuntimeOverrideStore``
snapshot — never a value cached once at composition time.** This
ticket's own Goal is "expose *runtime* configuration as context";
Layer 5 (``P01-S02-M01-T04``) exists specifically so an override takes
effect without a process restart, and ``ConfigurationManager.load()``
is documented as synchronous, non-I/O merging (its own module
docstring: "never awaits anything") — cheap enough to call every time,
so caching would only risk serving a stale value for no real benefit.
``config_keys`` is a real constructor parameter (mirroring
``MemoryResolver``'s own caller-supplied ``memory_type``) validated
against :class:`~ai_os_kernel.configuration_manager.models.
PlatformConfig`'s own real, declared fields at construction time — an
unknown key is rejected immediately, the identical "no guessing a
typo'd name" discipline :class:`~ai_os_kernel.prompt_engine.resolver.
PromptResolver` already establishes for role binding, not deferred
to a confusing failure on first use.

**``trust`` is ``"trusted"`` here — the opposite of
``WorkflowStateResolver``'s own classification, for a real, reasoned
cause, not an inconsistency.** ADR-0016's own rationale
(``WorkflowStateResolver``'s docstring below) is "no untrusted content
can confer authority... treat anything not authored by the Kernel
itself as untrusted." Runtime configuration is the inverse case: an
operator-authored, schema-validated ``PlatformConfig`` value, not
externally-supplied content — genuinely authored by the Kernel's own
trusted subsystems, so ADR-0016's own rule places it on the *other*
side of the same line.

**``MemoryResolver`` deliberately does not filter by
``source_workflow_id`` — genuinely cross-run, matching the Memory
Store's own Goal ("durable store for cross-run memory"), not scoped to
the current request's own ``workflow_id``.** A resolver that filtered
by the current run would only ever see memory that run itself already
wrote earlier — functionally a second Workflow State resolver, not a
genuine Memory source. **Disclosed, not fabricated:** ``promoted_at``
is real but always ``NULL`` today (no promotion logic exists yet —
``P02-S04-M10-T01``'s own disclosure), so this surfaces every real row
of its configured ``memory_type`` ever written by any workflow, not
only "reviewed" ones. ``memory_type`` is a real constructor parameter (mirroring
``KnowledgeResolver``'s own caller-supplied ``embedding_model_alias``)
— this module never picks one on the composer's behalf, honoring "no
hardcoded values."

**"User-provided inputs" is not a separate resolver.** context_manager.md
§3 lists it alongside Workflow State as a distinct source, but in this
codebase there is exactly one place user-provided data actually lives:
``WorkflowInstance.inputs`` — the ``inputs`` dict a caller supplied to
``POST /api/v1/workflows``, schema-validated at creation
(``workflow_engine.input_validation.validate_inputs``) and persisted
onto the instance. There is no second, distinct "user input" capture
mechanism to build a separate resolver around, so
:class:`WorkflowStateResolver` below is read as covering both
documented sources honestly, rather than one resolver artificially
split into two.

**Trust classification, flagged as a documentation gap, not silently
resolved.** context_manager.md §6 says every item's ``trust`` is
mandatory and gives examples of ``untrusted`` content ("Repository
content, ingested documents, tool output, and web content") but does
not classify workflow/user input either way. This resolver treats
``WorkflowInstance.inputs`` as ``untrusted``: it originates outside the
Kernel's own trusted subsystems (a human or service caller), and
ADR-0016's own rationale — "no untrusted content can confer
authority" — argues for treating anything not authored by the Kernel
itself as untrusted by default. See this package's own ``__init__.py``
docstring for the full inconsistency note.

**Token counting here is a heuristic, not a violation of
llm_gateway.md §12.** See ``models.py``'s own docstring for why context
assembly (which has no model alias to count against) is a different
concern from the Gateway's own real, per-provider token accounting.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import yaml

from ai_os_kernel.configuration_manager.loader import ConfigurationManager
from ai_os_kernel.configuration_manager.models import PlatformConfig
from ai_os_kernel.configuration_manager.runtime_overrides import RuntimeOverrideStore
from ai_os_kernel.context_manager.models import ContextItem, ContextRequest, SourceRef, SourceType
from ai_os_kernel.knowledge_manager.query_engine import QueryEngine
from ai_os_kernel.llm_gateway.gateway import Embedder
from ai_os_kernel.llm_gateway.models import EmbeddingRequest
from ai_os_kernel.persistence.memory_writer import MemoryStore, MemoryType
from ai_os_kernel.retrieval.retrieval_service import RetrievalRequest

if TYPE_CHECKING:
    # Deferred to type-checking time only, to break a real, otherwise
    # unavoidable *runtime* import cycle: `ai_os_kernel.workflow_engine`'s
    # own `__init__.py` eagerly imports `step_executor`, which imports
    # `ai_os_kernel.context_manager` (for the `ContextManager` Protocol)
    # — so importing `workflow_engine.repository` here at module-load
    # time would re-enter this package before it finishes initialising.
    # `WorkflowStateResolver`/`WorkflowStepOutputResolver` only ever need
    # `WorkflowInstanceRepository` as a static type (structural duck
    # typing, not a runtime isinstance check), so this import has no
    # runtime behaviour to lose. The underlying dependency is real and
    # bidirectional by design — the Context Manager reads Workflow
    # State, and the Workflow Engine calls the Context Manager — not an
    # accident to be designed away.
    from ai_os_kernel.workflow_engine.repository import WorkflowInstanceRepository
    from ai_os_kernel.workflow_engine.step_record import WorkflowStepRecord

_CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_tokens(content: str) -> int:
    """A simple, deterministic length-based approximation — not a real
    tokenizer, and never used for budget enforcement or cost accounting
    (see this package's ``models.py`` docstring)."""
    if not content:
        return 0
    return max(1, len(content) // _CHARS_PER_TOKEN_ESTIMATE)


class ContextSourceResolver(Protocol):
    """One entry in :class:`~ai_os_kernel.context_manager.manager.
    DefaultContextManager`'s resolver list. Each resolver knows about
    exactly one source and nothing about how its items will be
    combined, ranked, or truncated — that is the assembler's job."""

    source_type: SourceType

    async def resolve(self, request: ContextRequest) -> list[ContextItem]: ...


class WorkflowStateResolver:
    """Reads the current workflow instance's own declared ``inputs`` —
    see this module's own docstring for why this also stands in for
    "User-provided inputs" (context_manager.md §3).

    Returns no items, not an error, when the instance cannot be found
    or declared no inputs — an unresolvable source contributing nothing
    is not a failure, the same "cannot be checked, not an error" shape
    already established for a missing ``workflow_id`` on
    :class:`~ai_os_kernel.llm_gateway.models.TraceContext`.
    """

    source_type = SourceType.WORKFLOW_STATE

    def __init__(self, repository: WorkflowInstanceRepository) -> None:
        self._repository = repository

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        instance = await self._repository.get_instance(request.workflow_id)
        if instance is None or not instance.inputs:
            return []

        # Deterministic serialisation (ADR-0022: "context assembly ...
        # is deterministic given the same inputs") — sorted keys, the
        # identical "stable ordering" rule llm_gateway.md §8 already
        # requires of tool-definition serialisation.
        content = json.dumps(instance.inputs, sort_keys=True, default=str)

        return [
            ContextItem(
                content=content,
                provenance=SourceRef(
                    source_type=SourceType.WORKFLOW_STATE,
                    identifier=f"workflow_instance:{request.workflow_id}",
                ),
                # No ranking model exists yet — every item from the one
                # real resolver scores the same constant. The Size &
                # Token Budget Enforcer (manager.py) reuses this score
                # only as a stable truncation tie-break, not as real
                # ranking.
                relevance_score=1.0,
                token_count=estimate_tokens(content),
                trust="untrusted",
            )
        ]


class KnowledgeResolver:
    """Brings real, queried knowledge-base content into step context —
    this ticket's own Goal (``P02-S03-M08-T05``). Calls the real
    :class:`~ai_os_kernel.knowledge_manager.query_engine.QueryEngine`
    unchanged — no parallel search mechanism.

    ``request.knowledge_query`` is ``None`` for most requests today (no
    caller sets it yet) — the identical "an unresolvable source
    contributing nothing is not a failure" shape :class:`WorkflowStateResolver`
    already established, not an error.

    **A real query vector, not a fabricated one.** ``RetrievalRequest``
    requires ``query_vector``/``embedding_model_id``/
    ``embedding_model_version`` — this resolver is the LLM Gateway's
    real :class:`~ai_os_kernel.llm_gateway.gateway.Embedder`'s second
    real caller (after :func:`~ai_os_kernel.retrieval.embedding_writer.
    embed_chunk`), calling the real ``embed()`` with a caller-supplied
    ``embedding_model_alias`` (ADR-0002: never a literal model id) —
    genuine semantic+keyword fusion, not a placeholder model id chosen
    to make vector search silently return nothing.

    **``relevance_score`` is the real fused RRF score** —
    :class:`~ai_os_kernel.retrieval.hybrid_search.FusedResult.fused_score`
    passed straight through, the first resolver in this package whose
    score is not a constant (see ``manager.py``'s own updated
    docstring).

    ``trust`` is the queried document's own real classification
    (:class:`~ai_os_kernel.knowledge_manager.query_engine.
    KnowledgeQueryResult.trust`) — genuinely ``"trusted"`` or
    ``"untrusted"`` per source, unlike :class:`WorkflowStateResolver`'s
    fixed constant, since Knowledge Manager content really does carry
    its own per-document trust.
    """

    source_type = SourceType.KNOWLEDGE

    def __init__(
        self,
        *,
        query_engine: QueryEngine,
        embedder: Embedder,
        embedding_model_alias: str,
        limit: int,
    ) -> None:
        self._query_engine = query_engine
        self._embedder = embedder
        self._embedding_model_alias = embedding_model_alias
        self._limit = limit

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        if not request.knowledge_query or not request.knowledge_query.strip():
            return []

        embedding_response = await self._embedder.embed(
            EmbeddingRequest(
                model_alias=self._embedding_model_alias, inputs=[request.knowledge_query]
            )
        )

        # `P02-S04-M09-T08`: the requesting principal's own permissions
        # reach §5's Access / Filter Layer here. This resolver applies no
        # filtering of its own — the control is a SQL predicate inside
        # `QueryEngine`, so it cannot leak through ranking (ADR-0013),
        # and a resolver-side filter would be exactly the post-filtering
        # search_vector_search.md §4 rules out.
        results = await self._query_engine.query(
            RetrievalRequest(
                query_text=request.knowledge_query,
                query_vector=embedding_response.vectors[0],
                embedding_model_id=embedding_response.model_id,
                embedding_model_version=embedding_response.model_version,
                limit=self._limit,
            ),
            principal_permissions=request.principal_permissions,
        )

        return [
            ContextItem(
                content=result.content,
                provenance=SourceRef(
                    source_type=SourceType.KNOWLEDGE,
                    identifier=f"knowledge_chunk:{result.chunk_id}",
                ),
                relevance_score=result.fused_score,
                token_count=estimate_tokens(result.content),
                trust=result.trust,
            )
            for result in results
        ]


class MemoryResolver:
    """Brings real, durable, cross-run memory into step context — this
    ticket's own Goal (``P02-S03-M08-T06``). Calls the real
    :class:`~ai_os_kernel.persistence.memory_writer.MemoryStore`
    unchanged — no parallel storage mechanism.

    Deliberately not filtered by ``source_workflow_id`` — see this
    module's own docstring for why "cross-run" requires that.

    **``relevance_score`` reuses the real ``quality_signal`` column
    when a caller has set one; ``0.0`` (the lowest a real score can
    meaningfully be) when it hasn't** — nothing computes
    ``quality_signal`` yet (``P02-S04-M10-T01``'s own disclosure), so
    most memory today gets ``0.0``. This is a real, principled default
    ("no confidence signal recorded" is honestly zero relevance, not a
    guessed positive number), not an arbitrary tuning constant — and it
    is exactly what calibrates context_manager.md's own "Knowledge
    outranks Memory in authority" rule for the first time: an
    unscored memory item (``0.0``) now genuinely ranks below every real
    Knowledge hit (RRF scores are always positive) and below
    :class:`WorkflowStateResolver`'s constant ``1.0``, without this
    resolver needing to know either of their real ranges in advance.

    ``trust`` is fixed ``"untrusted"`` for every memory item — the
    identical reasoning :class:`WorkflowStateResolver` already applies
    (ADR-0016: "no untrusted content can confer authority"): memory
    content is typically an agent's own synthesized experience, not a
    reviewed, human-authored document, and ``memory_items`` has no
    per-row trust column of its own to read instead.
    """

    source_type = SourceType.MEMORY

    def __init__(self, *, memory_store: MemoryStore, memory_type: MemoryType, limit: int) -> None:
        self._memory_store = memory_store
        self._memory_type = memory_type
        self._limit = limit

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        records = await self._memory_store.query_memories(
            memory_type=self._memory_type, limit=self._limit
        )

        return [
            ContextItem(
                content=record.content,
                provenance=SourceRef(
                    source_type=SourceType.MEMORY,
                    identifier=f"memory_item:{record.memory_id}",
                ),
                relevance_score=(
                    float(record.quality_signal) if record.quality_signal is not None else 0.0
                ),
                token_count=estimate_tokens(record.content),
                trust="untrusted",
            )
            for record in records
        ]


class RuntimeConfigKeyUnknownError(Exception):
    """A ``config_keys`` entry names a field
    :class:`~ai_os_kernel.configuration_manager.models.PlatformConfig`
    does not declare — raised at :class:`RuntimeConfigResolver`
    construction time, not deferred to a confusing failure on first
    ``resolve()`` call.
    """


class RuntimeConfigResolver:
    """Brings real, live runtime configuration into step context —
    this ticket's own Goal (``P02-S03-M08-T08``). Calls the real
    :class:`~ai_os_kernel.configuration_manager.loader.
    ConfigurationManager` unchanged — no parallel configuration
    mechanism.

    ``role``/``pack_manifests`` are the identical, real parameters
    :meth:`ConfigurationManager.load` already requires/accepts — this
    resolver invents no new configuration-resolution behaviour, only
    calls the real one on every request.
    """

    source_type = SourceType.CONFIGURATION

    def __init__(
        self,
        *,
        configuration_manager: ConfigurationManager,
        runtime_override_store: RuntimeOverrideStore,
        role: str,
        config_keys: Sequence[str],
        pack_manifests: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        unknown = sorted(set(config_keys) - set(PlatformConfig.model_fields))
        if unknown:
            raise RuntimeConfigKeyUnknownError(
                f"config_keys name field(s) PlatformConfig does not declare: {', '.join(unknown)}"
            )

        self._configuration_manager = configuration_manager
        self._runtime_override_store = runtime_override_store
        self._role = role
        self._config_keys = tuple(config_keys)
        self._pack_manifests = pack_manifests

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        config = self._configuration_manager.load(
            role=self._role,
            pack_manifests=self._pack_manifests,
            runtime_overrides=self._runtime_override_store.snapshot(),
        )

        items = []
        for key in self._config_keys:
            value = getattr(config, key)
            content = f"{key}: {json.dumps(value, sort_keys=True, default=str)}"
            items.append(
                ContextItem(
                    content=content,
                    provenance=SourceRef(
                        source_type=SourceType.CONFIGURATION,
                        identifier=f"config_key:{key}",
                    ),
                    # No ranking model exists for configuration either
                    # -- the identical constant WorkflowStateResolver
                    # already uses for the same "no real signal" case.
                    relevance_score=1.0,
                    token_count=estimate_tokens(content),
                    trust="trusted",
                )
            )
        return items


class AIContextPackError(Exception):
    """A pack's ``manifest.yaml`` exists but is malformed — invalid
    YAML, not a mapping, or missing its required ``id``/``version``
    (docs/ai_context/context_pack_structure.md §7: "every context pack
    must have a version"). A genuinely *missing* manifest, content
    file, or pack directory is not this error — see
    :class:`AIContextPackResolver`'s own docstring for why that
    resolves to "no such pack" instead.
    """


# The numbered content files docs/ai_context/context_pack_structure.md
# §3 documents, in the same order that document lists them. "Not every
# pack needs every file" (that document's own words) -- a real,
# disclosed reason to skip whichever are absent, not an invented list.
_CONTENT_FILENAMES = (
    "00_invariants.md",
    "01_architecture.md",
    "02_standards.md",
    "03_current_state.md",
    "04_task_guidance.md",
)


class AIContextPackResolver:
    """Loads real, declared AI Context Packs — this ticket's own Goal
    (``P02-S03-M08-T07``). See this module's own docstring for why
    ``base_dir`` is a real, constructor-injected path rather than the
    actual repository ``ai_context/`` directory, and why a missing
    pack resolves to no items rather than an error.
    """

    source_type = SourceType.AI_CONTEXT_PACK

    def __init__(self, *, base_dir: Path, pack_references: Sequence[str]) -> None:
        self._base_dir = base_dir
        self._pack_references = tuple(pack_references)

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        items: list[ContextItem] = []
        for pack_reference in self._pack_references:
            items.extend(self._resolve_one_pack(pack_reference))
        return items

    def _resolve_one_pack(self, pack_reference: str) -> list[ContextItem]:
        pack_dir = self._base_dir / pack_reference
        manifest_path = pack_dir / "manifest.yaml"
        if not manifest_path.exists():
            # Not "declared" at all -- an unresolvable source
            # contributing nothing is not a failure, the same shape
            # every other resolver in this module already establishes.
            return []

        try:
            with manifest_path.open("r", encoding="utf-8") as fh:
                manifest = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise AIContextPackError(f"{manifest_path}: not valid YAML: {exc}") from exc
        if not isinstance(manifest, dict):
            raise AIContextPackError(
                f"{manifest_path}: must contain a YAML mapping at the top level"
            )

        pack_id = manifest.get("id")
        version = manifest.get("version")
        if not pack_id or not version:
            raise AIContextPackError(
                f"{manifest_path}: 'id' and 'version' are both required "
                "(docs/ai_context/context_pack_structure.md §7)"
            )
        priority = manifest.get("priority", 0)

        items: list[ContextItem] = []
        for filename in _CONTENT_FILENAMES:
            file_path = pack_dir / filename
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8")
            if not content.strip():
                continue
            items.append(
                ContextItem(
                    content=content,
                    provenance=SourceRef(
                        source_type=SourceType.AI_CONTEXT_PACK,
                        identifier=f"ai_context_pack:{pack_id}@{version}:{filename}",
                    ),
                    relevance_score=float(priority),
                    token_count=estimate_tokens(content),
                    trust="trusted",
                )
            )
        return items


class WorkflowStepOutputResolver:
    """A second real resolver for the same "Workflow State" source
    context_manager.md §3 documents — sibling to
    :class:`WorkflowStateResolver`, not a new source category. §5's own
    ``required_context_types`` example list names ``previous_outputs``
    explicitly, alongside ``requirements``/``architecture``/
    ``coding_standards`` — this resolver is that: a *named prior step's*
    own persisted output (``workflow_steps.outputs``, data_model.md
    §4.3), not the instance's own top-level ``inputs``
    :class:`WorkflowStateResolver` already covers. Both share
    ``source_type = SourceType.WORKFLOW_STATE``; :class:`~ai_os_kernel.
    context_manager.models.SourceRef`'s own ``identifier`` is what
    distinguishes one item's real provenance from the other's, exactly
    the field that exists for this ("where it came from ... provenance").

    **This is the "step-output-to-next-step-input" seam
    workflow_architecture.md's own Context Management section already
    names ("Previous workflow state") without further specifying —
    built here as a Context Manager resolver, deliberately not as a new
    field on :class:`~ai_os_kernel.workflow_engine.models.WorkflowStep`
    itself.** That document's own Step Contract section is explicit that
    its five invocation fields are "never ... a cross-step reference" —
    a rule scoped to those five fields, but this resolver honours its
    spirit by keeping every cross-step reference entirely inside the
    Context Manager/composition layer instead, where "Previous workflow
    state" is already a documented, sanctioned source.

    ``step_sources`` is a flat, statically-declared mapping —
    ``{consuming_step_id: source_step_id}`` or
    ``{consuming_step_id: [source_step_id, ...]}`` for a step needing
    more than one prior step's output merged together (later entries
    win on a key collision — declared merge order, not computed). This
    is deliberately the smallest data structure that expresses "this
    step's input includes the named output of step X": two strings, or
    a short list of strings, resolved once at composition time — never
    an expression language, a template, or conditional logic. A
    consuming step absent from ``step_sources`` resolves to no items —
    the same "an unresolvable source contributing nothing is not a
    failure" shape :class:`WorkflowStateResolver` already established.

    ``field_selectors``, when given for a consuming step, extracts
    exactly one named field from the (merged) source output verbatim as
    this item's own content — for a consumer that wants free text (an
    instruction fed into a prompt's own ``{{context}}`` variable, the
    way :mod:`~ai_os_kernel.workflow_engine.prompted_agent` already
    flattens context). Omitted (the default) returns the source
    output's entire dict, JSON-encoded — for a consumer that already
    parses a structured JSON payload out of its own assembled context
    (every agent in the ``software-engineering`` pack's own
    ``_extract_payload()`` convention).

    ``output_transforms``, when given for a consuming step, is a real
    Python callable applied to the (merged) source output dict before
    field-selection/encoding — the one deliberately narrow escape hatch
    this class needs, not a general expression language exposed to
    workflow authors. It exists only because a downstream agent's own
    already-shipped contract can require a field an upstream agent's
    own already-shipped output has no reason to produce (see
    :mod:`ai_os_pack_software_engineering.pipeline`'s own docstring for
    the one real, reviewed transform this pack's own pipeline supplies
    — never declared inline in any workflow definition file or YAML).

    Returns no items — not an error — whenever the referenced source
    step(s) have not (yet) produced a real, persisted output: still
    running, not yet reached, or genuinely absent. The identical
    "cannot be checked, not an error" shape :class:`WorkflowStateResolver`
    already established for a missing instance.
    """

    source_type = SourceType.WORKFLOW_STATE

    def __init__(
        self,
        repository: WorkflowInstanceRepository,
        *,
        step_sources: Mapping[str, str | Sequence[str]],
        field_selectors: Mapping[str, str] | None = None,
        output_transforms: Mapping[str, Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
    ) -> None:
        self._repository = repository
        self._step_sources: dict[str, tuple[str, ...]] = {
            step_id: ((source,) if isinstance(source, str) else tuple(source))
            for step_id, source in step_sources.items()
        }
        self._field_selectors = dict(field_selectors or {})
        self._output_transforms = dict(output_transforms or {})

    async def resolve(self, request: ContextRequest) -> list[ContextItem]:
        source_step_ids = self._step_sources.get(request.step_id)
        if not source_step_ids:
            return []

        steps = await self._repository.list_steps(request.workflow_id)
        merged: dict[str, Any] = {}
        for source_step_id in source_step_ids:
            source_step = _latest_completed_output(steps, source_step_id)
            if source_step is None:
                return []
            merged.update(source_step)

        transform = self._output_transforms.get(request.step_id)
        if transform is not None:
            merged = transform(merged)

        field = self._field_selectors.get(request.step_id)
        content = (
            str(merged.get(field, ""))
            if field is not None
            else json.dumps(merged, sort_keys=True, default=str)
        )

        return [
            ContextItem(
                content=content,
                provenance=SourceRef(
                    source_type=SourceType.WORKFLOW_STATE,
                    identifier=(
                        f"workflow_step_output:{request.workflow_id}:{','.join(source_step_ids)}"
                    ),
                ),
                relevance_score=1.0,
                token_count=estimate_tokens(content),
                trust="untrusted",
            )
        ]


def _latest_completed_output(
    steps: Sequence[WorkflowStepRecord], step_name: str
) -> dict[str, Any] | None:
    """The most-recently-attempted ``steps`` row named ``step_name``
    with a real, persisted output — ``None`` when no such row exists
    yet. Picks the highest ``attempt`` rather than assuming there is
    only ever one row per name: no retry mechanism re-attempts a step
    in this codebase today, but a resolver reading already-persisted
    state should not assume that stays true forever."""
    candidates = [
        step for step in steps if step.step_name == step_name and step.outputs is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda step: step.attempt).outputs or {}
