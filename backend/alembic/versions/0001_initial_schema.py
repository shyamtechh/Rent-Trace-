"""Create the RentTrace schema and safely upgrade legacy users.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa

from app.database import Base
import app.models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        actual_columns = {column["name"] for column in inspector.get_columns(table.name)}
        expected_columns = {column.name for column in table.columns}
        allowed_user_additions = {"role", "is_active", "created_at", "updated_at"}
        missing_columns = expected_columns - actual_columns
        if table.name == "users":
            missing_columns -= allowed_user_additions
        if missing_columns:
            raise RuntimeError(
                f"Existing table '{table.name}' is missing columns {sorted(missing_columns)}. "
                "Migration stopped without dropping or rewriting that table; back it up and plan a data migration first."
            )

    if "users" in existing_tables:
        duplicate_emails = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM ("
                "SELECT LOWER(email) FROM users GROUP BY LOWER(email) HAVING COUNT(*) > 1"
                ") AS duplicate_users"
            )
        ).scalar_one()
        if duplicate_emails:
            raise RuntimeError(
                "Existing users contain duplicate case-insensitive emails. "
                "Resolve those duplicates before applying this migration; no records were deleted."
            )

        columns = {column["name"] for column in inspector.get_columns("users")}
        if "role" not in columns:
            op.add_column("users", sa.Column("role", sa.String(length=30), nullable=False, server_default="user"))
        if "is_active" not in columns:
            op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "created_at" not in columns:
            op.add_column("users", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        if "updated_at" not in columns:
            updated_at_column = sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=bind.dialect.name == "sqlite",
                server_default=None if bind.dialect.name == "sqlite" else sa.text("CURRENT_TIMESTAMP"),
            )
            op.add_column("users", updated_at_column)
            if bind.dialect.name == "sqlite":
                op.execute(sa.text("UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))

    Base.metadata.create_all(bind=bind, checkfirst=True)

    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrades are disabled to protect user accounts and historical data. "
        "Create and verify a backup before planning any manual rollback."
    )
