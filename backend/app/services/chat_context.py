import math
import re
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Locality,
    LocalityFactor,
    Prediction,
    PriceHistory,
    Property,
    RentalPrice,
)
from app.schemas import ChatRequest
from app.services.renttrace_dataset import (
    get_locality_land_price_history,
    get_locality_land_rate,
    get_locality_records,
    get_processed_locality_names,
)

_MAX_LOCALITIES = 4
_MAX_HISTORY_MESSAGES = 6
_MAX_HISTORY_CHARS = 800
_SUPPORTED_FACTORS = (
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


def _number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, (int, float)) and math.isfinite(value):
        return value
    return None


def _mentioned_localities(message: str, names: list[str]) -> list[str]:
    normalized_message = message.casefold()
    matches = [
        name for name in names
        if re.search(
            rf"(?<![\w]){re.escape(name.casefold())}(?![\w])",
            normalized_message,
        )
    ]
    return sorted(set(matches), key=lambda name: (-len(name), name.casefold()))[
        :_MAX_LOCALITIES
    ]


def _workbook_rents(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    annual_by_bhk: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    forecast_by_bhk: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        bedroom_count = record.get("bedroom_count")
        if not isinstance(bedroom_count, int) or bedroom_count <= 0:
            continue
        for row in record.get("historical_prices", []):
            year = row.get("year")
            value = _number(row.get("value"))
            if isinstance(year, int) and value is not None and value > 0:
                annual_by_bhk[bedroom_count][year].append(value)
        for row in record.get("predicted_prices", []):
            year = row.get("year")
            value = _number(row.get("value"))
            if isinstance(year, int) and value is not None and value > 0:
                forecast_by_bhk[bedroom_count][year].append(value)

    if not annual_by_bhk and not forecast_by_bhk:
        return None

    rentals: dict[str, Any] = {}
    for bhk, yearly in sorted(annual_by_bhk.items()):
        annual_averages = [
            {"year": year, "average_monthly_rent": sum(values) / len(values)}
            for year, values in sorted(yearly.items())
            if values
        ]
        trend_percent = None
        if len(annual_averages) >= 2:
            first_value = annual_averages[0]["average_monthly_rent"]
            latest_value = annual_averages[-1]["average_monthly_rent"]
            if first_value > 0:
                trend_percent = (latest_value - first_value) / first_value * 100
        rentals[f"{bhk}_bhk"] = {
            "latest": annual_averages[-1] if annual_averages else None,
            "history": annual_averages[-10:],
            "change_percent_first_to_latest": trend_percent,
            "change_period": (
                f"{annual_averages[0]['year']} to {annual_averages[-1]['year']}"
                if len(annual_averages) >= 2
                else None
            ),
        }
    forecasts = {
        f"{bhk}_bhk": [
            {"year": year, "predicted_monthly_rent": sum(values) / len(values)}
            for year, values in sorted(yearly.items())
            if values
        ]
        for bhk, yearly in sorted(forecast_by_bhk.items())
    }
    return {
        "source": "processed RentTrace workbook",
        "record_count": len(records),
        "rentals_by_bhk": rentals,
        "predictions_by_bhk": forecasts,
    }


def _database_locality_data(db: Session, locality: Locality) -> dict[str, Any]:
    rental_rows = db.execute(
        select(
            Property.bedrooms,
            func.avg(RentalPrice.rent),
            func.count(RentalPrice.id),
            func.max(RentalPrice.observation_date),
        )
        .join(RentalPrice, RentalPrice.property_id == Property.id)
        .where(
            RentalPrice.locality_id == locality.id,
            RentalPrice.deleted_at.is_(None),
        )
        .group_by(Property.bedrooms)
        .order_by(Property.bedrooms)
    ).all()
    rentals_by_bhk = {
        f"{row.bedrooms}_bhk": {
            "average_monthly_rent": _number(row[1]),
            "sample_count": row[2],
            "latest_observation": row[3].isoformat() if row[3] else None,
        }
        for row in rental_rows
        if isinstance(row.bedrooms, int) and row.bedrooms > 0
    }

    history = db.scalars(
        select(PriceHistory)
        .where(PriceHistory.locality_id == locality.id)
        .order_by(PriceHistory.observation_date)
        .limit(50)
    ).all()
    price_history = [
        {
            "date": item.observation_date.isoformat(),
            "average_rent": _number(item.average_rent),
            "average_property_price": _number(item.average_property_price),
            "average_price_per_sqft": _number(item.average_price_per_sqft),
            "median_rent": _number(item.median_rent),
            "sample_size": item.sample_size,
        }
        for item in history
    ]
    rent_history = [
        {"date": item.observation_date.isoformat(), "average_rent": _number(item.average_rent)}
        for item in history
        if item.average_rent is not None
    ]
    rent_change_percent = None
    if len(rent_history) >= 2 and rent_history[0]["average_rent"]:
        rent_change_percent = (
            (rent_history[-1]["average_rent"] - rent_history[0]["average_rent"])
            / rent_history[0]["average_rent"]
            * 100
        )

    factor = db.scalar(
        select(LocalityFactor)
        .where(LocalityFactor.locality_id == locality.id)
        .order_by(LocalityFactor.observation_date.desc())
        .limit(1)
    )
    factors = (
        {
            "observation_date": factor.observation_date.isoformat(),
            **{
                name: _number(getattr(factor, name))
                for name in _SUPPORTED_FACTORS
                if getattr(factor, name) is not None
            },
        }
        if factor
        else None
    )

    predictions = db.scalars(
        select(Prediction)
        .where(Prediction.locality_id == locality.id)
        .order_by(Prediction.forecast_date)
        .limit(20)
    ).all()
    forecast = [
        {
            "type": item.prediction_type,
            "value": _number(item.predicted_value),
            "forecast_date": item.forecast_date.isoformat(),
            "model": item.model_name,
            "version": item.model_version,
            "confidence": _number(item.confidence_score),
        }
        for item in predictions
    ]
    return {
        "location": {
            "name": locality.name,
            "city": locality.city,
            "state": locality.state,
            "country": locality.country,
        },
        "rentals_by_bhk": rentals_by_bhk,
        "price_history": price_history,
        "average_rent_change_percent_first_to_latest": rent_change_percent,
        "latest_supported_factors": factors,
        "forecasts": forecast,
        "sources": ["RentTrace PostgreSQL"],
    }


def _database_rental_aggregates(db: Session) -> dict[str, Any]:
    rows = db.execute(
        select(
            Locality.name,
            Property.bedrooms,
            func.avg(RentalPrice.rent),
            func.count(RentalPrice.id),
            func.max(RentalPrice.observation_date),
        )
        .join(RentalPrice, RentalPrice.locality_id == Locality.id)
        .join(Property, RentalPrice.property_id == Property.id)
        .where(RentalPrice.deleted_at.is_(None))
        .group_by(Locality.name, Property.bedrooms)
        .order_by(Locality.name, Property.bedrooms)
    ).all()
    by_bhk: dict[str, dict[str, float | int | str | None]] = {}
    localities: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row.bedrooms, int) or row.bedrooms <= 0:
            continue
        rent = _number(row[2])
        if rent is None:
            continue
        label = f"{row.bedrooms}_bhk"
        count = int(row[3])
        latest = row[4].isoformat() if row[4] else None
        current = by_bhk.setdefault(label, {"weighted_total": 0.0, "sample_count": 0})
        current["weighted_total"] = float(current["weighted_total"]) + rent * count
        current["sample_count"] = int(current["sample_count"]) + count
        localities.setdefault(row.name, {})[label] = {
            "average_monthly_rent": rent,
            "sample_count": count,
            "latest_observation": latest,
        }
    overall = {
        label: {
            "average_monthly_rent": data["weighted_total"] / data["sample_count"],
            "sample_count": data["sample_count"],
        }
        for label, data in by_bhk.items()
        if data["sample_count"]
    }
    return {
        "overall_by_bhk": overall,
        "by_locality": localities,
        "source": "RentTrace PostgreSQL",
    }


def build_renttrace_context(
    db: Session,
    request: ChatRequest,
) -> dict[str, Any]:
    database_names = list(db.scalars(select(Locality.name).distinct()).all())
    try:
        workbook_names = get_processed_locality_names()
        workbook_available = True
    except (FileNotFoundError, OSError, ValueError):
        workbook_names = []
        workbook_available = False

    all_names = sorted(
        set(database_names + workbook_names),
        key=lambda name: (-len(name), name.casefold()),
    )
    current_mentions = _mentioned_localities(request.message, all_names)
    history_text = " ".join(
        message.content[:_MAX_HISTORY_CHARS]
        for message in request.history[-_MAX_HISTORY_MESSAGES:]
        if message.role == "user"
    )
    history_mentions = _mentioned_localities(history_text, all_names)
    mentioned = list(dict.fromkeys(current_mentions + history_mentions))[
        :_MAX_LOCALITIES
    ]
    selected_name = (
        request.selected_context.locality_name.strip()
        if request.selected_context and request.selected_context.locality_name
        else None
    )
    if not mentioned and selected_name:
        mentioned = _mentioned_localities(selected_name, all_names)
        if not mentioned and selected_name.strip():
            mentioned = [selected_name.strip()]

    needs_citywide_rent_data = (
        not mentioned
        and re.search(
            r"\b(average|compare|comparison|lower|lowest|cheaper|cheapest)\b",
            request.message,
            re.IGNORECASE,
        )
        and re.search(r"\b(rent|rental|bhk|bedroom)\b", request.message, re.IGNORECASE)
    )
    rental_aggregates = (
        _database_rental_aggregates(db) if needs_citywide_rent_data else None
    )

    locality_data: list[dict[str, Any]] = []
    sources: set[str] = set()
    if rental_aggregates:
        sources.add(rental_aggregates["source"])
    for name in mentioned[:_MAX_LOCALITIES]:
        normalized = name.casefold()
        database_localities = db.scalars(
            select(Locality)
            .where(func.lower(Locality.name) == normalized)
            .order_by(Locality.city, Locality.state)
        ).all()
        if database_localities:
            for locality in database_localities[:2]:
                data = _database_locality_data(db, locality)
                locality_data.append(data)
                sources.update(data["sources"])

        if workbook_available:
            try:
                records = get_locality_records(name)
                workbook_data = _workbook_rents(records)
                if workbook_data:
                    existing = next(
                        (
                            item for item in locality_data
                            if item["location"]["name"].casefold() == normalized
                        ),
                        None,
                    )
                    if existing:
                        existing["workbook_rental_data"] = workbook_data
                        existing["sources"].append(workbook_data["source"])
                    else:
                        locality_data.append({
                            "location": {"name": name, "city": "Hyderabad", "state": "Telangana"},
                            "workbook_rental_data": workbook_data,
                            "sources": [workbook_data["source"]],
                        })
                    sources.add(workbook_data["source"])
            except (FileNotFoundError, OSError, ValueError):
                workbook_available = False

        try:
            land_rate = get_locality_land_rate(name)
            land_history = get_locality_land_price_history(name)
        except (FileNotFoundError, OSError, ValueError):
            land_rate = None
            land_history = []
        data = next(
            (
                item for item in locality_data
                if item["location"]["name"].casefold() == normalized
            ),
            None,
        )
        if data:
            data["land_price_data"] = {
                "guideline_or_market_rate": (
                    land_rate if land_rate and land_rate.get("available") else None
                ),
                "historical_land_prices": land_history,
                "availability": "available" if land_history else "unavailable",
            }
            if land_rate and land_rate.get("available"):
                sources.add("processed RentTrace land-price fields")

    selected_context = None
    if request.selected_context:
        selected_context = {
            "locality_name": request.selected_context.locality_name,
            "latitude": _number(request.selected_context.latitude),
            "longitude": _number(request.selected_context.longitude),
            "polygon_area_square_feet": _number(
                request.selected_context.polygon_area_square_feet
            ),
            "area_method": request.selected_context.area_method,
            "notice": (
                "This is user-selected map context, not a verified parcel boundary, "
                "official survey number, or independently measured cadastral area."
            ),
        }

    return {
        "localities": locality_data,
        "rental_aggregates": rental_aggregates,
        "selected_map_context": selected_context,
        "data_availability": {
            "processed_workbook_available": workbook_available,
            "land_price_columns_available": any(
                item.get("land_price_data", {}).get("availability") == "available"
                for item in locality_data
            ),
        },
        "sources": sorted(sources),
    }
