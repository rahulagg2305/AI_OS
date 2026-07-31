"""One-time backfill: add ``module_path:`` to every existing ticket.

Run once (Phase R3b). Inserts the field immediately after
``evidence:`` in each ticket's frontmatter, taking the value from
:data:`scripts.roadmap.stages.MODULE_PATHS` — the frozen registry — so
no path is typed twice. Idempotent: a ticket that already carries the
field is left untouched.

Deliberately edits in place rather than re-running the seeder: ticket
``status:`` values are now hand-maintained truth (``P01-S02-M19-T03``
was set to ``done`` by the R3 pilot, ``P01-S03-M28-T02`` to ``blocked``),
and re-seeding would overwrite them.
"""

from __future__ import annotations

from pathlib import Path

from scripts.roadmap.stages import MODULE_PATHS

REPO_ROOT = Path(__file__).resolve().parents[2]
TICKETS_ROOT = REPO_ROOT / "docs" / "19_roadmap" / "tickets"


def main() -> int:
    added = skipped = 0
    for path in sorted(TICKETS_ROOT.rglob("P*-S*-M*-T*.md")):
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        if any(line.startswith("module_path:") for line in lines):
            skipped += 1
            continue

        module = int(path.stem.split("-M")[1].split("-T")[0])
        module_path = MODULE_PATHS[module]

        out: list[str] = []
        for line in lines:
            out.append(line)
            if line.startswith("evidence:"):
                out.append(f"module_path: {module_path}\n")
        path.write_text("".join(out), encoding="utf-8")
        added += 1

    print(f"module_path added to {added} ticket(s), {skipped} already had it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
