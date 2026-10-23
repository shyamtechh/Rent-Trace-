from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email_lower", text("lower(email)"), unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), server_default=func.now(), onupdate=func.now())


class Locality(Base):
    __tablename__ = "localities"
    __table_args__ = (
        UniqueConstraint("name", "city", "state", "country", name="uq_locality_name_location"),
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)", name="ck_locality_latitude"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)", name="ck_locality_longitude"),
        Index("ix_localities_name_city", "name", "city"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    city: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    properties: Mapped[list["Property"]] = relationship(back_populates="locality")
    rental_prices: Mapped[list["RentalPrice"]] = relationship(back_populates="locality")
    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="locality")
    factors: Mapped[list["LocalityFactor"]] = relationship(back_populates="locality")
    predictions: Mapped[list["Prediction"]] = relationship(back_populates="locality")
    analytics_snapshots: Mapped[list["AnalyticsSnapshot"]] = relationship(back_populates="locality")


class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        CheckConstraint("bedrooms IS NULL OR bedrooms >= 0", name="ck_property_bedrooms"),
        CheckConstraint("bathrooms IS NULL OR bathrooms >= 0", name="ck_property_bathrooms"),
        CheckConstraint("area_sqft IS NULL OR area_sqft > 0", name="ck_property_area"),
        CheckConstraint("floor IS NULL OR floor >= 0", name="ck_property_floor"),
        CheckConstraint("total_floors IS NULL OR total_floors > 0", name="ck_property_total_floors"),
        Index("ix_properties_locality_id", "locality_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    locality_id: Mapped[int] = mapped_column(ForeignKey("localities.id", ondelete="RESTRICT"), nullable=False)
    property_type: Mapped[str] = mapped_column(String(80), nullable=False)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    area_sqft: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    furnishing: Mapped[str | None] = mapped_column(String(80))
    floor: Mapped[int | None] = mapped_column(Integer)
    total_floors: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    locality: Mapped[Locality] = relationship(back_populates="properties")
    rental_prices: Mapped[list["RentalPrice"]] = relationship(back_populates="property")


class DataSource(Base):
    __tablename__ = "data_sources"
    __table_args__ = (UniqueConstraint("source_name", "dataset_name", name="uq_data_source_dataset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(180), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    dataset_name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rental_prices: Mapped[list["RentalPrice"]] = relationship(back_populates="source")


class RentalPrice(Base):
    __tablename__ = "rental_prices"
    __table_args__ = (
        CheckConstraint("rent >= 0", name="ck_rental_rent_nonnegative"),
        CheckConstraint("security_deposit IS NULL OR security_deposit >= 0", name="ck_rental_deposit_nonnegative"),
        CheckConstraint("price_per_sqft IS NULL OR price_per_sqft >= 0", name="ck_rental_per_sqft_nonnegative"),
        UniqueConstraint("property_id", "observation_date", "source_id", name="uq_rental_observation_source"),
        Index("ix_rental_prices_locality_date", "locality_id", "observation_date"),
        Index("ix_rental_prices_property_date", "property_id", "observation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="RESTRICT"), nullable=False)
    locality_id: Mapped[int] = mapped_column(ForeignKey("localities.id", ondelete="RESTRICT"), nullable=False)
    rent: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    security_deposit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_per_sqft: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    observation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    property: Mapped[Property] = relationship(back_populates="rental_prices")
    locality: Mapped[Locality] = relationship(back_populates="rental_prices")
    source: Mapped[DataSource] = relationship(back_populates="rental_prices")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint("locality_id", "observation_date", name="uq_price_history_locality_date"),
        CheckConstraint("sample_size IS NULL OR sample_size >= 0", name="ck_price_history_sample_size"),
        Index("ix_price_history_locality_date", "locality_id", "observation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    locality_id: Mapped[int] = mapped_column(ForeignKey("localities.id", ondelete="RESTRICT"), nullable=False)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    average_property_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    average_rent: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    average_price_per_sqft: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    median_rent: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    median_price: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    sample_size: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    locality: Mapped[Locality] = relationship(back_populates="price_history")


class LocalityFactor(Base):
    __tablename__ = "locality_factors"
    __table_args__ = (
        UniqueConstraint("locality_id", "observation_date", name="uq_locality_factor_date"),
        Index("ix_locality_factors_locality_date", "locality_id", "observation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    locality_id: Mapped[int] = mapped_column(ForeignKey("localities.id", ondelete="RESTRICT"), nullable=False)
    observation_date: Mapped[date] = mapped_column(Date, nullable=False)
    population: Mapped[int | None] = mapped_column(Integer)
    population_growth: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    migration_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    infrastructure_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    employment_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    education_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    healthcare_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    transport_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    construction_cost_index: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    economic_activity_index: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    locality: Mapped[Locality] = relationship(back_populates="factors")


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        CheckConstraint("confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)", name="ck_prediction_confidence"),
        Index("ix_predictions_locality_forecast", "locality_id", "forecast_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    locality_id: Mapped[int] = mapped_column(ForeignKey("localities.id", ondelete="RESTRICT"), nullable=False)
    prediction_type: Mapped[str] = mapped_column(String(100), nullable=False)
    predicted_value: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    prediction_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(180), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    locality: Mapped[Locality] = relationship(back_populates="predictions")


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    training_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(180), nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    parameters: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    feature_importance: Mapped[list["FeatureImportance"]] = relationship(back_populates="model_run")


class FeatureImportance(Base):
    __tablename__ = "feature_importance"
    __table_args__ = (
        UniqueConstraint("model_run_id", "feature_name", "importance_method", name="uq_feature_importance_run_feature"),
        CheckConstraint("importance_value >= 0", name="ck_feature_importance_nonnegative"),
        Index("ix_feature_importance_model_run_id", "model_run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model_run_id: Mapped[int] = mapped_column(ForeignKey("model_runs.id", ondelete="RESTRICT"), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(180), nullable=False)
    importance_value: Mapped[Decimal] = mapped_column(Numeric(14, 8), nullable=False)
    importance_method: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    model_run: Mapped[ModelRun] = relationship(back_populates="feature_importance")


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        UniqueConstraint("locality_id", "snapshot_date", "metric_name", name="uq_analytics_snapshot_metric"),
        Index("ix_analytics_snapshots_locality_date", "locality_id", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    locality_id: Mapped[int] = mapped_column(ForeignKey("localities.id", ondelete="RESTRICT"), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(180), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    metric_unit: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    locality: Mapped[Locality] = relationship(back_populates="analytics_snapshots")


class LandParcel(Base):
    __tablename__ = "land_parcels"
    __table_args__ = (
        UniqueConstraint("source_name", "source_feature_id", name="uq_land_parcel_source_feature"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_land_parcel_latitude"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_land_parcel_longitude"),
        Index("ix_land_parcels_coordinates", "latitude", "longitude"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_feature_id: Mapped[str] = mapped_column(String(120), nullable=False)
    district: Mapped[str | None] = mapped_column(String(150))
    mandal: Mapped[str | None] = mapped_column(String(150))
    village: Mapped[str | None] = mapped_column(String(150))
    parcel_reference: Mapped[str | None] = mapped_column(String(150))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    geometry: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GovernmentLandRate(Base):
    __tablename__ = "government_land_rates"
    __table_args__ = (
        CheckConstraint("rate_per_sq_yard > 0", name="ck_government_land_rate_positive"),
        Index("ix_government_land_rates_area_date", "district", "mandal", "village", "rate_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id: Mapped[int | None] = mapped_column(ForeignKey("land_parcels.id", ondelete="RESTRICT"))
    district: Mapped[str | None] = mapped_column(String(150))
    mandal: Mapped[str | None] = mapped_column(String(150))
    village: Mapped[str | None] = mapped_column(String(150))
    survey_subdivision: Mapped[str | None] = mapped_column(String(150))
    rate_per_sq_yard: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    rate_unit: Mapped[str] = mapped_column(String(30), nullable=False, default="INR/sq_yd", server_default="INR/sq_yd")
    property_category: Mapped[str] = mapped_column(String(80), nullable=False, default="Unspecified", server_default="Unspecified")
    source_type: Mapped[str] = mapped_column(String(60), nullable=False, default="government_guideline_rate", server_default="government_guideline_rate")
    survey_subdivision_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    rate_date: Mapped[date] = mapped_column(Date, nullable=False)
    verified_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LandValuation(Base):
    __tablename__ = "land_valuations"
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_land_valuations_latitude"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_land_valuations_longitude"),
        CheckConstraint("area_square_feet > 0", name="ck_land_valuations_area_sqft"),
        CheckConstraint("area_square_yards > 0", name="ck_land_valuations_area_sqyd"),
        CheckConstraint("rate_per_sq_yard > 0", name="ck_land_valuations_rate_positive"),
        CheckConstraint("total_value >= 0", name="ck_land_valuations_total_nonnegative"),
        Index("ix_land_valuations_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parcel_id: Mapped[int | None] = mapped_column(ForeignKey("land_parcels.id", ondelete="RESTRICT"))
    rate_id: Mapped[int] = mapped_column(ForeignKey("government_land_rates.id", ondelete="RESTRICT"), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    area_square_feet: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    area_square_yards: Mapped[Decimal] = mapped_column(Numeric(16, 4), nullable=False)
    area_method: Mapped[str] = mapped_column(String(120), nullable=False)
    rate_per_sq_yard: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    estimation_method: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence_note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
