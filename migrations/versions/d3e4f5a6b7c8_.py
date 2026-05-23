"""rename verborgen to gepinnt on mitglied

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-23

"""
from alembic import op

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('mitglied', 'verborgen', new_column_name='gepinnt')


def downgrade():
    op.alter_column('mitglied', 'gepinnt', new_column_name='verborgen')
