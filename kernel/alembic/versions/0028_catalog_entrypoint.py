"""Add catalog.agents.entrypoint and catalog.tools.entrypoint.

Revision ID: 0028_catalog_entrypoint
Revises: 0027_workflow_steps_prompt
Create Date: 2026-07-26

Adds a required ``entrypoint`` column to ``catalog.agents`` and
``catalog.tools`` — closing a gap discovered while building
``SqlAgentRegistry``/``SqlToolRegistry``
(``ai_os_kernel.workflow_engine.registry``): the Agent Contract
(agent_architecture.md) and the Tool Contract have always required an
``entrypoint``, and ``platform_sdk/schemas/manifest.schema.json``'s own
``agents[]``/``tools[]`` entries already require and validate one
(pattern ``^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$``, "Python
import path, ``module.path:ClassName``"), but neither catalog table ever
had a column for it.

``entrypoint`` is ``TEXT NOT NULL`` — required in the manifest schema,
the same "required in the manifest maps to ``NOT NULL`` here" pattern
every other column on these two tables already follows. No ``CHECK``
constraint mirroring the manifest's own regex: format validation for a
patterned string is the Manifest Loader's job at manifest-load time,
the same convention already followed for ``agent_id``'s/``tool_id``'s
own documented id shapes, neither of which carries a Postgres-level
format constraint either.

**Why a plain additive column, not an expand/migrate/contract
sequence** (data_model.md §12 Migration Rule 2 governs backward-
incompatible changes to *populated* tables): neither ``catalog.agents``
nor ``catalog.tools`` has a writer anywhere in this codebase yet (the
Manifest Loader validates a manifest file; it does not persist one), so
there is no live data an added ``NOT NULL`` column could violate.

Schema and migration only — no entrypoint loading logic (dynamic
import, construction) is added here, and
``SqlAgentRegistry``/``SqlToolRegistry`` are unchanged: they still
confirm a row exists and return the same trivial ``EchoAgent``/
``EchoTool`` stand-in regardless of what ``entrypoint`` says. Real
entrypoint loading is Capability Manager territory (Stage C), explicitly
out of scope here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0028_catalog_entrypoint"
down_revision: str | None = "0027_workflow_steps_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("entrypoint", sa.Text, nullable=False),
        schema="catalog",
    )
    op.add_column(
        "tools",
        sa.Column("entrypoint", sa.Text, nullable=False),
        schema="catalog",
    )


def downgrade() -> None:
    op.drop_column("tools", "entrypoint", schema="catalog")
    op.drop_column("agents", "entrypoint", schema="catalog")
