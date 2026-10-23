from typing import Protocol

from app.core.config import TGRAC_CADASTRAL_LAYER_URL
from app.services.telangana_land_sources import (
    TelanganaLandSourceUnavailableError,
    TelanganaParcelAmbiguousError,
    lookup_cadastral_parcel,
)


class LandRecordProvider(Protocol):
    name: str
    source_url: str
    state_name: str | None

    async def identify(self, latitude: float, longitude: float) -> dict | None: ...


class TelanganaTgracProvider:
    name = "TGRAC HMDA GIS"
    state_name = "Telangana"
    source_url = TGRAC_CADASTRAL_LAYER_URL.rsplit("/query", 1)[0]

    async def identify(self, latitude: float, longitude: float) -> dict | None:
        return await lookup_cadastral_parcel(latitude, longitude)


LAND_RECORD_PROVIDERS: tuple[LandRecordProvider, ...] = (
    TelanganaTgracProvider(),
)


def _empty_result(
    latitude: float,
    longitude: float,
    status: str,
    provider: LandRecordProvider | None,
    notice: str,
) -> dict:
    return {
        "status": status,
        "coordinates": {"latitude": latitude, "longitude": longitude},
        "state": None,
        "district": None,
        "mandal_taluk": None,
        "village": None,
        "locality": None,
        "survey_number": None,
        "subdivision_number": None,
        "survey_number_status": "unavailable",
        "administrative_status": "not_available",
        "gis_feature_boundary": None,
        "parcel_boundary": None,
        "land_area_square_meters": None,
        "government_guideline_rate": None,
        "estimated_market_rate": None,
        "estimated_total_land_value": None,
        "provider": provider.name if provider else None,
        "source_url": provider.source_url if provider else None,
        "source_record_id": None,
        "verification_status": "not_verified",
        "last_updated": None,
        "notice": notice,
    }


async def identify_land(latitude: float, longitude: float) -> dict:
    if not LAND_RECORD_PROVIDERS:
        return _empty_result(
            latitude,
            longitude,
            "source_not_configured",
            None,
            "No authorized cadastral provider is configured for this location.",
        )

    matches: list[tuple[LandRecordProvider, dict]] = []
    for provider in LAND_RECORD_PROVIDERS:
        try:
            feature = await provider.identify(latitude, longitude)
        except TelanganaParcelAmbiguousError:
            result = _empty_result(
                latitude,
                longitude,
                "ambiguous",
                provider,
                "Multiple GIS features contain this coordinate. No parcel or survey number was selected.",
            )
            result["administrative_status"] = "ambiguous"
            return result
        except TelanganaLandSourceUnavailableError:
            raise
        if feature is not None:
            matches.append((provider, feature))

    if len(matches) > 1:
        return _empty_result(
            latitude,
            longitude,
            "ambiguous",
            None,
            "Multiple configured providers returned a containing feature. No parcel or survey number was selected.",
        )

    if not matches:
        provider = LAND_RECORD_PROVIDERS[0]
        return _empty_result(
            latitude,
            longitude,
            "no_verified_data",
            provider,
            (
                "The configured TGRAC HMDA layer returned no containing feature. "
                "This does not establish that no parcel exists or that the location is outside Telangana."
            ),
        )

    provider, feature = matches[0]
    result = _empty_result(
        latitude,
        longitude,
        "administrative_match_only",
        provider,
        (
            "TGRAC returned a containing GIS feature, but its Parcels field is not verified as a survey number. "
            "This feature is not confirmed as an official cadastral parcel boundary."
        ),
    )
    result.update({
        "state": getattr(provider, "state_name", None),
        "district": feature.get("district"),
        "mandal_taluk": feature.get("mandal"),
        "village": feature.get("village"),
        "administrative_status": "matched",
        "gis_feature_boundary": feature.get("geometry"),
        "source_record_id": feature.get("source_feature_id"),
        "verification_status": "administrative_gis_only",
    })
    return result
