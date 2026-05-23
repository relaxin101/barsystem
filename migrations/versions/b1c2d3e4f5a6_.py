"""Add alle_mitglieder and brevo_template to aussendung

Revision ID: b1c2d3e4f5a6
Revises: 6b86097926f6
Create Date: 2026-05-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c2d3e4f5a6'
down_revision = '6b86097926f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('aussendung', schema=None) as batch_op:
        batch_op.add_column(sa.Column('alle_mitglieder', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('brevo_template', sa.Integer(), nullable=True))
    # Ensure member_days has a sensible default for existing rows
    op.execute("UPDATE aussendung SET member_days = 7 WHERE member_days = 0 AND alle_mitglieder = FALSE")


def downgrade():
    with op.batch_alter_table('aussendung', schema=None) as batch_op:
        batch_op.drop_column('brevo_template')
        batch_op.drop_column('alle_mitglieder')
