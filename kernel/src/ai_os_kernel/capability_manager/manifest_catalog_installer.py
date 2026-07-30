"""Derives real ``catalog.agents``/``catalog.prompts``/``catalog.tools``
row values from an already-validated pack manifest — the "no automated
manifest -> catalog installer exists yet" gap several integration
tests' own docstrings named explicitly (e.g.
``tests/integration/workflow_engine/test_architecture_agent_pack.py``'s
own ``_seed_agent_row``: "No automated manifest -> catalog.agents
installer exists yet (a real, documented gap...) — this mirrors
tests/integration/workflow_engine/test_registry.py's own direct
seeding... exactly").

**Pure derivation only — no database access at all.** Every function
here takes an already-parsed ``manifest: dict`` (the same shape
:class:`~ai_os_kernel.manifest_loader.ManifestLoader` already validates
and :meth:`~ai_os_kernel.capability_manager.repository.SqlPackLifecycleRepository.register`
already accepts) and returns plain row dicts, ready for
``sa.insert(table), rows`` — never a connection, a transaction, or an
``INSERT`` statement itself. :meth:`SqlPackLifecycleRepository.register`
is the one real caller that turns these into actual writes, inside its
own existing transaction, so a derivation failure (an unresolvable
``inputSchema`` import path, an unreadable prompt file) never leaves a
partially-registered pack behind — see that method's own docstring for
the "derive everything before opening the transaction" ordering this
enables.

**``inputSchema``/``outputSchema`` are Python import paths
(``module.path:ClassName``), not inline JSON Schema** — the manifest
schema's own field descriptions say so explicitly
(``platform_sdk/schemas/manifest.schema.json``: "Import path to the
Pydantic input model"), and the one real pack's own manifest.yaml
confirms it in practice for every agent and prompt. Resolving them to
real classes and calling ``model_json_schema()`` is the same "resolve
model, get real JSON schema" logic
:mod:`ai_os_sdk.testing.pack_contract_suite` already established for
check 3 (I/O-model matching) — reimplemented here, not imported, since
that module lives in ``ai_os_sdk`` and this one is real Kernel-only
composition with no reason to add an SDK dependency for three lines of
``importlib``.

**Every agent's own ``version``/``permissions``/``requiredTools`` are
read from *that agent's own* manifest entry, never assumed equal to the
pack's own top-level version or to another agent's declared
permissions.** A real, discovered bug in the hand-seeded test fixtures
this module replaces: several of them used the *pack's* version for
every agent's own ``version`` column (numerically identical for this
one pack today, coincidentally, since every agent happens to be versioned
``0.1.0`` same as the pack — not a rule this installer should
perpetuate), and one (``tests/integration/workflow_engine/test_delivery_pipeline.py``'s
own ``_seed_agent_rows``) granted `sandbox:execute` to
`requirements-analyst`/`architecture` uniformly with `build`/`documentation`,
even though neither of the first two actually declares that permission
in the real manifest — over-permissive, silently harmless only because
neither agent ever actually tries to use a tool. This installer derives
each agent's own real, exact permission set instead.

**Tools are derived correctly but currently unexercised by the one real
pack** — ``capability_packs/software-engineering/manifest.yaml``
declares zero ``tools[]`` entries (confirmed by direct inspection), so
:func:`derive_tool_rows` has no real data to prove itself against today.
Built to the identical, documented shape as agents/prompts rather than
left unbuilt, for the same reason
:mod:`ai_os_sdk.testing.pack_contract_suite`'s own check 5 (trust-tier
consistency) already builds real tool-trust-tier validation logic ahead
of any manifest actually declaring one — recorded here explicitly so
this gap is never mistaken for an oversight.
"""

from __future__ import annotations

import hashlib
import importlib
import inspect
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ai_os_kernel.capability_manager.errors import PackRegistrationError


def _resolve_dotted_path(dotted: str) -> Any:
    """Resolves a manifest ``module.path:AttributeName`` reference —
    the documented shape ``platform_sdk/schemas/manifest.schema.json``'s
    own ``entrypoint`` pattern already establishes, reused here for
    ``inputSchema``/``outputSchema`` references too. Raises
    :class:`PackRegistrationError` with a clear message rather than
    letting a raw ``ImportError``/``AttributeError`` propagate — the
    same "one clear error for every failure mode" discipline
    :class:`~ai_os_kernel.workflow_engine.entrypoint_loader.EntrypointLoader`
    already established for ``entrypoint`` resolution specifically."""
    module_name, _, attribute_name = dotted.partition(":")
    try:
        module = importlib.import_module(module_name)
        return getattr(module, attribute_name)
    except (ImportError, AttributeError) as exc:
        raise PackRegistrationError(f"cannot resolve manifest reference {dotted!r}: {exc}") from exc


def _resolve_model_json_schema(dotted: str) -> dict[str, Any]:
    resolved = _resolve_dotted_path(dotted)
    if not (inspect.isclass(resolved) and issubclass(resolved, BaseModel)):
        raise PackRegistrationError(
            f"manifest reference {dotted!r} does not resolve to a pydantic BaseModel subclass"
        )
    return resolved.model_json_schema()


def derive_agent_rows(manifest: dict[str, Any], *, pack_id: str) -> list[dict[str, Any]]:
    """One row per ``manifest["agents"]`` entry, matching
    ``catalog.agents``'s own real columns
    (:data:`~ai_os_kernel.persistence.catalog_schema.agents`) exactly."""
    return [
        {
            "agent_id": f"{pack_id}/{agent['id']}",
            "pack_id": pack_id,
            "version": agent["version"],
            "entrypoint": agent["entrypoint"],
            "input_schema": _resolve_model_json_schema(agent["inputSchema"]),
            "output_schema": _resolve_model_json_schema(agent["outputSchema"]),
            "required_permissions": agent.get("permissions", []),
            "required_tools": agent.get("requiredTools", []),
        }
        for agent in manifest.get("agents", [])
    ]


def derive_prompt_rows(
    manifest: dict[str, Any], *, pack_id: str, pack_root: Path
) -> list[dict[str, Any]]:
    """One row per ``manifest["prompts"]`` entry, matching
    ``catalog.prompts``'s own real columns
    (:data:`~ai_os_kernel.persistence.catalog_schema.prompts`) exactly.
    ``content`` is the prompt's own real, on-disk file content (read
    from ``pack_root / location``) — never a placeholder; ``content_hash``
    is a real ``sha256`` of that same content, computed here rather than
    left as the ``'sha256:abc'`` placeholder every hand-seeded test
    fixture this module replaces used, since ``catalog_schema.py``'s own
    documented purpose for this column is "so what was actually run can
    be verified later," which a fake hash cannot do."""
    rows: list[dict[str, Any]] = []
    for prompt in manifest.get("prompts", []):
        location = pack_root / prompt["location"]
        try:
            content = location.read_text(encoding="utf-8")
        except OSError as exc:
            raise PackRegistrationError(
                f"prompt {prompt['id']!r}: cannot read declared location "
                f"{prompt['location']!r} under {pack_root}: {exc}"
            ) from exc
        content_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
        rows.append(
            {
                "prompt_id": prompt["id"],
                "version": prompt["version"],
                "pack_id": pack_id,
                "content": content,
                "input_schema": _resolve_model_json_schema(prompt["inputSchema"]),
                "content_hash": content_hash,
            }
        )
    return rows


def derive_tool_rows(manifest: dict[str, Any], *, pack_id: str) -> list[dict[str, Any]]:
    """One row per ``manifest["tools"]`` entry, matching
    ``catalog.tools``'s own real columns
    (:data:`~ai_os_kernel.persistence.catalog_schema.tools`) exactly.
    See this module's own docstring: the one real pack declares no
    tools, so this is real, correct, currently-unexercised logic, not
    an oversight."""
    return [
        {
            "tool_id": tool["id"],
            "pack_id": pack_id,
            "version": tool["version"],
            "entrypoint": tool["entrypoint"],
            "trust_tier": tool["trustTier"],
            "input_schema": _resolve_model_json_schema(tool["inputSchema"]),
            "output_schema": _resolve_model_json_schema(tool["outputSchema"]),
            "required_permissions": tool.get("permissions", []),
        }
        for tool in manifest.get("tools", [])
    ]
