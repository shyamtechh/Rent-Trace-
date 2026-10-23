import { readApiResponse } from './apiResponse.js';

const IDENTIFICATION_STATUSES = new Set([
  'source_not_configured',
  'no_verified_data',
  'ambiguous',
  'administrative_match_only',
]);

export async function identifyLandAtPoint(latitude, longitude, signal) {
  const parameters = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  });
  const response = await fetch(`/api/land/identify?${parameters}`, { signal });
  const payload = await readApiResponse(response, 'Identify land at this point');
  if (
    !IDENTIFICATION_STATUSES.has(payload.status)
    || typeof payload.coordinates?.latitude !== 'number'
    || typeof payload.coordinates?.longitude !== 'number'
    || !['unavailable', 'not_found', 'found'].includes(payload.survey_number_status)
    || typeof payload.verification_status !== 'string'
    || typeof payload.notice !== 'string'
    || (payload.source_url !== null && typeof payload.source_url !== 'string')
    || (payload.gis_feature_boundary !== null
      && !Array.isArray(payload.gis_feature_boundary?.rings))
  ) {
    throw new Error('The land-identification API returned an invalid response.');
  }
  return payload;
}
