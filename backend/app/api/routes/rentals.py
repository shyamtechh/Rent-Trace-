from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.api.utils import commit_or_conflict
from app.database import get_db
from app.models import DataSource, Locality, Property, RentalPrice, User
from app.schemas import RentalCreate, RentalRead

router = APIRouter(prefix="/api/rentals", tags=["rentals"])


def validate_rental_links(payload: RentalCreate, db: Session) -> None:
    property_record = db.get(Property, payload.property_id)
    if property_record is None:
        raise HTTPException(status_code=422, detail="property_id does not reference an existing property.")
    if property_record.locality_id != payload.locality_id:
        raise HTTPException(status_code=422, detail="The rental locality must match the property's locality.")
    if db.get(Locality, payload.locality_id) is None:
        raise HTTPException(status_code=422, detail="locality_id does not reference an existing locality.")
    if db.get(DataSource, payload.source_id) is None:
        raise HTTPException(status_code=422, detail="source_id does not reference an existing data source.")


@router.get("", response_model=list[RentalRead])
def list_rentals(
    locality_id: int | None = None,
    property_id: int | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(RentalPrice).where(RentalPrice.deleted_at.is_(None))
    if locality_id is not None:
        query = query.where(RentalPrice.locality_id == locality_id)
    if property_id is not None:
        query = query.where(RentalPrice.property_id == property_id)
    return list(db.scalars(query.order_by(RentalPrice.observation_date.desc()).offset(skip).limit(limit)).all())


@router.get("/{rental_id}", response_model=RentalRead)
def get_rental(rental_id: int, db: Session = Depends(get_db)):
    rental = db.get(RentalPrice, rental_id)
    if rental is None or rental.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Rental observation not found.")
    return rental


@router.post("", response_model=RentalRead, status_code=status.HTTP_201_CREATED)
def create_rental(
    payload: RentalCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    validate_rental_links(payload, db)
    rental = RentalPrice(**payload.model_dump())
    db.add(rental)
    commit_or_conflict(db, "A rental observation for this property, date, and source already exists.")
    db.refresh(rental)
    return rental


@router.put("/{rental_id}", response_model=RentalRead)
def update_rental(
    rental_id: int,
    payload: RentalCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rental = db.get(RentalPrice, rental_id)
    if rental is None:
        raise HTTPException(status_code=404, detail="Rental observation not found.")
    validate_rental_links(payload, db)
    for field, value in payload.model_dump().items():
        setattr(rental, field, value)
    commit_or_conflict(db, "A rental observation for this property, date, and source already exists.")
    db.refresh(rental)
    return rental


@router.delete("/{rental_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rental(
    rental_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    rental = db.get(RentalPrice, rental_id)
    if rental is None or rental.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Rental observation not found.")
    rental.deleted_at = datetime.now(timezone.utc)
    commit_or_conflict(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
