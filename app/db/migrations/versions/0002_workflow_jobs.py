"""add workflow jobs

Revision ID: 0002_workflow_jobs
Revises: 0001_initial
Create Date: 2026-06-15
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_workflow_jobs"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text()),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("owner_id", sa.Text()),
        sa.Column("access_scope", sa.Text(), nullable=False),
        sa.Column("dify_user", sa.Text(), nullable=False),
        sa.Column("dify_task_id", sa.Text()),
        sa.Column("dify_workflow_run_id", sa.Text()),
        sa.Column("dify_upload_file_id", sa.Text()),
        sa.Column("request_inputs_json", postgresql.JSONB(), nullable=False),
        sa.Column("result_json", postgresql.JSONB()),
        sa.Column("result_summary_json", postgresql.JSONB()),
        sa.Column("error_code", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("current_node_id", sa.Text()),
        sa.Column("current_node_title", sa.Text()),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temporary_file_manifest_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_unique_constraint("uq_workflow_jobs_job_id", "workflow_jobs", ["job_id"])
    op.create_unique_constraint("uq_workflow_jobs_idempotency_key", "workflow_jobs", ["idempotency_key"])
    op.create_index("ix_workflow_jobs_job_id", "workflow_jobs", ["job_id"])
    op.create_index("ix_workflow_jobs_dify_workflow_run_id", "workflow_jobs", ["dify_workflow_run_id"])
    op.create_index("ix_workflow_jobs_dify_task_id", "workflow_jobs", ["dify_task_id"])
    op.create_index("ix_workflow_jobs_owner_id", "workflow_jobs", ["owner_id"])
    op.create_index("ix_workflow_jobs_status", "workflow_jobs", ["status"])
    op.create_index("ix_workflow_jobs_source_type", "workflow_jobs", ["source_type"])
    op.create_index("ix_workflow_jobs_created_at", "workflow_jobs", ["created_at"])
    op.create_index("ix_workflow_jobs_expires_at", "workflow_jobs", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_workflow_jobs_expires_at", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_created_at", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_source_type", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_status", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_owner_id", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_dify_task_id", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_dify_workflow_run_id", table_name="workflow_jobs")
    op.drop_index("ix_workflow_jobs_job_id", table_name="workflow_jobs")
    op.drop_constraint("uq_workflow_jobs_idempotency_key", "workflow_jobs", type_="unique")
    op.drop_constraint("uq_workflow_jobs_job_id", "workflow_jobs", type_="unique")
    op.drop_table("workflow_jobs")

