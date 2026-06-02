"""add ranking_artikel and ranking_konfiguration

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-02

"""
import sqlalchemy as sa
from alembic import op

revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ranking_konfiguration',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stunden', sa.Integer(), nullable=False, server_default='24'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'ranking_artikel',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('artikel_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['artikel_id'], ['artikel.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('artikel_id'),
    )


def downgrade():
    op.drop_table('ranking_artikel')
    op.drop_table('ranking_konfiguration')
