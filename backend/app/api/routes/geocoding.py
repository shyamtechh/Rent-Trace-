from fastapi import APIRouter, HTTPException, Query

from app.schemas import CitySearchResult, ReverseGeocodeResult
from app.services.geocoding import (
    GeocoderUnavailableError,
    reverse_geocode,
    search_cities,
    search_hyderabad_area,
)

router = APIRouter(prefix="/api/geocoding", tags=["geocoding"])


@router.get("/reverse", response_model=ReverseGeocodeResult | None)
async def reverse_geocode_location(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict | None:
    try:
        return await reverse_geocode(latitude, longitude)
    except GeocoderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/search", response_model=list[CitySearchResult])
async def search_city(city: str = Query(min_length=2, max_length=100)) -> list[CitySearchResult]:
    try:
        return await search_cities(city)
    except GeocoderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/area-search", response_model=CitySearchResult)
async def search_hyderabad_area_route(
    area: str = Query(min_length=2, max_length=100),
    city: str = Query(default="Hyderabad", min_length=2, max_length=100),
) -> CitySearchResult:
    try:
        result = await search_hyderabad_area(area, city)
    except GeocoderUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Area not found. Please enter a valid {city} locality.",
        )
    return result
