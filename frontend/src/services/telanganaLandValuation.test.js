import assert from 'node:assert/strict';
import test from 'node:test';
import {
  BHUBHARATI_MARKET_VALUE_URL,
  fetchCadastralParcel,
  submitLandValuation,
} from './telanganaLandValuation.js';

test('looks up cadastral geometry through the backend', async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl;
  globalThis.fetch = async (url) => {
    requestUrl = url;
    return new Response(JSON.stringify({
      found: true,
      administrative_status: 'matched',
      survey_number_status: 'not_verified',
      source_url: 'https://tgrac.telangana.gov.in/arcgis/rest/services/HMDA_Folder/HMDA/MapServer/5',
      parcel: {
        source_feature_id: '42',
        geometry: { rings: [[[78.3, 17.4], [78.4, 17.4], [78.4, 17.5], [78.3, 17.4]]] },
      },
    }), { status: 200 });
  };
  try {
    const result = await fetchCadastralParcel(17.4, 78.3);
    assert.equal(requestUrl, '/api/land-analysis/parcel?latitude=17.4&longitude=78.3');
    assert.equal(result.parcel.source_feature_id, '42');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('submits the manually confirmed rate and validates the valuation response', async () => {
  const originalFetch = globalThis.fetch;
  let request;
  globalThis.fetch = async (url, options) => {
    request = { url, options };
    return new Response(JSON.stringify({
      valuation_id: 9,
      area_square_yards: '272.2222',
      rate_per_sq_yard: '7550.00',
      total_value: '2055277.78',
      rate_unit: 'INR/sq_yd',
      property_category: 'Residential',
      source_type: 'government_guideline_rate',
      survey_subdivision_verified: false,
      parcel_status: 'no_match',
      confidence_note: 'Manual entry, not independently verified.',
      market_value_estimate: null,
    }), { status: 201 });
  };
  try {
    const body = {
      latitude: 17.4,
      longitude: 78.3,
      area_square_feet: 2450,
      rate_per_sq_yard: 7550,
      rate_unit: 'INR/sq_yd',
      property_category: 'Residential',
      rate_date: '2026-10-19',
      verified_date: '2026-10-19',
      user_confirmed_rate: true,
      survey_subdivision_verified: false,
      source_url: BHUBHARATI_MARKET_VALUE_URL,
    };
    const result = await submitLandValuation(body);
    assert.equal(request.url, '/api/land-analysis/valuation');
    assert.equal(request.options.method, 'POST');
    assert.equal(JSON.parse(request.options.body).rate_per_sq_yard, 7550);
    assert.equal(result.total_value, '2055277.78');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('surfaces service errors and rejects invalid payload shapes', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(
      JSON.stringify({ detail: 'TGRAC cadastral lookup is temporarily unavailable.' }),
      { status: 502 },
    );
    await assert.rejects(
      fetchCadastralParcel(17.4, 78.3),
      { message: 'TGRAC cadastral lookup is temporarily unavailable.' },
    );

    globalThis.fetch = async () => new Response(
      JSON.stringify({
        found: true,
        administrative_status: 'matched',
        survey_number_status: 'not_verified',
        source_url: 'url',
        parcel: {},
      }),
      { status: 200 },
    );
    await assert.rejects(fetchCadastralParcel(17.4, 78.3), /invalid response/i);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
