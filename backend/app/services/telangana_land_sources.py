import math

import httpx

from app.core.config import TGRAC_CADASTRAL_LAYER_URL
PARCEL_FIELDS = (
    "OBJECTID_1,OBJECTID,Village,Mandal,District,Parcels,Govt_Land,"
    "Shape_Area,Shape_Length"
)
_BOUNDARY_TOLERANCE = 1e-10


class TelanganaLandSourceUnavailableError(Exception):
    pass


class TelanganaParcelAmbiguousError(Exception):
    pass


def _point_in_ring(longitude: float, latitude: float, ring: list) -> bool:
    inside = False
    for index, point in enumerate(ring):
        next_point = ring[(index + 1) % len(ring)]
        if (
            not isinstance(point, (list, tuple))
            or not isinstance(next_point, (list, tuple))
            or len(point) < 2
            or len(next_point) < 2
        ):
            return False
        try:
            x1, y1 = float(point[0]), float(point[1])
            x2, y2 = float(next_point[0]), float(next_point[1])
        except (TypeError, ValueError):
            return False
        if not all(map(math.isfinite, (x1, y1, x2, y2))):
            return False

        cross = (longitude - x1) * (y2 - y1) - (latitude - y1) * (x2 - x1)
        if (
            abs(cross) <= _BOUNDARY_TOLERANCE
            and min(x1, x2) - _BOUNDARY_TOLERANCE <= longitude <= max(x1, x2) + _BOUNDARY_TOLERANCE
            and min(y1, y2) - _BOUNDARY_TOLERANCE <= latitude <= max(y1, y2) + _BOUNDARY_TOLERANCE
        ):
            return True

        if (y1 > latitude) != (y2 > latitude):
            crossing_longitude = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < crossing_longitude:
                inside = not inside
    return inside


def point_in_esri_rings(longitude: float, latitude: float, rings: list) -> bool:
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return False
    if not isinstance(rings, list) or not rings:
        return False

    inside = False
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            continue
        if _point_in_ring(longitude, latitude, ring):
            inside = not inside
    return inside


async def lookup_cadastral_parcel(latitude: float, longitude: float) -> dict | None:
    parameters = {
        "geometry": f"{longitude},{latitude}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": PARCEL_FIELDS,
        "returnGeometry": "true",
        "outSR": 4326,
        "resultRecordCount": 10,
        "f": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(TGRAC_CADASTRAL_LAYER_URL, params=parameters)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TelanganaLandSourceUnavailableError(
            "TGRAC cadastral lookup is temporarily unavailable."
        ) from exc

    if not isinstance(payload, dict):
        raise TelanganaLandSourceUnavailableError(
            "TGRAC returned an invalid cadastral response."
        )
    if payload.get("error"):
        raise TelanganaLandSourceUnavailableError(
            "TGRAC could not complete the cadastral lookup."
        )
    if payload.get("exceededTransferLimit"):
        raise TelanganaParcelAmbiguousError(
            "TGRAC returned a truncated set of GIS polygons; no unique administrative match can be confirmed."
        )

    features = payload.get("features")
    if not isinstance(features, list):
        raise TelanganaLandSourceUnavailableError(
            "TGRAC returned an invalid cadastral feature list."
        )
    containing_features = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        attributes = feature.get("attributes")
        geometry = feature.get("geometry")
        if (
            isinstance(attributes, dict)
            and isinstance(geometry, dict)
            and isinstance(geometry.get("rings"), list)
            and geometry["rings"]
            and point_in_esri_rings(longitude, latitude, geometry["rings"])
        ):
            containing_features.append({
                "source_name": "TGRAC HMDA Cadastral",
                "source_url": TGRAC_CADASTRAL_LAYER_URL.rsplit("/query", 1)[0],
                "source_feature_id": str(
                    attributes.get("OBJECTID_1")
                    or attributes.get("OBJECTID")
                    or feature.get("id")
                    or ""
                ),
                "district": _optional_text(attributes.get("District")),
                "mandal": _optional_text(attributes.get("Mandal")),
                "village": _optional_text(attributes.get("Village")),
                "parcel_reference": _optional_text(attributes.get("Parcels")),
                "attributes": attributes,
                "geometry": geometry,
                "survey_subdivision_verified": False,
            })
    if len(containing_features) > 1:
        raise TelanganaParcelAmbiguousError(
            "Multiple TGRAC GIS polygons contain this coordinate; no single administrative feature was selected."
        )
    return containing_features[0] if containing_features else None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
