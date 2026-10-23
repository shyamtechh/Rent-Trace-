from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import TGRAC_CADASTRAL_LAYER_URL
from app.database import get_db
from app.models import GovernmentLandRate, LandParcel, LandValuation
from app.schemas import LandValuationCreate
from app.services.land_valuation import calculate_land_value
from app.services.renttrace_dataset import (
    get_locality_land_price_history,
    get_locality_land_rate,
    get_locality_records,
)
from app.services.telangana_land_sources import (
    TelanganaParcelAmbiguousError,
    TelanganaLandSourceUnavailableError,
    lookup_cadastral_parcel,
)

router = APIRouter(prefix="/api/land-analysis", tags=["land analysis"])


@router.get("/locality/{locality_name}")
def get_land_analysis_dataset(locality_name: str) -> dict:
    try:
        records = get_locality_records(locality_name)
        estimated_land_rate = get_locality_land_rate(locality_name)
        historical_land_prices = get_locality_land_price_history(locality_name)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    locality = records[0]["locality"] if records else locality_name
    return {
        "locality": locality,
        "record_count": len(records),
        "records": records,
        "estimated_land_rate": estimated_land_rate,
        "historical_land_prices": historical_land_prices,
    }


@router.get("/parcel")
async def get_cadastral_parcel(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict:
    try:
        parcel = await lookup_cadastral_parcel(latitude, longitude)
    except TelanganaLandSourceUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TelanganaParcelAmbiguousError as exc:
        return {
            "found": False,
            "ambiguous": True,
            "administrative_status": "ambiguous",
            "survey_number_status": "not_verified",
            "parcel": None,
            "lookup_coordinates": {"latitude": latitude, "longitude": longitude},
            "source_url": TGRAC_CADASTRAL_LAYER_URL.rsplit("/query", 1)[0],
            "notice": (
                "Multiple TGRAC GIS polygons contain this coordinate. "
                "No single administrative feature was selected."
            ),
        }
    return {
        "found": parcel is not None,
        "ambiguous": False,
        "administrative_status": "matched" if parcel else "not_available",
        "parcel": parcel,
        "lookup_coordinates": {"latitude": latitude, "longitude": longitude},
        "source_url": TGRAC_CADASTRAL_LAYER_URL.rsplit("/query", 1)[0],
        "notice": (
            "District, mandal, and village are attributes from the TGRAC polygon containing the query point. "
            "This is an administrative GIS match, not a legal plot-boundary or ownership determination."
            if parcel
            else "No containing feature was returned in the available HMDA layer. Administrative coverage may be limited; this does not establish that no parcel exists."
        ),
        "survey_number_status": "not_verified",
        "survey_number_notice": (
            "TGRAC's Parcels attribute is not treated as an official survey/subdivision number. "
            "Verify survey details through Bhu Bharati."
        ),
    }


@router.post("/valuation", status_code=status.HTTP_201_CREATED)
async def create_land_valuation(
    payload: LandValuationCreate,
    db: Session = Depends(get_db),
) -> dict:
    area_square_yards, total_value = calculate_land_value(
        payload.area_square_feet,
        payload.rate_per_sq_yard,
    )
    parcel_source_status = "no_match"
    parcel_id = None
    parcel_details = None
    try:
        parcel_details = await lookup_cadastral_parcel(
            float(payload.latitude),
            float(payload.longitude),
        )
    except TelanganaLandSourceUnavailableError:
        parcel_source_status = "unavailable"
    except TelanganaParcelAmbiguousError:
        parcel_source_status = "ambiguous"

    if parcel_details:
        parcel_source_status = "matched"
        feature_id = parcel_details["source_feature_id"]
        if feature_id:
            existing_parcel = db.query(LandParcel).filter_by(
                source_name=parcel_details["source_name"],
                source_feature_id=feature_id,
            ).one_or_none()
            if existing_parcel is None:
                existing_parcel = LandParcel(
                    **parcel_details,
                    latitude=payload.latitude,
                    longitude=payload.longitude,
                )
                db.add(existing_parcel)
                db.flush()
            else:
                existing_parcel.latitude = payload.latitude
                existing_parcel.longitude = payload.longitude
                existing_parcel.district = parcel_details["district"]
                existing_parcel.mandal = parcel_details["mandal"]
                existing_parcel.village = parcel_details["village"]
                existing_parcel.parcel_reference = parcel_details["parcel_reference"]
                existing_parcel.attributes = parcel_details["attributes"]
                existing_parcel.geometry = parcel_details["geometry"]
            parcel_id = existing_parcel.id

    rate_record = GovernmentLandRate(
        parcel_id=parcel_id,
        district=payload.district or (parcel_details or {}).get("district"),
        mandal=payload.mandal or (parcel_details or {}).get("mandal"),
        village=payload.village or (parcel_details or {}).get("village"),
        survey_subdivision=payload.survey_subdivision,
        rate_per_sq_yard=payload.rate_per_sq_yard,
        rate_unit=payload.rate_unit,
        property_category=payload.property_category.strip(),
        source_type="government_guideline_rate",
        survey_subdivision_verified=payload.survey_subdivision_verified,
        rate_date=payload.rate_date,
        verified_date=payload.verified_date,
        source_url=payload.source_url,
        verification_method="manual_user_attested",
    )
    db.add(rate_record)
    db.flush()

    confidence_note = (
        "Arithmetic uses the polygon area and a rate manually entered and confirmed by the user from Bhu Bharati. "
        "RentTrace does not independently verify the rate; this is not a market sale price or legal valuation."
    )
    if parcel_source_status == "unavailable":
        confidence_note += " TGRAC parcel lookup was unavailable; valuation is not linked to a GIS parcel."
    elif parcel_source_status == "no_match":
        confidence_note += " No matching TGRAC cadastral feature was returned for the lookup coordinate."
    elif parcel_source_status == "ambiguous":
        confidence_note += " Multiple TGRAC cadastral features were returned; no single GIS parcel was selected."

    valuation = LandValuation(
        parcel_id=parcel_id,
        rate_id=rate_record.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        area_square_feet=payload.area_square_feet,
        area_square_yards=area_square_yards,
        area_method=payload.area_method,
        rate_per_sq_yard=payload.rate_per_sq_yard,
        total_value=total_value,
        estimation_method="Area (sq.yd) × manually confirmed Bhu Bharati rate (INR/sq.yd)",
        confidence_note=confidence_note,
    )
    db.add(valuation)
    db.commit()
    db.refresh(valuation)
    db.refresh(rate_record)

    return {
        "valuation_id": valuation.id,
        "latitude": valuation.latitude,
        "longitude": valuation.longitude,
        "area_square_feet": valuation.area_square_feet,
        "area_square_yards": valuation.area_square_yards,
        "rate_per_sq_yard": valuation.rate_per_sq_yard,
        "total_value": valuation.total_value,
        "source_url": rate_record.source_url,
        "source_type": rate_record.source_type,
        "rate_unit": rate_record.rate_unit,
        "property_category": rate_record.property_category,
        "survey_subdivision_verified": rate_record.survey_subdivision_verified,
        "district": rate_record.district,
        "mandal": rate_record.mandal,
        "village": rate_record.village,
        "survey_subdivision": rate_record.survey_subdivision,
        "rate_date": rate_record.rate_date,
        "verified_date": rate_record.verified_date,
        "verification_method": rate_record.verification_method,
        "area_method": valuation.area_method,
        "estimation_method": valuation.estimation_method,
        "confidence_note": valuation.confidence_note,
        "parcel_status": parcel_source_status,
        "parcel": parcel_details,
        "market_value_estimate": None,
        "market_value_note": "No verified market comparable data is currently available; this result is based only on the user-confirmed government guidance rate.",
    }
