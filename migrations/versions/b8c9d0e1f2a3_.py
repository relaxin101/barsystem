"""Zeitspalten auf timestamptz umstellen

Die App hat bisher naive UTC-Werte gespeichert (der Container läuft in UTC).
Mit timestamptz rechnet Postgres sie je Session in APP_TIMEZONE um, dadurch
stimmen auch gespeicherte Berichte, ohne dass ihr SQL geändert werden muss.
Das explizite 'UTC' macht die Migration unabhängig von der Session-Zeitzone.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-30 12:00:00.000000

"""
from alembic import op

revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None

COLUMNS = [
    ('buchung', 'zeitstempel'),
    ('buchung', 'storno_updated_at'),
    ('abrechnung', 'zeitstempel'),
    ('aussendung', 'last_run'),
]


def upgrade():
    for table, column in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE TIMESTAMP WITH TIME ZONE USING {column} AT TIME ZONE 'UTC'"
        )


def downgrade():
    for table, column in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE TIMESTAMP WITHOUT TIME ZONE USING {column} AT TIME ZONE 'UTC'"
        )
