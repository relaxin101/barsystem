"""normalize line endings in bericht.sql (#25)

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-10-17

"""
from alembic import op

revision = 'a7b8c9d0e1f2'
down_revision = 'f5a6b7c8d9e0'
branch_labels = None
depends_on = None


def upgrade():
    # Alte Restores haben "\r" als Literal "_x000D_" gespeichert; CRLF -> LF.
    op.execute(
        "UPDATE bericht SET sql = "
        "replace(replace(replace(sql, '_x000D_', chr(13)), chr(13) || chr(10), chr(10)), chr(13), chr(10)) "
        "WHERE sql LIKE '%\\_x000D\\_%' OR sql LIKE '%' || chr(13) || '%'"
    )


def downgrade():
    pass
