"""Engine construction for workflow-state persistence (ADR-0011).

SQLAlchemy 2.0 **Core**, not the ORM — explicit table definitions
(:mod:`ai_os_kernel.persistence.schema`) and explicit SQL, no
lazy-loading surprises on the hot path. Async because the rest of the
Kernel (FastAPI, the future Workflow Engine) is asyncio-based.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def build_engine(database_url: str) -> AsyncEngine:
    """Build the single engine for one Kernel process.

    ``pool_pre_ping`` avoids handing out a connection that a database
    restart or load balancer has already silently dropped.
    """
    return create_async_engine(database_url, pool_pre_ping=True)
