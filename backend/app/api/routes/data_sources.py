from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.database import get_db
from app.models import DataSource, User
from app.schemas import DataSourceCreate, DataSourceRead

router = APIRouter(prefix="/api/data-sources", tags=["data sources"])


@router.get("", response_model=list[DataSourceRead])
def list_data_sources(db: Session = Depends(get_db)):
    return list(db.scalars(select(DataSource).order_by(DataSource.source_name)).all())


@router.post("", response_model=DataSourceRead, status_code=status.HTTP_201_CREATED)
def create_data_source(
    payload: DataSourceCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    source = DataSource(**payload.model_dump())
    db.add(source)
    try:
        db.commit()
        db.refresh(source)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This source and dataset are already registered.") from exc
    return source
