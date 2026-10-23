from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import land_analysis
from app.database import Base, get_db
from app.main import app
from app.models import GovernmentLandRate, LandParcel, LandValuation
from app.services.land_valuation import calculate_land_value
from app.services.telangana_land_sources import TelanganaLandSourceUnavailableError

BHUBHARATI_URL = "https://bhubharati.telangana.gov.in/viewMarketValueLandStampDuty?lang=en"


@pytest.fixture
def client():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine, "connect")
    def enable_test_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    testing_session = sessionmaker(bind=test_engine, expire_on_commit=False)
    Base.metadata.create_all(test_engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, testing_session
    app.dependency_overrides.clear()
    test_engine.dispose()


def valuation_request(**overrides):
    body = {
        "latitude": 17.44,
        "longitude": 78.39,
        "area_square_feet": 2450,
        "rate_per_sq_yard": 7550,
        "rate_unit": "INR/sq_yd",
        "property_category": "Residential",
        "rate_date": date.today().isoformat(),
        "verified_date": date.today().isoformat(),
        "user_confirmed_rate": True,
        "survey_subdivision_verified": False,
        "source_url": BHUBHARATI_URL,
        "district": "Rangareddy",
        "mandal": "Serilingampally",
        "village": "Madhapur",
        "survey_subdivision": "123/4",
    }
    body.update(overrides)
    return body


def test_calculates_square_yard_conversion_and_value():
    area, value = calculate_land_value(Decimal("2450"), Decimal("7550"))

    assert area == Decimal("272.2222")
    assert value == Decimal("2055277.78")


@pytest.mark.parametrize(
    ("area", "rate"),
    [
        (Decimal("0"), Decimal("100")),
        (Decimal("-10"), Decimal("100")),
        (Decimal("100"), Decimal("0")),
        (Decimal("100"), Decimal("-1")),
        (Decimal("NaN"), Decimal("100")),
        (Decimal("100"), Decimal("Infinity")),
    ],
)
def test_rejects_invalid_area_or_rate(area, rate):
    with pytest.raises(ValueError):
        calculate_land_value(area, rate)


def test_parcel_lookup_returns_source_metadata_and_distinguishes_no_match(client, monkeypatch):
    async def matched(_latitude, _longitude):
        return {
            "source_name": "TGRAC HMDA Cadastral",
            "source_url": "https://tgrac.telangana.gov.in/arcgis/rest/services/HMDA_Folder/HMDA/MapServer/5",
            "source_feature_id": "42",
            "district": "Rangareddy",
            "mandal": "Serilingampally",
            "village": "Madhapur",
            "parcel_reference": "21",
            "attributes": {"Parcels": "21"},
            "geometry": {"rings": [[[78.39, 17.44], [78.4, 17.44], [78.4, 17.45], [78.39, 17.44]]]},
        }

    monkeypatch.setattr(land_analysis, "lookup_cadastral_parcel", matched)
    test_client, _ = client
    response = test_client.get(
        "/api/land-analysis/parcel",
        params={"latitude": 17.44, "longitude": 78.39},
    )

    assert response.status_code == 200
    assert response.json()["found"] is True
    assert response.json()["administrative_status"] == "matched"
    assert response.json()["survey_number_status"] == "not_verified"
    assert response.json()["parcel"]["source_feature_id"] == "42"
    assert response.json()["parcel"]["parcel_reference"] == "21"
    assert response.json()["parcel"]["district"] == "Rangareddy"
    assert response.json()["parcel"]["mandal"] == "Serilingampally"
    assert response.json()["parcel"]["geometry"]["rings"]

    async def no_match(_latitude, _longitude):
        return None

    monkeypatch.setattr(land_analysis, "lookup_cadastral_parcel", no_match)
    response = test_client.get(
        "/api/land-analysis/parcel",
        params={"latitude": 17.44, "longitude": 78.39},
    )
    assert response.status_code == 200
    assert response.json()["found"] is False
    assert response.json()["parcel"] is None


def test_valuation_persists_rate_and_result_with_provenance(client, monkeypatch):
    async def matched(_latitude, _longitude):
        return {
            "source_name": "TGRAC HMDA Cadastral",
            "source_url": "https://tgrac.telangana.gov.in/arcgis/rest/services/HMDA_Folder/HMDA/MapServer/5",
            "source_feature_id": "42",
            "district": "Rangareddy",
            "mandal": "Serilingampally",
            "village": "Madhapur",
            "parcel_reference": "21",
            "attributes": {"Parcels": "21"},
            "geometry": {"rings": [[[78.39, 17.44], [78.4, 17.44], [78.4, 17.45], [78.39, 17.44]]]},
        }

    monkeypatch.setattr(land_analysis, "lookup_cadastral_parcel", matched)
    test_client, testing_session = client
    response = test_client.post("/api/land-analysis/valuation", json=valuation_request())

    assert response.status_code == 201
    result = response.json()
    assert result["area_square_yards"] == "272.2222"
    assert result["rate_per_sq_yard"] == "7550.00"
    assert result["total_value"] == "2055277.78"
    assert result["source_url"] == BHUBHARATI_URL
    assert result["verification_method"] == "manual_user_attested"
    assert result["source_type"] == "government_guideline_rate"
    assert result["rate_unit"] == "INR/sq_yd"
    assert result["property_category"] == "Residential"
    assert result["survey_subdivision_verified"] is False
    assert result["parcel_status"] == "matched"
    assert result["market_value_estimate"] is None
    assert "does not independently verify" in result["confidence_note"]

    with testing_session() as db:
        assert len(db.scalars(select(LandParcel)).all()) == 1
        rate = db.scalars(select(GovernmentLandRate)).one()
        valuation = db.scalars(select(LandValuation)).one()
        assert rate.parcel_id == valuation.parcel_id
        assert rate.rate_per_sq_yard == Decimal("7550.00")
        assert rate.survey_subdivision == "123/4"
        assert rate.survey_subdivision_verified is False
        assert rate.rate_unit == "INR/sq_yd"
        assert valuation.total_value == Decimal("2055277.78")


def test_valuation_can_proceed_when_gis_is_unavailable_but_marks_limitation(client, monkeypatch):
    async def unavailable(_latitude, _longitude):
        raise TelanganaLandSourceUnavailableError("TGRAC offline")

    monkeypatch.setattr(land_analysis, "lookup_cadastral_parcel", unavailable)
    test_client, _ = client
    response = test_client.post("/api/land-analysis/valuation", json=valuation_request())

    assert response.status_code == 201
    assert response.json()["parcel_status"] == "unavailable"
    assert response.json()["total_value"] == "2055277.78"
    assert "not linked to a GIS parcel" in response.json()["confidence_note"]


def test_valuation_does_not_choose_between_multiple_gis_features(client, monkeypatch):
    async def ambiguous(_latitude, _longitude):
        raise land_analysis.TelanganaParcelAmbiguousError("multiple features")

    monkeypatch.setattr(land_analysis, "lookup_cadastral_parcel", ambiguous)
    test_client, testing_session = client
    response = test_client.post("/api/land-analysis/valuation", json=valuation_request())

    assert response.status_code == 201
    assert response.json()["parcel_status"] == "ambiguous"
    assert response.json()["parcel"] is None
    assert "no single GIS parcel was selected" in response.json()["confidence_note"]

    with testing_session() as db:
        assert db.scalars(select(LandParcel)).all() == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": 91},
        {"longitude": 181},
        {"area_square_feet": 0},
        {"rate_per_sq_yard": 0},
        {"source_url": "https://example.com/rate"},
        {"user_confirmed_rate": False},
        {"survey_subdivision_verified": True, "survey_subdivision": None},
        {"rate_unit": "INR/sq_ft"},
        {"rate_date": "2099-01-01"},
        {"verified_date": "2099-01-01"},
    ],
)
def test_valuation_rejects_invalid_inputs(client, overrides):
    test_client, _ = client
    response = test_client.post(
        "/api/land-analysis/valuation",
        json=valuation_request(**overrides),
    )
    assert response.status_code == 422
