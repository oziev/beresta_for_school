"""Add lesson plans, kits, kit items and design settings.

Revision ID: 0003_lesson_kits_design
Revises: 0002_add_indexes
Create Date: 2026-05-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_lesson_kits_design"
down_revision = "0002_add_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lesson_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("stages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_email"], ["users.email"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lesson_plans_user_email", "lesson_plans", ["user_email"], unique=False)

    op.create_table(
        "kits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_email", sa.String(length=255), nullable=True),
        sa.Column("lesson_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lesson_plan_id"], ["lesson_plans.id"]),
        sa.ForeignKeyConstraint(["user_email"], ["users.email"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kits_user_email", "kits", ["user_email"], unique=False)
    op.create_index("ix_kits_lesson_plan_id", "kits", ["lesson_plan_id"], unique=False)

    op.create_table(
        "kit_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_name", sa.String(length=100), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content_levels", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("complexity_distribution", sa.String(length=50), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["kit_id"], ["kits.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kit_items_kit_id", "kit_items", ["kit_id"], unique=False)

    op.create_table(
        "design_settings",
        sa.Column("user_email", sa.String(length=255), nullable=False),
        sa.Column("font_family", sa.String(length=50), server_default="Inter", nullable=False),
        sa.Column("font_size", sa.Integer(), server_default=sa.text("12"), nullable=False),
        sa.Column("margins", sa.String(length=20), server_default="normal", nullable=False),
        sa.Column("show_date", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("show_name", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("show_class", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_email"], ["users.email"]),
        sa.PrimaryKeyConstraint("user_email"),
    )


def downgrade() -> None:
    op.drop_table("design_settings")
    op.drop_index("ix_kit_items_kit_id", table_name="kit_items")
    op.drop_table("kit_items")
    op.drop_index("ix_kits_lesson_plan_id", table_name="kits")
    op.drop_index("ix_kits_user_email", table_name="kits")
    op.drop_table("kits")
    op.drop_index("ix_lesson_plans_user_email", table_name="lesson_plans")
    op.drop_table("lesson_plans")
