"""The documented, expiring waiver mechanism for
:mod:`ai_os_sdk.testing.forbidden_imports` (check 7),
``platform_sdk_v1_scope.md`` step 8.

**Why a waiver exists at all — a real, load-bearing design constraint,
not an escape hatch invented for convenience.** Wiring check 7 into CI
with no waiver mechanism would make CI red at step 8 and keep it red
through step 13 (finding P4, §4.1) — six steps of a knowingly-broken
pipeline, which this project's own zero-regression rule forbids. A
waiver is the only honest way to ship a real, enforced check *before*
every pack that would fail it has been migrated, without either
disabling the check entirely or lying about what it found.

**A waiver must be loud, dated, and self-expiring — never a silent
allowlist.** Concretely, that means:

- It lives in a real file, checked into the pack's own repository root
  (sibling to ``manifest.yaml``), not a hidden central registry or a
  code-level ``# noqa``-style annotation buried in the violating file
  itself. Anyone who opens the pack's own directory sees it.
- It names an ``expires_at_step`` — an integer step number from
  ``platform_sdk_v1_scope.md``'s own 18-step sequence — not a date. A
  step-bound expiry is enforceable by this same tooling checking whether
  that step has been marked done; a date-bound one would silently drift
  if the migration ran long or short.
- It lists the **exact** modules it covers, by dotted module path
  matching :func:`~ai_os_sdk.testing.forbidden_imports.scan_pack_source`'s
  own reported ``module`` field — not "the whole pack," so a *new*
  violation introduced in an already-compliant module is never silently
  covered by an old, broader grant.
- Every application of a waiver is reported explicitly, even when it
  succeeds — see :func:`apply_waiver`'s own return shape. A CI run that
  passes because of an active waiver looks visibly different from one
  that passes because there is genuinely nothing to waive.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ai_os_sdk.testing.forbidden_imports import ForbiddenImportViolation


class WaiverFileError(ValueError):
    """A waiver file exists but is malformed — missing a required field,
    or a field of the wrong shape. Raised rather than silently ignored,
    since a broken waiver file failing open (as if it granted nothing)
    would make check 7 fail where a human expected it to pass, and
    failing closed (as if it granted everything) would defeat the check
    entirely — neither is acceptable, so this is a hard error instead."""


@dataclass(frozen=True)
class ImportWaiver:
    """One real, dated exception to check 7, for exactly the modules
    named — see this module's own docstring for why each field exists."""

    check: int
    reason: str
    plan_reference: str
    expires_at_step: int
    granted: str
    modules: frozenset[str]


_REQUIRED_FIELDS = ("check", "reason", "plan_reference", "expires_at_step", "granted", "modules")


def load_waiver(path: Path) -> ImportWaiver | None:
    """Loads a waiver file if one exists at ``path``; returns ``None`` if
    it does not (no waiver -> full, unwaived enforcement — the safe
    default). Raises :class:`WaiverFileError` if the file exists but is
    malformed, rather than guessing at a partial waiver."""
    if not path.is_file():
        return None

    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise WaiverFileError(f"{path}: must contain a YAML mapping at the top level")

    missing = [field for field in _REQUIRED_FIELDS if field not in raw]
    if missing:
        raise WaiverFileError(f"{path}: missing required field(s): {', '.join(missing)}")

    modules = raw["modules"]
    if not isinstance(modules, list) or not all(isinstance(m, str) for m in modules):
        raise WaiverFileError(f"{path}: 'modules' must be a list of strings")

    return ImportWaiver(
        check=int(raw["check"]),
        reason=str(raw["reason"]),
        plan_reference=str(raw["plan_reference"]),
        expires_at_step=int(raw["expires_at_step"]),
        granted=str(raw["granted"]),
        modules=frozenset(modules),
    )


@dataclass(frozen=True)
class WaiverApplication:
    """The real outcome of checking a set of violations against a
    waiver — both lists are always populated explicitly, even when
    empty, so a caller never has to infer "nothing was waived" from an
    absent field."""

    unwaived: list[ForbiddenImportViolation]
    waived: list[ForbiddenImportViolation]
    waiver: ImportWaiver | None


def apply_waiver(
    violations: list[ForbiddenImportViolation], waiver: ImportWaiver | None
) -> WaiverApplication:
    """Splits ``violations`` into what the waiver actually covers
    (``waived``) and what it does not (``unwaived``) — matched by each
    violation's own ``module`` field against ``waiver.modules`` exactly,
    never by pack name or category, so a waiver can never accidentally
    cover more than it explicitly lists."""
    if waiver is None:
        return WaiverApplication(unwaived=list(violations), waived=[], waiver=None)

    waived = [v for v in violations if v.module in waiver.modules]
    unwaived = [v for v in violations if v.module not in waiver.modules]
    return WaiverApplication(unwaived=unwaived, waived=waived, waiver=waiver)


def render_report(application: WaiverApplication) -> str:
    """A real, human-readable report — used by
    ``scripts/check_import_boundaries.py`` and by this module's own
    tests, so the CI-facing wording and the test-verified wording are
    the exact same string, not two hand-maintained copies.

    **Plain ASCII only, deliberately — a real, discovered portability
    bug, not a style choice.** An earlier version of this function used
    emoji markers; on Windows, the default console codepage (``cp1252``)
    cannot encode them, and a bare ``print()`` of this string crashed
    with ``UnicodeEncodeError`` before this script ever reported a
    single real violation. CI itself runs on Ubuntu with a UTF-8 locale,
    where the crash would never have shown up — exactly the kind of
    "works in CI, breaks for a real contributor running it locally"
    gap this project's own discipline exists to catch before it ships.
    """
    lines: list[str] = []

    if application.waiver is not None:
        w = application.waiver
        lines.append(
            f"[WAIVER ACTIVE] check {w.check}: {len(application.waived)} violation(s) "
            f"waived across {len(w.modules)} module(s), granted {w.granted}, "
            f"expiring at step {w.expires_at_step} ({w.plan_reference})."
        )
        lines.append(f"   Reason: {w.reason.strip()}")
        for violation in application.waived:
            lines.append(
                f"   [WAIVED] {violation.file}:{violation.line} - "
                f"{violation.category.value} ({violation.imported!r})"
            )

    if application.unwaived:
        lines.append(f"[FAIL] {len(application.unwaived)} unwaived violation(s):")
        for violation in application.unwaived:
            lines.append(
                f"   {violation.file}:{violation.line} - "
                f"{violation.category.value} ({violation.imported!r})"
            )
    else:
        lines.append("[PASS] No unwaived forbidden imports.")

    return "\n".join(lines)
