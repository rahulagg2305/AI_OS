"""``pack_contract_suite`` check 7 — no forbidden imports
(``platform_sdk.md`` §9 item 7, §10): "no provider SDK, no
``ai_os_kernel``, no other pack, no database driver, no HTTP client to a
provider" (``platform_sdk_v1_scope.md`` step 8).

**A pure AST import-scanner over a pack's own source tree** — exactly
the mechanism §4's own reasoning names: "``ast.walk`` for ``Import``/
``ImportFrom`` nodes naming ``ai_os_kernel``, ``ai_os_services``, or
another pack's package." No ``PackContext``, no ``CapabilityPack``
semantics, no activation lifecycle — this needs none of step 7's
entry-point contract to run, which is why it ships alone, first, ahead
of the other 8 checks (step 15).

**Five forbidden categories, one denylist each, checked against the
*root* module of every import** (``import a.b.c`` and
``from a.b.c import d`` both root at ``a``):

1. ``ai_os_kernel`` — always forbidden, no exceptions. This is the
   mechanism that would have caught the Software Engineering pack's own
   current, months-long, hand-recorded violation
   (``capability_pack_contract.md`` §1a) — the entire reason this check
   ships as its own step, ahead of everything else in the remaining
   suite.
2. ``ai_os_services`` — always forbidden (§10's own second bullet names
   it alongside ``ai_os_kernel``).
3. **Another pack's own package** — any root beginning
   ``ai_os_pack_`` that is not *this* scan's own
   ``own_pack_package``. A pack may freely import its own package
   (``ai_os_pack_software_engineering.agents.build`` importing
   ``ai_os_pack_software_engineering.agents.architecture`` is not a
   violation); importing a sibling pack's package is.
4. **Provider SDK** — a maintained denylist of known LLM/embedding
   provider client libraries (``anthropic``, the real one this codebase
   actually depends on today at the Kernel layer —
   ``kernel/pyproject.toml`` — plus the other major providers a future
   adapter might reach for, so the list does not need to grow the day a
   second provider is added).
5. **Database driver** — a maintained denylist of the real drivers this
   codebase's own Kernel layer depends on (``sqlalchemy``, ``asyncpg``)
   plus their common siblings, so a pack cannot bypass ``WorkspaceService``/
   ``StorageService`` by reaching for persistence directly.

**A sixth category, deliberately broader than the section's own literal
wording, recorded as a real decision rather than silently narrowed:
"HTTP client to a provider" is treated as "any direct HTTP client
import," full stop.** A pure import-name scanner cannot determine
*where* an ``httpx``/``requests`` call is actually routed — that
requires tracing call sites and their arguments, not import statements.
Narrowing the check to only fire when a provider's own hostname appears
somewhere nearby would be unreliable and easy to accidentally bypass;
treating any raw HTTP client import in pack code as forbidden is both
safely over-inclusive relative to the literal text and consistent with
the surrounding rule's own intent — a compliant pack reaches external
services only through the SDK's own Protocols (``LLMGateway``,
``ToolInvoker``, ...), never a raw transport library, to *any*
destination, not merely a provider's.

**No pack currently triggers categories 4-6** — the one real pack's
only present violations are category 1 (``ai_os_kernel``), confirmed by
running this scanner for real, not assumed (see
``tests/unit/platform_sdk/test_forbidden_imports_check.py``).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_PROVIDER_SDK_ROOTS = frozenset(
    {
        "anthropic",  # the real provider this codebase depends on today
        "openai",
        "google.generativeai",
        "cohere",
        "mistralai",
        "boto3",  # AWS Bedrock's own SDK entry point
    }
)

_DATABASE_DRIVER_ROOTS = frozenset(
    {
        "sqlalchemy",
        "asyncpg",
        "psycopg",
        "psycopg2",
        "pymongo",
        "motor",
        "redis",
        "aiomysql",
        "aiosqlite",
    }
)

_HTTP_CLIENT_ROOTS = frozenset({"httpx", "requests", "aiohttp", "urllib3"})

_OTHER_PACK_PREFIX = "ai_os_pack_"


class ForbiddenImportCategory(StrEnum):
    """Which of §9 item 7's five named categories a violation falls
    under. String values are the human-readable label used in reports —
    not a wire contract, so free to read naturally."""

    KERNEL = "ai_os_kernel import"
    PLATFORM_SERVICE = "ai_os_services import"
    OTHER_PACK = "another pack's import"
    PROVIDER_SDK = "provider SDK import"
    DATABASE_DRIVER = "database driver import"
    HTTP_CLIENT = "direct HTTP client import"


@dataclass(frozen=True)
class ForbiddenImportViolation:
    """One forbidden import, found in one real file, at one real line —
    never a summary or an aggregate. ``module`` is the *pack's own*
    dotted module path the violation was found in (for matching against
    a waiver's own ``modules`` list), not the name that was imported."""

    file: Path
    line: int
    module: str
    imported: str
    category: ForbiddenImportCategory


def _root(name: str) -> str:
    return name.split(".")[0]


def _classify(name: str) -> ForbiddenImportCategory | None:
    root = _root(name)
    if root == "ai_os_kernel":
        return ForbiddenImportCategory.KERNEL
    if root == "ai_os_services":
        return ForbiddenImportCategory.PLATFORM_SERVICE
    if root in _PROVIDER_SDK_ROOTS:
        return ForbiddenImportCategory.PROVIDER_SDK
    if root in _DATABASE_DRIVER_ROOTS:
        return ForbiddenImportCategory.DATABASE_DRIVER
    if root in _HTTP_CLIENT_ROOTS:
        return ForbiddenImportCategory.HTTP_CLIENT
    return None


def _classify_with_own_pack(name: str, *, own_pack_package: str) -> ForbiddenImportCategory | None:
    root = _root(name)
    if root.startswith(_OTHER_PACK_PREFIX) and root != own_pack_package:
        return ForbiddenImportCategory.OTHER_PACK
    return _classify(name)


def _file_to_module(file: Path, *, src_root: Path) -> str:
    """Converts a real file path back to the dotted module name Python
    would import it as, relative to the ``src/`` directory containing
    the pack's own top-level package — e.g.
    ``src/ai_os_pack_software_engineering/agents/build.py`` ->
    ``ai_os_pack_software_engineering.agents.build``."""
    relative = file.relative_to(src_root).with_suffix("")
    parts = relative.parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def scan_module_source(
    source: str, file: Path, *, own_pack_package: str, module: str
) -> list[ForbiddenImportViolation]:
    """Scans one real, already-read Python source string for forbidden
    imports. Exposed separately from :func:`scan_pack_source` so a
    caller with source already in memory (a test, an editor plugin) need
    not round-trip through the filesystem."""
    tree = ast.parse(source, filename=str(file))
    violations: list[ForbiddenImportViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                category = _classify_with_own_pack(alias.name, own_pack_package=own_pack_package)
                if category is not None:
                    violations.append(
                        ForbiddenImportViolation(
                            file=file,
                            line=node.lineno,
                            module=module,
                            imported=alias.name,
                            category=category,
                        )
                    )
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            category = _classify_with_own_pack(node.module, own_pack_package=own_pack_package)
            if category is not None:
                violations.append(
                    ForbiddenImportViolation(
                        file=file,
                        line=node.lineno,
                        module=module,
                        imported=node.module,
                        category=category,
                    )
                )
    return violations


def scan_pack_source(src_root: Path, *, own_pack_package: str) -> list[ForbiddenImportViolation]:
    """Scans every ``*.py`` file under ``src_root`` (a pack's own
    ``src/`` directory, containing exactly its own top-level package) for
    forbidden imports. Deterministic order: files are visited sorted by
    path, so two runs against the same tree always report violations in
    the same order."""
    violations: list[ForbiddenImportViolation] = []
    for file in sorted(src_root.rglob("*.py")):
        module = _file_to_module(file, src_root=src_root)
        source = file.read_text(encoding="utf-8")
        violations.extend(
            scan_module_source(source, file, own_pack_package=own_pack_package, module=module)
        )
    return violations


def group_by_category(
    violations: Iterable[ForbiddenImportViolation],
) -> dict[ForbiddenImportCategory, list[ForbiddenImportViolation]]:
    """A small, real reporting convenience — not load-bearing logic — so
    a caller printing a report doesn't re-implement the same grouping."""
    grouped: dict[ForbiddenImportCategory, list[ForbiddenImportViolation]] = {}
    for violation in violations:
        grouped.setdefault(violation.category, []).append(violation)
    return grouped
