"""Unit tests for ``load_provider_config`` — no database, no network,
pure local YAML parsing (ADR-0015 does not apply), mirroring
``tests/unit/kernel/configuration_manager/test_loader.py``'s own
real-temp-file pattern rather than mocking the filesystem.
"""

from pathlib import Path

import pytest
import yaml

from ai_os_kernel.llm_gateway.adapters.model_config import FallbackCandidate, load_provider_config
from ai_os_kernel.llm_gateway.capability_negotiator import ProviderCapabilities
from ai_os_kernel.llm_gateway.errors import LLMProviderError


def _write_yaml(path: Path, content: object) -> None:
    path.write_text(yaml.safe_dump(content), encoding="utf-8")


def _capabilities_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "supports_tools": True,
        "supports_parallel_tool_calls": True,
        "supports_strict_tools": False,
        "supports_structured_output": False,
        "supports_streaming": True,
        "supports_thinking": True,
        "supports_effort": True,
        "supports_prompt_caching": True,
        "prompt_cache_min_tokens": 1024,
        "supports_vision": True,
        "max_input_tokens": 1000000,
        "max_output_tokens": 8192,
        "accepts_sampling_params": False,
    }
    entry.update(overrides)
    return entry


def test_load_provider_config_reads_aliases_and_pricing(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(
        path,
        {
            "aliases": {"coding-balanced": "claude-sonnet-5"},
            "pricing": {
                "claude-sonnet-5": {
                    "input_per_million_usd": "3.00",
                    "output_per_million_usd": "15.00",
                }
            },
        },
    )

    config = load_provider_config(path)

    assert config.model_ids == {"coding-balanced": "claude-sonnet-5"}
    pricing = config.pricing["claude-sonnet-5"]
    assert pricing.input_per_million_usd == 3
    assert pricing.output_per_million_usd == 15


def test_load_provider_config_raises_for_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LLMProviderError, match="no such file"):
        load_provider_config(tmp_path / "does-not-exist.yaml")


def test_load_provider_config_raises_for_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    path.write_text("aliases: [this is not a mapping", encoding="utf-8")

    with pytest.raises(LLMProviderError, match="not valid YAML"):
        load_provider_config(path)


def test_load_provider_config_raises_when_top_level_is_not_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, ["not", "a", "mapping"])

    with pytest.raises(LLMProviderError, match="must contain a YAML mapping"):
        load_provider_config(path)


def test_load_provider_config_raises_when_aliases_is_not_a_string_mapping(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"aliases": {"coding-balanced": 5}})

    with pytest.raises(LLMProviderError, match="'aliases' must be a mapping"):
        load_provider_config(path)


def test_load_provider_config_raises_when_pricing_section_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"pricing": "not a mapping"})

    with pytest.raises(LLMProviderError, match="'pricing' must be a mapping"):
        load_provider_config(path)


def test_load_provider_config_raises_when_a_pricing_entry_is_not_keyed_by_a_string(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"pricing": {"claude-sonnet-5": "not a mapping"}})

    with pytest.raises(LLMProviderError, match="'pricing' entries must be keyed"):
        load_provider_config(path)


def test_load_provider_config_raises_when_a_pricing_entry_is_missing_a_field(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(
        path,
        {
            "aliases": {},
            "pricing": {"claude-sonnet-5": {"input_per_million_usd": "3.00"}},
        },
    )

    with pytest.raises(LLMProviderError, match="pricing.claude-sonnet-5"):
        load_provider_config(path)


def test_load_provider_config_defaults_to_empty_mappings_when_sections_are_absent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {})

    config = load_provider_config(path)

    assert config.model_ids == {}
    assert config.pricing == {}
    assert config.providers == {}
    assert config.fallbacks == {}
    assert config.capabilities == {}
    assert config.local_base_url is None


def test_load_provider_config_reads_an_alias_provider_override(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(
        path,
        {
            "aliases": {"local-fast": "llama3.1:8b"},
            "providers": {"local-fast": "local"},
            "pricing": {
                "llama3.1:8b": {"input_per_million_usd": "0.00", "output_per_million_usd": "0.00"}
            },
        },
    )

    config = load_provider_config(path)

    assert config.providers == {"local-fast": "local"}


def test_load_provider_config_raises_when_providers_is_not_a_string_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"providers": {"local-fast": 5}})

    with pytest.raises(LLMProviderError, match="'providers' must be a mapping"):
        load_provider_config(path)


def test_load_provider_config_reads_the_local_provider_base_url(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"local_provider": {"base_url": "http://127.0.0.1:11434/v1"}})

    config = load_provider_config(path)

    assert config.local_base_url == "http://127.0.0.1:11434/v1"


def test_load_provider_config_raises_when_local_provider_has_no_base_url(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"local_provider": {}})

    with pytest.raises(LLMProviderError, match="'local_provider' must be a mapping"):
        load_provider_config(path)


def test_load_provider_config_raises_when_local_provider_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"local_provider": "not a mapping"})

    with pytest.raises(LLMProviderError, match="'local_provider' must be a mapping"):
        load_provider_config(path)


def test_load_provider_config_reads_a_fallback_chain(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(
        path,
        {
            "fallbacks": {
                "coding-strong": [
                    {"provider": "anthropic", "model": "claude-sonnet-5"},
                    {"provider": "local", "model": "llama3.1:8b"},
                ]
            }
        },
    )

    config = load_provider_config(path)

    assert config.fallbacks == {
        "coding-strong": [
            FallbackCandidate(provider="anthropic", model_id="claude-sonnet-5"),
            FallbackCandidate(provider="local", model_id="llama3.1:8b"),
        ]
    }


def test_load_provider_config_raises_when_fallbacks_is_not_a_mapping(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"fallbacks": "not a mapping"})

    with pytest.raises(LLMProviderError, match="'fallbacks' must be a mapping"):
        load_provider_config(path)


def test_load_provider_config_raises_when_a_fallback_alias_entry_is_not_a_list(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"fallbacks": {"coding-strong": "not a list"}})

    with pytest.raises(LLMProviderError, match="must be a list"):
        load_provider_config(path)


@pytest.mark.parametrize(
    "entry",
    [
        {"provider": "anthropic"},
        {"model": "claude-sonnet-5"},
        {"provider": 5, "model": "claude-sonnet-5"},
        "not a mapping",
    ],
)
def test_load_provider_config_raises_for_a_malformed_fallback_entry(
    tmp_path: Path, entry: object
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"fallbacks": {"coding-strong": [entry]}})

    with pytest.raises(LLMProviderError, match="must declare a string"):
        load_provider_config(path)


def test_load_provider_config_reads_a_real_capabilities_entry(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"capabilities": {"claude-sonnet-5": _capabilities_entry()}})

    config = load_provider_config(path)

    capabilities = config.capabilities["claude-sonnet-5"]
    assert capabilities == ProviderCapabilities(**_capabilities_entry())


def test_load_provider_config_reads_a_capabilities_entry_with_no_prompt_caching(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    entry = _capabilities_entry(supports_prompt_caching=False, prompt_cache_min_tokens=None)
    _write_yaml(path, {"capabilities": {"llama3.1:8b": entry}})

    config = load_provider_config(path)

    assert config.capabilities["llama3.1:8b"].supports_prompt_caching is False
    assert config.capabilities["llama3.1:8b"].prompt_cache_min_tokens is None


def test_load_provider_config_raises_when_capabilities_section_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"capabilities": "not a mapping"})

    with pytest.raises(LLMProviderError, match="'capabilities' must be a mapping"):
        load_provider_config(path)


def test_load_provider_config_raises_when_a_capabilities_entry_is_not_a_mapping(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    _write_yaml(path, {"capabilities": {"claude-sonnet-5": "not a mapping"}})

    with pytest.raises(LLMProviderError, match="'capabilities' entries must be keyed"):
        load_provider_config(path)


def test_load_provider_config_raises_when_a_capabilities_entry_is_missing_a_field(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    entry = _capabilities_entry()
    del entry["supports_vision"]
    _write_yaml(path, {"capabilities": {"claude-sonnet-5": entry}})

    with pytest.raises(LLMProviderError, match="capabilities.claude-sonnet-5"):
        load_provider_config(path)


def test_load_provider_config_raises_when_prompt_cache_min_tokens_contradicts_support(
    tmp_path: Path,
) -> None:
    path = tmp_path / "llm.yaml"
    entry = _capabilities_entry(supports_prompt_caching=False, prompt_cache_min_tokens=1024)
    _write_yaml(path, {"capabilities": {"claude-sonnet-5": entry}})

    with pytest.raises(LLMProviderError, match="capabilities.claude-sonnet-5"):
        load_provider_config(path)


def test_load_provider_config_raises_when_a_token_ceiling_is_not_positive(tmp_path: Path) -> None:
    path = tmp_path / "llm.yaml"
    entry = _capabilities_entry(max_output_tokens=0)
    _write_yaml(path, {"capabilities": {"claude-sonnet-5": entry}})

    with pytest.raises(LLMProviderError, match="capabilities.claude-sonnet-5"):
        load_provider_config(path)
