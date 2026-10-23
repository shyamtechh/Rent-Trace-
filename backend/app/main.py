from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.routes import admin, analytics, auth, chat, data_sources, geocoding, health, imports, land_analysis, land_identification, localities, properties, rentals
from app.core.config import CORS_ORIGINS
from app.database import get_db
from app.models import DataSource, Locality, PriceHistory, RentalPrice

app = FastAPI(title="RentTrace API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def protect_cookie_mutations(request: Request, call_next):
    if (
        request.method in {"POST", "PUT", "DELETE"}
        and request.cookies.get("renttrace_session")
        and not request.headers.get("Authorization", "").lower().startswith("bearer ")
        and request.headers.get("origin") not in CORS_ORIGINS
    ):
        return JSONResponse(status_code=403, content={"detail": "Request origin is not allowed."})
    return await call_next(request)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, _exc: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Database operation unavailable."})

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(localities.router)
app.include_router(geocoding.router)
app.include_router(properties.router)
app.include_router(rentals.router)
app.include_router(analytics.router)
app.include_router(data_sources.router)
app.include_router(imports.router)
app.include_router(land_analysis.router)
app.include_router(land_identification.router)
app.include_router(chat.router)


@app.get("/")
def root() -> dict:
    return {"message": "RentTrace API is running"}


@app.get("/api/db-status")
def get_db_status(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    dialect = db.get_bind().dialect.name
    return {"status": "ok", "database": "postgresql" if dialect == "postgresql" else "sqlite"}


@app.get("/api/overview")
def get_overview(db: Session = Depends(get_db)) -> dict:
    city_name = "Hyderabad"
    localities = db.scalars(
        select(Locality)
        .where(func.lower(Locality.city) == city_name.lower())
        .order_by(Locality.name)
    ).all()
    history = db.execute(
        select(PriceHistory.observation_date, PriceHistory.average_rent)
        .join(Locality, PriceHistory.locality_id == Locality.id)
        .where(
            func.lower(Locality.city) == city_name.lower(),
            PriceHistory.average_rent.is_not(None),
        )
        .order_by(PriceHistory.observation_date)
    ).all()
    monthly_rents: dict[tuple[int, int], list[float]] = {}
    for observation_date, average_rent_value in history:
        monthly_rents.setdefault((observation_date.year, observation_date.month), []).append(
            float(average_rent_value)
        )
    trend = [
        {
            "month": date(year, month, 1).strftime("%b %y"),
            "price": round(sum(values) / len(values), 2),
        }
        for (year, month), values in sorted(monthly_rents.items())[-6:]
    ]
    rents = [row["price"] for row in trend]
    if not rents:
        average = db.scalar(
            select(func.avg(RentalPrice.rent))
            .join(Locality, RentalPrice.locality_id == Locality.id)
            .where(
                func.lower(Locality.city) == city_name.lower(),
                RentalPrice.deleted_at.is_(None),
            )
        )
        rents = [float(average)] if average is not None else []
    average_rent = round(rents[-1]) if rents else 0
    monthly_change = 0.0
    if len(rents) > 1 and float(rents[-2]) != 0:
        monthly_change = round((float(rents[-1]) - float(rents[-2])) / float(rents[-2]) * 100, 1)
    has_synthetic_source = db.scalar(
        select(DataSource.id)
        .join(RentalPrice, RentalPrice.source_id == DataSource.id)
        .join(Locality, RentalPrice.locality_id == Locality.id)
        .where(
            DataSource.source_name == "RentTrace synthetic development sample",
            func.lower(Locality.city) == city_name.lower(),
        )
        .limit(1)
    ) is not None

    return {
        "city": city_name,
        "average_rent": average_rent,
        "monthly_change": monthly_change,
        "market_status": "Stable" if trend else "No market observations",
        "localities": [locality.name for locality in localities[:4]],
        "data_notice": (
            "DEMO DATA: These values are synthetic examples, not real-world market observations."
            if has_synthetic_source
            else None
        ),
        "trend": trend,
    }
