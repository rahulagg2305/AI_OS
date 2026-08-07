"""Prompt adaptation recording (`P04-S03-M34-T04`, FR-077) —
`overview.md` §7's own real, decided fairness rule: "Prompts are held
byte-identical across models by default; a required per-model
adaptation is recorded as a declared variable and reported."

**Pure string comparison — no rendering, no Kernel dependency.** This
ticket's own literal Input, "an adapted prompt," is already a rendered
string (produced by the real `InMemoryPromptEngine`,
`P02-S03-M07-T01`, elsewhere — rendering is that component's own job,
not this one's). Detecting whether two already-rendered prompt strings
genuinely differ needs nothing this pack cannot already do.

**Why this matters, concretely**: §7 also states "Variation must be
deliberate and recorded. Anything varying that was not declared as a
variable invalidates the experiment." A per-model prompt adaptation
that silently varies content without being recorded as a declared
`ExperimentSpec.variables` entry is exactly the undisclosed variation
that rule forbids — this module is the real mechanism that closes that
gap, by folding a genuine adaptation into the same `variables` dict
`validate_experiment_spec` (`experiment_definition.py`) already
inspects for other declared variables.
"""

from __future__ import annotations

from ai_os_pack_benchmarking.experiment_definition import ExperimentSpec

_PROMPT_ADAPTATION_VARIABLE_PREFIX = "prompt_adaptation"


def record_prompt_adaptation(
    *, variant_key: str, canonical_prompt: str, adapted_prompt: str
) -> tuple[str, dict[str, str]] | None:
    """Returns `(variable_name, variable_value)` if `adapted_prompt`
    genuinely differs from `canonical_prompt` — the real, declared
    variable §7 requires recording. Returns `None` when they are
    byte-identical (the default, unadapted case, per §7's own "by
    default" framing) — nothing to record."""
    if adapted_prompt == canonical_prompt:
        return None
    variable_name = f"{_PROMPT_ADAPTATION_VARIABLE_PREFIX}:{variant_key}"
    return variable_name, {"canonical_prompt": canonical_prompt, "adapted_prompt": adapted_prompt}


def with_recorded_prompt_adaptation(
    spec: ExperimentSpec, *, variant_key: str, canonical_prompt: str, adapted_prompt: str
) -> ExperimentSpec:
    """Returns a new `ExperimentSpec` with the real, declared
    prompt-adaptation variable folded into `variables` when
    `adapted_prompt` genuinely differs from `canonical_prompt` —
    otherwise returns `spec` unchanged (a byte-identical prompt is
    already fair by default, nothing to declare)."""
    recorded = record_prompt_adaptation(
        variant_key=variant_key, canonical_prompt=canonical_prompt, adapted_prompt=adapted_prompt
    )
    if recorded is None:
        return spec
    variable_name, variable_value = recorded
    return spec.model_copy(update={"variables": {**spec.variables, variable_name: variable_value}})
