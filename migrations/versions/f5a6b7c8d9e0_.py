"""add typ, volumen_liter, reinalkohol_liter to artikel

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-02

"""
import sqlalchemy as sa
from alembic import op

revision = 'f5a6b7c8d9e0'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('artikel', sa.Column('typ', sa.String(10), nullable=False, server_default='volumen'))
    op.add_column('artikel', sa.Column('volumen_liter', sa.Float(), nullable=True, server_default='0.5'))
    op.add_column('artikel', sa.Column('reinalkohol_liter', sa.Float(), nullable=True, server_default='0.0'))


def downgrade():
    op.drop_column('artikel', 'reinalkohol_liter')
    op.drop_column('artikel', 'volumen_liter')
    op.drop_column('artikel', 'typ')
