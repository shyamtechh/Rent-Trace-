from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.database import get_db
from app.models import DataSource, Locality, Property, User

router = APIRouter(prefix="/api/admin", tags=["administration"])


@router.get("/overview")
def admin_overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    has_synthetic_source = db.scalar(
        select(DataSource.id).where(
            DataSource.source_name == "RentTrace synthetic development sample"
        ).limit(1)
    ) is not None
    return {
        "message": "Admin dashboard access granted",
        "admin_name": admin.name,
        "data_notice": (
            "DEMO DATA: Synthetic development records are included in these counts; they are not real-world observations."
            if has_synthetic_source
            else None
        ),
        "summary": {
            "total_users": db.scalar(select(func.count(User.id))) or 0,
            "active_listings": db.scalar(select(func.count(Property.id))) or 0,
            "localities": db.scalar(select(func.count(Locality.id))) or 0,
        },
    }
