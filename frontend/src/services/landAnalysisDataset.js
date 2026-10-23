import { readApiResponse } from './apiResponse.js';

export async function fetchLandAnalysisLocality(localityName, signal) {
  const response = await fetch(
    `/api/land-analysis/locality/${encodeURIComponent(localityName)}`,
    { signal },
  );
  const payload = await readApiResponse(response, 'Load the validated locality dataset');
  if (
    typeof payload.locality !== 'string'
    || !Number.isInteger(payload.record_count)
    || !Array.isArray(payload.records)
    || payload.record_count !== payload.records.length
    || !Array.isArray(payload.historical_land_prices)
    || payload.historical_land_prices.some((item) => (
      !Number.isInteger(item?.year)
      || typeof item.value_per_sqft !== 'number'
      || !Number.isFinite(item.value_per_sqft)
      || item.value_per_sqft <= 0
      || !Number.isInteger(item.sample_count)
      || item.sample_count < 1
      || !Array.isArray(item.source_fields)
      || item.source_fields.some((field) => typeof field !== 'string')
    ))
    || typeof payload.estimated_land_rate?.available !== 'boolean'
    || (
      payload.estimated_land_rate.available
      && (
        typeof payload.estimated_land_rate.value_per_sqft !== 'number'
        || !Number.isFinite(payload.estimated_land_rate.value_per_sqft)
        || payload.estimated_land_rate.value_per_sqft <= 0
      )
    )
  ) {
    throw new Error('The land-analysis dataset API returned invalid locality records.');
  }

  return payload;
}
