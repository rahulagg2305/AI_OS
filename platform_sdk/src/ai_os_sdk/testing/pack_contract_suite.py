"""``pack_contract_suite`` checks 1-6, 8, 9 — the remaining checks
named by ``platform_sdk.md`` §9's own numbered list, built against a
real, fully-migrated pack for the first time (``platform_sdk_v1_scope.md``
step 15). Check 7 (forbidden imports) shipped alone at step 8 — see
:mod:`ai_os_sdk.testing.forbidden_imports`'s own docstring — and is
wrapped into this module's :func:`run_pack_contract_suite` unchanged,
not reimplemented.

**A discovered arithmetic correction, made explicit here rather than
silently absorbed.** Every doc written across steps 12-14 (this
package's own ``__init__`` docstring included) called this "the
remaining 8 checks." Re-reading ``platform_sdk.md`` §9's own numbered
list directly (the primary source, not any doc this project's own prior
steps wrote) shows checks 2-9 are eight items *total*, one of which
(check 7) was already built at step 8. The genuinely remaining count at
the start of this step was therefore **seven** (2, 3, 4, 5, 6, 8, 9),
not eight. Check 1 (manifest validity) was never in the "remaining"
bucket at all — ``platform_sdk.md`` line 668 names it as already,
separately, genuinely enforced by ``ai_os_kernel.manifest_loader``. It
is still built here as :func:`check_1_manifest_is_valid`, because this
step's own task explicitly asks for a *unified* 9-check suite runnable
against a pack in one call — not because it was outstanding.

**Why check 1 is reimplemented here rather than calling the Kernel's
real ``ManifestLoader``.** ``platform_sdk.md`` §2 rule 1 makes this SDK
package the dependency floor: it may import nothing from
``ai_os_kernel``. This module's :func:`check_1_manifest_is_valid`
therefore validates the same schema with the same library
(``jsonschema.Draft202012Validator``) directly, taking ``schema_path``
as an explicit caller-supplied argument — mirroring
:func:`~ai_os_sdk.testing.forbidden_imports.scan_pack_source`'s and
:func:`~ai_os_sdk.testing.waiver.load_waiver`'s own established "the
caller supplies real paths, this package never guesses a location"
precedent. ``platform_sdk/schemas/manifest.schema.json`` is a sibling
of ``src/ai_os_sdk``, not packaged into the wheel
(``platform_sdk/pyproject.toml``'s own
``[tool.hatch.build.targets.wheel] packages = ["src/ai_os_sdk"]``), so
there is no installed location this function could assume even if it
wanted to.

**Every check function takes real, already-loaded/parsed data (a
``manifest: dict`` already read from YAML, a ``pack_root: Path``) or an
explicit path — never a pack id string it resolves internally**, for
the same "no internal path-guessing" reason. :func:`run_pack_contract_suite`
is the one place that reads the manifest file and threads the parsed
result to every check that needs it, so a caller running one check in
isolation (as this module's own tests for checks 2-9 mostly do) is
never forced to also supply the raw YAML text redundantly.

**Check 9 is the only ``async`` check** — ``CapabilityPack.activate``/
``deactivate``/``health`` are async per their own Protocol
(``ai_os_sdk.contracts.capability_pack``), so proving them clean
genuinely requires awaiting them, not just resolving the class.
:func:`run_pack_contract_suite` is therefore itself ``async def``, and
every check to date is safe to call from inside a running event loop
(none of checks 1-8 spawns its own).
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from pydantic import BaseModel

from ai_os_sdk.contracts.agent import Agent
from ai_os_sdk.contracts.capability_pack import PackContext
from ai_os_sdk.contracts.tool_invoker import PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR
from ai_os_sdk.models.tool import TrustTier
from ai_os_sdk.testing.forbidden_imports import scan_pack_source
from ai_os_sdk.testing.waiver import apply_waiver, load_waiver

_SDK_DISTRIBUTION_NAME = "ai-os-sdk"

_PERMISSION_VOCABULARY_PATH = ("properties", "permissions", "items", "enum")


@dataclass(frozen=True)
class PackContractCheckResult:
    """One check's real outcome — never a summary of several checks.
    ``details`` is always populated, even on a pass, so a report reads
    the same whether it is being used to prove success or diagnose a
    failure."""

    check_id: int
    name: str
    passed: bool
    details: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PackContractSuiteReport:
    """All 9 checks' real results, in check-id order."""

    results: tuple[PackContractCheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    raw: Any = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{manifest_path}: must contain a YAML mapping at the top level")
    return raw


class _ManifestUnreadable(Exception):
    """Raised internally when a manifest is not parseable YAML or not a
    mapping — caught by :func:`check_1_manifest_is_valid` and
    :func:`run_pack_contract_suite` so a malformed manifest is reported
    as a clean check failure, never an uncaught crash. Real, discovered
    gap: a first version of this module let `yaml.YAMLError`/`ValueError`
    from `_load_manifest` propagate straight out of `check_1_manifest_is_valid`
    (and out of the orchestrator, which also calls `_load_manifest`
    directly) — the one behavior every other check in this suite
    deliberately avoids (each reports its own failure in
    `PackContractCheckResult`, never raises for a bad *pack*, only for a
    genuinely unexpected bug). Found by
    `tests/unit/platform_sdk/test_manifest_check_agrees_with_kernel_loader.py`,
    which expected `check_1_manifest_is_valid` to return `passed=False`
    for a non-mapping/invalid-YAML document the same way
    `ManifestLoader.load_one` raises a clean `ManifestError` for it —
    instead it crashed with an unhandled exception."""


def _load_manifest_or_raise_unreadable(manifest_path: Path) -> dict[str, Any]:
    try:
        return _load_manifest(manifest_path)
    except yaml.YAMLError as exc:
        raise _ManifestUnreadable(f"{manifest_path}: not valid YAML: {exc}") from exc
    except ValueError as exc:
        raise _ManifestUnreadable(str(exc)) from exc


def _resolve_dotted_path(dotted: str) -> Any:
    """Resolves a manifest ``module.path:AttributeName`` reference to the
    real object it names, raising the natural ``ImportError``/
    ``AttributeError`` unchanged rather than swallowing it — a caller
    building a :class:`PackContractCheckResult` catches and records the
    exact exception text, so nothing here needs its own error type."""
    module_name, _, attribute_name = dotted.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attribute_name)


def check_1_manifest_is_valid(manifest_path: Path, schema_path: Path) -> PackContractCheckResult:
    """Manifest validity (checklist item 1) plus, since both are real,
    checkable facts about the same document: whether ``dependencies.
    sdkVersion``'s declared PEP 440 range is satisfied by the ``ai-os-sdk``
    distribution actually installed in this environment (checklist item
    3, "dependencies are satisfied") — the one part of that item this
    process can verify about itself, as opposed to ``dependencies.packs``
    emptiness and ``dependencies.python``, both already schema-shape
    checked and not this function's own added value.

    Reuses the exact validator (``jsonschema.Draft202012Validator``)
    ``ai_os_kernel.manifest_loader.ManifestLoader`` already runs in
    production against the identical schema file — this function is a
    second, independent proof over the same real artifact, not a new
    rule invented for this suite.

    **Fails closed on unparseable input, like every other check in this
    suite — never raises for a bad manifest.** Invalid YAML or a
    non-mapping top-level document is reported as ``passed=False``, the
    same real outcome ``ManifestLoader.load_one`` reaches by raising a
    caught ``ManifestError`` — a genuine, discovered gap this function
    used not to close (see :class:`_ManifestUnreadable`'s own docstring).
    """
    details: list[str] = []
    try:
        manifest = _load_manifest_or_raise_unreadable(manifest_path)
    except _ManifestUnreadable as exc:
        return PackContractCheckResult(1, "manifest is valid", False, (str(exc),))
    schema: dict[str, Any] = yaml.safe_load(schema_path.read_text(encoding="utf-8"))

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(manifest), key=lambda e: list(e.absolute_path))
    if errors:
        for error in errors:
            location = "/".join(str(part) for part in error.absolute_path) or "<root>"
            details.append(f"schema violation at '{location}': {error.message}")
        return PackContractCheckResult(1, "manifest is valid", False, tuple(details))
    details.append(f"{manifest_path}: valid against {schema_path}")

    declared_range = manifest.get("dependencies", {}).get("sdkVersion")
    if declared_range is not None:
        try:
            specifier = SpecifierSet(declared_range)
        except InvalidSpecifier as exc:
            return PackContractCheckResult(
                1, "manifest is valid", False, (*details, f"invalid sdkVersion range: {exc}")
            )
        try:
            real_version = installed_version(_SDK_DISTRIBUTION_NAME)
        except PackageNotFoundError:
            return PackContractCheckResult(
                1,
                "manifest is valid",
                False,
                (*details, f"{_SDK_DISTRIBUTION_NAME} is not installed in this environment"),
            )
        if real_version not in specifier:
            return PackContractCheckResult(
                1,
                "manifest is valid",
                False,
                (
                    *details,
                    f"installed {_SDK_DISTRIBUTION_NAME} {real_version} does not satisfy "
                    f"declared dependencies.sdkVersion range {declared_range!r}",
                ),
            )
        details.append(
            f"dependencies.sdkVersion {declared_range!r} satisfied by installed "
            f"{_SDK_DISTRIBUTION_NAME} {real_version}"
        )

    return PackContractCheckResult(1, "manifest is valid", True, tuple(details))


def check_2_entry_points_resolve(
    manifest: dict[str, Any], pack_root: Path
) -> PackContractCheckResult:
    """Every dotted ``module:Attribute`` reference the manifest names as
    something Python must import — the top-level ``entryPoint``, every
    ``agents[].entrypoint``/``tools[].entrypoint``/
    ``qualityGates[].entrypoint`` — genuinely resolves to a real object,
    and every ``workflows[].definition`` file genuinely exists on disk
    relative to the pack root. Real ``importlib.import_module`` calls
    against the real installed pack, not a static text check.

    **``tools[]``/``qualityGates[]`` added `P03-S04-M31-T03`.** A real,
    discovered gap: this docstring's own prose already claimed "every"
    entrypoint-bearing section, but the two sections added after
    ``agents[]`` first existed were never folded in — the Software
    Engineering pack declared zero of either until this same ticket, so
    the omission was never exercised. `qualityGates[].entrypoint` is
    schema-only today (no Gate Executor resolves or invokes it at
    runtime — `quality_gate_engine.md`'s own Implementation Status),
    but this check still verifies it is at least a genuinely resolvable
    class, the identical shallow guarantee already made for every other
    entrypoint here."""
    details: list[str] = []
    failed = False

    entry_point = manifest.get("entryPoint")
    if entry_point is not None:
        try:
            resolved = _resolve_dotted_path(entry_point)
        except (ImportError, AttributeError, ValueError) as exc:
            failed = True
            details.append(f"entryPoint {entry_point!r} does not resolve: {exc}")
        else:
            details.append(f"entryPoint {entry_point!r} resolves to {resolved!r}")

    for agent in manifest.get("agents", []):
        entrypoint = agent["entrypoint"]
        try:
            resolved = _resolve_dotted_path(entrypoint)
        except (ImportError, AttributeError, ValueError) as exc:
            failed = True
            details.append(
                f"agent {agent['id']!r} entrypoint {entrypoint!r} does not resolve: {exc}"
            )
            continue
        if not inspect.isclass(resolved):
            failed = True
            details.append(f"agent {agent['id']!r} entrypoint {entrypoint!r} is not a class")
            continue
        details.append(f"agent {agent['id']!r} entrypoint {entrypoint!r} resolves to a class")

    for tool in manifest.get("tools", []):
        entrypoint = tool["entrypoint"]
        try:
            resolved = _resolve_dotted_path(entrypoint)
        except (ImportError, AttributeError, ValueError) as exc:
            failed = True
            details.append(f"tool {tool['id']!r} entrypoint {entrypoint!r} does not resolve: {exc}")
            continue
        if not inspect.isclass(resolved):
            failed = True
            details.append(f"tool {tool['id']!r} entrypoint {entrypoint!r} is not a class")
            continue
        details.append(f"tool {tool['id']!r} entrypoint {entrypoint!r} resolves to a class")

    for gate in manifest.get("qualityGates", []):
        entrypoint = gate["entrypoint"]
        try:
            resolved = _resolve_dotted_path(entrypoint)
        except (ImportError, AttributeError, ValueError) as exc:
            failed = True
            details.append(f"gate {gate['id']!r} entrypoint {entrypoint!r} does not resolve: {exc}")
            continue
        if not inspect.isclass(resolved):
            failed = True
            details.append(f"gate {gate['id']!r} entrypoint {entrypoint!r} is not a class")
            continue
        details.append(f"gate {gate['id']!r} entrypoint {entrypoint!r} resolves to a class")

    for workflow in manifest.get("workflows", []):
        definition_path = pack_root / workflow["definition"]
        if not definition_path.is_file():
            failed = True
            details.append(
                f"workflow {workflow['id']!r} definition {workflow['definition']!r} "
                f"does not exist at {definition_path}"
            )
        else:
            details.append(
                f"workflow {workflow['id']!r} definition file exists at {definition_path}"
            )

    return PackContractCheckResult(2, "entry points resolve", not failed, tuple(details))


def check_3_io_models_match(manifest: dict[str, Any]) -> PackContractCheckResult:
    """Every ``inputSchema``/``outputSchema`` reference (agents and
    workflows alike) resolves to a real ``pydantic.BaseModel`` subclass,
    and — the genuinely dynamic half of this check — each agent's own
    constructed entrypoint reports an ``output_schema`` attribute whose
    field names (``properties`` keys) and ``required`` set match the
    manifest's own declared ``outputSchema`` model's
    ``model_json_schema()``. A mismatch here means the manifest is
    describing a contract the real code does not actually honour, which
    a purely static "does it import" check could never catch.

    **Compared by field names and required-set, not full schema
    equality — a real, discovered distinction, not an oversight.**
    Every real agent's ``output_schema`` attribute is a deliberately
    separate, hand-authored, strict JSON Schema (``additionalProperties:
    false``, no ``title``/``description`` noise) — the actual contract a
    caller validates a returned dict against — while ``model_json_schema()``
    is Pydantic's own generated schema, carrying metadata
    (``title``, field ``description``) the hand-authored version never
    had and was never meant to. Running this check with full-dict
    equality against the real pack proved that immediately (every one of
    the five real agents "failed" on cosmetic metadata alone, with
    identical field names and required sets) — asserting byte-for-byte
    equality would be testing an invariant this codebase never actually
    holds, not catching a real defect."""
    details: list[str] = []
    failed = False

    def _check_model_reference(owner: str, field_name: str, dotted: str) -> type[BaseModel] | None:
        nonlocal failed
        try:
            resolved = _resolve_dotted_path(dotted)
        except (ImportError, AttributeError, ValueError) as exc:
            failed = True
            details.append(f"{owner} {field_name} {dotted!r} does not resolve: {exc}")
            return None
        if not (inspect.isclass(resolved) and issubclass(resolved, BaseModel)):
            failed = True
            details.append(f"{owner} {field_name} {dotted!r} is not a pydantic BaseModel subclass")
            return None
        details.append(f"{owner} {field_name} {dotted!r} resolves to a real BaseModel subclass")
        return resolved

    for agent in manifest.get("agents", []):
        owner = f"agent {agent['id']!r}"
        _check_model_reference(owner, "inputSchema", agent["inputSchema"])
        output_model = _check_model_reference(owner, "outputSchema", agent["outputSchema"])
        if output_model is None:
            continue

        try:
            entrypoint_class = _resolve_dotted_path(agent["entrypoint"])
            instance = entrypoint_class()
        except Exception as exc:  # noqa: BLE001 - reported as a check failure, not raised
            failed = True
            details.append(f"{owner} could not be constructed to compare output_schema: {exc}")
            continue

        runtime_schema = getattr(instance, "output_schema", {})
        declared_schema = output_model.model_json_schema()
        runtime_fields = set(runtime_schema.get("properties", {}))
        declared_fields = set(declared_schema.get("properties", {}))
        runtime_required = set(runtime_schema.get("required", []))
        declared_required = set(declared_schema.get("required", []))
        if runtime_fields != declared_fields or runtime_required != declared_required:
            failed = True
            details.append(
                f"{owner} runtime output_schema fields {sorted(runtime_fields)}/required "
                f"{sorted(runtime_required)} do not match {agent['outputSchema']!r}'s own "
                f"model_json_schema() fields {sorted(declared_fields)}/required "
                f"{sorted(declared_required)}"
            )
        else:
            details.append(
                f"{owner} runtime output_schema fields and required set match its declared "
                f"outputSchema model"
            )

    for workflow in manifest.get("workflows", []):
        owner = f"workflow {workflow['id']!r}"
        _check_model_reference(owner, "inputsSchema", workflow["inputsSchema"])
        _check_model_reference(owner, "outputsSchema", workflow["outputsSchema"])

    return PackContractCheckResult(3, "I/O models match", not failed, tuple(details))


def check_4_workflow_steps_resolve(
    manifest: dict[str, Any], pack_root: Path
) -> PackContractCheckResult:
    """Every workflow's own definition file, loaded and parsed for real,
    references only agent ids and prompt ids the same manifest actually
    declares — catching a workflow step that names a typo'd or removed
    agent/prompt, which schema validation alone (each document validated
    in isolation) cannot see."""
    details: list[str] = []
    failed = False

    pack_id = manifest["metadata"]["id"]
    declared_agent_ids = {f"{pack_id}/{agent['id']}" for agent in manifest.get("agents", [])}
    declared_prompts = {(prompt["id"], prompt["version"]) for prompt in manifest.get("prompts", [])}

    for workflow in manifest.get("workflows", []):
        definition_path = pack_root / workflow["definition"]
        if not definition_path.is_file():
            failed = True
            details.append(
                f"workflow {workflow['id']!r}: definition file missing, cannot check steps"
            )
            continue

        definition: dict[str, Any] = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
        for step in definition.get("steps", []):
            step_id = step.get("id", "<unnamed>")
            agent_id = step.get("agentId")
            if agent_id is not None and agent_id not in declared_agent_ids:
                failed = True
                details.append(
                    f"workflow {workflow['id']!r} step {step_id!r}: agentId {agent_id!r} "
                    f"is not declared in this manifest's own agents[]"
                )
            elif agent_id is not None:
                details.append(
                    f"workflow {workflow['id']!r} step {step_id!r}: agentId {agent_id!r} resolves"
                )

            prompt_id = step.get("promptId")
            if prompt_id is not None:
                prompt_version = step.get("promptVersion")
                if (prompt_id, prompt_version) not in declared_prompts:
                    failed = True
                    details.append(
                        f"workflow {workflow['id']!r} step {step_id!r}: promptId "
                        f"{prompt_id!r}@{prompt_version!r} is not declared in this "
                        f"manifest's own prompts[]"
                    )
                else:
                    details.append(
                        f"workflow {workflow['id']!r} step {step_id!r}: promptId "
                        f"{prompt_id!r}@{prompt_version!r} resolves"
                    )

    if not manifest.get("workflows"):
        details.append("no workflows declared; nothing to check")

    return PackContractCheckResult(4, "workflow steps resolve", not failed, tuple(details))


def check_5_trust_tier_consistency(manifest: dict[str, Any]) -> PackContractCheckResult:
    """Every manifest-declared ``tools[].trustTier`` is one of the two
    real values (schema-enforced already, re-checked here so this suite
    does not silently depend on that enforcement staying in place), plus
    the one concrete trust-tier fact this pack's own ``sandbox:execute``
    permission actually depends on: the platform-provided
    :data:`~ai_os_sdk.contracts.tool_invoker.PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR`
    is genuinely ``TrustTier.TIER1_SANDBOXED`` (ADR-0016 requires this
    for any tool that executes a command). A pack declaring zero
    manifest-level tools still relies on this platform tool, so this
    check has real substance even when ``tools[]`` is empty."""
    details: list[str] = []
    failed = False

    for tool in manifest.get("tools", []):
        trust_tier = tool.get("trustTier")
        if trust_tier not in {"tier1_sandboxed", "tier2_trusted"}:
            failed = True
            details.append(f"tool {tool['id']!r}: trustTier {trust_tier!r} is not a real value")
        else:
            details.append(f"tool {tool['id']!r}: trustTier {trust_tier!r} is a real value")

    if not manifest.get("tools"):
        details.append("no manifest-level tools declared")

    uses_sandbox = any(
        "sandbox:execute" in agent.get("permissions", []) for agent in manifest.get("agents", [])
    )
    if uses_sandbox:
        if PLATFORM_SANDBOX_RUN_COMMAND_DESCRIPTOR.trust_tier is not TrustTier.TIER1_SANDBOXED:
            failed = True
            details.append(
                "platform.sandbox.run_command's own descriptor is not TIER1_SANDBOXED, "
                "violating ADR-0016 for every agent declaring sandbox:execute"
            )
        else:
            details.append(
                "platform.sandbox.run_command (the real tool this pack's sandbox:execute "
                "agents depend on) is genuinely TIER1_SANDBOXED"
            )

    return PackContractCheckResult(5, "trust tier consistency", not failed, tuple(details))


def check_6_permission_vocabulary(
    manifest: dict[str, Any], schema_path: Path
) -> PackContractCheckResult:
    """Every permission string appearing anywhere in the manifest — top
    level, every agent, every workflow — is drawn from the schema's own
    closed vocabulary. The vocabulary is read out of the schema file
    itself (the exact list at ``properties.permissions.items.enum``),
    never duplicated as a second hardcoded list, so this check can never
    silently drift out of sync with the real schema.

    This is real, added value beyond schema validation alone: the
    schema only enum-constrains the *top-level* ``permissions`` field
    (``manifest.schema.json`` lines 82-103); per-agent and per-workflow
    ``permissions`` are schema-typed as bare ``array of string`` with no
    enum at all (lines 154, 210-215) — a confirmed, real, currently
    unenforced gap this check closes.
    """
    details: list[str] = []
    failed = False

    schema: dict[str, Any] = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    vocabulary: Any = schema
    for key in _PERMISSION_VOCABULARY_PATH:
        vocabulary = vocabulary[key]
    if not isinstance(vocabulary, list):
        raise ValueError(f"{schema_path}: expected a list at {_PERMISSION_VOCABULARY_PATH}")
    vocabulary_set = set(vocabulary)
    details.append(f"closed vocabulary read from schema: {len(vocabulary_set)} permissions")

    def _check(owner: str, permissions: list[str]) -> None:
        nonlocal failed
        unknown = [p for p in permissions if p not in vocabulary_set]
        if unknown:
            failed = True
            details.append(
                f"{owner}: unknown permission(s) not in the closed vocabulary: {unknown}"
            )
        else:
            details.append(f"{owner}: every declared permission is in the closed vocabulary")

    _check("manifest top level", manifest.get("permissions", []))
    for agent in manifest.get("agents", []):
        _check(f"agent {agent['id']!r}", agent.get("permissions", []))
    for workflow in manifest.get("workflows", []):
        _check(f"workflow {workflow['id']!r}", workflow.get("permissions", []))

    return PackContractCheckResult(6, "permission vocabulary", not failed, tuple(details))


def check_7_no_forbidden_imports(
    pack_root: Path, *, own_pack_package: str, waiver_path: Path | None
) -> PackContractCheckResult:
    """Wraps the check 7 mechanism that has shipped since step 8
    (:func:`~ai_os_sdk.testing.forbidden_imports.scan_pack_source`,
    :func:`~ai_os_sdk.testing.waiver.load_waiver`/:func:`~ai_os_sdk.testing.waiver.apply_waiver`)
    into this suite's own uniform result shape — the scan/waiver logic
    itself is not reimplemented here."""
    src_root = pack_root / "src" / own_pack_package
    violations = scan_pack_source(src_root, own_pack_package=own_pack_package)
    waiver = load_waiver(waiver_path) if waiver_path is not None else None
    application = apply_waiver(violations, waiver)

    details = [
        f"{v.file}:{v.line} - {v.category.value} ({v.imported!r}) [WAIVED]"
        for v in application.waived
    ] + [f"{v.file}:{v.line} - {v.category.value} ({v.imported!r})" for v in application.unwaived]
    if not details:
        details.append("no forbidden imports found")

    return PackContractCheckResult(
        7, "no forbidden imports", not application.unwaived, tuple(details)
    )


def check_8_required_prompts_exist(
    manifest: dict[str, Any], pack_root: Path
) -> PackContractCheckResult:
    """Every agent's ``requiredPrompts`` entry (``"<id>@<version>"``)
    matches a real ``prompts[]`` declaration in the same manifest, whose
    own ``location`` file genuinely exists on disk and is non-empty —
    catching a prompt id typo, a version mismatch, or a declared-but-
    never-written prompt file, none of which schema validation alone can
    see (``location``/``inputSchema`` are just strings to the schema)."""
    details: list[str] = []
    failed = False

    prompts_by_key = {
        (prompt["id"], prompt["version"]): prompt for prompt in manifest.get("prompts", [])
    }

    for agent in manifest.get("agents", []):
        for required in agent.get("requiredPrompts", []):
            prompt_id, _, prompt_version = required.partition("@")
            key = (prompt_id, prompt_version)
            prompt = prompts_by_key.get(key)
            if prompt is None:
                failed = True
                details.append(
                    f"agent {agent['id']!r} requires prompt {required!r}, "
                    f"which is not declared in this manifest's own prompts[]"
                )
                continue

            location_path = pack_root / prompt["location"]
            if not location_path.is_file():
                failed = True
                details.append(
                    f"prompt {required!r}: location {prompt['location']!r} does not exist"
                )
            elif not location_path.read_text(encoding="utf-8").strip():
                failed = True
                details.append(f"prompt {required!r}: location {prompt['location']!r} is empty")
            else:
                details.append(
                    f"agent {agent['id']!r} requiredPrompt {required!r} resolves to a real, "
                    f"non-empty file"
                )

    if not details:
        details.append("no agent declares a requiredPrompts entry")

    return PackContractCheckResult(8, "required prompts exist", not failed, tuple(details))


async def check_9_clean_activation(
    manifest: dict[str, Any],
) -> PackContractCheckResult:
    """The only genuinely dynamic, end-to-end check: resolve the
    manifest's own top-level ``entryPoint``, construct it zero-arg,
    and run a real ``activate()`` -> inspect ``PackRegistration`` ->
    ``health()`` -> ``deactivate()`` cycle — proving the pack's actual
    entry point is a clean, working :class:`~ai_os_sdk.contracts.CapabilityPack`
    implementation, not merely that the class exists (check 2's job).

    Deliberately does **not** assert that every manifest-declared agent
    id appears in ``PackRegistration.agents`` — the real Software
    Engineering pack's own ``activate()`` registers only ``architecture``
    today (``pack.py``'s own docstring: nothing in this codebase calls
    ``activate()`` yet, so the other four agents are wired directly by
    the Workflow Engine's own entry-point loader instead). Asserting
    "all declared agents are registered" would fail this check against
    a real, correct, already-explained implementation — checking what
    is actually true, not what would be convenient to assert, per this
    project's own verification discipline.
    """
    details: list[str] = []
    entry_point = manifest.get("entryPoint")
    if entry_point is None:
        return PackContractCheckResult(9, "clean activation", False, ("no entryPoint declared",))

    try:
        pack_class = _resolve_dotted_path(entry_point)
        pack = pack_class()
    except Exception as exc:  # noqa: BLE001 - reported as a check failure, not raised
        return PackContractCheckResult(
            9,
            "clean activation",
            False,
            (f"entryPoint {entry_point!r} could not be constructed: {exc}",),
        )

    context = PackContext(
        pack_id=manifest["metadata"]["id"], pack_version=manifest["metadata"]["version"]
    )
    try:
        registration = await pack.activate(context)
    except Exception as exc:  # noqa: BLE001
        return PackContractCheckResult(9, "clean activation", False, (f"activate() raised: {exc}",))
    registered = sorted(registration.agents)
    details.append(f"activate() returned a PackRegistration with agents: {registered}")

    failed = False
    for agent_id, agent in registration.agents.items():
        if not isinstance(agent, Agent):
            failed = True
            details.append(f"registered agent {agent_id!r} does not satisfy the Agent Protocol")
        else:
            details.append(f"registered agent {agent_id!r} genuinely satisfies the Agent Protocol")

    try:
        health = await pack.health()
    except Exception as exc:  # noqa: BLE001
        return PackContractCheckResult(
            9, "clean activation", False, (*details, f"health() raised: {exc}")
        )
    details.append(f"health() returned status={health.status!r}")
    if health.status not in {"healthy", "degraded", "unhealthy"}:
        failed = True
        details.append(f"health() status {health.status!r} is not one of the real Literal values")

    try:
        await pack.deactivate()
    except Exception as exc:  # noqa: BLE001
        return PackContractCheckResult(
            9, "clean activation", False, (*details, f"deactivate() raised: {exc}")
        )
    details.append("deactivate() completed without error")

    return PackContractCheckResult(9, "clean activation", not failed, tuple(details))


async def run_pack_contract_suite(
    *,
    pack_root: Path,
    manifest_path: Path,
    schema_path: Path,
    own_pack_package: str,
    waiver_path: Path | None,
) -> PackContractSuiteReport:
    """Runs all 9 real checks against one real, on-disk pack and returns
    every result together, in check-id order. Loads and parses the
    manifest exactly once, threading the same parsed ``dict`` to every
    check that needs it — see this module's own docstring for why no
    check resolves its own manifest path internally.

    **Runs check 1 first and never crashes on an unreadable manifest.**
    Checks 2-6, 8, and 9 all need the manifest already parsed into a
    ``dict``; check 1 is the one place that parsing can fail (invalid
    YAML, a non-mapping document). If it does, this function reports
    check 1's own real failure plus an honest "cannot run without a
    valid manifest" result for every check that needs the parse to have
    succeeded — check 7 is pack-source-only and independent of the
    manifest, so it still runs for real regardless. A prior version of
    this function called the unguarded ``_load_manifest`` directly here,
    which raised past this function entirely on the same input — found
    by :mod:`tests.unit.platform_sdk.test_manifest_check_agrees_with_kernel_loader`,
    fixed here rather than only inside :func:`check_1_manifest_is_valid`.
    """
    check_1 = check_1_manifest_is_valid(manifest_path, schema_path)
    check_7 = check_7_no_forbidden_imports(
        pack_root, own_pack_package=own_pack_package, waiver_path=waiver_path
    )

    if not check_1.passed:
        unrunnable = (
            "skipped: check 1 (manifest is valid) failed, so the manifest could not be "
            "parsed for this check to run against"
        )
        results = (
            check_1,
            PackContractCheckResult(2, "entry points resolve", False, (unrunnable,)),
            PackContractCheckResult(3, "I/O models match", False, (unrunnable,)),
            PackContractCheckResult(4, "workflow steps resolve", False, (unrunnable,)),
            PackContractCheckResult(5, "trust tier consistency", False, (unrunnable,)),
            PackContractCheckResult(6, "permission vocabulary", False, (unrunnable,)),
            check_7,
            PackContractCheckResult(8, "required prompts exist", False, (unrunnable,)),
            PackContractCheckResult(9, "clean activation", False, (unrunnable,)),
        )
        return PackContractSuiteReport(results=results)

    manifest = _load_manifest(manifest_path)
    results = (
        check_1,
        check_2_entry_points_resolve(manifest, pack_root),
        check_3_io_models_match(manifest),
        check_4_workflow_steps_resolve(manifest, pack_root),
        check_5_trust_tier_consistency(manifest),
        check_6_permission_vocabulary(manifest, schema_path),
        check_7,
        check_8_required_prompts_exist(manifest, pack_root),
        await check_9_clean_activation(manifest),
    )
    return PackContractSuiteReport(results=results)


def render_suite_report(report: PackContractSuiteReport) -> str:
    """A real, human-readable report — plain ASCII only, deliberately,
    mirroring :func:`~ai_os_sdk.testing.waiver.render_report`'s own
    documented reason (Windows console codepage cannot encode emoji)."""
    lines: list[str] = []
    for result in report.results:
        marker = "[PASS]" if result.passed else "[FAIL]"
        lines.append(f"{marker} check {result.check_id}: {result.name}")
        for detail in result.details:
            lines.append(f"   {detail}")
    lines.append(
        "[PASS] all 9 checks passed" if report.passed else "[FAIL] one or more checks failed"
    )
    return "\n".join(lines)
