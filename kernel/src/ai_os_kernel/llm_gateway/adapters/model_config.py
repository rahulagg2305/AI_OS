"""Loads the small, static ``model_alias -> real model id`` mapping and
per-model pricing that :class:`~ai_os_kernel.llm_gateway.router.StaticRouter`
(the resolution) and :class:`~ai_os_kernel.llm_gateway.adapters.
anthropic_adapter.AnthropicAdapter` (the pricing) need to honour
ADR-0002 ("never a literal model id") and to compute an honest
``cost_usd`` for a real call, without hardcoding either in source
(Coding Standards' Configuration Standards: "Model names ... shall
always come from configuration").

**No alias chains, no per-alias fallback, no provider health, no
experiment pinning — one alias resolves to exactly one model id,
always.** A real :class:`~ai_os_kernel.llm_gateway.router.Router`
Protocol now exists and is the thing that actually resolves an alias
(:class:`StaticRouter`, built from the ``model_ids``/``providers`` this
function returns); this loader itself remains unchanged in shape — it
was never the Router, only the Router's one real implementation's
configuration source, and still is. Building the Retry & Fallback
Manager that would walk a real chain is a distinct, later Gateway
subsystem, still out of scope ("no routing mesh").

**``providers`` is additive, not a redesign of the ``aliases:`` shape.**
An alias absent from ``providers:`` is unspecified here — the
composition root (``kernel/bootstrap.py``), not this loader, decides
what an unspecified alias defaults to (today: Anthropic, the only
provider that existed before this step), the identical "this loader
reads configuration, the composition root decides" split its own
earlier docstring already drew for the Router itself. This keeps every
existing ``config/llm.yaml`` entry, and every existing test asserting
``model_ids``, valid unchanged — the second real provider is reached by
adding a new alias with a ``providers:`` entry, not by changing the
shape of an existing one.

**``fallbacks`` is the config-side half of the Router's real fallback
chain** (:func:`~ai_os_kernel.llm_gateway.router.build_routing_chain`,
:class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`'s
chain-walking). An alias absent from ``fallbacks:`` gets exactly the
single-candidate :class:`~ai_os_kernel.llm_gateway.router.RoutingDecision`
it always got — no ``fallback`` field set, identical behaviour to
before this existed. Each entry names one additional ``{provider,
model}`` candidate, in order — the same key names llm_gateway.md §7's
own documented ``chain:`` shape uses (minus ``effort``, not part of
this reduced ``LLMRequest`` contract).

**``local_provider.base_url`` is the one new, distinct piece of
configuration a second, non-Anthropic adapter needs that pricing/alias
mappings do not already cover** — a network location, not a credential
(:mod:`~ai_os_kernel.llm_gateway.adapters.local_adapter` takes no
:mod:`~ai_os_kernel.secrets_manager` reference at all, see that
module's own docstring for why). Its absence is not an error: a
deployment that configures no local server simply has no ``"local"``
entry to register in :class:`~ai_os_kernel.llm_gateway.gateway.DispatchingLLMGateway`'s
``gateways`` mapping — any alias still naming ``provider: local`` then
fails clearly, and only when actually called, the identical "an
unregistered provider is a real configuration error, not a silent
fallback" rule that class already documents.

Deliberately **not** :class:`~ai_os_kernel.configuration_manager.loader.
ConfigurationManager`: that class resolves ``PlatformConfig``'s own
fixed schema (``docs/03_architecture/kernel/configuration_manager.md``
§4's ``kernel:`` section) — extending it to also carry LLM alias/pricing
data is a design decision belonging to the full Router/Policy & Budget
Enforcer work, not this one adapter. This loader reads a small,
dedicated file instead, mirroring
:meth:`~ai_os_kernel.configuration_manager.loader.ConfigurationManager._read_section`'s
own "missing file is not automatically an error, malformed YAML is"
shape closely enough to stay consistent without reusing that class's
larger, differently-scoped schema.

**``capabilities`` follows the identical ``model id -> real fact``
shape ``pricing`` already established**, for the Capability
Negotiator's own step (:mod:`~ai_os_kernel.llm_gateway.
capability_negotiator`). Keyed by model id, not alias — a capability is
a fact about the model an alias currently resolves to, the same
reasoning ``pricing`` already uses. A model id absent from this section
is not defaulted to anything: :class:`~ai_os_kernel.llm_gateway.
capability_negotiator.StaticCapabilityNegotiator` raises clearly
(``llm.no_capabilities``) rather than fabricating a matrix, the
identical "no pricing" shape :class:`~ai_os_kernel.llm_gateway.adapters.
anthropic_adapter.AnthropicAdapter` already uses for an unpriced model.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from ai_os_kernel.llm_gateway.capability_negotiator import ProviderCapabilities
from ai_os_kernel.llm_gateway.errors import LLMProviderError


class ModelPricing(BaseModel):
    """Per-million-token USD pricing for one real provider model id —
    the same ``$/1M tokens`` shape every model's own published pricing
    uses. Used only to compute ``UsageRecord.cost_usd`` honestly; no
    budget enforcement reads this (that is the separate, deferred
    Policy & Budget Enforcer)."""

    model_config = ConfigDict(frozen=True)

    input_per_million_usd: Decimal
    output_per_million_usd: Decimal


class FallbackCandidate(BaseModel):
    """One additional ``(provider, model_id)`` candidate in an alias's
    real fallback chain — llm_gateway.md §7's own documented chain-entry
    shape (``{provider, model}``), minus ``effort`` (not part of this
    reduced ``LLMRequest`` contract)."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model_id: str


class LLMProviderConfig(BaseModel):
    """The mappings the real provider adapters, :class:`StaticRouter`,
    and :class:`~ai_os_kernel.llm_gateway.capability_negotiator.
    StaticCapabilityNegotiator` need: ``model_ids`` (alias -> real model
    id), ``providers`` (alias -> provider name, only for aliases that
    need something other than the composition root's default),
    ``fallbacks`` (alias -> ordered list of additional
    ``FallbackCandidate`` entries, only for aliases that configure a
    real chain), ``pricing`` (real model id -> :class:`ModelPricing`),
    ``capabilities`` (real model id -> ``ProviderCapabilities``, only
    for model ids a caller has actually configured — see this module's
    own docstring for why an absent id is not defaulted to anything),
    and ``local_base_url`` (the local server's OpenAI-compatible root
    URL, or ``None`` if none is configured).
    """

    model_config = ConfigDict(frozen=True)

    model_ids: dict[str, str]
    providers: dict[str, str]
    fallbacks: dict[str, list[FallbackCandidate]]
    pricing: dict[str, ModelPricing]
    capabilities: dict[str, ProviderCapabilities]
    local_base_url: str | None = None


def load_provider_config(path: Path) -> LLMProviderConfig:
    """Read ``aliases:``/``providers:``/``fallbacks:``/``pricing:``/
    ``local_provider:`` from ``path`` (mirroring llm_gateway.md §7's
    documented ``config/llm.yaml`` shape). Raises
    :class:`LLMProviderError` for a missing file, invalid YAML, or a
    malformed entry; a missing file is not silently treated as "no
    configuration" the way
    :class:`~ai_os_kernel.configuration_manager.loader.ConfigurationManager`
    treats an absent layer file, since there is no lower layer or
    built-in default an LLM provider adapter could fall back to.
    """

    if not path.exists():
        raise LLMProviderError(f"{path}: no such file")

    try:
        with path.open("r", encoding="utf-8") as fh:
            document = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise LLMProviderError(f"{path}: not valid YAML: {exc}") from exc

    if not isinstance(document, dict):
        raise LLMProviderError(f"{path}: must contain a YAML mapping at the top level")

    aliases = document.get("aliases", {})
    if not isinstance(aliases, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in aliases.items()
    ):
        raise LLMProviderError(f"{path}: 'aliases' must be a mapping of alias -> model id string")

    providers = document.get("providers", {})
    if not isinstance(providers, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in providers.items()
    ):
        raise LLMProviderError(
            f"{path}: 'providers' must be a mapping of alias -> provider name string"
        )

    fallbacks = _parse_fallbacks_section(path, document.get("fallbacks", {}))

    pricing_section = document.get("pricing", {})
    if not isinstance(pricing_section, dict):
        raise LLMProviderError(f"{path}: 'pricing' must be a mapping of model id -> pricing")

    pricing: dict[str, ModelPricing] = {}
    for model_id, entry in pricing_section.items():
        if not isinstance(model_id, str) or not isinstance(entry, dict):
            raise LLMProviderError(f"{path}: 'pricing' entries must be keyed by model id string")
        pricing[model_id] = _parse_pricing_entry(path, model_id, entry)

    capabilities_section = document.get("capabilities", {})
    if not isinstance(capabilities_section, dict):
        raise LLMProviderError(
            f"{path}: 'capabilities' must be a mapping of model id -> capability matrix"
        )

    capabilities: dict[str, ProviderCapabilities] = {}
    for model_id, entry in capabilities_section.items():
        if not isinstance(model_id, str) or not isinstance(entry, dict):
            raise LLMProviderError(
                f"{path}: 'capabilities' entries must be keyed by model id string"
            )
        capabilities[model_id] = _parse_capabilities_entry(path, model_id, entry)

    local_base_url = _parse_local_provider_section(path, document.get("local_provider"))

    return LLMProviderConfig(
        model_ids=aliases,
        providers=providers,
        fallbacks=fallbacks,
        pricing=pricing,
        capabilities=capabilities,
        local_base_url=local_base_url,
    )


def _parse_fallbacks_section(path: Path, section: Any) -> dict[str, list[FallbackCandidate]]:
    if not isinstance(section, dict):
        raise LLMProviderError(
            f"{path}: 'fallbacks' must be a mapping of alias -> list of {{provider, model}}"
        )

    fallbacks: dict[str, list[FallbackCandidate]] = {}
    for alias, entries in section.items():
        if not isinstance(alias, str) or not isinstance(entries, list):
            raise LLMProviderError(
                f"{path}: 'fallbacks.{alias}' must be a list of {{provider, model}} mappings"
            )
        candidates: list[FallbackCandidate] = []
        for entry in entries:
            provider = entry.get("provider") if isinstance(entry, dict) else None
            model_id = entry.get("model") if isinstance(entry, dict) else None
            if not isinstance(provider, str) or not isinstance(model_id, str):
                raise LLMProviderError(
                    f"{path}: each 'fallbacks.{alias}' entry must declare a string "
                    "'provider' and 'model'"
                )
            candidates.append(FallbackCandidate(provider=provider, model_id=model_id))
        fallbacks[alias] = candidates
    return fallbacks


def _parse_local_provider_section(path: Path, section: Any) -> str | None:
    if section is None:
        return None
    base_url = section.get("base_url") if isinstance(section, dict) else None
    if not isinstance(base_url, str):
        raise LLMProviderError(
            f"{path}: 'local_provider' must be a mapping with a string 'base_url'"
        )
    return base_url


def _parse_pricing_entry(path: Path, model_id: str, entry: dict[str, Any]) -> ModelPricing:
    try:
        return ModelPricing(
            input_per_million_usd=Decimal(str(entry["input_per_million_usd"])),
            output_per_million_usd=Decimal(str(entry["output_per_million_usd"])),
        )
    except (KeyError, InvalidOperation) as exc:
        raise LLMProviderError(
            f"{path}: 'pricing.{model_id}' must declare numeric "
            "'input_per_million_usd' and 'output_per_million_usd'"
        ) from exc


def _parse_capabilities_entry(
    path: Path, model_id: str, entry: dict[str, Any]
) -> ProviderCapabilities:
    try:
        return ProviderCapabilities(**entry)
    except (TypeError, ValidationError) as exc:
        raise LLMProviderError(
            f"{path}: 'capabilities.{model_id}' does not declare a complete, valid "
            f"ProviderCapabilities matrix: {exc}"
        ) from exc
