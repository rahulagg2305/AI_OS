"""Generate every roadmap rollup view from the ticket files.

Run ``python -m scripts.roadmap.generate`` to rewrite the generated docs;
``--check`` verifies they are current without writing (this is what CI
and :mod:`tests.roadmap` use).

**Why this exists.** Phase R1 measured a real, structural failure in the
hand-maintained trackers this replaces: a single 67,634-character
append-only paragraph in ``implementation_status.md`` (44% of the file),
read in full every session, plus three cells of the same shape in
``feature_inventory.md``. Regenerating the rollup from fixed-size tickets
removes the place where such a paragraph could accumulate: there is no
hand-typed narrative field anywhere in the pipeline, and the ticket
parser rejects any line over 200 chars or ticket over 24 lines before it
ever reaches a generated file.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from scripts.roadmap.model import Ticket, load_all, suspicious_empty_dependencies
from scripts.roadmap.stages import MODULES, PHASES, phase_label, stage_title

REPO_ROOT = Path(__file__).resolve().parents[2]
TICKETS_ROOT = REPO_ROOT / "docs" / "19_roadmap" / "tickets"
STATUS_OUT = REPO_ROOT / "docs" / "19_roadmap" / "STATUS.md"
BOARD_OUT = REPO_ROOT / "docs" / "19_roadmap" / "MODULE_BOARD.md"
# Read, never written: the authority for per-module completion.
FEATURE_INVENTORY = REPO_ROOT / "docs" / "19_roadmap" / "feature_inventory.md"

BANNER = (
    "<!-- GENERATED FILE - DO NOT EDIT BY HAND.\n"
    "     Source of truth: docs/19_roadmap/tickets/**.md\n"
    "                      + docs/19_roadmap/feature_inventory.md (module %)\n"
    "     Regenerate:      python -m scripts.roadmap.generate\n"
    "     Verified by:     tests/roadmap/test_generated_docs_are_current.py\n"
    "     Hand edits are overwritten and fail CI. -->\n"
)


MODULE_PCT_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*[^|]*\|\s*(\d+)%\s*\|")


def _pct(done: float, total: float) -> int:
    return 0 if total == 0 else round(100 * done / total)


def load_module_percentages() -> dict[int, int]:
    """The per-module completion percentages from
    ``feature_inventory.md``'s own table.

    **Why the generator reads a second file at all.** A document-only
    audit on 2026-08-13 found the two headline numbers this project
    publishes had drifted **35 points apart** — ticket-weighted
    completion read 96% while the mean of these module percentages read
    60.4% — and only the flattering one was ever surfaced. They measure
    genuinely different things (see :func:`render_status`), so the fix
    is to publish both, always, from one command.

    ``feature_inventory.md`` remains the source of truth for module
    percentages: every process document already names it as *the*
    authority for "how complete is this module", and it is updated in
    the same step as the code it describes. This function only reads it.

    The cross-check against :data:`MODULES` is the load-bearing part.
    Silently skipping an unparsed row would understate the denominator
    and quietly inflate the average — exactly the class of error this
    whole change exists to prevent — so a mismatch raises instead.
    """
    text = FEATURE_INVENTORY.read_text(encoding="utf-8")
    found: dict[int, int] = {}
    for line in text.split("\n"):
        match = MODULE_PCT_ROW.match(line)
        if match is None:
            continue
        module_id = int(match.group(1))
        if module_id not in MODULES or module_id in found:
            # Not the completion table (the file has other numbered
            # tables), or a row already seen. Either way, not a new
            # data point — the identity check below is what catches a
            # genuinely missing module.
            continue
        found[module_id] = int(match.group(3))

    missing = sorted(set(MODULES) - set(found))
    if missing:
        raise ValueError(
            f"{FEATURE_INVENTORY.name} has no completion percentage for module(s) "
            f"{missing}. Every module in scripts/roadmap/stages.py MODULES must appear "
            "in the completion table with a '<n>%' cell, or the module-average "
            "published in STATUS.md would be computed over an incomplete set."
        )
    return found


def _weight(t: Ticket) -> float:
    """A partial Task counts half. Deliberately coarse: the number is a
    navigation aid, not an estimate to defend."""
    return {"done": 1.0, "partial": 0.5}.get(t.status, 0.0)


def render_status(tickets: list[Ticket]) -> str:
    by_phase: dict[int, list[Ticket]] = defaultdict(list)
    for t in tickets:
        by_phase[t.phase].append(t)

    done = sum(_weight(t) for t in tickets)
    module_pcts = load_module_percentages()
    module_total = sum(module_pcts.values())
    module_remaining = 100 * len(module_pcts) - module_total
    lines: list[str] = [
        BANNER,
        "# AI_OS - Roadmap Status",
        "",
        f"**Generated:** {datetime.now(UTC).date().isoformat()} from {len(tickets)} Task tickets.",
        "",
        "This file is a rollup. **A normal development step must not read it** "
        "(`docs/process/standing_rules.md`): read only your own Task ticket and "
        "its direct dependencies.",
        "",
        # BOTH numbers, always, side by side. Publishing only the
        # ticket-weighted one let a 35-point gap open unnoticed
        # (document-only audit, 2026-08-13). They are not two estimates
        # of the same quantity: one measures how much of the *currently
        # known* work is ticketed and closed, the other how complete the
        # subsystems themselves are. The first can sit still while real
        # work lands, because discovering new work grows its denominator
        # in lockstep with its numerator; the second cannot.
        f"**Ticket-weighted completion: {_pct(done, len(tickets))}%** "
        f"({done:g} of {len(tickets)} Task-equivalents complete) — "
        "the share of *currently ticketed* work that is done. A `partial` "
        "Task counts half. This number moves very little late in a project: "
        "each newly discovered Task adds to the denominator as well as, "
        "eventually, the numerator.",
        "",
        # NOT `_pct`: that helper takes a ratio and multiplies by 100,
        # and these values are already percentages. Passing them to it
        # printed "6043%" on the first real run — caught by executing
        # the generator, not by reading it.
        f"**Module-average completion: {round(module_total / len(module_pcts))}%** "
        f"({module_total} points across {len(module_pcts)} modules, "
        f"unweighted mean; {module_remaining} points remain to 100%) — "
        "the share of the *system itself* that exists, from "
        "`feature_inventory.md`'s per-module table. A module reaches 100% "
        "only when the subsystem is genuinely complete, so this is the "
        "harder and more honest of the two.",
        "",
        "**Neither number alone is the answer, and the gap between them is "
        "the point.** Report both, every time "
        "(`docs/process/reporting_format.md`).",
        "",
        "| Phase | Stage | Tasks | Done | Partial | Todo | % |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]

    for phase in sorted(by_phase):
        by_stage: dict[int, list[Ticket]] = defaultdict(list)
        for t in by_phase[phase]:
            by_stage[t.stage].append(t)
        for stage in sorted(by_stage):
            st = by_stage[stage]
            d = sum(1 for t in st if t.status == "done")
            p = sum(1 for t in st if t.status == "partial")
            td = sum(1 for t in st if t.status in ("todo", "blocked"))
            lines.append(
                f"| P{phase:02d} ({PHASES[phase][0]}) | S{stage:02d} "
                f"{stage_title(phase, stage)} | {len(st)} | {d} | {p} | {td} | "
                f"{_pct(sum(_weight(t) for t in st), len(st))}% |"
            )

    lines += ["", "## Phase totals", "", "| Phase | Tasks | Done | % |", "|---|---:|---:|---:|"]
    for phase in sorted(by_phase):
        ph = by_phase[phase]
        lines.append(
            f"| {phase_label(phase)} | {len(ph)} | "
            f"{sum(1 for t in ph if t.status == 'done')} | "
            f"{_pct(sum(_weight(t) for t in ph), len(ph))}% |"
        )

    ready = [t for t in tickets if t.status == "todo" and _deps_met(t, tickets)]
    lines += [
        "",
        "## Ready to start",
        "",
        f"{len(ready)} Task(s) whose dependencies are all satisfied "
        "(Definition of Ready, `docs/process/ticket_templates.md`):",
        "",
    ]
    lines += [f"- `{t.id}` {t.title}" for t in sorted(ready, key=lambda x: x.id)[:25]]
    if len(ready) > 25:
        lines.append(f"- ... and {len(ready) - 25} more")

    # `blocked` Tasks were invisible in this document until 2026-08-12,
    # which is exactly how they came to be misreported. The "Ready to
    # start" list above deliberately shows only `todo` Tasks whose
    # dependencies are met, so a `blocked` Task appears nowhere — yet it
    # still occupies a slot in every denominator on this page. A reader
    # comparing "1 ready" against 23 not-done Tasks had no way to learn
    # that three of them are blocked, or why.
    #
    # A blocked Task's blocker is deliberately *not* a `depends_on` edge:
    # it is an unresolved decision or a missing prerequisite that no
    # other Task owns (Definition of Ready item 5). That is why the
    # dependency checker never contradicts this status, and why the
    # reason lives in the ticket's own body rather than in metadata.
    blocked = sorted((t for t in tickets if t.status == "blocked"), key=lambda x: x.id)
    lines += [
        "",
        "## Blocked",
        "",
        f"{len(blocked)} Task(s) with a real blocker that is **not** a `depends_on` edge — an "
        "unresolved decision or a missing prerequisite no other Task owns (Definition of Ready "
        "item 5). Their dependencies may well all be `done`; that does not make them ready. "
        "Each ticket's own body states its blocker:",
        "",
    ]
    lines += [f"- `{t.id}` {t.title}" for t in blocked]

    # A review signal, never a gate — see suspicious_empty_dependencies'
    # own docstring for why this is advisory.
    flagged = suspicious_empty_dependencies(tickets)
    lines += [
        "",
        "## Dependency review signal",
        "",
        f"{len(flagged)} `todo` Task(s) record no dependency although an earlier Task in "
        "the same module is unfinished. **Advisory only** — some Tasks genuinely start "
        "from nothing. Review when touching that module.",
        "",
    ]
    lines += [f"- `{t.id}` {t.title}" for t in flagged[:15]]
    if len(flagged) > 15:
        lines.append(f"- ... and {len(flagged) - 15} more")
    return "\n".join(lines) + "\n"


def _deps_met(t: Ticket, tickets: list[Ticket]) -> bool:
    index = {x.id: x for x in tickets}
    return all(index[d].status in ("done", "partial") for d in t.depends_on if d in index)


def render_board(tickets: list[Ticket]) -> str:
    by_module: dict[int, list[Ticket]] = defaultdict(list)
    for t in tickets:
        by_module[t.module].append(t)

    lines: list[str] = [
        BANNER,
        "# AI_OS - Module Board",
        "",
        f"**Generated:** {datetime.now(UTC).date().isoformat()}. "
        "Replaces `feature_inventory.md` §5's hand-maintained completion table.",
        "",
        "Module numbers are frozen (Phase R1). M35 (Analytics Pack) is "
        "permanently retired and never reused.",
        "",
        "| # | Module | Phase(s) | Tasks | Done | % |",
        "|---|---|---|---:|---:|---:|",
    ]
    for module in sorted(by_module):
        mt = by_module[module]
        phases = sorted({f"P{t.phase:02d}" for t in mt})
        lines.append(
            f"| M{module:02d} | {MODULES.get(module, '?')} | {'+'.join(phases)} | "
            f"{len(mt)} | {sum(1 for t in mt if t.status == 'done')} | "
            f"{_pct(sum(_weight(t) for t in mt), len(mt))}% |"
        )

    missing = sorted(set(MODULES) - set(by_module))
    if missing:
        lines += ["", f"**Modules with no tickets yet:** {missing}"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify without writing")
    args = ap.parse_args(argv)

    tickets = load_all(TICKETS_ROOT)
    outputs = {STATUS_OUT: render_status(tickets), BOARD_OUT: render_board(tickets)}

    stale = []
    for path, content in outputs.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            stale.append(path)
            if not args.check:
                path.write_text(content, encoding="utf-8")

    if args.check:
        if stale:
            print("STALE (run `python -m scripts.roadmap.generate`):", file=sys.stderr)
            for p in stale:
                print(f"  {p.relative_to(REPO_ROOT)}", file=sys.stderr)
            return 1
        print(f"generated docs are current ({len(tickets)} tickets)")
        return 0

    print(f"wrote {len(outputs)} file(s) from {len(tickets)} tickets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
