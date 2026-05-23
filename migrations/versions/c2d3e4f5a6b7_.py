"""rename storniert to storno+storno_updated_at

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-23

"""
from alembic import op
import sqlalchemy as sa

revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('buchung', sa.Column('storno', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('buchung', sa.Column('storno_updated_at', sa.DateTime(), nullable=True))

    # Bestandsdaten übertragen: storniert → storno + storno_updated_at
    op.execute("""
        UPDATE buchung
        SET storno = (storniert IS NOT NULL),
            storno_updated_at = storniert
    """)

    op.drop_column('buchung', 'storniert')


def downgrade():
    op.add_column('buchung', sa.Column('storniert', sa.DateTime(), nullable=True))

    op.execute("""
        UPDATE buchung
        SET storniert = storno_updated_at
        WHERE storno = true
    """)

    op.drop_column('buchung', 'storno_updated_at')
    op.drop_column('buchung', 'storno')
