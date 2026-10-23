import { readApiResponse } from './apiResponse.js';

export async function fetchLocationSuggestion(latitude, longitude, signal) {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  });
  const response = await fetch(`/api/geocoding/reverse?${params}`, { signal });
  const payload = await readApiResponse(response, 'Get an address suggestion', { allowNull: true });
  if (payload === null) {
    return null;
  }
  if (
    typeof payload.display_name !== 'string'
    || typeof payload.source_name !== 'string'
    || typeof payload.source_url !== 'string'
    || payload.verification_status !== 'suggestion_only'
    || (payload.suggested_locality !== null && typeof payload.suggested_locality !== 'string')
    || (payload.suggested_district !== null && typeof payload.suggested_district !== 'string')
  ) {
    throw new Error('The reverse-geocoding API returned an invalid address suggestion.');
  }
  return payload;
}
