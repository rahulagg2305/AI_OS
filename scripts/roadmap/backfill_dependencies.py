"""One-time pass recording the real dependency graph (Phase R3c).

Run once. R3b found only 2 of 219 tickets carried 2+ dependencies, so
"ready to start" reported unrecorded sequencing rather than genuine
readiness. Every entry below was derived by asking one question of each
Task: **does this Task need another Task's real output to exist before
it can be built?** An entry exists only where the answer is yes — none
were added to make the graph look thorough.

Only ``todo``/``blocked`` tickets are touched. ``status:`` is never
modified, and no ``done`` ticket gains a dependency (which would trip
the parser's own done-on-top-of-todo invariant).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TICKETS_ROOT = REPO_ROOT / "docs" / "19_roadmap" / "tickets"

# ticket id -> real prerequisites, with the reason in a trailing comment.
DEPENDENCIES: dict[str, list[str]] = {
    # M01 Configuration Manager: every new layer plugs into the existing
    # precedence resolution (T01).
    "P01-S02-M01-T03": ["P01-S02-M01-T01"],
    "P01-S02-M01-T04": ["P01-S02-M01-T01"],
    # An experiment-override layer cannot exist before experiments do.
    "P01-S02-M01-T05": ["P01-S02-M01-T01", "P04-S03-M34-T01"],
    # A secrets layer needs the reference-resolution contract.
    "P01-S02-M01-T06": ["P01-S02-M01-T01", "P01-S02-M19-T02"],
    "P01-S02-M01-T07": ["P01-S02-M01-T01"],
    # A change-audit trail needs somewhere audited to write to.
    "P01-S02-M01-T08": ["P01-S02-M01-T01", "P01-S05-M04-T05"],
    # M02: both validate what they discover against the schema path.
    "P01-S03-M02-T03": ["P01-S03-M02-T01"],
    "P01-S03-M02-T04": ["P01-S03-M02-T01"],
    # M03: draining must be visible through readiness while it happens.
    "P01-S04-M03-T06": ["P01-S04-M03-T01"],
    # M04: nothing to export until spans exist; no Collector to receive
    # until an exporter does; audit needs an authenticated actor to
    # attribute an action to; verification needs a chain to verify.
    "P01-S05-M04-T03": ["P01-S05-M04-T01"],
    "P01-S05-M04-T04": ["P01-S05-M04-T03"],
    "P01-S05-M04-T05": ["P03-S05-M14-T01"],
    "P01-S05-M04-T06": ["P01-S05-M04-T05"],
    # M05: a new step type must be declarable (T01) and dispatchable
    # (T03); a sub-workflow also spawns a real child instance (T02).
    "P02-S01-M05-T09": ["P02-S01-M05-T01", "P02-S01-M05-T03"],
    "P02-S01-M05-T10": ["P02-S01-M05-T01", "P02-S01-M05-T03"],
    "P02-S01-M05-T11": ["P02-S01-M05-T01", "P02-S01-M05-T02", "P02-S01-M05-T03"],
    # Leasing is exactly what makes many workers safe.
    "P02-S01-M05-T12": ["P02-S01-M05-T04"],
    "P02-S01-M05-T13": ["P02-S01-M05-T02"],
    # M06: every new call shape needs an adapter to reach and a route to it.
    "P02-S02-M06-T08": ["P02-S02-M06-T01", "P02-S02-M06-T02"],
    "P02-S02-M06-T09": ["P02-S02-M06-T01", "P02-S02-M06-T02"],
    "P02-S02-M06-T10": ["P02-S02-M06-T01"],
    # Rate limiting is per-provider and cooperates with backoff.
    "P02-S02-M06-T11": ["P02-S02-M06-T02", "P02-S02-M06-T03"],
    # A cache planner needs somewhere to put boundaries (M07 T06).
    "P02-S02-M06-T12": ["P02-S02-M06-T01", "P02-S03-M07-T06"],
    # M07: both build on the render contract.
    "P02-S03-M07-T05": ["P02-S03-M07-T01"],
    "P02-S03-M07-T06": ["P02-S03-M07-T01"],
    # M08: every resolver plugs into assembly (T01); the knowledge and
    # memory ones additionally need something real to read from.
    "P02-S03-M08-T05": ["P02-S03-M08-T01", "P02-S04-M09-T04"],
    "P02-S03-M08-T06": ["P02-S03-M08-T01", "P02-S04-M10-T01"],
    "P02-S03-M08-T07": ["P02-S03-M08-T01"],
    "P02-S03-M08-T08": ["P02-S03-M08-T01", "P01-S02-M01-T04"],
    "P02-S03-M08-T09": ["P02-S03-M08-T01"],
    "P02-S03-M08-T10": ["P02-S03-M08-T01"],
    # M09: nothing to index or attribute without the writer; the query
    # engine sits over both retrieval paths.
    "P02-S04-M09-T03": ["P02-S04-M09-T01"],
    "P02-S04-M09-T04": ["P02-S04-M09-T02", "P02-S04-M09-T03"],
    "P02-S04-M09-T05": ["P02-S04-M09-T01"],
    # M10: strictly sequential - store, then writer, then promotion.
    "P02-S04-M10-T02": ["P02-S04-M10-T01"],
    "P02-S04-M10-T03": ["P02-S04-M10-T02"],
    # M11: embeddings come from the Gateway and land in the pgvector
    # schema; search needs vectors; fusion needs both rankings.
    "P02-S04-M11-T03": ["P02-S04-M11-T02", "P02-S02-M06-T09"],
    "P02-S04-M11-T04": ["P02-S04-M11-T03"],
    "P02-S04-M11-T05": ["P02-S04-M11-T01", "P02-S04-M11-T04"],
    "P02-S04-M11-T06": ["P02-S04-M11-T05"],
    # M12: collectors need their tables; variance needs replicates to
    # vary across; cache exclusion needs a cache that can serve a run.
    "P04-S01-M12-T04": ["P04-S01-M12-T01"],
    "P04-S01-M12-T05": ["P04-S01-M12-T01"],
    "P04-S01-M12-T06": ["P04-S01-M12-T04", "P04-S03-M34-T02"],
    "P04-S01-M12-T07": ["P04-S01-M12-T06", "P02-S07-M23-T02"],
    "P04-S01-M12-T08": ["P04-S01-M12-T06"],
    # M13: upgrade extends the lifecycle; enforcement needs the rule
    # monotonic narrowing defines.
    "P02-S05-M13-T07": ["P02-S05-M13-T01"],
    "P02-S05-M13-T08": ["P02-S05-M13-T01", "P03-S05-M14-T03"],
    # M14: narrowing extends route permission checks; the approval
    # manager needs a writer to persist decisions and a step to pause at;
    # the writer needs a principal to attribute a decision to.
    "P03-S05-M14-T03": ["P03-S05-M14-T02"],
    "P03-S05-M14-T04": ["P03-S05-M14-T05", "P02-S01-M05-T03"],
    "P03-S05-M14-T05": ["P03-S05-M14-T01"],
    "P07-S02-M14-T01": ["P03-S05-M14-T01"],
    "P07-S02-M14-T02": ["P07-S02-M14-T01", "P03-S05-M14-T02"],
    # M15: the registry is what the executor resolves through; declared
    # gates must be manifest-validated and registered somewhere.
    "P02-S06-M15-T05": ["P02-S06-M15-T01"],
    "P02-S06-M15-T06": ["P02-S06-M15-T05", "P01-S03-M02-T01"],
    "P02-S06-M15-T07": ["P02-S06-M15-T05"],
    "P02-S06-M15-T08": ["P02-S06-M15-T05"],
    # M16: both queries read what the writer records.
    "P04-S02-M16-T02": ["P04-S02-M16-T01"],
    "P04-S02-M16-T03": ["P04-S02-M16-T01"],
    # M17: a relay needs both the outbox rows and a bus to publish onto.
    "P02-S07-M17-T03": ["P02-S07-M17-T01", "P02-S07-M17-T02"],
    # M18: resolving a declared tool needs the Protocol and the catalog
    # rows the manifest installer writes.
    "P02-S05-M18-T03": ["P02-S05-M18-T01", "P02-S05-M13-T04"],
    # M19: the broker gates references and needs a principal; TTL and
    # Vault both build on the reference contract; the leak scan needs
    # both resolved values and an assembled prompt to scan.
    "P01-S02-M19-T04": ["P01-S02-M19-T02", "P03-S05-M14-T01"],
    "P01-S02-M19-T05": ["P01-S02-M19-T02"],
    "P01-S02-M19-T06": ["P01-S02-M19-T02", "P02-S03-M07-T01"],
    "P07-S02-M19-T01": ["P01-S02-M19-T02"],
    # M20: a stronger tier extends the container-backed baseline.
    "P03-S01-M20-T05": ["P03-S01-M20-T02"],
    # M22: notifications are driven by platform events.
    "P06-S05-M22-T01": ["P02-S07-M17-T02"],
    "P06-S05-M22-T02": ["P06-S05-M22-T01"],
    # M23: a response cache needs a client and calls worth caching.
    "P02-S07-M23-T02": ["P02-S07-M23-T01", "P02-S02-M06-T01"],
    # M24: R-001 (approval guardrail) plus the credential handling
    # ADR-0024 rule 4 requires it to hold on the sandbox's behalf.
    "P03-S01-M24-T01": ["P03-S05-M14-T04", "P03-S05-M14-T05", "P01-S02-M19-T02"],
    # M26: chunking needs parsed text, and a writer that accepts chunks.
    "P05-S01-M26-T02": ["P05-S01-M26-T01", "P02-S04-M09-T01"],
    # M28: signed fields extend the schema (out of v1 scope regardless).
    "P01-S03-M28-T02": ["P01-S03-M28-T01"],
    # M29: each agent needs the upstream agent whose output it consumes.
    "P03-S02-M29-T07": ["P03-S02-M29-T03"],
    "P03-S02-M29-T08": ["P03-S02-M29-T02"],
    "P08-S01-M29-T01": ["P03-S02-M29-T08"],
    "P08-S01-M29-T02": ["P03-S02-M29-T02"],
    "P08-S01-M29-T03": ["P03-S02-M29-T02"],
    "P08-S01-M29-T04": ["P03-S02-M29-T03"],
    "P08-S01-M29-T05": ["P03-S02-M29-T03", "P03-S02-M29-T04"],
    "P08-S01-M29-T06": ["P03-S02-M29-T03", "P03-S02-M29-T04"],
    "P08-S01-M29-T07": ["P03-S02-M29-T03"],
    # M30: the pipeline is what changes; the revise loop needs findings
    # to revise from; the fuller workflows need the fuller agent set.
    "P03-S03-M30-T02": ["P03-S03-M30-T01"],
    "P03-S03-M30-T03": ["P03-S03-M30-T01", "P03-S02-M29-T07"],
    "P08-S02-M30-T01": ["P03-S02-M29-T07", "P03-S02-M29-T08"],
    "P08-S02-M30-T02": ["P03-S02-M29-T08"],
    # M31: declaring pack tools/gates needs the Kernel-side mechanisms
    # that resolve them.
    "P03-S04-M31-T02": ["P02-S05-M18-T03"],
    "P03-S04-M31-T03": ["P02-S06-M15-T06"],
    # M32: ingestion needs parsers; everything else chains off the model.
    "P05-S02-M32-T01": ["P05-S01-M26-T01"],
    "P05-S02-M32-T02": ["P05-S02-M32-T01"],
    "P05-S02-M32-T03": ["P05-S02-M32-T01"],
    "P05-S02-M32-T04": ["P05-S02-M32-T03"],
    "P05-S02-M32-T05": ["P05-S02-M32-T04"],
    "P05-S02-M32-T06": ["P05-S02-M32-T01", "P02-S03-M08-T04"],
    # M33: a voice pack needs the gateway that hears and speaks.
    "P06-S06-M33-T01": ["P06-S06-M25-T01"],
    # M34: replicates/ceilings/adaptations all qualify an experiment.
    "P04-S03-M34-T01": ["P04-S01-M12-T01"],
    "P04-S03-M34-T02": ["P04-S03-M34-T01"],
    "P04-S03-M34-T03": ["P04-S03-M34-T01", "P02-S02-M06-T07"],
    "P04-S03-M34-T04": ["P04-S03-M34-T01", "P02-S03-M07-T01"],
    # M36: the artifact is exported from real routes; RFC 9457 needs the
    # shared error hierarchy to shape; the rest extend the route pattern.
    "P06-S01-M36-T01": ["P02-S08-M36-T01"],
    "P06-S01-M36-T02": ["P02-S07-M44-T01"],
    "P06-S01-M36-T03": ["P02-S08-M36-T02"],
    "P06-S01-M36-T04": ["P02-S08-M36-T02"],
    # M37: a stream needs events to carry and an HTTP surface to sit on.
    "P06-S02-M37-T01": ["P02-S07-M17-T02", "P02-S08-M36-T01"],
    # M38/M39: both consume the published contract, never Kernel
    # internals (docs/process/api_contract_boundary.md).
    "P06-S04-M38-T01": ["P06-S01-M36-T01"],
    "P06-S03-M39-T01": ["P06-S01-M36-T01"],
    "P06-S03-M39-T02": ["P06-S03-M39-T01", "P03-S05-M14-T04"],
    "P06-S03-M39-T03": ["P06-S03-M39-T01", "P04-S01-M12-T08"],
    # M40: an image is built from the workspace; there is nothing to
    # deploy without one; egress policy needs a cluster; a restore
    # rehearsal must verify the audit chain.
    "P01-S01-M40-T04": ["P01-S01-M40-T01"],
    "P07-S01-M40-T01": ["P03-S05-M14-T04", "P03-S05-M14-T05", "P01-S01-M40-T04"],
    "P07-S01-M40-T02": ["P07-S01-M40-T01"],
    "P07-S01-M40-T03": ["P01-S05-M04-T05"],
    # M41: the controls live in the suite structure M42 T04 creates.
    "P03-S06-M41-T02": ["P01-S06-M42-T04"],
    # M42: chaos needs a worker loop to kill and a Redis to drop; cost
    # alerting needs collected metrics and a delivery channel.
    "P07-S03-M42-T01": ["P02-S01-M05-T12", "P02-S07-M23-T01"],
    "P07-S03-M42-T02": ["P04-S01-M12-T04", "P06-S05-M22-T01"],
}


def main() -> int:
    changed = unchanged = 0
    for ticket_id, deps in DEPENDENCIES.items():
        matches = list(TICKETS_ROOT.rglob(f"{ticket_id}.md"))
        if not matches:
            raise SystemExit(f"unknown ticket {ticket_id}")
        path = matches[0]

        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        rendered = f"depends_on: [{', '.join(deps)}]\n"
        out, hit = [], False
        for line in lines:
            if line.startswith("depends_on:"):
                hit = True
                if line == rendered:
                    unchanged += 1
                else:
                    changed += 1
                out.append(rendered)
            else:
                out.append(line)
        if not hit:
            raise SystemExit(f"{ticket_id}: no depends_on line found")
        path.write_text("".join(out), encoding="utf-8")

    print(f"dependencies written: {changed} changed, {unchanged} already correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
