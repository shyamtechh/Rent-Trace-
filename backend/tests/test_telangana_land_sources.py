import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.routes import land_identification
from app.main import app
from app.services import land_identification as land_identification_service
from app.services.telangana_land_sources import (
    TelanganaLandSourceUnavailableError,
    TelanganaParcelAmbiguousError,
    lookup_cadastral_parcel,
    point_in_esri_rings,
)

MADHAPUR_RINGS = [[
    [78.390, 17.440],
    [78.394, 17.440],
    [78.394, 17.444],
    [78.390, 17.444],
    [78.390, 17.440],
]]
GACHIBOWLI_RINGS = [[
    [78.350, 17.442],
    [78.354, 17.442],
    [78.354, 17.446],
    [78.350, 17.446],
    [78.350, 17.442],
]]


@pytest.mark.parametrize(
    ("longitude", "latitude", "rings", "expected"),
    [
        (78.392, 17.442, MADHAPUR_RINGS, True),
        (78.352, 17.444, GACHIBOWLI_RINGS, True),
        (78.400, 17.450, MADHAPUR_RINGS, False),
        (78.390, 17.442, MADHAPUR_RINGS, True),
    ],
)
def test_point_in_esri_rings_for_inside_outside_and_boundary(
    longitude,
    latitude,
    rings,
    expected,
):
    assert point_in_esri_rings(longitude, latitude, rings) is expected


def test_point_in_esri_rings_excludes_hole():
    rings_with_hole = [
        MADHAPUR_RINGS[0],
        [
            [78.391, 17.441],
            [78.393, 17.441],
            [78.393, 17.443],
            [78.391, 17.443],
            [78.391, 17.441],
        ],
    ]

    assert point_in_esri_rings(78.3905, 17.442, rings_with_hole)
    assert not point_in_esri_rings(78.392, 17.442, rings_with_hole)


def test_lookup_selects_only_the_polygon_containing_point(monkeypatch):
    features = [
        {
            "attributes": {
                "OBJECTID": 1,
                "District": "Rangareddy",
                "Mandal": "Serilingampally",
                "Village": "Madhapur",
                "Parcels": "reference-not-survey",
            },
            "geometry": {"rings": MADHAPUR_RINGS},
        },
        {
            "attributes": {
                "OBJECTID": 2,
                "District": "Rangareddy",
                "Mandal": "Serilingampally",
                "Village": "Other locality",
                "Parcels": "other-reference",
            },
            "geometry": {"rings": GACHIBOWLI_RINGS},
        },
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": features}

    class FakeClient:
        def __init__(self, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, params):
            assert params["geometry"] == "78.392,17.442"
            return FakeResponse()

    monkeypatch.setattr("app.services.telangana_land_sources.httpx.AsyncClient", FakeClient)

    result = asyncio.run(lookup_cadastral_parcel(17.442, 78.392))

    assert result["village"] == "Madhapur"
    assert result["survey_subdivision_verified"] is False
    assert result["parcel_reference"] == "reference-not-survey"


def test_lookup_returns_no_match_when_query_point_is_outside_features(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [{
                "attributes": {"OBJECTID": 1, "Village": "Madhapur"},
                "geometry": {"rings": MADHAPUR_RINGS},
            }]}

    class FakeClient:
        def __init__(self, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, params):
            assert params["geometry"] == "78.4,17.45"
            return FakeResponse()

    monkeypatch.setattr("app.services.telangana_land_sources.httpx.AsyncClient", FakeClient)

    assert asyncio.run(lookup_cadastral_parcel(17.45, 78.4)) is None


def test_lookup_selects_gachibowli_polygon_for_its_coordinate(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [{
                "attributes": {
                    "OBJECTID": 2,
                    "District": "Rangareddy",
                    "Mandal": "Serilingampally",
                    "Village": "Gachibowli",
                },
                "geometry": {"rings": GACHIBOWLI_RINGS},
            }]}

    class FakeClient:
        def __init__(self, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, params):
            return FakeResponse()

    monkeypatch.setattr("app.services.telangana_land_sources.httpx.AsyncClient", FakeClient)

    result = asyncio.run(lookup_cadastral_parcel(17.444, 78.352))

    assert result["village"] == "Gachibowli"


def test_lookup_reports_multiple_containing_features_as_ambiguous(monkeypatch):
    features = [
        {
            "attributes": {"OBJECTID": index, "Village": "Overlapping feature"},
            "geometry": {"rings": MADHAPUR_RINGS},
        }
        for index in (1, 2)
    ]

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": features}

    class FakeClient:
        def __init__(self, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, params):
            return FakeResponse()

    monkeypatch.setattr("app.services.telangana_land_sources.httpx.AsyncClient", FakeClient)

    with pytest.raises(TelanganaParcelAmbiguousError):
        asyncio.run(lookup_cadastral_parcel(17.442, 78.392))


def test_lookup_reports_truncated_gis_response_as_ambiguous(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"features": [], "exceededTransferLimit": True}

    class FakeClient:
        def __init__(self, **_kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, params):
            return FakeResponse()

    monkeypatch.setattr("app.services.telangana_land_sources.httpx.AsyncClient", FakeClient)

    with pytest.raises(TelanganaParcelAmbiguousError, match="truncated"):
        asyncio.run(lookup_cadastral_parcel(17.442, 78.392))


def test_land_identify_rejects_invalid_coordinates():
    response = TestClient(app).get(
        "/api/land/identify",
        params={"latitude": 91, "longitude": 78.39},
    )

    assert response.status_code == 422


def test_land_identify_returns_not_configured_without_claiming_coverage(monkeypatch):
    monkeypatch.setattr(land_identification_service, "LAND_RECORD_PROVIDERS", ())

    response = TestClient(app).get(
        "/api/land/identify",
        params={"latitude": 19.076, "longitude": 72.8777},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "source_not_configured"
    assert result["survey_number"] is None
    assert result["survey_number_status"] == "unavailable"
    assert result["verification_status"] == "not_verified"


def test_land_identify_returns_only_administrative_match_for_gis_feature(monkeypatch):
    class FakeProvider:
        name = "TGRAC HMDA GIS"
        state_name = "Telangana"
        source_url = "https://tgrac.telangana.gov.in/arcgis/map"

        async def identify(self, _latitude, _longitude):
            return {
                "district": "Rangareddy",
                "mandal": "Serilingampally",
                "village": "Madhapur",
                "geometry": {"rings": MADHAPUR_RINGS},
                "source_feature_id": "feature-1",
                "parcel_reference": "not-a-survey-number",
            }

    monkeypatch.setattr(
        land_identification_service,
        "LAND_RECORD_PROVIDERS",
        (FakeProvider(),),
    )
    response = TestClient(app).get(
        "/api/land/identify",
        params={"latitude": 17.442, "longitude": 78.392},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "administrative_match_only"
    assert result["state"] == "Telangana"
    assert result["district"] == "Rangareddy"
    assert result["mandal_taluk"] == "Serilingampally"
    assert result["village"] == "Madhapur"
    assert result["survey_number"] is None
    assert result["subdivision_number"] is None
    assert result["survey_number_status"] == "unavailable"
    assert result["parcel_boundary"] is None
    assert result["land_area_square_meters"] is None
    assert result["gis_feature_boundary"]["rings"] == MADHAPUR_RINGS
    assert result["source_record_id"] == "feature-1"


def test_land_identify_maps_no_match_to_no_verified_data(monkeypatch):
    class FakeProvider:
        name = "TGRAC HMDA GIS"
        source_url = "https://tgrac.telangana.gov.in/arcgis/map"

        async def identify(self, _latitude, _longitude):
            return None

    monkeypatch.setattr(land_identification_service, "LAND_RECORD_PROVIDERS", (FakeProvider(),))
    response = TestClient(app).get(
        "/api/land/identify",
        params={"latitude": 19.076, "longitude": 72.8777},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_verified_data"
    assert response.json()["survey_number"] is None


def test_land_identify_returns_ambiguous_without_selecting_a_feature(monkeypatch):
    class FakeProvider:
        name = "TGRAC HMDA GIS"
        source_url = "https://tgrac.telangana.gov.in/arcgis/map"

        async def identify(self, _latitude, _longitude):
            raise TelanganaParcelAmbiguousError("overlapping polygons")

    monkeypatch.setattr(land_identification_service, "LAND_RECORD_PROVIDERS", (FakeProvider(),))
    response = TestClient(app).get(
        "/api/land/identify",
        params={"latitude": 17.442, "longitude": 78.392},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ambiguous"
    assert response.json()["survey_number"] is None
    assert response.json()["gis_feature_boundary"] is None


def test_land_identify_reports_overlapping_configured_provider_results(monkeypatch):
    class FakeProvider:
        source_url = "https://example.gov/records"
        state_name = "Example State"

        def __init__(self, name):
            self.name = name

        async def identify(self, _latitude, _longitude):
            return {"source_feature_id": self.name}

    monkeypatch.setattr(
        land_identification_service,
        "LAND_RECORD_PROVIDERS",
        (FakeProvider("provider-a"), FakeProvider("provider-b")),
    )
    response = TestClient(app).get(
        "/api/land/identify",
        params={"latitude": 17.442, "longitude": 78.392},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ambiguous"
    assert response.json()["survey_number"] is None
    assert response.json()["source_record_id"] is None


def test_land_identify_returns_503_when_provider_is_unavailable(monkeypatch):
    class FakeProvider:
        name = "TGRAC HMDA GIS"
        source_url = "https://tgrac.telangana.gov.in/arcgis/map"

        async def identify(self, _latitude, _longitude):
            raise TelanganaLandSourceUnavailableError("provider is offline")

    monkeypatch.setattr(land_identification_service, "LAND_RECORD_PROVIDERS", (FakeProvider(),))
    response = TestClient(app).get(
        "/api/land/identify",
        params={"latitude": 17.442, "longitude": 78.392},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "source_unavailable"
    assert response.json()["detail"]["survey_number_status"] == "unavailable"
