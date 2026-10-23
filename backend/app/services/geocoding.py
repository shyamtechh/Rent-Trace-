import asyncio
from collections import OrderedDict
from time import monotonic

import httpx

from app.core.config import GEOCODER_REVERSE_URL, GEOCODER_SEARCH_URL, GEOCODER_USER_AGENT
from app.schemas import CitySearchResult

REQUEST_INTERVAL_SECONDS = 1.0
CACHE_TTL_SECONDS = 900
CACHE_MAX_ENTRIES = 256
_PROVIDER_LOCK = asyncio.Lock()
_PROVIDER_RATE_LOCK = asyncio.Lock()
_LAST_PROVIDER_REQUEST = 0.0
_CACHE: OrderedDict[str, tuple[float, list[CitySearchResult]]] = OrderedDict()
_REVERSE_CACHE: OrderedDict[str, tuple[float, dict | None]] = OrderedDict()


class GeocoderUnavailableError(Exception):
    pass


def _parse_result(result: dict) -> CitySearchResult | None:
    try:
        latitude = float(result["lat"])
        longitude = float(result["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    display_name = str(result.get("display_name") or "").strip()
    name = str(result.get("name") or display_name.split(",", 1)[0]).strip()
    if not name or not display_name:
        return None

    bounds = None
    raw_bounds = result.get("boundingbox")
    if isinstance(raw_bounds, list) and len(raw_bounds) == 4:
        try:
            south, north, west, east = (float(value) for value in raw_bounds)
        except (TypeError, ValueError):
            pass
        else:
            valid_latitudes = -90 <= south <= north <= 90
            valid_longitudes = -180 <= west <= east <= 180
            if valid_latitudes and valid_longitudes:
                bounds = ((south, west), (north, east))

    osm_type = str(result.get("osm_type") or "place")
    osm_id = str(result.get("osm_id") or result.get("place_id") or f"{latitude}:{longitude}")
    return CitySearchResult(
        id=f"{osm_type}:{osm_id}",
        name=name,
        display_name=display_name,
        center=(latitude, longitude),
        bounds=bounds,
    )


def _cached_results(key: str) -> list[CitySearchResult] | None:
    cached = _CACHE.get(key)
    if cached is None:
        return None
    expires_at, results = cached
    if expires_at <= monotonic():
        del _CACHE[key]
        return None
    _CACHE.move_to_end(key)
    return results


async def _request_provider(url: str, params: dict[str, object]) -> object:
    global _LAST_PROVIDER_REQUEST

    async with _PROVIDER_RATE_LOCK:
        wait_seconds = REQUEST_INTERVAL_SECONDS - (monotonic() - _LAST_PROVIDER_REQUEST)
        if wait_seconds > 0:
            await asyncio.sleep(wait_seconds)

        async with httpx.AsyncClient(
            timeout=8.0,
            headers={
                "User-Agent": GEOCODER_USER_AGENT,
                "Accept-Language": "en",
            },
        ) as client:
            _LAST_PROVIDER_REQUEST = monotonic()
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    return payload


async def _request_geocoder(params: dict[str, object]) -> list[dict]:
    payload = await _request_provider(GEOCODER_SEARCH_URL, params)
    if not isinstance(payload, list):
        raise GeocoderUnavailableError("The geocoding provider returned an invalid response.")
    return payload


async def reverse_geocode(latitude: float, longitude: float) -> dict | None:
    cache_key = f"{latitude:.6f}:{longitude:.6f}"
    cached = _REVERSE_CACHE.get(cache_key)
    if cached and cached[0] > monotonic():
        _REVERSE_CACHE.move_to_end(cache_key)
        return cached[1]
    if cached:
        del _REVERSE_CACHE[cache_key]

    try:
        payload = await _request_provider(
            GEOCODER_REVERSE_URL,
            {
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "addressdetails": 1,
            },
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocoderUnavailableError("Address suggestion is temporarily unavailable.") from exc
    if not isinstance(payload, dict):
        raise GeocoderUnavailableError("The geocoding provider returned an invalid address response.")

    display_name = str(payload.get("display_name") or "").strip()
    address = payload.get("address")
    if not display_name or not isinstance(address, dict):
        result = None
    else:
        locality = next(
            (
                str(address[key]).strip()
                for key in ("suburb", "neighbourhood", "quarter", "village", "town", "city_district", "city")
                if isinstance(address.get(key), str) and address[key].strip()
            ),
            None,
        )
        result = {
            "display_name": display_name,
            "suggested_locality": locality,
            "suggested_district": next(
                (
                    str(address[key]).strip()
                    for key in ("state_district", "county", "district")
                    if isinstance(address.get(key), str) and address[key].strip()
                ),
                None,
            ),
            "source_name": "OpenStreetMap Nominatim",
            "source_url": GEOCODER_REVERSE_URL,
            "verification_status": "suggestion_only",
        }

    _REVERSE_CACHE[cache_key] = (monotonic() + CACHE_TTL_SECONDS, result)
    _REVERSE_CACHE.move_to_end(cache_key)
    while len(_REVERSE_CACHE) > CACHE_MAX_ENTRIES:
        _REVERSE_CACHE.popitem(last=False)
    return result


async def search_hyderabad_area(area: str, city: str = "Hyderabad") -> CitySearchResult | None:
    normalized_city = " ".join(city.split())
    city_context = f"{normalized_city}, Telangana, India" if normalized_city.casefold() == "hyderabad" else f"{normalized_city}, India"
    query = f"{area.strip()}, {city_context}"
    try:
        payload = await _request_geocoder(
            {
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": 1,
            }
        )
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocoderUnavailableError("Area search is temporarily unavailable.") from exc

    if not payload:
        return None
    result = _parse_result(payload[0])
    if result is None:
        return None
    display_name = result.display_name.casefold()
    if normalized_city.casefold() not in display_name:
        return None
    if normalized_city.casefold() == "hyderabad" and "telangana" not in display_name:
        return None
    return result


async def search_cities(city: str) -> list[CitySearchResult]:
    query = " ".join(city.split())
    cache_key = query.casefold()
    cached = _cached_results(cache_key)
    if cached is not None:
        return cached

    async with _PROVIDER_LOCK:
        cached = _cached_results(cache_key)
        if cached is not None:
            return cached

        try:
            payload = await _request_geocoder(
                {
                    "q": query,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "featuretype": "city",
                    "limit": 5,
                }
            )
        except (httpx.HTTPError, ValueError) as exc:
            raise GeocoderUnavailableError("City search is temporarily unavailable.") from exc

        results = [parsed for item in payload if (parsed := _parse_result(item)) is not None]
        _CACHE[cache_key] = (monotonic() + CACHE_TTL_SECONDS, results)
        _CACHE.move_to_end(cache_key)
        while len(_CACHE) > CACHE_MAX_ENTRIES:
            _CACHE.popitem(last=False)
        return results
