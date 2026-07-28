"""Add evaluation.metrics.run_id -> evaluation.experiment_runs.run_id FK.

Revision ID: 0026_metrics_run_id_fk
Revises: 0025_experiments_definition_fk
Create Date: 2026-07-26

Retrofits the foreign key `evaluation_schema.py` has deferred since
`evaluation.metrics` was created: `metrics.run_id` -> `experiment_runs.
run_id`. Already indexed (`ix_metrics_run_id`, added when `metrics` was
created); this migration only adds the constraint.

**Unlike every other foreign-key retrofit in this persistence layer,
this one was not safe against the existing test suite unmodified —
verified, not assumed, by attempting it and running the full suite
first.** Three tests in `tests/integration/persistence/test_migrations.py`
inserted a `metrics` row referencing `run_id = 'run_1'`, a value with no
matching `evaluation.experiment_runs` row anywhere in this codebase
(nothing writes to either table in real application code yet — no
Evaluation Engine exists, so there was no risk to any real code path,
only to test fixtures). Two of the three
(`test_evaluation_metrics_requires_all_columns`,
`test_evaluation_metrics_metric_value_stores_numeric_20_6_precision`)
were updated to seed a real `experiment_runs` row — and, transitively,
a real `experiments` row for *its own* foreign key — before the
`metrics` insert. The third
(`test_evaluation_metrics_requires_an_existing_workflow_instance`)
needed no change: it already expects failure, for its own unrelated
`workflow_id` foreign key, and `'run_1'` still does not exist as an
`experiment_runs` row either way.

Schema only — no writer exists for `evaluation.metrics` or
`evaluation.experiment_runs` yet.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026_metrics_run_id_fk"
down_revision: str | None = "0025_experiments_definition_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_NAME = "fk_metrics_run_id"


def upgrade() -> None:
    op.create_foreign_key(
        _FK_NAME,
        "metrics",
        "experiment_runs",
        ["run_id"],
        ["run_id"],
        source_schema="evaluation",
        referent_schema="evaluation",
    )


def downgrade() -> None:
    op.drop_constraint(
        _FK_NAME,
        "metrics",
        schema="evaluation",
        type_="foreignkey",
    )
