import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import renttrace_dataset
from app.services.renttrace_dataset import (
    get_locality_land_price_history,
    get_locality_land_rate,
    process_dataset,
)


def make_workbook(path, rows):
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def sample_row(record_id=1, locality="Madhapur", rent=18000):
    return {
        "ID": record_id,
        "Bedrooms": "2 BHK Apartment",
        "Area": "1080 sqft",
        "Locality": locality,
        "Price_2025": rent,
        "Price_2026": rent + 1000,
        "Price_2027_Predicted": rent + 1500,
    }


def test_process_dataset_validates_rows_and_preserves_actual_source_fields(tmp_path):
    source = make_workbook(
        tmp_path / "raw.xlsx",
        [
            sample_row(),
            sample_row(record_id=2, locality="Gachibowli", rent=-100),
            sample_row(record_id=3, locality="Kondapur"),
            sample_row(record_id=4, locality="Kondapur"),
        ],
    )
    processed = tmp_path / "processed" / "dataset.json"
    report_path = tmp_path / "processed" / "validation.json"

    report = process_dataset(source, processed, report_path)
    output = json.loads(processed.read_text(encoding="utf-8"))

    assert report["total_records"] == 4
    assert report["valid_records"] == 3
    assert report["invalid_records"] == 1
    assert report["invalid_record_details"][0]["record_id"] == 2
    assert report["land_price_fields"] == []
    assert report["historical_price_fields"] == ["Price_2025", "Price_2026"]
    assert report["predicted_price_fields"] == ["Price_2027_Predicted"]
    assert report["invalid_historical_price_values"] == 1
    assert report["invalid_predicted_price_values"] == 0
    assert report["possible_duplicate_key_rows"] == 1
    assert output["records"][0]["source_fields"]["Price_2025"] == 18000
    assert output["records"][0]["area_sqft"] == 1080
    assert report_path.is_file()


def test_process_dataset_reports_missing_fields_and_rejects_invalid_coordinates(tmp_path):
    source = make_workbook(
        tmp_path / "raw.xlsx",
        [
            {**sample_row(), "Latitude": 17.4, "Longitude": 78.4},
            {**sample_row(record_id=2), "Latitude": 95, "Longitude": 78.4},
            {**sample_row(record_id=3), "Locality": None, "Latitude": 17.4, "Longitude": 78.4},
        ],
    )

    report = process_dataset(source, tmp_path / "processed.json", tmp_path / "report.json")

    assert report["valid_records"] == 1
    assert report["invalid_records"] == 2
    assert report["latitude_fields"] == ["Latitude"]
    assert report["longitude_fields"] == ["Longitude"]
    assert report["coordinate_validation_available"] is True
    assert report["invalid_latitude_values"] == 1
    assert report["invalid_longitude_values"] == 0
    assert report["missing_fields"] == {"Locality": 1}
    assert any("Latitude is outside" in issue for item in report["invalid_record_details"] for issue in item["errors"])


def test_process_dataset_rejects_output_path_equal_to_source(tmp_path):
    source = make_workbook(tmp_path / "raw.xlsx", [sample_row()])

    with pytest.raises(ValueError, match="cannot overwrite"):
        process_dataset(source, source, tmp_path / "report.json")


def test_process_dataset_validates_land_price_fields_when_present(tmp_path):
    source = make_workbook(
        tmp_path / "raw.xlsx",
        [
            {**sample_row(), "Land_Price": 1_000_000, "Land_Price_Per_Sqft": 1000},
            {**sample_row(record_id=2), "Land_Price": -500, "Land_Price_Per_Sqft": 0},
        ],
    )

    report = process_dataset(source, tmp_path / "processed.json", tmp_path / "report.json")

    assert report["land_price_fields"] == ["Land_Price", "Land_Price_Per_Sqft"]
    assert report["land_price_per_sqft_fields"] == ["Land_Price_Per_Sqft"]
    assert report["invalid_land_price_values"] == 2
    assert report["valid_records"] == 1
    assert report["invalid_records"] == 1


def test_land_rate_uses_latest_historical_field_and_ignores_future_predictions(tmp_path, monkeypatch):
    source = make_workbook(
        tmp_path / "raw.xlsx",
        [
            {
                **sample_row(),
                "Land_Price_Per_Sqft_2023": 1200,
                "Land_Price_Per_Sqft_2024": 1500,
                "Land_Price_Per_Sqft_2027_Predicted": 9999,
            },
            {
                **sample_row(record_id=2),
                "Land_Price_Per_Sqft_2023": 1400,
                "Land_Price_Per_Sqft_2024": 1700,
                "Land_Price_Per_Sqft_2027_Predicted": 9999,
            },
            {
                **sample_row(record_id=3, locality="Gachibowli"),
                "Land_Price_Per_Sqft_2023": 2500,
                "Land_Price_Per_Sqft_2024": 3000,
                "Land_Price_Per_Sqft_2027_Predicted": 19999,
            },
        ],
    )
    processed = tmp_path / "processed.json"
    process_dataset(source, processed, tmp_path / "report.json")
    monkeypatch.setattr(renttrace_dataset, "PROCESSED_DATASET_PATH", processed)

    madhapur_rate = get_locality_land_rate("Madhapur", current_year=2025)
    gachibowli_rate = get_locality_land_rate("Gachibowli", current_year=2025)
    missing_rate = get_locality_land_rate("Kondapur", current_year=2025)

    assert madhapur_rate == {
        "available": True,
        "message": None,
        "source_field": "Land_Price_Per_Sqft_2024",
        "year": 2024,
        "value_per_sqft": 1600,
        "sample_count": 2,
    }
    assert gachibowli_rate["value_per_sqft"] == 3000
    assert gachibowli_rate["year"] == 2024
    assert missing_rate["available"] is False
    assert missing_rate["message"] == "Land price data unavailable for this locality."


def test_land_rate_can_use_a_non_year_per_square_foot_field(tmp_path, monkeypatch):
    source = make_workbook(
        tmp_path / "raw.xlsx",
        [{**sample_row(), "Land_Price_Per_Sqft": 2200}],
    )
    processed = tmp_path / "processed.json"
    process_dataset(source, processed, tmp_path / "report.json")
    monkeypatch.setattr(renttrace_dataset, "PROCESSED_DATASET_PATH", processed)

    rate = get_locality_land_rate("Madhapur", current_year=2025)

    assert rate["available"] is True
    assert rate["source_field"] == "Land_Price_Per_Sqft"
    assert rate["year"] is None
    assert rate["value_per_sqft"] == 2200


def test_land_price_history_averages_only_validated_locality_historical_fields(tmp_path, monkeypatch):
    source = make_workbook(
        tmp_path / "raw.xlsx",
        [
            {
                **sample_row(),
                "Land_Price_Per_Sqft_2017": 1000,
                "Land_Price_Per_Sqft_2020": 1800,
                "Land_Price_Per_Sqft_2027_Predicted": 5000,
            },
            {
                **sample_row(record_id=2),
                "Land_Price_Per_Sqft_2017": 1200,
                "Land_Price_Per_Sqft_2020": 2200,
                "Land_Price_Per_Sqft_2027_Predicted": 6000,
            },
            {
                **sample_row(record_id=3, locality="Gachibowli"),
                "Land_Price_Per_Sqft_2017": 9000,
                "Land_Price_Per_Sqft_2020": 12000,
            },
        ],
    )
    processed = tmp_path / "processed.json"
    process_dataset(source, processed, tmp_path / "report.json")
    monkeypatch.setattr(renttrace_dataset, "PROCESSED_DATASET_PATH", processed)

    history = get_locality_land_price_history("mAdHaPuR", current_year=2026)

    assert history == [
        {
            "year": 2017,
            "value_per_sqft": 1100,
            "source_fields": ["Land_Price_Per_Sqft_2017"],
            "sample_count": 2,
        },
        {
            "year": 2020,
            "value_per_sqft": 2000,
            "source_fields": ["Land_Price_Per_Sqft_2020"],
            "sample_count": 2,
        },
    ]
    assert get_locality_land_price_history("Madhapur", current_year=2016) == []


def test_land_analysis_api_serves_only_processed_records_by_locality(tmp_path, monkeypatch):
    processed_path = tmp_path / "processed.json"
    processed_path.write_text(
        json.dumps({
            "records": [
                {"locality": "Madhapur", "record_id": 1, "historical_prices": []},
                {"locality": "Gachibowli", "record_id": 2, "historical_prices": []},
            ],
            "validation": {
                "land_price_per_sqft_fields": [],
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(renttrace_dataset, "PROCESSED_DATASET_PATH", processed_path)

    with TestClient(app) as client:
        response = client.get("/api/land-analysis/locality/mAdHaPuR")
        missing_response = client.get("/api/land-analysis/locality/Miyapur")

    assert response.status_code == 200
    assert response.json()["locality"] == "Madhapur"
    assert response.json()["record_count"] == 1
    assert [row["record_id"] for row in response.json()["records"]] == [1]
    assert response.json()["estimated_land_rate"] == {
        "available": False,
        "message": "Land price data unavailable for this locality.",
        "source_field": None,
        "year": None,
        "value_per_sqft": None,
        "sample_count": 0,
    }
    assert response.json()["historical_land_prices"] == []
    assert missing_response.json() == {
        "locality": "Miyapur",
        "record_count": 0,
        "records": [],
        "estimated_land_rate": {
            "available": False,
            "message": "Land price data unavailable for this locality.",
            "source_field": None,
            "year": None,
            "value_per_sqft": None,
            "sample_count": 0,
        },
        "historical_land_prices": [],
    }


def test_land_analysis_api_returns_historical_land_price_series(tmp_path, monkeypatch):
    processed_path = tmp_path / "processed.json"
    processed_path.write_text(
        json.dumps({
            "records": [
                {
                    "locality": "Madhapur",
                    "record_id": 1,
                    "source_fields": {
                        "Land_Price_Per_Sqft_2017": 1000,
                        "Land_Price_Per_Sqft_2020": 1800,
                        "Land_Price_Per_Sqft_2027_Predicted": 5000,
                    },
                },
                {
                    "locality": "Madhapur",
                    "record_id": 2,
                    "source_fields": {
                        "Land_Price_Per_Sqft_2017": 1200,
                        "Land_Price_Per_Sqft_2020": 2200,
                    },
                },
            ],
            "validation": {
                "land_price_per_sqft_fields": [
                    "Land_Price_Per_Sqft_2017",
                    "Land_Price_Per_Sqft_2020",
                    "Land_Price_Per_Sqft_2027_Predicted",
                ],
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(renttrace_dataset, "PROCESSED_DATASET_PATH", processed_path)

    with TestClient(app) as client:
        response = client.get("/api/land-analysis/locality/Madhapur")

    assert response.status_code == 200
    assert response.json()["historical_land_prices"] == [
        {
            "year": 2017,
            "value_per_sqft": 1100,
            "source_fields": ["Land_Price_Per_Sqft_2017"],
            "sample_count": 2,
        },
        {
            "year": 2020,
            "value_per_sqft": 2000,
            "source_fields": ["Land_Price_Per_Sqft_2020"],
            "sample_count": 2,
        },
    ]
