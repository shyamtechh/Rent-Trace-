import asyncio
import logging
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.api.routes import chat as chat_route
from app.database import Base, get_db
from app.main import app
from app.models import DataSource, Locality, PriceHistory, Property, RentalPrice, User
from app.services import chat_ai, chat_context
from app.services.chat_ai import ChatAIConfigurationError, ChatAIUnavailableError
from app.services.chat_rate_limit import chat_rate_limiter


@pytest.fixture
def client():
    chat_rate_limiter.reset()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        user = User(
            name="Chat User",
            email="chat@example.com",
            password_hash="not-used",
            role="user",
        )
        locality = Locality(
            name="Gachibowli",
            city="Hyderabad",
            state="Telangana",
            country="India",
        )
        source = DataSource(
            source_name="RentTrace test",
            dataset_name="Chat unit test data",
        )
        db.add_all([user, locality, source])
        db.flush()
        property_record = Property(
            locality_id=locality.id,
            property_type="Apartment",
            bedrooms=2,
            area_sqft=900,
        )
        db.add(property_record)
        db.flush()
        db.add_all([
            RentalPrice(
                property_id=property_record.id,
                locality_id=locality.id,
                rent=28000,
                observation_date=date(2026, 1, 1),
                source_id=source.id,
            ),
            PriceHistory(
                locality_id=locality.id,
                observation_date=date(2026, 1, 1),
                average_rent=28000,
                average_property_price=9000000,
                average_price_per_sqft=10000,
                sample_size=12,
            ),
        ])
        db.commit()
        user_id = user.id

    def override_db():
        with testing_session() as db:
            yield db

    def override_user():
        with testing_session() as db:
            yield db.get(User, user_id)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    chat_rate_limiter.reset()
    engine.dispose()


def _patch_empty_workbook(monkeypatch):
    monkeypatch.setattr(chat_context, "get_processed_locality_names", lambda: [])
    monkeypatch.setattr(chat_context, "get_locality_records", lambda _name: [])
    monkeypatch.setattr(
        chat_context,
        "get_locality_land_rate",
        lambda _name: {"available": False},
    )
    monkeypatch.setattr(chat_context, "get_locality_land_price_history", lambda _name: [])


def test_chat_answers_available_rent_from_database_without_openai(client, monkeypatch):
    _patch_empty_workbook(monkeypatch)

    async def unexpected_completion(_messages):
        raise AssertionError("A direct RentTrace data answer must not call OpenAI.")

    monkeypatch.setattr(chat_route, "generate_chat_completion", unexpected_completion)
    response = client.post(
        "/api/chat",
        json={"message": "What is the 2 BHK rent in Gachibowli?"},
    )

    assert response.status_code == 200
    assert "₹28,000" in response.json()["answer"]
    assert response.json()["answer_kind"] == "renttrace_data"
    assert response.json()["sources"] == ["RentTrace PostgreSQL"]


def test_chat_preserves_context_and_calls_openai_for_interpretation(client, monkeypatch):
    _patch_empty_workbook(monkeypatch)
    captured = {}

    async def fake_completion(messages):
        captured["messages"] = messages
        return "The supplied data records one rental sample."

    monkeypatch.setattr(chat_route, "generate_chat_completion", fake_completion)
    response = client.post(
        "/api/chat",
        json={
            "message": "Explain the rental trend in Gachibowli.",
            "history": [
                {"role": "user", "content": "What does this data show?"},
                {"role": "assistant", "content": "Rent data is available."},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["answer_kind"] == "ai_interpretation"
    assert len(captured["messages"]) == 5
    assert "9000000.0" in captured["messages"][1]["content"]


def test_chat_rejects_empty_and_oversized_messages(client):
    assert client.post("/api/chat", json={"message": "  "}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 1201}).status_code == 422


def test_chat_does_not_invent_rent_when_data_is_missing(client, monkeypatch):
    _patch_empty_workbook(monkeypatch)

    async def unexpected_completion(_messages):
        raise AssertionError("Missing factual data must not be sent to OpenAI to invent a number.")

    monkeypatch.setattr(chat_route, "generate_chat_completion", unexpected_completion)
    response = client.post("/api/chat", json={"message": "What is the rent in Madhapur?"})

    assert response.status_code == 200
    assert "not currently available in the RentTrace data" in response.json()["answer"]
    assert response.json()["answer_kind"] == "data_unavailable"


def test_chat_reports_unconfigured_openai_without_leaking_details(client, monkeypatch):
    async def unconfigured(_messages):
        raise ChatAIConfigurationError("missing key")

    monkeypatch.setattr(chat_route, "generate_chat_completion", unconfigured)
    response = client.post("/api/chat", json={"message": "Explain rental trends."})

    assert response.status_code == 503
    assert "project-root .env" in response.json()["detail"]


def test_chat_rate_limit_is_friendly_and_stops_provider_request(client, monkeypatch):
    monkeypatch.setattr(chat_route.chat_rate_limiter, "allow_request", lambda _user_id: False)

    async def unexpected_completion(_messages):
        raise AssertionError("Rate-limited requests must not call OpenAI.")

    monkeypatch.setattr(chat_route, "generate_chat_completion", unexpected_completion)
    response = client.post("/api/chat", json={"message": "Explain rental trends."})

    assert response.status_code == 429
    assert response.json()["detail"] == (
        "The RentTrace AI assistant is receiving too many requests from this session. "
        "Please wait a moment and try again."
    )


def test_openai_responses_api_uses_server_key_and_model(monkeypatch):
    captured = {}

    class FakeResponse:
        output_text = "Grounded response."

    class FakeResponses:
        async def create(self, **kwargs):
            captured["request"] = kwargs
            return FakeResponse()

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = FakeResponses()

        async def close(self):
            captured["closed"] = True

    monkeypatch.setattr(chat_ai, "OPENAI_API_KEY", "test-secret-key")
    monkeypatch.setattr(chat_ai, "OPENAI_MODEL", "gpt-test-model")
    monkeypatch.setattr(chat_ai, "OPENAI_TIMEOUT_SECONDS", 12)
    monkeypatch.setattr(chat_ai, "OPENAI_MAX_RETRIES", 2)
    monkeypatch.setattr(chat_ai, "AsyncOpenAI", FakeClient)

    answer = asyncio.run(
        chat_ai.generate_chat_completion([
            {"role": "system", "content": "Use verified data only."},
            {"role": "user", "content": "Explain the recorded trend."},
        ])
    )

    assert answer == "Grounded response."
    assert captured["client"] == {
        "api_key": "test-secret-key",
        "timeout": 12,
        "max_retries": 2,
    }
    assert captured["request"] == {
        "model": "gpt-test-model",
        "instructions": "Use verified data only.",
        "input": [{"role": "user", "content": "Explain the recorded trend."}],
    }
    assert captured["closed"] is True


def _make_status_error(error_type, status_code, code):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(status_code, request=request)
    return error_type(
        "provider message must not reach the user",
        response=response,
        body={"error": {"code": code, "message": "sensitive provider detail"}},
    )


@pytest.mark.parametrize(
    ("error_type", "status_code", "code", "expected"),
    [
        (AuthenticationError, 401, "invalid_api_key", "currently unavailable"),
        (RateLimitError, 429, "insufficient_quota", "usage limit"),
        (RateLimitError, 429, "rate_limit_exceeded", "too many requests"),
        (APIStatusError, 500, "server_error", "temporarily unavailable"),
    ],
)
def test_openai_api_errors_are_safe_and_logged_without_secrets(
    monkeypatch,
    caplog,
    error_type,
    status_code,
    code,
    expected,
):
    secret = "test-secret-key"

    class FakeResponses:
        async def create(self, **_kwargs):
            raise _make_status_error(error_type, status_code, code)

    class FakeClient:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()

        async def close(self):
            return None

    monkeypatch.setattr(chat_ai, "OPENAI_API_KEY", secret)
    monkeypatch.setattr(chat_ai, "OPENAI_MODEL", "gpt-test-model")
    monkeypatch.setattr(chat_ai, "AsyncOpenAI", FakeClient)

    with caplog.at_level(logging.ERROR, logger="app.services.chat_ai"):
        with pytest.raises(ChatAIUnavailableError, match=expected) as error:
            asyncio.run(
                chat_ai.generate_chat_completion([
                    {"role": "user", "content": "Explain."},
                ])
            )

    assert "sensitive provider detail" not in str(error.value)
    assert "provider message must not reach the user" not in str(error.value)
    assert secret not in caplog.text
    assert f"http_status={status_code}" in caplog.text
    assert f"error_code={code}" in caplog.text


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        (APITimeoutError, "request timed out"),
        (APIConnectionError, "could not connect"),
    ],
)
def test_openai_network_errors_are_user_friendly(monkeypatch, error_type, expected):
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")

    class FakeResponses:
        async def create(self, **_kwargs):
            if error_type is APITimeoutError:
                raise APITimeoutError(request=request)
            raise APIConnectionError(message="private network detail", request=request)

    class FakeClient:
        def __init__(self, **_kwargs):
            self.responses = FakeResponses()

        async def close(self):
            return None

    monkeypatch.setattr(chat_ai, "OPENAI_API_KEY", "test-secret-key")
    monkeypatch.setattr(chat_ai, "OPENAI_MODEL", "gpt-test-model")
    monkeypatch.setattr(chat_ai, "AsyncOpenAI", FakeClient)

    with pytest.raises(ChatAIUnavailableError, match=expected):
        asyncio.run(
            chat_ai.generate_chat_completion([
                {"role": "user", "content": "Explain."},
            ])
        )


def test_openai_configuration_requires_server_api_key(monkeypatch):
    monkeypatch.setattr(chat_ai, "OPENAI_API_KEY", "")
    monkeypatch.setattr(chat_ai, "OPENAI_MODEL", "gpt-test-model")
    assert chat_ai.chat_ai_is_configured() is False
