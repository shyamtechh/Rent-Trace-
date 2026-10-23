from fastapi import APIRouter, HTTPException, Query, status

from app.services.land_identification import identify_land
from app.services.telangana_land_sources import TelanganaLandSourceUnavailableError

router = APIRouter(prefix="/api/land", tags=["land identification"])


@router.get("/identify")
async def identify_land_route(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict:
    try:
        return await identify_land(latitude, longitude)
    except TelanganaLandSourceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "source_unavailable",
                "message": str(exc),
                "survey_number_status": "unavailable",
                "verification_status": "not_verified",
            },
        ) from exc
