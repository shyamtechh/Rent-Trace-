import assert from 'node:assert/strict';
import test from 'node:test';
import { identifyLandAtPoint } from './landIdentification.js';

test('requests point identification and preserves unverified survey status', async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl;
  globalThis.fetch = async (url) => {
    requestUrl = url;
    return new Response(JSON.stringify({
      status: 'administrative_match_only',
      coordinates: { latitude: 17.44, longitude: 78.39 },
      state: 'Telangana',
      district: 'Rangareddy',
      mandal_taluk: 'Serilingampally',
      village: 'Madhapur',
      locality: null,
      survey_number: null,
      subdivision_number: null,
      survey_number_status: 'unavailable',
      administrative_status: 'matched',
      gis_feature_boundary: { rings: [[[78.3, 17.4], [78.4, 17.4], [78.3, 17.4]]] },
      parcel_boundary: null,
      land_area_square_meters: null,
      government_guideline_rate: null,
      estimated_market_rate: null,
      estimated_total_land_value: null,
      provider: 'TGRAC HMDA GIS',
      source_url: 'https://tgrac.telangana.gov.in/map',
      source_record_id: 'feature-1',
      verification_status: 'administrative_gis_only',
      last_updated: null,
      notice: 'No official survey number is provided.',
    }), { status: 200 });
  };
  try {
    const result = await identifyLandAtPoint(17.44, 78.39);
    assert.equal(requestUrl, '/api/land/identify?latitude=17.44&longitude=78.39');
    assert.equal(result.survey_number, null);
    assert.equal(result.survey_number_status, 'unavailable');
    assert.equal(result.parcel_boundary, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('reports unsupported or unavailable provider results without inventing a survey number', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    status: 'no_verified_data',
    coordinates: { latitude: 19.07, longitude: 72.87 },
    state: null,
    district: null,
    mandal_taluk: null,
    village: null,
    locality: null,
    survey_number: null,
    subdivision_number: null,
    survey_number_status: 'unavailable',
    administrative_status: 'not_available',
    gis_feature_boundary: null,
    parcel_boundary: null,
    land_area_square_meters: null,
    government_guideline_rate: null,
    estimated_market_rate: null,
    estimated_total_land_value: null,
    provider: 'TGRAC HMDA GIS',
    source_url: 'https://tgrac.telangana.gov.in/map',
    source_record_id: null,
    verification_status: 'not_verified',
    last_updated: null,
    notice: 'No coverage confirmed.',
  }), { status: 200 });
  try {
    const result = await identifyLandAtPoint(19.07, 72.87);
    assert.equal(result.status, 'no_verified_data');
    assert.equal(result.survey_number, null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('rejects invalid identification response shapes and surfaces provider errors', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(
      JSON.stringify({ detail: { status: 'source_unavailable', message: 'Provider unavailable.' } }),
      { status: 503 },
    );
    await assert.rejects(identifyLandAtPoint(17.44, 78.39), /Provider unavailable/);

    globalThis.fetch = async () => new Response(
      JSON.stringify({ status: 'verified', survey_number: 'made-up' }),
      { status: 200 },
    );
    await assert.rejects(identifyLandAtPoint(17.44, 78.39), /invalid response/i);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
