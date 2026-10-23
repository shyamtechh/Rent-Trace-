import json
import math
import re
import tempfile
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[3]
RAW_DATASET_PATH = PROJECT_DIR / "data" / "raw" / "hyderabad_renttrace_dataset.xlsx"
PROCESSED_DATASET_PATH = PROJECT_DIR / "data" / "processed" / "hyderabad_renttrace_dataset.json"
VALIDATION_REPORT_PATH = PROJECT_DIR / "data" / "processed" / "hyderabad_renttrace_validation.json"
REQUIRED_FIELDS = ("ID", "Bedrooms", "Area", "Locality")
PRICE_COLUMN_PATTERN = re.compile(r"^Price_(\d{4})(?:_(Predicted))?$")
AREA_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square\s*feet)\s*$", re.IGNORECASE)
BEDROOM_PATTERN = re.compile(r"^\s*(\d+)\s*BHK\s+(.+?)\s*$", re.IGNORECASE)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


def _as_number(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _json_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _clean_locality(value: str) -> str:
    return " ".join(value.split())


def _discover_columns(columns: list[str]) -> dict[str, Any]:
    historical_prices: list[dict[str, Any]] = []
    predicted_prices: list[dict[str, Any]] = []
    invalid_price_year_fields: list[str] = []
    for column in columns:
        if not column.startswith("Price_"):
            continue
        match = PRICE_COLUMN_PATTERN.fullmatch(column)
        if not match:
            invalid_price_year_fields.append(column)
            continue
        year = int(match.group(1))
        if year < 1900 or year > 2200:
            invalid_price_year_fields.append(column)
            continue
        target = predicted_prices if match.group(2) else historical_prices
        target.append({"field": column, "year": year})

    latitude_fields = [
        field for field in columns
        if field.strip().casefold() in {"latitude", "lat"}
    ]
    longitude_fields = [
        field for field in columns
        if field.strip().casefold() in {"longitude", "lon", "lng"}
    ]
    land_price_fields = [
        field for field in columns
        if "land" in field.casefold() and any(term in field.casefold() for term in ("price", "value"))
    ]
    land_price_per_sqft_fields = [
        field for field in land_price_fields
        if "sqft" in field.casefold() or "sq ft" in field.casefold() or "square foot" in field.casefold()
    ]

    return {
        "historical_prices": sorted(historical_prices, key=lambda item: item["year"]),
        "predicted_prices": sorted(predicted_prices, key=lambda item: item["year"]),
        "invalid_price_year_fields": invalid_price_year_fields,
        "latitude_fields": latitude_fields,
        "longitude_fields": longitude_fields,
        "land_price_fields": land_price_fields,
        "land_price_per_sqft_fields": land_price_per_sqft_fields,
    }


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(value, temporary_file, ensure_ascii=False, indent=2, allow_nan=False)
            temporary_file.write("\n")
        temporary_path.replace(path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def process_dataset(
    source_path: Path = RAW_DATASET_PATH,
    processed_path: Path = PROCESSED_DATASET_PATH,
    report_path: Path = VALIDATION_REPORT_PATH,
) -> dict[str, Any]:
    source_path = Path(source_path)
    processed_path = Path(processed_path)
    report_path = Path(report_path)
    if source_path.resolve() == processed_path.resolve():
        raise ValueError("The processed output cannot overwrite the original workbook.")
    if not source_path.is_file():
        raise FileNotFoundError(f"Raw RentTrace workbook not found: {source_path}")

    with pd.ExcelFile(source_path) as workbook:
        sheet_name = workbook.sheet_names[0]
        frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
    columns = [str(column) for column in frame.columns]
    missing_required_columns = sorted(set(REQUIRED_FIELDS) - set(columns))
    if missing_required_columns:
        raise ValueError(
            "Workbook is missing required fields: " + ", ".join(missing_required_columns)
        )

    discovered = _discover_columns(columns)
    missing_value_counts = {
        column: int(frame[column].map(_is_missing).sum())
        for column in columns
    }
    exact_duplicate_rows = frame.duplicated(keep="first")
    def normalized_id(value: Any) -> str:
        numeric_id = _as_number(value)
        return str(int(numeric_id)) if numeric_id is not None and numeric_id.is_integer() else ""

    id_values = frame["ID"].map(normalized_id)
    duplicate_ids = id_values.ne("") & id_values.duplicated(keep=False)

    locality_variants: dict[str, set[str]] = defaultdict(set)
    for value in frame["Locality"]:
        if isinstance(value, str) and value.strip():
            clean_name = _clean_locality(value)
            locality_variants[clean_name.casefold()].add(value)
    inconsistent_locality_groups = {
        key: sorted(variants)
        for key, variants in locality_variants.items()
        if len(variants) > 1
    }

    normalized_keys: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, row in frame.iterrows():
        locality = row["Locality"]
        bedrooms = row["Bedrooms"]
        area = row["Area"]
        if not any(_is_missing(value) for value in (locality, bedrooms, area)):
            normalized_keys[
                (
                    _clean_locality(str(locality)).casefold(),
                    " ".join(str(bedrooms).split()).casefold(),
                    " ".join(str(area).split()).casefold(),
                )
            ].append(index)
    possible_duplicate_groups = [
        {
            "locality": str(frame.at[indexes[0], "Locality"]),
            "bedrooms": str(frame.at[indexes[0], "Bedrooms"]),
            "area": str(frame.at[indexes[0], "Area"]),
            "record_ids": [_json_value(frame.at[index, "ID"]) for index in indexes],
        }
        for indexes in normalized_keys.values()
        if len(indexes) > 1
    ]

    coordinate_fields_present = bool(discovered["latitude_fields"] or discovered["longitude_fields"])
    coordinates_available = bool(discovered["latitude_fields"] and discovered["longitude_fields"])
    if coordinate_fields_present and not coordinates_available:
        raise ValueError("Workbook must provide both latitude and longitude fields to validate coordinates.")

    records: list[dict[str, Any]] = []
    invalid_record_details: list[dict[str, Any]] = []
    normalized_localities: list[str] = []
    invalid_historical_price_values = 0
    invalid_predicted_price_values = 0
    invalid_land_price_values = 0
    invalid_latitude_values = 0
    invalid_longitude_values = 0
    for index, row in frame.iterrows():
        source_row = {column: _json_value(row[column]) for column in columns}
        issues: list[str] = []
        for field in REQUIRED_FIELDS:
            if _is_missing(row[field]):
                issues.append(f"{field} is missing.")

        raw_id = _as_number(row["ID"])
        if raw_id is None or not raw_id.is_integer() or raw_id <= 0:
            issues.append("ID must be a positive integer.")
        if bool(exact_duplicate_rows.iloc[index]):
            issues.append("Record duplicates an earlier complete row.")
        if bool(duplicate_ids.iloc[index]):
            issues.append("ID is duplicated in the workbook.")

        locality = _clean_locality(str(row["Locality"])) if not _is_missing(row["Locality"]) else ""
        if locality and locality.casefold() in inconsistent_locality_groups:
            issues.append("Locality has inconsistent spelling or whitespace variants.")
        if locality and locality != str(row["Locality"]):
            normalized_localities.append(str(row["Locality"]))

        bedroom_match = BEDROOM_PATTERN.fullmatch(str(row["Bedrooms"])) if not _is_missing(row["Bedrooms"]) else None
        if not bedroom_match or int(bedroom_match.group(1)) <= 0:
            issues.append("Bedrooms must include a positive BHK count and dwelling type.")

        area_match = AREA_PATTERN.fullmatch(str(row["Area"])) if not _is_missing(row["Area"]) else None
        area_sqft = float(area_match.group(1)) if area_match else None
        if area_sqft is None or area_sqft <= 0:
            issues.append("Area must contain a positive square-foot value.")

        historical_prices: list[dict[str, Any]] = []
        predicted_prices: list[dict[str, Any]] = []
        for price_column in discovered["historical_prices"] + discovered["predicted_prices"]:
            price = _as_number(row[price_column["field"]])
            if price is None or price <= 0:
                issues.append(f"{price_column['field']} must be a positive finite price.")
                if price_column in discovered["predicted_prices"]:
                    invalid_predicted_price_values += 1
                else:
                    invalid_historical_price_values += 1
                continue
            price_record = {
                "year": price_column["year"],
                "source_field": price_column["field"],
                "value": _json_value(price),
            }
            target = predicted_prices if price_column in discovered["predicted_prices"] else historical_prices
            target.append(price_record)

        for field in discovered["land_price_fields"]:
            price = _as_number(row[field])
            if price is None or price <= 0:
                issues.append(f"{field} must be a positive finite land price.")
                invalid_land_price_values += 1

        if coordinates_available:
            latitude_value = row[discovered["latitude_fields"][0]]
            longitude_value = row[discovered["longitude_fields"][0]]
            latitude = _as_number(latitude_value)
            longitude = _as_number(longitude_value)
            if not _is_missing(latitude_value) and (
                latitude is None or not -90 <= latitude <= 90
            ):
                issues.append("Latitude is outside the valid range.")
                invalid_latitude_values += 1
            if not _is_missing(longitude_value) and (
                longitude is None or not -180 <= longitude <= 180
            ):
                issues.append("Longitude is outside the valid range.")
                invalid_longitude_values += 1

        if issues:
            invalid_record_details.append({
                "row": int(index) + 2,
                "record_id": _json_value(row["ID"]),
                "errors": issues,
            })
            continue

        record = {
            "record_id": int(raw_id),
            "locality": locality,
            "bedrooms": str(row["Bedrooms"]).strip(),
            "bedroom_count": int(bedroom_match.group(1)),
            "property_type": bedroom_match.group(2).strip(),
            "area_sqft": _json_value(area_sqft),
            "historical_prices": historical_prices,
            "predicted_prices": predicted_prices,
            "source_fields": source_row,
        }
        records.append(record)

    invalid_year_fields = discovered["invalid_price_year_fields"]
    if invalid_year_fields:
        raise ValueError("Invalid or unrecognized year in price columns: " + ", ".join(invalid_year_fields))

    report = {
        "source_file": str(source_path),
        "sheet": sheet_name,
        "source_columns": columns,
        "total_records": int(len(frame)),
        "valid_records": len(records),
        "invalid_records": len(frame) - len(records),
        "unique_localities": int(frame["Locality"].dropna().map(
            lambda value: _clean_locality(str(value)).casefold()
        ).nunique()),
        "missing_fields": {
            field: count for field, count in missing_value_counts.items() if count > 0
        },
        "missing_value_counts": missing_value_counts,
        "duplicate_exact_rows": int(exact_duplicate_rows.sum()),
        "duplicate_id_rows": int(duplicate_ids.sum()),
        "possible_duplicate_key_rows": sum(len(group["record_ids"]) - 1 for group in possible_duplicate_groups),
        "possible_duplicate_key_groups": possible_duplicate_groups,
        "locality_normalization_count": len(normalized_localities),
        "locality_normalization_examples": sorted(set(normalized_localities)),
        "inconsistent_locality_name_groups": inconsistent_locality_groups,
        "invalid_price_year_fields": discovered["invalid_price_year_fields"],
        "available_locality_fields": ["Locality"] if "Locality" in columns else [],
        "available_area_fields": ["Area"] if "Area" in columns else [],
        "street_or_road_fields": [
            field for field in columns
            if any(term in field.casefold() for term in ("street", "road"))
        ],
        "latitude_fields": discovered["latitude_fields"],
        "longitude_fields": discovered["longitude_fields"],
        "coordinate_validation_available": coordinates_available,
        "invalid_latitude_values": invalid_latitude_values,
        "invalid_longitude_values": invalid_longitude_values,
        "land_price_fields": discovered["land_price_fields"],
        "land_price_per_sqft_fields": discovered["land_price_per_sqft_fields"],
        "invalid_land_price_values": invalid_land_price_values,
        "bedroom_fields": ["Bedrooms"] if "Bedrooms" in columns else [],
        "square_foot_fields": ["Area"] if "Area" in columns else [],
        "historical_price_fields": [item["field"] for item in discovered["historical_prices"]],
        "predicted_price_fields": [item["field"] for item in discovered["predicted_prices"]],
        "invalid_historical_price_values": invalid_historical_price_values,
        "invalid_predicted_price_values": invalid_predicted_price_values,
        "other_housing_fields": [
            field for field in columns
            if field not in {
                "ID",
                "Bedrooms",
                "Area",
                "Locality",
                *report_price_fields(discovered),
            }
        ],
        "invalid_record_details": invalid_record_details,
    }

    _atomic_write_json(processed_path, {"records": records, "validation": report})
    _atomic_write_json(report_path, report)
    return report


def report_price_fields(discovered: dict[str, Any]) -> set[str]:
    return {
        item["field"]
        for item in discovered["historical_prices"] + discovered["predicted_prices"]
    }


def _load_processed_dataset() -> dict[str, Any]:
    if not PROCESSED_DATASET_PATH.is_file():
        raise FileNotFoundError(
            "Processed RentTrace dataset is missing; run backend/process_renttrace_dataset.py."
        )
    payload = json.loads(PROCESSED_DATASET_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("Processed RentTrace dataset has an invalid format.")
    return payload


def get_locality_records(locality_name: str) -> list[dict[str, Any]]:
    if not locality_name.strip():
        return []
    payload = _load_processed_dataset()
    requested = " ".join(locality_name.split()).casefold()
    return [
        record for record in payload["records"]
        if isinstance(record, dict)
        and isinstance(record.get("locality"), str)
        and " ".join(record["locality"].split()).casefold() == requested
    ]


def get_processed_locality_names() -> list[str]:
    payload = _load_processed_dataset()
    names = {
        " ".join(record["locality"].split())
        for record in payload["records"]
        if isinstance(record, dict)
        and isinstance(record.get("locality"), str)
        and record["locality"].strip()
    }
    return sorted(names, key=str.casefold)


def get_locality_land_rate(
    locality_name: str,
    current_year: int | None = None,
) -> dict[str, Any]:
    if not locality_name.strip():
        return {
            "available": False,
            "message": "Land price data unavailable for this locality.",
            "source_field": None,
            "year": None,
            "value_per_sqft": None,
            "sample_count": 0,
        }

    payload = _load_processed_dataset()
    validation = payload.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("Processed RentTrace dataset has no validation metadata.")

    report_localities = [
        record for record in payload["records"]
        if isinstance(record, dict)
        and isinstance(record.get("locality"), str)
        and " ".join(record["locality"].split()).casefold()
        == " ".join(locality_name.split()).casefold()
    ]
    per_sqft_fields = validation.get("land_price_per_sqft_fields", [])
    if not isinstance(per_sqft_fields, list):
        raise ValueError("Processed dataset land-price field metadata is invalid.")

    year_limit = date.today().year if current_year is None else current_year
    if not isinstance(year_limit, int) or year_limit < 1900 or year_limit > 2200:
        raise ValueError("Current year must be a valid year.")

    field_candidates: list[tuple[int, str]] = []
    for field in per_sqft_fields:
        if not isinstance(field, str):
            continue
        if re.search(r"_predicted(?:_|$)", field, re.IGNORECASE):
            continue
        years = re.findall(r"(?<!\d)(\d{4})(?!\d)", field)
        if years:
            year = max(map(int, years))
            if year <= year_limit:
                field_candidates.append((year, field))
        else:
            field_candidates.append((0, field))

    if not report_localities or not field_candidates:
        return {
            "available": False,
            "message": "Land price data unavailable for this locality.",
            "source_field": None,
            "year": None,
            "value_per_sqft": None,
            "sample_count": 0,
        }

    latest_year = max(year for year, _ in field_candidates)
    selected_fields = [
        field for year, field in field_candidates if year == latest_year
    ]
    values = [
        number
        for record in report_localities
        for field in selected_fields
        if (number := _as_number(record.get("source_fields", {}).get(field))) is not None
        and number > 0
    ]
    if not values:
        return {
            "available": False,
            "message": "Land price data unavailable for this locality.",
            "source_field": selected_fields[0],
            "year": latest_year or None,
            "value_per_sqft": None,
            "sample_count": 0,
        }

    return {
        "available": True,
        "message": None,
        "source_field": selected_fields[0],
        "year": latest_year or None,
        "value_per_sqft": sum(values) / len(values),
        "sample_count": len(values),
    }


def get_locality_land_price_history(
    locality_name: str,
    current_year: int | None = None,
) -> list[dict[str, Any]]:
    if not locality_name.strip():
        return []

    payload = _load_processed_dataset()
    validation = payload.get("validation")
    if not isinstance(validation, dict):
        raise ValueError("Processed RentTrace dataset has no validation metadata.")

    records = [
        record for record in payload["records"]
        if isinstance(record, dict)
        and isinstance(record.get("locality"), str)
        and " ".join(record["locality"].split()).casefold()
        == " ".join(locality_name.split()).casefold()
    ]
    fields = validation.get("land_price_per_sqft_fields", [])
    if not isinstance(fields, list):
        raise ValueError("Processed dataset land-price field metadata is invalid.")

    year_limit = date.today().year if current_year is None else current_year
    if not isinstance(year_limit, int) or year_limit < 1900 or year_limit > 2200:
        raise ValueError("Current year must be a valid year.")

    fields_by_year: dict[int, list[str]] = defaultdict(list)
    for field in fields:
        if not isinstance(field, str) or re.search(r"_predicted(?:_|$)", field, re.IGNORECASE):
            continue
        years = re.findall(r"(?<!\d)(\d{4})(?!\d)", field)
        if not years:
            continue
        year = max(map(int, years))
        if 1900 <= year <= year_limit:
            fields_by_year[year].append(field)

    history = []
    for year, year_fields in sorted(fields_by_year.items()):
        values = [
            value
            for record in records
            for field in year_fields
            if (value := _as_number(record.get("source_fields", {}).get(field))) is not None
            and value > 0
        ]
        if values:
            history.append({
                "year": year,
                "value_per_sqft": sum(values) / len(values),
                "source_fields": year_fields,
                "sample_count": len(values),
            })

    return history
