from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.api.routes import auth as auth_routes
from app.core.security import hash_password
from app.database import Base, engine as configured_engine
from app.main import app
from app.models import DataSource, Locality, PriceHistory, Property, RentalPrice, User


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

    TestingSession = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(test_engine)
    with TestingSession() as db:
        db.add_all([
            User(name="RentTrace Admin", email="admin@example.com", password_hash=hash_password("AdminPass123!"), role="admin"),
            User(name="Regular User", email="user@example.com", password_hash=hash_password("UserPass123!")),
        ])
        locality = Locality(name="Test District", city="Test City", state="Test State", country="Test Country")
        source = DataSource(source_name="Unit test source", dataset_name="Unit test dataset")
        db.add_all([locality, source])
        db.flush()
        property_record = Property(locality_id=locality.id, property_type="Apartment", bedrooms=2, area_sqft=900)
        db.add(property_record)
        db.flush()
        db.add(RentalPrice(
            property_id=property_record.id,
            locality_id=locality.id,
            rent=20000,
            observation_date=date(2026, 1, 1),
            source_id=source.id,
        ))
        db.add(PriceHistory(
            locality_id=locality.id,
            observation_date=date(2026, 1, 1),
            average_rent=20000,
            average_property_price=8000000,
            sample_size=1,
        ))
        db.commit()

    def override_get_db():
        with TestingSession() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_health_checks_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_signup_hashes_password_and_rejects_duplicate_case_insensitive_email(client):
    payload = {"name": "New User", "email": "New.User@example.com", "password": "StrongPass123!"}
    response = client.post("/api/signup", json=payload)
    assert response.status_code == 201
    assert "password_hash" not in response.json()["user"]
    duplicate = client.post("/api/signup", json={**payload, "email": "new.user@EXAMPLE.com"})
    assert duplicate.status_code == 409


def test_login_sets_http_only_cookie_and_restores_current_user(client):
    response = client.post("/api/login", json={"email": "ADMIN@example.com", "password": "AdminPass123!"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["message"] == "Login successful"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "password_hash" not in response.json()["user"]
    assert client.get("/api/me").json()["user"]["role"] == "admin"


def test_login_invalid_password_returns_json_unauthorized_response(client):
    response = client.post("/api/login", json={"email": "user@example.com", "password": "wrong-password"})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Invalid email or password."}


def test_login_invalid_payload_returns_json_validation_error(client):
    response = client.post("/api/login", json={"email": "not-an-email", "password": ""})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"]


def test_oauth_start_redirects_to_provider_with_signed_state(client, monkeypatch):
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["google"], "client_id", "google-client")
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["google"], "client_secret", "google-secret")

    response = client.get("/api/auth/oauth/google?remember_me=true", follow_redirects=False)

    assert response.status_code == 303
    authorization = urlparse(response.headers["location"])
    assert authorization.netloc == "accounts.google.com"
    assert parse_qs(authorization.query)["redirect_uri"] == [
        auth_routes.OAUTH_CONFIG["google"]["redirect_uri"]
    ]
    assert response.cookies["renttrace_oauth_state"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_oauth_start_returns_actionable_configuration_error_without_secret(client, monkeypatch):
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["google"], "client_id", "configured-google-client")
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["google"], "client_secret", "")

    response = client.get("/api/auth/oauth/google", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"{auth_routes.FRONTEND_URL}/?oauth_error=not_configured"
    assert all(
        not cookie.startswith("renttrace_oauth_state=") or "max-age=0" in cookie.lower()
        for cookie in response.headers.get_list("set-cookie")
    )


def test_google_oauth_config_status_reports_presence_without_values(client, monkeypatch):
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["google"], "client_id", "configured-google-client")
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["google"], "client_secret", "sensitive-google-secret")
    monkeypatch.setitem(
        auth_routes.OAUTH_CONFIG["google"],
        "redirect_uri",
        "http://localhost:5176/api/auth/oauth/google/callback",
    )
    monkeypatch.setattr(auth_routes, "FRONTEND_URL", "http://localhost:5176")

    response = client.get("/api/auth/oauth/google/config-status")

    assert response.status_code == 200
    assert response.json() == {
        "google_client_id_present": True,
        "google_client_secret_present": True,
        "google_redirect_uri_present": True,
        "google_redirect_uri_matches_callback": True,
        "google_redirect_uri_matches_frontend": True,
    }
    assert "sensitive-google-secret" not in response.text
    assert "configured-google-client" not in response.text


def test_oauth_callback_creates_and_authenticates_user(client, monkeypatch):
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["github"], "client_id", "github-client")
    monkeypatch.setitem(auth_routes.OAUTH_CONFIG["github"], "client_secret", "github-secret")

    async def fake_fetch_identity(_provider, _code):
        return "OAuth User", "oauth-user@example.com"

    monkeypatch.setattr(auth_routes, "fetch_oauth_identity", fake_fetch_identity)
    start_response = client.get("/api/auth/oauth/github?remember_me=true", follow_redirects=False)
    state = parse_qs(urlparse(start_response.headers["location"]).query)["state"][0]

    response = client.get(
        "/api/auth/oauth/github/callback",
        params={"code": "authorization-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"{auth_routes.FRONTEND_URL}/"
    assert "renttrace_session=" in response.headers["set-cookie"]
    assert client.get("/api/me").json()["user"]["email"] == "oauth-user@example.com"


def test_oauth_callback_rejects_state_mismatch(client):
    response = client.get(
        "/api/auth/oauth/google/callback",
        params={"code": "authorization-code", "state": "untrusted-state"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "oauth_error=invalid_state" in response.headers["location"]


def test_logout_clears_session_cookie(client):
    client.post("/api/login", json={"email": "user@example.com", "password": "UserPass123!"})
    response = client.post("/api/logout", headers={"Origin": auth_routes.FRONTEND_URL})
    assert response.status_code == 200
    assert client.get("/api/me").status_code == 401


def test_admin_route_uses_verified_role_not_email_header(client):
    assert client.get("/api/admin/overview", headers={"X-User-Email": "admin@example.com"}).status_code == 401
    client.post("/api/login", json={"email": "user@example.com", "password": "UserPass123!"})
    assert client.get("/api/admin/overview").status_code == 403
    client.post(
        "/api/login",
        json={"email": "admin@example.com", "password": "AdminPass123!"},
        headers={"Origin": auth_routes.FRONTEND_URL},
    )
    assert client.get("/api/admin/overview").status_code == 200


def test_locality_crud_and_historical_delete_protection(client):
    client.post("/api/login", json={"email": "admin@example.com", "password": "AdminPass123!"})
    origin = {"Origin": auth_routes.FRONTEND_URL}
    created = client.post("/api/localities", headers=origin, json={
        "name": "Another District", "city": "Test City", "state": "Test State", "country": "Test Country",
    })
    assert created.status_code == 201
    locality_id = created.json()["id"]
    assert client.get(f"/api/localities/{locality_id}").status_code == 200
    assert client.delete("/api/localities/1", headers=origin).status_code == 409
    assert client.delete(f"/api/localities/{locality_id}", headers=origin).status_code == 204


def test_property_and_rental_crud(client):
    client.post("/api/login", json={"email": "admin@example.com", "password": "AdminPass123!"})
    origin = {"Origin": auth_routes.FRONTEND_URL}
    property_response = client.post("/api/properties", headers=origin, json={
        "locality_id": 1,
        "property_type": "Studio",
        "bedrooms": 0,
        "area_sqft": 450,
    })
    assert property_response.status_code == 201
    property_id = property_response.json()["id"]
    update_property = client.put(f"/api/properties/{property_id}", headers=origin, json={
        "locality_id": 1,
        "property_type": "Studio",
        "bedrooms": 0,
        "area_sqft": 500,
    })
    assert update_property.status_code == 200
    assert float(update_property.json()["area_sqft"]) == 500

    rental_response = client.post("/api/rentals", headers=origin, json={
        "property_id": property_id,
        "locality_id": 1,
        "rent": 12000,
        "observation_date": "2026-02-01",
        "source_id": 1,
    })
    assert rental_response.status_code == 201
    rental_id = rental_response.json()["id"]
    assert client.get(f"/api/rentals/{rental_id}").status_code == 200
    assert client.delete(f"/api/rentals/{rental_id}", headers=origin).status_code == 204
    assert client.get(f"/api/rentals/{rental_id}").status_code == 404
    assert len(client.get("/api/rentals").json()) == 1
    assert client.delete(f"/api/properties/{property_id}", headers=origin).status_code == 409


def test_csv_import_reports_valid_invalid_and_duplicate_rows(client):
    client.post("/api/login", json={"email": "admin@example.com", "password": "AdminPass123!"})
    csv_content = (
        "name,city,state,country\n"
        "CSV District,Test City,Test State,Test Country\n"
        "CSV District,Test City,Test State,Test Country\n"
        ",Test City,Test State,Test Country\n"
    )
    response = client.post(
        "/api/import/localities",
        headers={"Origin": auth_routes.FRONTEND_URL},
        files={"file": ("localities.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["total_rows"] == 3
    assert response.json()["successful_rows"] == 1
    assert response.json()["failed_rows"] == 2
    assert len(response.json()["errors"]) == 2


def test_analytics_trends_query_database(client):
    response = client.get("/api/analytics/locality/1/rent-trend")
    assert response.status_code == 200
    assert response.json()["observations"][0]["average_rent"] == 20000


def test_dashboard_overview_is_hyderabad_scoped(client):
    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json()["city"] == "Hyderabad"
    assert response.json()["localities"] == []
    assert response.json()["trend"] == []


@pytest.mark.postgres
def test_configured_postgresql_connection():
    if configured_engine.dialect.name != "postgresql":
        pytest.skip("Set DATABASE_URL to PostgreSQL to run this connection test.")
    with TestClient(app) as postgres_client:
        response = postgres_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
