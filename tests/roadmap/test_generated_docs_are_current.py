"""The mechanism that makes the Phase R1 file-size pathology
structurally impossible rather than merely discouraged.

Phase R1 measured the real failure: ``implementation_status.md`` carried
a single hand-typed ``**Last Updated:**`` paragraph of 67,634 characters
(~16,900 tokens — 44% of the whole file), grown by one append every
step, and read in full every session; ``feature_inventory.md`` had the
same shape in three cells (19,546 / 12,892 / 12,396 chars).

Three independent guards, each of which fails CI on its own:

1. :func:`test_every_ticket_parses_and_obeys_structural_limits` — no
   ticket may exceed 200 chars on a line or 24 lines total, so an
   append-only paragraph cannot even reach a first overflow.
2. :func:`test_generated_docs_are_current` — the generated rollups must
   byte-match what the generator produces, so a hand edit to a generated
   file is a build failure.
3. :func:`test_generated_docs_carry_the_do_not_edit_banner` — the
   generated files say so on line 1.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.roadmap.generate import BANNER, BOARD_OUT, STATUS_OUT, main
from scripts.roadmap.model import (
    MAX_LINE_CHARS,
    MAX_TICKET_LINES,
    RETIRED_MODULES,
    load_all,
    parse_ticket,
)
from scripts.roadmap.stages import MODULES, PHASES, STAGES

REPO_ROOT = Path(__file__).resolve().parents[2]
TICKETS_ROOT = REPO_ROOT / "docs" / "19_roadmap" / "tickets"


def _ticket_paths() -> list[Path]:
    return sorted(TICKETS_ROOT.rglob("P*-S*-M*-T*.md"))


def test_tickets_exist() -> None:
    assert _ticket_paths(), "no ticket files found — run scripts.roadmap.seed_tickets"


@pytest.mark.parametrize("path", _ticket_paths(), ids=lambda p: p.stem)
def test_every_ticket_parses_and_obeys_structural_limits(path: Path) -> None:
    """Guard 1: the append-only-paragraph pathology cannot start."""
    ticket = parse_ticket(path)  # raises TicketError on any violation
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAX_TICKET_LINES
    assert max((len(line) for line in lines), default=0) <= MAX_LINE_CHARS
    if ticket.status in ("done", "partial"):
        assert ticket.evidence, f"{ticket.id}: {ticket.status} requires real evidence"


def test_cross_ticket_invariants_hold() -> None:
    """Unique ids, resolvable dependencies, and no done-on-top-of-todo."""
    tickets = load_all(TICKETS_ROOT)
    assert len({t.id for t in tickets}) == len(tickets)


def test_every_ticket_names_the_path_its_work_lives_in() -> None:
    """The R3 pilot's own finding: without `module_path`, a working
    session had to derive the location from the module number."""
    from scripts.roadmap.stages import MODULE_PATHS

    for t in load_all(TICKETS_ROOT):
        assert t.module_path, f"{t.id}: module_path is missing"
        assert t.module_path == MODULE_PATHS[t.module], f"{t.id}: module_path disagrees"


def test_every_ticket_maps_to_a_real_phase_stage_and_module() -> None:
    for t in load_all(TICKETS_ROOT):
        assert t.phase in PHASES, f"{t.id}: unknown phase"
        assert (t.phase, t.stage) in STAGES, f"{t.id}: unnamed stage"
        assert t.module in MODULES, f"{t.id}: unknown module"
        assert t.module not in RETIRED_MODULES, f"{t.id}: retired module"


def test_generated_docs_are_current() -> None:
    """Guard 2: a hand edit to a generated rollup fails the build."""
    assert main(["--check"]) == 0, (
        "generated roadmap docs are stale or were hand-edited. "
        "Run `python -m scripts.roadmap.generate`. Generated files are never "
        "edited by hand — edit the ticket instead."
    )


@pytest.mark.parametrize("path", [STATUS_OUT, BOARD_OUT], ids=lambda p: p.name)
def test_generated_docs_carry_the_do_not_edit_banner(path: Path) -> None:
    """Guard 3: the file states its own provenance."""
    assert path.exists(), f"{path.name} has not been generated"
    assert path.read_text(encoding="utf-8").startswith(BANNER.split("\n")[0])


@pytest.mark.parametrize("path", [STATUS_OUT, BOARD_OUT], ids=lambda p: p.name)
def test_generated_docs_have_no_oversized_lines(path: Path) -> None:
    """The output inherits the input's shape — prove it, don't assume."""
    longest = max(len(line) for line in path.read_text(encoding="utf-8").splitlines())
    assert longest <= 400, (
        f"{path.name} has a {longest}-char line — the generator has grown a "
        "narrative field, which is exactly what Phase R2 removed."
    )
