"""Superadmin-Rolle und Einstellungen

is_admin wurde nie ausgewertet und war überall false. Die Spalte wird daher
umbenannt statt neu angelegt: das bestehende, geteilte Admin-Konto bleibt
bewusst kein Superadmin (siehe `flask auth create-superadmin`).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-31 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('user', 'is_admin', new_column_name='is_superadmin')
    op.execute('UPDATE "user" SET is_superadmin = false')
    op.alter_column('user', 'is_superadmin', nullable=False, server_default=sa.false())

    op.create_table(
        'einstellung',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_by', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table('einstellung')

    op.alter_column('user', 'is_superadmin', nullable=True, server_default=None)
    op.alter_column('user', 'is_superadmin', new_column_name='is_admin')
