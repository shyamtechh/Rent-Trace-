from fastapi.testclient import TestClient

from app.api.routes import geocoding as geocoding_route
from app.main import app
from app.schemas import CitySearchResult


def test_city_search_returns_provider_center_and_bounds(monkeypatch):
    calls = []

    async def fake_search(city: str):
        calls.append(city)
        return [
            CitySearchResult(
                id="relation:123",
                name="Requested City",
                display_name="Requested City, Region, Country",
                center=(17.4, 78.5),
                bounds=((17.0, 78.0), (17.8, 79.0)),
            )
        ]

    monkeypatch.setattr(geocoding_route, "search_cities", fake_search)
    response = TestClient(app).get("/api/geocoding/search", params={"city": "Requested City"})

    assert response.status_code == 200
    assert calls == ["Requested City"]
    assert response.json() == [
        {
            "id": "relation:123",
            "name": "Requested City",
            "display_name": "Requested City, Region, Country",
            "center": [17.4, 78.5],
            "bounds": [[17.0, 78.0], [17.8, 79.0]],
        }
    ]


def test_city_search_requires_nontrivial_query():
    response = TestClient(app).get("/api/geocoding/search", params={"city": "x"})
    assert response.status_code == 422


def test_hyderabad_area_search_returns_real_coordinates(monkeypatch):
    calls = []

    async def fake_search(area: str, city: str):
        calls.append((area, city))
        return CitySearchResult(
            id="node:123",
            name="Madhapur",
            display_name="Madhapur, Hyderabad, Telangana, India",
            center=(17.385, 78.480),
            bounds=((17.38, 78.47), (17.39, 78.49)),
        )

    monkeypatch.setattr(geocoding_route, "search_hyderabad_area", fake_search)
    response = TestClient(app).get(
        "/api/geocoding/area-search",
        params={"area": "Madhapur"},
    )

    assert response.status_code == 200
    assert calls == [("Madhapur", "Hyderabad")]
    assert response.json()["center"] == [17.385, 78.48]


def test_hyderabad_area_search_returns_not_found(monkeypatch):
    async def fake_search(area: str, city: str):
        return None

    monkeypatch.setattr(geocoding_route, "search_hyderabad_area", fake_search)
    response = TestClient(app).get(
        "/api/geocoding/area-search",
        params={"area": "Unknown locality"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Area not found. Please enter a valid Hyderabad locality."
    }


def test_area_search_passes_selected_city(monkeypatch):
    calls = []

    async def fake_search(area: str, city: str):
        calls.append((area, city))
        return CitySearchResult(
            id="node:456",
            name="Baner",
            display_name="Baner, Pune, Maharashtra, India",
            center=(18.56, 73.78),
        )

    monkeypatch.setattr(geocoding_route, "search_hyderabad_area", fake_search)
    response = TestClient(app).get(
        "/api/geocoding/area-search",
        params={"area": "Baner", "city": "Pune"},
    )

    assert response.status_code == 200
    assert calls == [("Baner", "Pune")]


def test_reverse_geocode_returns_suggestion_not_verified_administration(monkeypatch):
    async def fake_reverse(latitude: float, longitude: float):
        assert (latitude, longitude) == (17.44, 78.39)
        return {
            "display_name": "Madhapur, Hyderabad, Telangana, India",
            "suggested_locality": "Madhapur",
            "suggested_district": "Rangareddy",
            "source_name": "OpenStreetMap Nominatim",
            "source_url": "https://nominatim.openstreetmap.org/reverse",
            "verification_status": "suggestion_only",
        }

    monkeypatch.setattr(geocoding_route, "reverse_geocode", fake_reverse)
    response = TestClient(app).get(
        "/api/geocoding/reverse",
        params={"latitude": 17.44, "longitude": 78.39},
    )

    assert response.status_code == 200
    assert response.json()["suggested_locality"] == "Madhapur"
    assert response.json()["verification_status"] == "suggestion_only"


def test_reverse_geocode_rejects_invalid_coordinates():
    response = TestClient(app).get(
        "/api/geocoding/reverse",
        params={"latitude": 91, "longitude": 78.39},
    )
    assert response.status_code == 422
