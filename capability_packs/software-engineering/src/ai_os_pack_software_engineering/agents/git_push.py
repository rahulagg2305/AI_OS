"""The Git Push Agent — this pack's seventh agent, and the first real
consumer of the Git Integration Service's ``platform.git.commit``/
``platform.git.push`` tools (``P03-S04-M31-T04``). Given the file Build
wrote, genuinely commit and push it through the real
:class:`~ai_os_kernel.git_integration.service.GitIntegrationService`,
reached exclusively through :class:`~ai_os_sdk.contracts.ToolInvoker` —
never a direct Kernel import (check 7).

**A new, narrowly-scoped catalog entry — the identical reasoning
``build``/``lint`` already established (``agents.md``'s own "Currently
Implemented Subset").** The already-documented ``release`` catalog
entry ("Manage versioning, prepare changelogs and release notes, verify
release readiness") is a genuinely broader, later, distinct agent
(``P08-S01-M29-T05``) — commit-and-push is not release management, and
force-fitting this narrower slice onto that id would misrepresent both.
``devops`` ("Build CI/CD pipelines, manage containers, IaC and
deployment readiness") is broader still. Rather than force-fit an
ill-matching id, this is a new, honestly-scoped entry, exactly as
``build``'s own catalog reconciliation already reasoned.

**Deliberately degrades to a real, structured "not configured" no-op —
never a failure — when ``remote_url`` is absent, which is how this
agent preserves the existing, proven ``se.delivery_pipeline`` behaviour
unchanged for every current real caller.** ``remote_url`` is this
agent's own constructor parameter (zero-arg-constructible like every
other entrypoint in this pack — ``EntrypointLoader`` always calls
``cls()`` with no arguments in production). When not given explicitly,
it reads ``AIOS_GIT_REMOTE_URL`` directly via ``os.environ`` as its bare
default — the identical "one env var, read once at construction, absent
means the existing safe default" shape
``ai_os_kernel.sandbox.default_executor.build_default_sandbox_executor``
already establishes for the same "zero-arg constructed, needs a real
deployment value" problem. Read via plain ``os.environ``, never a
``from ai_os_kernel...`` import: this pack has zero forbidden-import
violations today (``pack_contract_suite`` check 7's own "zero
violations, zero waiver file" state), and a Kernel-internal Settings
import here would reintroduce exactly the direct-Kernel-import coupling
that migration removed. A caller that wants this agent to genuinely
push either passes a real ``remote_url`` explicitly or sets
``AIOS_GIT_REMOTE_URL`` in its environment, and binds a
:class:`~ai_os_kernel.git_integration.service.GitIntegrationService`
-backed ``PackContext`` — exactly what this pack's own end-to-end test
does. Production wiring of the ``PackContext`` side
(``bootstrap.py`` constructing a real ``GitIntegrationService`` from
``ai_os_kernel.git_integration.default_service.
build_git_integration_service_from_env`` and threading it through
``SqlAgentRegistry``) is this same step's own real, non-deferred work —
see ``git_integration.md``'s own Implementation Status.

**Also checks ``context.tools.available_tools()`` before attempting
either tool call** — an SDK-Protocol-documented, side-effect-free fact
lookup, not a Kernel-internal exception type a pack may not import
(check 7). A configured ``remote_url`` with no genuine git-tool backing
(``ToolInvokerAdapter`` constructed without a real
``git_service``) is a real configuration error, raised loudly
(:class:`GitPushInstructionError`), not silently downgraded to a skip —
unlike the "not configured at all" case above, this caller clearly
intended a real push.

**Commit message is derived, never hand-typed at call time**: from
Build's own real, already-known ``filePath`` — the identical "derive
from a now-known real field" shape ``lint``/``qa-test``'s own
``lintCommand``/``runCommand`` transforms already establish in
``ai_os_kernel.workflow_engine.delivery_pipeline``.

**The branch pushed is exactly the branch just committed to** —
``platform.git.commit``'s own real, returned ``branch`` field, read
back and threaded directly into the following ``platform.git.push``
call, never independently re-derived or assumed.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field

from ai_os_sdk.contracts.tool_invoker import PLATFORM_GIT_COMMIT, PLATFORM_GIT_PUSH
from ai_os_sdk.models import ToolStatus

_ACTOR_ID = "se.delivery_pipeline"
_ACTOR_TYPE = "workflow"
_REMOTE_URL_ENV_VAR = "AIOS_GIT_REMOTE_URL"

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pushed": {"type": "boolean"},
        "commitSha": {"type": ["string", "null"]},
        "branch": {"type": ["string", "null"]},
        "reason": {"type": ["string", "null"]},
    },
    "required": ["pushed", "commitSha", "branch", "reason"],
    "additionalProperties": False,
}

_REQUIRED_FIELDS = ("workingDirectory", "filePath")


class GitPushAgentInput(BaseModel):
    """Documents this agent's Agent Contract "Required Inputs"
    (capability_pack_contract.md). **Not yet validated at runtime** —
    the identical, still unchanged "no per-step input-mapping mechanism
    exists" scope every agent in this pack already documents. Field
    names deliberately match ``BuildAgentOutput``'s own
    ``workingDirectory``/``filePath`` — this agent is meant to consume
    a Build Agent result directly."""

    working_directory: str = Field(..., alias="workingDirectory")
    file_path: str = Field(..., alias="filePath")

    model_config = {"populate_by_name": True}


class GitPushAgentOutput(BaseModel):
    """Documents this agent's Agent Contract "Produced Outputs." Mirrors
    the real fields :meth:`GitPushAgentEntrypoint.execute` returns —
    ``pushed`` is ``False`` with a real, non-null ``reason`` exactly
    when no real push was attempted (no ``remote_url`` configured),
    never a silent partial result."""

    pushed: bool
    commit_sha: str | None = Field(..., alias="commitSha")
    branch: str | None
    reason: str | None

    model_config = {"populate_by_name": True}


class GitPushInstructionError(Exception):
    """A real, genuine misconfiguration — a real ``remote_url`` was
    supplied but this agent cannot actually honor it (no bound
    ``PackContext``, no real git-tool backing, or missing/malformed
    upstream fields), raised clearly rather than silently downgraded to
    a skip. Distinct from the "no ``remote_url`` at all" case, which is
    a real, structured no-op, not an error — see this module's own
    docstring."""


def _extract_payload(inputs: dict[str, Any]) -> tuple[str, str]:
    """Returns ``(workingDirectory, filePath)`` from ``inputs`` directly,
    or, when absent, parsed as JSON from the assembled context — the
    identical fallback ``lint.py``/``verification.py`` already
    establish."""
    if all(field in inputs for field in _REQUIRED_FIELDS):
        payload = {field: inputs[field] for field in _REQUIRED_FIELDS}
    else:
        context = inputs.get("context")
        items = getattr(context, "items", None)
        if not items:
            raise GitPushInstructionError(
                "GitPushAgentEntrypoint requires 'workingDirectory' and 'filePath' — either "
                "directly in inputs, or as a JSON object in the assembled context"
            )
        raw = "\n\n".join(item.content for item in items)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GitPushInstructionError(
                f"the assembled context is not a valid JSON object: {exc}"
            ) from exc
        if not isinstance(payload, dict) or not all(field in payload for field in _REQUIRED_FIELDS):
            raise GitPushInstructionError(
                "the assembled context's JSON object is missing 'workingDirectory' or 'filePath'"
            )

    working_directory, file_path = (payload[field] for field in _REQUIRED_FIELDS)
    if not isinstance(working_directory, str) or not isinstance(file_path, str):
        raise GitPushInstructionError("workingDirectory and filePath must both be strings")
    return working_directory, file_path


class GitPushAgentEntrypoint:
    """The manifest's own ``agents[].entrypoint`` for the Git Push
    Agent — zero-argument-constructible, like every other agent in this
    pack. Needs no LLM composition at all (the identical shape
    ``LintAgentEntrypoint``/``TestAgentEntrypoint`` already establish
    for the same reason).
    """

    output_schema: dict[str, Any] = _OUTPUT_SCHEMA

    def __init__(self, *, remote_url: str | None = None) -> None:
        self._remote_url = (
            remote_url if remote_url is not None else os.environ.get(_REMOTE_URL_ENV_VAR)
        )
        self._context: Any | None = None

    def bind_pack_context(self, context: Any) -> None:
        self._context = context

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        if self._remote_url is None:
            return {
                "pushed": False,
                "commitSha": None,
                "branch": None,
                "reason": "no remote_url configured",
            }

        if self._context is None or self._context.tools is None:
            raise GitPushInstructionError(
                "GitPushAgentEntrypoint.execute() called before bind_pack_context() bound a "
                "PackContext granting the sandbox:execute permission (context.tools) — a "
                "real caller must inject one before first use"
            )

        available = {descriptor.tool_id for descriptor in self._context.tools.available_tools()}
        if PLATFORM_GIT_COMMIT not in available or PLATFORM_GIT_PUSH not in available:
            raise GitPushInstructionError(
                "a remote_url was configured, but the injected ToolInvoker does not expose "
                f"{PLATFORM_GIT_COMMIT!r}/{PLATFORM_GIT_PUSH!r} — it was built without a real "
                "GitIntegrationService backing it"
            )

        working_directory, file_path = _extract_payload(inputs)

        commit_result = await self._context.tools.invoke(
            PLATFORM_GIT_COMMIT,
            {
                "workspace": working_directory,
                "message": f"Automated delivery: write {file_path}",
                "actor_id": _ACTOR_ID,
                "actor_type": _ACTOR_TYPE,
            },
        )
        if commit_result.status is not ToolStatus.SUCCESS or commit_result.outputs is None:
            error = commit_result.error
            raise GitPushInstructionError(
                f"platform.git.commit failed: {error.message if error else 'unknown error'}"
            )
        commit_sha = commit_result.outputs["commit_sha"]
        branch = commit_result.outputs["branch"]

        push_result = await self._context.tools.invoke(
            PLATFORM_GIT_PUSH,
            {
                "workspace": working_directory,
                "branch": branch,
                "remote_url": self._remote_url,
                "actor_id": _ACTOR_ID,
                "actor_type": _ACTOR_TYPE,
            },
        )
        if push_result.status is not ToolStatus.SUCCESS:
            error = push_result.error
            raise GitPushInstructionError(
                f"platform.git.push failed: {error.message if error else 'unknown error'}"
            )

        return {"pushed": True, "commitSha": commit_sha, "branch": branch, "reason": None}
