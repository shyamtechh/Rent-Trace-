from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.api.utils import commit_or_conflict
from app.database import get_db
from app.models import Locality, Property, User
from app.schemas import PropertyCreate, PropertyRead

router = APIRouter(prefix="/api/properties", tags=["properties"])


@router.get("", response_model=list[PropertyRead])
def list_properties(
    locality_id: int | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(Property)
    if locality_id is not None:
        query = query.where(Property.locality_id == locality_id)
    return list(db.scalars(query.order_by(Property.id).offset(skip).limit(limit)).all())


@router.get("/{property_id}", response_model=PropertyRead)
def get_property(property_id: int, db: Session = Depends(get_db)):
    property_record = db.get(Property, property_id)
    if property_record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    return property_record


@router.post("", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
def create_property(
    payload: PropertyCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    if db.get(Locality, payload.locality_id) is None:
        raise HTTPException(status_code=422, detail="locality_id does not reference an existing locality.")
    property_record = Property(**payload.model_dump())
    db.add(property_record)
    commit_or_conflict(db)
    db.refresh(property_record)
    return property_record


@router.put("/{property_id}", response_model=PropertyRead)
def update_property(
    property_id: int,
    payload: PropertyCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    property_record = db.get(Property, property_id)
    if property_record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    if db.get(Locality, payload.locality_id) is None:
        raise HTTPException(status_code=422, detail="locality_id does not reference an existing locality.")
    for field, value in payload.model_dump().items():
        setattr(property_record, field, value)
    commit_or_conflict(db)
    db.refresh(property_record)
    return property_record


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(
    property_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    property_record = db.get(Property, property_id)
    if property_record is None:
        raise HTTPException(status_code=404, detail="Property not found.")
    db.delete(property_record)
    commit_or_conflict(db, "This property has rental history and cannot be deleted.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
