"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-14
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id", sa.Text(), nullable=False),
        sa.Column("canonical_title", sa.Text()),
        sa.Column("normalized_title", sa.Text()),
        sa.Column("doi", sa.Text()),
        sa.Column("arxiv_id", sa.Text()),
        sa.Column("authors_json", postgresql.JSONB()),
        sa.Column("year", sa.Integer()),
        sa.Column("latest_content_hash", sa.Text()),
        sa.Column("latest_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_papers_paper_id", "papers", ["paper_id"])
    op.create_index("ix_papers_normalized_title", "papers", ["normalized_title"])
    op.create_unique_constraint("uq_papers_paper_id", "papers", ["paper_id"])
    op.create_unique_constraint("uq_papers_doi", "papers", ["doi"])
    op.create_unique_constraint("uq_papers_arxiv_id", "papers", ["arxiv_id"])

    op.create_table(
        "paper_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("profile_json", postgresql.JSONB(), nullable=False),
        sa.Column("chapter_index_json", postgresql.JSONB()),
        sa.Column("figure_index_json", postgresql.JSONB()),
        sa.Column("graph_json", postgresql.JSONB()),
        sa.Column("source_metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("knowledge_documents_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("paper_id", "content_hash", name="uq_paper_versions_paper_hash"),
        sa.UniqueConstraint("paper_id", "version_number", name="uq_paper_versions_paper_version"),
    )
    op.create_index("ix_paper_versions_paper_id", "paper_versions", ["paper_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="received"),
        sa.Column("dedup_status", sa.Text(), nullable=False),
        sa.Column("kb_status", sa.Text(), nullable=False, server_default="skipped"),
        sa.Column("graph_status", sa.Text(), nullable=False, server_default="skipped"),
        sa.Column("storage_status", sa.Text(), nullable=False, server_default="disabled"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text()),
        sa.Column("request_schema_version", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ingestion_jobs_paper_id", "ingestion_jobs", ["paper_id"])
    op.create_index("ix_ingestion_jobs_content_hash", "ingestion_jobs", ["content_hash"])

    op.create_table(
        "kb_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_key", sa.Text(), nullable=False),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("dataset_id", sa.Text()),
        sa.Column("remote_document_id", sa.Text()),
        sa.Column("batch_id", sa.Text()),
        sa.Column("indexing_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_kb_documents_document_key", "kb_documents", ["document_key"])
    op.create_index("ix_kb_documents_document_key", "kb_documents", ["document_key"])
    op.create_index("ix_kb_documents_paper_id", "kb_documents", ["paper_id"])

    op.create_table(
        "graph_sync_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("edge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sync_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("paper_id", "content_hash", name="uq_graph_sync_paper_hash"),
    )
    op.create_index("ix_graph_sync_records_paper_id", "graph_sync_records", ["paper_id"])

    op.create_table(
        "duplicate_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("paper_id_a", sa.Text(), nullable=False),
        sa.Column("paper_id_b", sa.Text(), nullable=False),
        sa.Column("similarity_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("paper_id_a", "paper_id_b", name="uq_duplicate_candidate_pair"),
    )


def downgrade() -> None:
    op.drop_table("duplicate_candidates")
    op.drop_table("graph_sync_records")
    op.drop_table("kb_documents")
    op.drop_table("ingestion_jobs")
    op.drop_table("paper_versions")
    op.drop_table("papers")

