import { readApiResponse } from './apiResponse.js';

export const BHUBHARATI_MARKET_VALUE_URL =
  'https://bhubharati.telangana.gov.in/viewMarketValueLandStampDuty?lang=en';
export const BHUBHARATI_GIS_URL = 'https://bhubharati.telangana.gov.in/gis/';

export async function fetchCadastralParcel(latitude, longitude, signal) {
  const parameters = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  });
  const response = await fetch(`/api/land-analysis/parcel?${parameters}`, { signal });
  const payload = await readApiResponse(response, 'Look up the TGRAC cadastral parcel');
  if (
    typeof payload.found !== 'boolean'
    || !['matched', 'not_available', 'ambiguous'].includes(payload.administrative_status)
    || payload.survey_number_status !== 'not_verified'
    || typeof payload.source_url !== 'string'
    || (payload.found && (
      !payload.parcel
      || typeof payload.parcel.source_feature_id !== 'string'
      || !payload.parcel.geometry
      || !Array.isArray(payload.parcel.geometry.rings)
    ))
    || (!payload.found && payload.parcel !== null)
  ) {
    throw new Error('The TGRAC parcel API returned an invalid response.');
  }
  return payload;
}

export async function submitLandValuation(valuation, signal) {
  const response = await fetch('/api/land-analysis/valuation', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(valuation),
    signal,
  });
  const payload = await readApiResponse(response, 'Calculate land value');
  if (
    !Number.isInteger(payload.valuation_id)
    || typeof payload.area_square_yards !== 'string'
    || typeof payload.rate_per_sq_yard !== 'string'
    || typeof payload.total_value !== 'string'
    || payload.rate_unit !== 'INR/sq_yd'
    || typeof payload.property_category !== 'string'
    || payload.source_type !== 'government_guideline_rate'
    || typeof payload.survey_subdivision_verified !== 'boolean'
    || !['matched', 'no_match', 'ambiguous', 'unavailable'].includes(payload.parcel_status)
    || typeof payload.confidence_note !== 'string'
    || payload.market_value_estimate !== null
  ) {
    throw new Error('The land valuation API returned an invalid response.');
  }
  return payload;
}
