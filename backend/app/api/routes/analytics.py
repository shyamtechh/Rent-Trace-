from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Locality, LocalityFactor, PriceHistory, RentalPrice

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def ensure_locality(locality_id: int, db: Session) -> Locality:
    locality = db.get(Locality, locality_id)
    if locality is None:
        raise HTTPException(status_code=404, detail="Locality not found.")
    return locality


@router.get("/locality/{locality_id}")
def locality_analytics(locality_id: int, db: Session = Depends(get_db)) -> dict:
    locality = ensure_locality(locality_id, db)
    latest = db.scalar(
        select(PriceHistory)
        .where(PriceHistory.locality_id == locality_id)
        .order_by(PriceHistory.observation_date.desc())
        .limit(1)
    )
    rental_average = db.scalar(
        select(func.avg(RentalPrice.rent)).where(
            RentalPrice.locality_id == locality_id,
            RentalPrice.deleted_at.is_(None),
        )
    )
    return {
        "locality_id": locality.id,
        "name": locality.name,
        "city": locality.city,
        "state": locality.state,
        "latest_market_observation": latest.observation_date if latest else None,
        "average_property_price": latest.average_property_price if latest else None,
        "average_rent": latest.average_rent if latest else rental_average,
        "median_rent": latest.median_rent if latest else None,
        "sample_size": latest.sample_size if latest else None,
    }


@router.get("/locality/{locality_id}/rent-trend")
def rent_trend(locality_id: int, db: Session = Depends(get_db)) -> dict:
    ensure_locality(locality_id, db)
    rows = db.execute(
        select(RentalPrice.observation_date, func.avg(RentalPrice.rent).label("average_rent"))
        .where(RentalPrice.locality_id == locality_id, RentalPrice.deleted_at.is_(None))
        .group_by(RentalPrice.observation_date)
        .order_by(RentalPrice.observation_date)
    ).all()
    return {
        "locality_id": locality_id,
        "observations": [
            {"observation_date": row.observation_date, "average_rent": row.average_rent}
            for row in rows
        ],
    }


@router.get("/locality/{locality_id}/price-trend")
def price_trend(locality_id: int, db: Session = Depends(get_db)) -> dict:
    ensure_locality(locality_id, db)
    rows = db.scalars(
        select(PriceHistory)
        .where(PriceHistory.locality_id == locality_id)
        .order_by(PriceHistory.observation_date)
    ).all()
    return {
        "locality_id": locality_id,
        "observations": [
            {
                "observation_date": row.observation_date,
                "average_property_price": row.average_property_price,
                "average_price_per_sqft": row.average_price_per_sqft,
                "median_price": row.median_price,
                "sample_size": row.sample_size,
            }
            for row in rows
        ],
    }


@router.get("/locality/{locality_id}/factors")
def locality_factors(locality_id: int, db: Session = Depends(get_db)) -> dict:
    ensure_locality(locality_id, db)
    rows = db.scalars(
        select(LocalityFactor)
        .where(LocalityFactor.locality_id == locality_id)
        .order_by(LocalityFactor.observation_date)
    ).all()
    return {"locality_id": locality_id, "observations": rows}


@router.get("/compare")
def compare_localities(
    locality_ids: list[int] = Query(min_length=2, max_length=10),
    db: Session = Depends(get_db),
) -> dict:
    localities = db.scalars(select(Locality).where(Locality.id.in_(set(locality_ids)))).all()
    by_id = {locality.id: locality for locality in localities}
    missing_ids = sorted(set(locality_ids) - by_id.keys())
    if missing_ids:
        raise HTTPException(status_code=404, detail={"message": "Localities not found.", "ids": missing_ids})

    latest_rows = db.execute(
        select(PriceHistory.locality_id, func.max(PriceHistory.observation_date).label("latest_date"))
        .where(PriceHistory.locality_id.in_(by_id))
        .group_by(PriceHistory.locality_id)
    ).all()
    latest_dates = {row.locality_id: row.latest_date for row in latest_rows}
    comparisons = []
    for locality_id in locality_ids:
        locality = by_id[locality_id]
        latest = None
        if locality_id in latest_dates:
            latest = db.scalar(
                select(PriceHistory).where(
                    PriceHistory.locality_id == locality_id,
                    PriceHistory.observation_date == latest_dates[locality_id],
                )
            )
        comparisons.append({
            "locality_id": locality.id,
            "name": locality.name,
            "city": locality.city,
            "state": locality.state,
            "observation_date": latest.observation_date if latest else None,
            "average_property_price": latest.average_property_price if latest else None,
            "average_rent": latest.average_rent if latest else None,
            "average_price_per_sqft": latest.average_price_per_sqft if latest else None,
            "median_rent": latest.median_rent if latest else None,
        })
    return {"comparisons": comparisons}
