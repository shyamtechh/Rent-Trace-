"""Add soft deletion to rental observations.

Revision ID: 0002_preserve_rental_history
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_preserve_rental_history"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("rental_prices")}
    if "deleted_at" not in columns:
        op.add_column("rental_prices", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrades are disabled to protect historical rental observations. "
        "Create and verify a backup before planning any manual rollback."
    )
