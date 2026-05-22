"""Add teacher sources.

Revision ID: 0004_teacher_sources
Revises: 0003_lesson_kits_design
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_teacher_sources"
down_revision = "0003_lesson_kits_design"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teacher_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_email"], ["users.email"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teacher_sources_user_email", "teacher_sources", ["user_email"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_teacher_sources_user_email", table_name="teacher_sources")
    op.drop_table("teacher_sources")
