from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import DataSource, Locality, LocalityFactor, PriceHistory, Property, RentalPrice
from app.schemas import LocalityCreate, PropertyCreate, RentalCreate

REQUIRED_COLUMNS = {
    "localities": {"name", "city", "state", "country"},
    "properties": {"locality_id", "property_type"},
    "rentals": {"property_id", "locality_id", "rent", "observation_date", "source_id"},
    "price_history": {"locality_id", "observation_date"},
    "locality_factors": {"locality_id", "observation_date"},
}


def _optional_decimal(value: str, field: str) -> Decimal | None:
    if value == "":
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be numeric.") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite number.")
    return parsed


def _optional_int(value: str, field: str) -> int | None:
    if value == "":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an integer.") from exc
    return parsed


def _required_date(value: str, field: str = "observation_date") -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format.") from exc


def _make_record(entity: str, row: dict[str, str], db: Session):
    if entity == "localities":
        payload = LocalityCreate.model_validate(row)
        return Locality(**payload.model_dump()), (
            func.lower(Locality.name) == payload.name.lower(),
            func.lower(Locality.city) == payload.city.lower(),
            func.lower(Locality.state) == payload.state.lower(),
            func.lower(Locality.country) == payload.country.lower(),
        )

    if entity == "properties":
        payload = PropertyCreate.model_validate({
            "locality_id": _optional_int(row["locality_id"], "locality_id"),
            "property_type": row["property_type"],
            "bedrooms": _optional_int(row.get("bedrooms", ""), "bedrooms"),
            "bathrooms": _optional_decimal(row.get("bathrooms", ""), "bathrooms"),
            "area_sqft": _optional_decimal(row.get("area_sqft", ""), "area_sqft"),
            "furnishing": row.get("furnishing") or None,
            "floor": _optional_int(row.get("floor", ""), "floor"),
            "total_floors": _optional_int(row.get("total_floors", ""), "total_floors"),
        })
        if db.get(Locality, payload.locality_id) is None:
            raise ValueError(f"Unknown locality_id {payload.locality_id}.")
        return Property(**payload.model_dump()), (
            Property.locality_id == payload.locality_id,
            Property.property_type == payload.property_type,
            Property.bedrooms == payload.bedrooms,
            Property.bathrooms == payload.bathrooms,
            Property.area_sqft == payload.area_sqft,
            Property.furnishing == payload.furnishing,
            Property.floor == payload.floor,
            Property.total_floors == payload.total_floors,
        )

    if entity == "rentals":
        payload = RentalCreate.model_validate({
            "property_id": _optional_int(row["property_id"], "property_id"),
            "locality_id": _optional_int(row["locality_id"], "locality_id"),
            "rent": _optional_decimal(row["rent"], "rent"),
            "security_deposit": _optional_decimal(row.get("security_deposit", ""), "security_deposit"),
            "price_per_sqft": _optional_decimal(row.get("price_per_sqft", ""), "price_per_sqft"),
            "observation_date": _required_date(row["observation_date"]),
            "source_id": _optional_int(row["source_id"], "source_id"),
        })
        property_record = db.get(Property, payload.property_id)
        if property_record is None:
            raise ValueError(f"Unknown property_id {payload.property_id}.")
        if property_record.locality_id != payload.locality_id:
            raise ValueError("locality_id must match the property's locality.")
        if db.get(DataSource, payload.source_id) is None:
            raise ValueError(f"Unknown source_id {payload.source_id}.")
        return RentalPrice(**payload.model_dump()), (
            RentalPrice.property_id == payload.property_id,
            RentalPrice.observation_date == payload.observation_date,
            RentalPrice.source_id == payload.source_id,
        )

    locality_id = _optional_int(row["locality_id"], "locality_id")
    if locality_id is None or db.get(Locality, locality_id) is None:
        raise ValueError(f"Unknown locality_id {locality_id}.")
    observation_date = _required_date(row["observation_date"])

    if entity == "price_history":
        values = {
            field: _optional_decimal(row.get(field, ""), field)
            for field in (
                "average_property_price",
                "average_rent",
                "average_price_per_sqft",
                "median_rent",
                "median_price",
            )
        }
        values["sample_size"] = _optional_int(row.get("sample_size", ""), "sample_size")
        if all(value is None for value in values.values()):
            raise ValueError("At least one price statistic or sample_size is required.")
        record = PriceHistory(locality_id=locality_id, observation_date=observation_date, **values)
        return record, (PriceHistory.locality_id == locality_id, PriceHistory.observation_date == observation_date)

    fields = (
        "population",
        "population_growth",
        "migration_rate",
        "infrastructure_score",
        "employment_score",
        "education_score",
        "healthcare_score",
        "transport_score",
        "construction_cost_index",
        "economic_activity_index",
    )
    values = {
        field: (_optional_int(row.get(field, ""), field) if field == "population" else _optional_decimal(row.get(field, ""), field))
        for field in fields
    }
    if all(value is None for value in values.values()):
        raise ValueError("At least one locality factor is required.")
    record = LocalityFactor(locality_id=locality_id, observation_date=observation_date, **values)
    return record, (LocalityFactor.locality_id == locality_id, LocalityFactor.observation_date == observation_date)


def import_csv(db: Session, entity: str, contents: bytes) -> dict:
    if entity not in REQUIRED_COLUMNS:
        raise ValueError(f"Unsupported entity '{entity}'.")
    if not contents:
        raise ValueError("CSV file is empty.")

    try:
        frame = pd.read_csv(BytesIO(contents), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError(f"Could not parse CSV: {exc}") from exc

    total_rows = len(frame.index)
    missing_columns = sorted(REQUIRED_COLUMNS[entity] - set(frame.columns))
    if missing_columns:
        return {
            "total_rows": total_rows,
            "successful_rows": 0,
            "failed_rows": total_rows,
            "errors": [{"row": 1, "error": f"Missing required columns: {', '.join(missing_columns)}."}],
        }

    successful_rows = 0
    errors = []
    seen_keys: set[tuple] = set()

    for index, values in enumerate(frame.to_dict(orient="records"), start=2):
        row = {key: str(value).strip() for key, value in values.items()}
        try:
            missing_values = sorted(column for column in REQUIRED_COLUMNS[entity] if not row.get(column))
            if missing_values:
                raise ValueError(f"Required values are missing: {', '.join(missing_values)}.")
            record, duplicate_filters = _make_record(entity, row, db)
            if duplicate_filters:
                ignored_columns = {"id", "created_at", "updated_at"}
                key = tuple(
                    str(getattr(record, column.name)).lower()
                    for column in record.__table__.columns
                    if column.name not in ignored_columns
                )
                if key in seen_keys or db.scalar(select(record.__class__.id).where(*duplicate_filters)) is not None:
                    raise ValueError("Duplicate record already exists.")
                seen_keys.add(key)
            with db.begin_nested():
                db.add(record)
                db.flush()
            successful_rows += 1
        except (ValueError, TypeError, InvalidOperation) as exc:
            errors.append({"row": index, "error": str(exc)})
        except IntegrityError:
            errors.append({"row": index, "error": "Record violates a database constraint or duplicates an existing record."})

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("Import transaction failed because of a database constraint.")

    return {
        "total_rows": total_rows,
        "successful_rows": successful_rows,
        "failed_rows": len(errors),
        "errors": errors,
    }
