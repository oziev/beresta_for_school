"""Add performance indexes.

Revision ID: 0002_add_indexes
Revises: 0001_initial
Create Date: 2026-05-15
"""
from __future__ import annotations

from alembic import op

revision = "0002_add_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CONCURRENTLY can't run inside a transaction; alembic wraps in one by default,
    # so we drop to non-transactional execution for these statements.
    op.execute("CREATE INDEX IF NOT EXISTS idx_materials_user_email ON materials(user_email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_material_id ON student_sessions(material_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_edits_user_email ON teacher_edits(user_email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_materials_created_at ON materials(created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_finished_at ON student_sessions(finished_at)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sessions_finished_at")
    op.execute("DROP INDEX IF EXISTS idx_materials_created_at")
    op.execute("DROP INDEX IF EXISTS idx_edits_user_email")
    op.execute("DROP INDEX IF EXISTS idx_sessions_material_id")
    op.execute("DROP INDEX IF EXISTS idx_materials_user_email")
