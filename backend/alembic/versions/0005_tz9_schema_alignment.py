"""Align schema with TZ 9.0 kit requirements.

Revision ID: 0005_tz9_schema_alignment
Revises: 0004_teacher_sources
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_tz9_schema_alignment"
down_revision = "0004_teacher_sources"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column.name},
    ).scalar()
    if not exists:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("student_sessions", sa.Column("kit_id", postgresql.UUID(as_uuid=True), nullable=True))
    _add_column_if_missing("teacher_edits", sa.Column("kit_id", postgresql.UUID(as_uuid=True), nullable=True))
    _add_column_if_missing("lesson_plans", sa.Column("lesson_type", sa.String(length=50), nullable=True))
    _add_column_if_missing("kits", sa.Column("parent_kit_id", postgresql.UUID(as_uuid=True), nullable=True))
    _add_column_if_missing("kits", sa.Column("name", sa.String(length=200), nullable=True))
    _add_column_if_missing("kits", sa.Column("lesson_type", sa.String(length=50), nullable=True))
    _add_column_if_missing("kits", sa.Column("mode", sa.String(length=50), nullable=True))
    _add_column_if_missing("kits", sa.Column("kit_type", sa.String(length=20), server_default="student", nullable=False))
    _add_column_if_missing("kits", sa.Column("is_template", sa.Boolean(), server_default="false", nullable=False))
    _add_column_if_missing("kits", sa.Column("template_name", sa.String(length=200), nullable=True))
    _add_column_if_missing("kits", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    _add_column_if_missing("kits", sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    _add_column_if_missing("kit_items", sa.Column("complexity_level", sa.Integer(), server_default="2", nullable=False))
    _add_column_if_missing("kit_items", sa.Column("teacher_notes", sa.Text(), nullable=True))
    _add_column_if_missing("kit_items", sa.Column("answer_key", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    _add_column_if_missing("kit_items", sa.Column("example_mistakes", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key("fk_student_sessions_kit_id", "student_sessions", "kits", ["kit_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_teacher_edits_kit_id", "teacher_edits", "kits", ["kit_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_kits_parent_kit_id", "kits", "kits", ["parent_kit_id"], ["id"])


def downgrade() -> None:
    for name, table in [
        ("fk_kits_parent_kit_id", "kits"),
        ("fk_teacher_edits_kit_id", "teacher_edits"),
        ("fk_student_sessions_kit_id", "student_sessions"),
    ]:
        try:
            op.drop_constraint(name, table, type_="foreignkey")
        except Exception:
            pass
