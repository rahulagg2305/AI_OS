"""Export the Kernel's OpenAPI 3.1 document to a committed artifact.

``python -m scripts.export_openapi`` rewrites ``docs/07_api/openapi.json``;
``--check`` verifies it is current without writing (CI, and the drift
check ADR-0018 line 27 already mandates: *"generation runs in CI and
drift fails the build"*).

This is the artifact that lets a Dashboard- or CLI-focused session read
**only the API contract**, never Kernel internals — see
``docs/process/api_contract_boundary.md``. No database is needed: route
*shapes* do not depend on runtime state, so the app is constructed with
an empty pack directory and never started.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "07_api" / "openapi.json"


def build_document() -> dict[str, object]:
    from ai_os_kernel.bootstrap import build_app
    from ai_os_kernel.configuration_manager.models import PlatformConfig

    # `env`/`role` are bootstrap identity and have no defaults; the pack
    # directory is emptied so the export never depends on what happens to
    # be on disk. `build_app` only registers routers here — `_lifespan`
    # (and therefore any database access) never runs.
    app = build_app(PlatformConfig(env="export", role="api", capability_pack_dirs=[]))
    doc = app.openapi()
    if not isinstance(doc, dict):  # pragma: no cover - FastAPI always returns a dict
        raise TypeError(f"FastAPI returned {type(doc).__name__}, expected a dict")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify without writing")
    args = ap.parse_args(argv)

    rendered = json.dumps(build_document(), indent=2, sort_keys=True) + "\n"
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else None

    if args.check:
        if current != rendered:
            print(
                "OpenAPI artifact is stale — run `python -m scripts.export_openapi`.\n"
                "Per ADR-0018, contract drift is a build failure.",
                file=sys.stderr,
            )
            return 1
        print(f"OpenAPI artifact is current ({OUT.relative_to(REPO_ROOT)})")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT)} ({len(rendered):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
