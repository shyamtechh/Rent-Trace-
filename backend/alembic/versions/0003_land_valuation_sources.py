"""Add provenance-aware parcel and government-rate valuations.

Revision ID: 0003_land_valuation_sources
Revises: 0002_preserve_rental_history
"""
from alembic import op
import sqlalchemy as sa

from app.models import JSON_DOCUMENT

revision = "0003_land_valuation_sources"
down_revision = "0002_preserve_rental_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "land_parcels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("source_feature_id", sa.String(length=120), nullable=False),
        sa.Column("district", sa.String(length=150)),
        sa.Column("mandal", sa.String(length=150)),
        sa.Column("village", sa.String(length=150)),
        sa.Column("parcel_reference", sa.String(length=150)),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("attributes", JSON_DOCUMENT, nullable=False),
        sa.Column("geometry", JSON_DOCUMENT),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_name", "source_feature_id", name="uq_land_parcel_source_feature"),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_land_parcel_latitude"),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_land_parcel_longitude"),
    )
    op.create_index("ix_land_parcels_coordinates", "land_parcels", ["latitude", "longitude"])
    op.create_table(
        "government_land_rates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parcel_id", sa.Integer(), sa.ForeignKey("land_parcels.id", ondelete="RESTRICT")),
        sa.Column("district", sa.String(length=150)),
        sa.Column("mandal", sa.String(length=150)),
        sa.Column("village", sa.String(length=150)),
        sa.Column("survey_subdivision", sa.String(length=150)),
        sa.Column("rate_per_sq_yard", sa.Numeric(16, 2), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("verified_date", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("verification_method", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("rate_per_sq_yard > 0", name="ck_government_land_rate_positive"),
    )
    op.create_index(
        "ix_government_land_rates_area_date",
        "government_land_rates",
        ["district", "mandal", "village", "rate_date"],
    )
    op.create_table(
        "land_valuations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parcel_id", sa.Integer(), sa.ForeignKey("land_parcels.id", ondelete="RESTRICT")),
        sa.Column("rate_id", sa.Integer(), sa.ForeignKey("government_land_rates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("area_square_feet", sa.Numeric(16, 4), nullable=False),
        sa.Column("area_square_yards", sa.Numeric(16, 4), nullable=False),
        sa.Column("area_method", sa.String(length=120), nullable=False),
        sa.Column("rate_per_sq_yard", sa.Numeric(16, 2), nullable=False),
        sa.Column("total_value", sa.Numeric(20, 2), nullable=False),
        sa.Column("estimation_method", sa.String(length=120), nullable=False),
        sa.Column("confidence_note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_land_valuations_latitude"),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_land_valuations_longitude"),
        sa.CheckConstraint("area_square_feet > 0", name="ck_land_valuations_area_sqft"),
        sa.CheckConstraint("area_square_yards > 0", name="ck_land_valuations_area_sqyd"),
        sa.CheckConstraint("rate_per_sq_yard > 0", name="ck_land_valuations_rate_positive"),
        sa.CheckConstraint("total_value >= 0", name="ck_land_valuations_total_nonnegative"),
    )
    op.create_index("ix_land_valuations_created_at", "land_valuations", ["created_at"])


def downgrade() -> None:
    raise RuntimeError(
        "Destructive downgrades are disabled to protect user-entered valuation records. "
        "Create and verify a backup before planning any manual rollback."
    )
