"""T11 — Git history/branch destruction (security_architecture.md
§4/§14). §14's own real controls (a Git Integration Service holding
credentials, per-operation audit, protected-branch policy) do not exist
anywhere in this codebase yet — confirmed by grep: no git push/force-push
tool implementation exists at all, in the Kernel or in any Capability
Pack.

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
