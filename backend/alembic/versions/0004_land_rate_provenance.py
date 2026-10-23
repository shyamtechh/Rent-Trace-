"""Record rate units, category, and survey verification provenance.

Revision ID: 0004_land_rate_provenance
Revises: 0003_land_valuation_sources
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_land_rate_provenance"
down_revision = "0003_land_valuation_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("government_land_rates")
    }
    if "rate_unit" not in columns:
        op.add_column(
            "government_land_rates",
            sa.Column(
                "rate_unit",
                sa.String(length=30),
                nullable=False,
                server_default="INR/sq_yd",
            ),
        )
    if "property_category" not in columns:
        op.add_column(
            "government_land_rates",
            sa.Column(
                "property_category",
                sa.String(length=80),
                nullable=False,
                server_default="Unspecified",
            ),
        )
    if "source_type" not in columns:
        op.add_column(
            "government_land_rates",
            sa.Column(
                "source_type",
                sa.String(length=60),
                nullable=False,
                server_default="government_guideline_rate",
            ),
        )
    if "survey_subdivision_verified" not in columns:
        op.add_column(
            "government_land_rates",
            sa.Column(
                "survey_subdivision_verified",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrades are disabled to protect recorded land-rate provenance. "
        "Create and verify a backup before planning any manual rollback."
    )
