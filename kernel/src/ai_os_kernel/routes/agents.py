"""api_architecture.md §6.4's own documented ``GET /api/v1/agents``
("Registered agents + stats") — the "Registered agents" half only.

**The "+ stats" half is a real, disclosed, narrower slice this route
deliberately does not attempt** — per-agent usage/cost/quality
aggregation needs the Evaluation Engine's own reporting surface
(module 12), which has no real view for this specific shape yet. The
identical "ship the documented endpoint's own real, buildable half,
disclose the rest" precedent this codebase already establishes
elsewhere (e.g. the worker Deployment's HPA scaling on CPU, not
"worker lease-queue depth" — deployment_architecture.md §6) is applied
here rather than inventing a fabricated stats block.

Reuses a new :meth:`~ai_os_kernel.workflow_engine.registry.
SqlAgentRegistry.list_all` — pure ``catalog.agents`` metadata, never
constructing a real :class:`~ai_os_kernel.workflow_engine.agent.Agent`
object the way :meth:`~ai_os_kernel.workflow_engine.registry.
SqlAgentRegistry.resolve_agent` does (see that method's own module
docstring for why a listing must not dynamically import/instantiate
every registered agent's own entrypoint).

Gated by ``workflow:read`` — §5's own documented permission table names
no dedicated ``agent:read`` permission, and §4.2's own role table
groups "agents" thematically with the same operational-introspection
concerns (`gate results`, `usage`) `viewer`'s own broad
"Read workflows, experiments, gate results, health" grant already
covers, not the narrower `pack:read`/`pack:manage` pair — an agent
registration is workflow-execution catalog data (`registry.py` lives in
`workflow_engine`, not `capability_manager`), not a pack-management
concern.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_os_kernel.security_manager import WORKFLOW_READ, SecurityContext, require_permission
from ai_os_kernel.workflow_engine.registry import AgentRegistration, SqlAgentRegistry

router = APIRouter(prefix="/api/v1", tags=["agents"])


def _get_engine(request: Request) -> AsyncEngine:
    # The identical `app.state.database_engine` accessor
    # `routes/approvals.py`/`routes/workflows.py` already establish.
    engine: AsyncEngine | None = getattr(request.app.state, "database_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="workflow engine is not available")
    return engine


@router.get("/agents", response_model=list[AgentRegistration])
async def list_agents(
    request: Request,
    _security_context: SecurityContext = Depends(require_permission(WORKFLOW_READ)),  # noqa: B008
) -> list[AgentRegistration]:
    engine = _get_engine(request)
    return await SqlAgentRegistry(engine).list_all()
