"""Parsing, validation, and invariants for Phase R2 Task tickets.

One ticket = one Task = one file under ``docs/19_roadmap/tickets/``.
Tickets are the **only** hand-authored source of roadmap truth; every
rollup view is generated from them by :mod:`scripts.roadmap.generate`.

**The structural guard this module exists to enforce.** Phase R1 measured
the real pathology in the files this replaces: ``implementation_status.md``
carried a single hand-typed ``**Last Updated:**`` paragraph of 67,634
characters (~16,900 tokens, 44% of the whole file) that grew by one
append every step, and ``feature_inventory.md`` had the same shape in
three table cells (19,546 / 12,892 / 12,396 chars). Both were read every
session. Prose limits alone would not have prevented that — a habit is
not a mechanism — so the limits below are enforced by
:func:`validate_ticket` and asserted by a real test, which fails CI the
moment any ticket exceeds them. An append-only paragraph cannot reach
17k characters without tripping :data:`MAX_LINE_CHARS` on its very first
overflow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# A ticket is a fixed-size unit of meaning, not a growing log. These two
# limits are what make the R1 pathology structurally impossible rather
# than merely discouraged: no line may become a paragraph, and no ticket
# may become a history.
MAX_LINE_CHARS = 200
MAX_TICKET_LINES = 24

TICKET_ID_RE = re.compile(r"^P(\d{2})-S(\d{2})-M(\d{2})-T(\d{2})$")
VALID_STATUSES = ("done", "partial", "todo", "blocked")

# Module 35 (Analytics Pack) was investigated and removed 2026-07-28.
# Its number is permanently retired: never reused, never re-issued.
RETIRED_MODULES = frozenset({35})


class TicketError(ValueError):
    """A ticket file is malformed, or violates a structural invariant."""


@dataclass(frozen=True)
class Ticket:
    """One parsed Task ticket."""

    id: str
    title: str
    status: str
    phase: int
    stage: int
    module: int
    task: int
    depends_on: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    module_path: str = ""
    goal: str = ""
    body: str = ""
    path: Path | None = None

    @property
    def is_done(self) -> bool:
        return self.status == "done"


@dataclass
class Stage:
    """A named work-slice inside a Phase — the level R1 identified as
    genuinely missing (what the ``Platform SDK v1.0.0`` initiative was,
    with no place to record it)."""

    phase: int
    stage: int
    title: str
    tickets: list[Ticket] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"P{self.phase:02d}-S{self.stage:02d}"


def parse_ticket(path: Path) -> Ticket:
    """Parse one ticket file, enforcing every structural invariant."""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()

    if len(lines) > MAX_TICKET_LINES:
        raise TicketError(
            f"{path.name}: {len(lines)} lines exceeds MAX_TICKET_LINES="
            f"{MAX_TICKET_LINES}. A ticket is a fixed-size unit of work, not a "
            "running log — split it into another Task instead of appending."
        )
    for n, line in enumerate(lines, 1):
        if len(line) > MAX_LINE_CHARS:
            raise TicketError(
                f"{path.name}:{n}: line is {len(line)} chars, over "
                f"MAX_LINE_CHARS={MAX_LINE_CHARS}. This is the exact "
                "append-only-paragraph pathology Phase R1 measured; write a "
                "new Task rather than growing this line."
            )

    if not raw.startswith("---\n"):
        raise TicketError(f"{path.name}: must open with a YAML frontmatter block")
    try:
        _, fm_text, body = raw.split("---\n", 2)
    except ValueError as exc:
        raise TicketError(f"{path.name}: unterminated frontmatter") from exc

    meta = yaml.safe_load(fm_text) or {}
    for required in ("id", "title", "status"):
        if required not in meta:
            raise TicketError(f"{path.name}: frontmatter missing required key '{required}'")

    ticket_id = str(meta["id"])
    m = TICKET_ID_RE.match(ticket_id)
    if not m:
        raise TicketError(f"{path.name}: id '{ticket_id}' does not match P00-S00-M00-T00")
    if path.stem != ticket_id:
        raise TicketError(f"{path.name}: filename must equal id '{ticket_id}'")

    status = str(meta["status"])
    if status not in VALID_STATUSES:
        raise TicketError(f"{ticket_id}: status '{status}' not in {VALID_STATUSES}")

    phase, stage, module, task = (int(g) for g in m.groups())
    if module in RETIRED_MODULES:
        raise TicketError(f"{ticket_id}: module M{module:02d} is permanently retired")

    def _tuple(key: str) -> tuple[str, ...]:
        value = meta.get(key) or []
        if isinstance(value, str):
            value = [value]
        return tuple(str(v) for v in value)

    goal = ""
    for line in body.splitlines():
        if line.startswith("**Goal:**"):
            goal = line.removeprefix("**Goal:**").strip()
            break

    # `module_path` (added 2026-07-31, the R3 pilot's own finding) tells
    # a working session where this Task's code lives without it having
    # to derive the location from the module number. Optional in the
    # schema so an older ticket still parses; validated against the
    # frozen registry when present, so it can never drift into naming a
    # module it does not belong to.
    module_path = str(meta.get("module_path") or "")
    if module_path:
        from scripts.roadmap.stages import MODULE_PATHS

        expected = MODULE_PATHS.get(module)
        if expected is not None and module_path != expected:
            raise TicketError(
                f"{ticket_id}: module_path '{module_path}' does not match the frozen "
                f"registry entry for M{module:02d} ('{expected}'). Edit "
                "scripts/roadmap/stages.py, not the ticket."
            )

    return Ticket(
        id=ticket_id,
        title=str(meta["title"]),
        status=status,
        phase=phase,
        stage=stage,
        module=module,
        task=task,
        depends_on=_tuple("depends_on"),
        evidence=_tuple("evidence"),
        module_path=module_path,
        goal=goal,
        body=body.strip(),
        path=path,
    )


def load_all(tickets_root: Path) -> list[Ticket]:
    """Parse every ticket, then check cross-ticket invariants."""
    tickets = [parse_ticket(p) for p in sorted(tickets_root.rglob("P*-S*-M*-T*.md"))]

    seen: dict[str, Path] = {}
    for t in tickets:
        if t.id in seen:
            raise TicketError(f"duplicate ticket id {t.id}: {seen[t.id]} and {t.path}")
        seen[t.id] = t.path  # type: ignore[assignment]

    known = set(seen)
    for t in tickets:
        for dep in t.depends_on:
            if dep not in known:
                raise TicketError(f"{t.id}: depends_on unknown ticket '{dep}'")
        if t.is_done:
            unmet = [d for d in t.depends_on if not seen_status(tickets, d).is_done]
            if unmet:
                raise TicketError(
                    f"{t.id} is done but depends on not-done ticket(s): {', '.join(unmet)}"
                )
    return tickets


def seen_status(tickets: list[Ticket], ticket_id: str) -> Ticket:
    for t in tickets:
        if t.id == ticket_id:
            return t
    raise TicketError(f"unknown ticket {ticket_id}")


def find_dependency_cycle(tickets: list[Ticket]) -> list[str] | None:
    """The first dependency cycle found, or ``None``.

    Added 2026-07-31 (Phase R3c) alongside the real dependency graph: a
    cycle makes every ticket in it permanently un-startable, and with 160
    edges recorded by hand that is a real hazard rather than a
    theoretical one. Iterative DFS — a 219-node graph is small, but
    recursion would make a genuine cycle surface as a
    ``RecursionError`` instead of a readable message.
    """
    graph = {t.id: [d for d in t.depends_on if d != t.id] for t in tickets}
    self_deps = [t.id for t in tickets if t.id in t.depends_on]
    if self_deps:
        return [self_deps[0], self_deps[0]]

    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)

    for root in graph:
        if colour[root] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        path: list[str] = [root]
        colour[root] = GREY
        while stack:
            node, index = stack[-1]
            if index < len(graph[node]):
                stack[-1] = (node, index + 1)
                nxt = graph[node][index]
                if colour.get(nxt) == GREY:
                    return [*path[path.index(nxt) :], nxt]
                if colour.get(nxt) == WHITE:
                    colour[nxt] = GREY
                    stack.append((nxt, 0))
                    path.append(nxt)
            else:
                colour[node] = BLACK
                stack.pop()
                path.pop()
    return None


def suspicious_empty_dependencies(tickets: list[Ticket]) -> list[Ticket]:
    """``todo`` tickets recording **no** dependency that probably should.

    A **signal for review, never a hard failure** — some Tasks genuinely
    start from nothing (``P02-S07-M21-T01``, a standalone artifact store,
    is a real example). The heuristic is deliberately narrow and
    explainable: flag a ``todo`` ticket with no dependencies when an
    *earlier-numbered Task in its own module* is not yet ``done``. That
    combination almost always means unrecorded intra-module sequencing —
    which is exactly the gap Phase R3b found, where 217 of 219 tickets
    recorded no dependency at all and "ready to start" therefore
    overstated real readiness by roughly double.
    """
    by_module: dict[int, list[Ticket]] = {}
    for t in tickets:
        by_module.setdefault(t.module, []).append(t)

    flagged = []
    for t in tickets:
        if t.status != "todo" or t.depends_on:
            continue
        earlier_unfinished = [
            o
            for o in by_module[t.module]
            if (o.phase, o.stage, o.task) < (t.phase, t.stage, t.task) and o.status != "done"
        ]
        if earlier_unfinished:
            flagged.append(t)
    return sorted(flagged, key=lambda x: x.id)
