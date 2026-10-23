from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.api.utils import commit_or_conflict
from app.database import get_db
from app.models import Locality, User
from app.schemas import LocalityCreate, LocalityRead

router = APIRouter(prefix="/api/localities", tags=["localities"])


@router.get("", response_model=list[LocalityRead])
def list_localities(
    q: str | None = None,
    city: str | None = None,
    state: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = select(Locality)
    if q:
        query = query.where(Locality.name.ilike(f"%{q.strip()}%"))
    if city:
        query = query.where(Locality.city.ilike(f"%{city.strip()}%"))
    if state:
        query = query.where(Locality.state.ilike(f"%{state.strip()}%"))
    return list(db.scalars(query.order_by(Locality.name).offset(skip).limit(limit)).all())


@router.get("/{locality_id}", response_model=LocalityRead)
def get_locality(locality_id: int, db: Session = Depends(get_db)):
    locality = db.get(Locality, locality_id)
    if locality is None:
        raise HTTPException(status_code=404, detail="Locality not found.")
    return locality


@router.post("", response_model=LocalityRead, status_code=status.HTTP_201_CREATED)
def create_locality(
    payload: LocalityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    locality = Locality(**payload.model_dump())
    db.add(locality)
    commit_or_conflict(db, "A locality with this name and location already exists.")
    db.refresh(locality)
    return locality


@router.put("/{locality_id}", response_model=LocalityRead)
def update_locality(
    locality_id: int,
    payload: LocalityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    locality = db.get(Locality, locality_id)
    if locality is None:
        raise HTTPException(status_code=404, detail="Locality not found.")
    for field, value in payload.model_dump().items():
        setattr(locality, field, value)
    commit_or_conflict(db, "A locality with this name and location already exists.")
    db.refresh(locality)
    return locality


@router.delete("/{locality_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_locality(
    locality_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    locality = db.get(Locality, locality_id)
    if locality is None:
        raise HTTPException(status_code=404, detail="Locality not found.")
    db.delete(locality)
    commit_or_conflict(db, "This locality has related historical or property records and cannot be deleted.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
