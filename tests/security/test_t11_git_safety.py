"""T11 — Git history/branch destruction (security_architecture.md
§4/§14).

**Stale by `P03-S01-M24-T02` (2026-08-02), corrected here rather than
silently left wrong (`P03-S06-M41-T02`, 2026-08-06): this docstring
used to claim §14's own real controls (a Git Integration Service
holding credentials, per-operation audit, protected-branch policy) "do
not exist anywhere in this codebase yet."** They do now —
:class:`~ai_os_kernel.git_integration.service.GitIntegrationService`,
real `platform.git.commit`/`platform.git.push` tools, a real
`git-push` agent chaining them as `se.delivery_pipeline`'s final step,
and a real, structural protected-branch refusal
(:class:`~ai_os_kernel.git_integration.models.GitPushPolicy`) —
`test_delivery_pipeline_git_push.py` proves a real commit and push end
to end. **This file still only tests the manifest-schema layer below,
not a positive-control proof that a live, configured
`GitIntegrationService` genuinely refuses a real force-push/branch-
delete attempt against its own `protected_branches` policy** — a real,
disclosed, still-open gap in this file's own coverage, named here so it
is not mistaken for "T11 fully proven," and a real candidate for its
own, correctly-scoped future ticket rather than attempted inline here.

**The real, structural control that does exist today**: the manifest's
own closed permission vocabulary (platform_sdk/schemas/manifest.schema.json,
ADR-0023 — "An unknown permission fails validation"). ``git:read`` and
``git:write`` are real, declarable permissions; a destructive operation
like force-push, branch deletion, or history rewrite has **no
corresponding permission string in the vocabulary at all** — so no
Capability Pack could ever declare it, even a maliciously-crafted
manifest attempting to.

The attempt: a manifest declares a destructive git permission the real
schema has never heard of — the real, committed JSON Schema, validated
with the identical ``jsonschema`` mechanism the Manifest Loader itself
uses, must genuinely reject it.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "platform_sdk" / "schemas" / "manifest.schema.json"


def _permissions_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    permissions_schema = schema["properties"]["permissions"]
    Draft202012Validator.check_schema(permissions_schema)
    return Draft202012Validator(permissions_schema)


def test_a_malicious_manifest_declaring_a_destructive_git_permission_is_rejected() -> None:
    """A real attempt at the threat: a manifest tries to declare a
    force-push (or equivalent history-destroying) capability. The real,
    closed permission vocabulary has never named such a string, so
    schema validation genuinely refuses it."""
    validator = _permissions_validator()

    for hostile_permission in ("git:force_push", "git:delete_branch", "git:rewrite_history"):
        errors = list(validator.iter_errors([hostile_permission]))
        assert errors, f"{hostile_permission!r} should be rejected by the closed vocabulary"


def test_the_real_vocabulary_does_permit_ordinary_read_and_write_git_access() -> None:
    """Proportionality check: the vocabulary is closed against
    destructive operations specifically, not against git access
    altogether — a pack genuinely needing to read or commit to a
    non-protected branch can still declare that."""
    validator = _permissions_validator()

    assert validator.is_valid(["git:read", "git:write"])
