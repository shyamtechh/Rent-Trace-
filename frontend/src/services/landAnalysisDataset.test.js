import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchLandAnalysisLocality } from './landAnalysisDataset.js';

test('requests processed locality records and validates the response shape', async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl;
  globalThis.fetch = async (url) => {
    requestUrl = url;
    return new Response(JSON.stringify({
      locality: 'Banjara Hills',
      record_count: 1,
      records: [{ record_id: 4, historical_prices: [], predicted_prices: [] }],
      historical_land_prices: [
        {
          year: 2025,
          value_per_sqft: 2400,
          source_fields: ['Land_Price_Per_Sqft_2025'],
          sample_count: 1,
        },
      ],
      estimated_land_rate: {
        available: true,
        message: null,
        source_field: 'Land_Price_Per_Sqft_2025',
        year: 2025,
        value_per_sqft: 2500,
        sample_count: 1,
      },
    }), { status: 200 });
  };

  try {
    const result = await fetchLandAnalysisLocality('Banjara Hills & Road');
    assert.equal(requestUrl, '/api/land-analysis/locality/Banjara%20Hills%20%26%20Road');
    assert.equal(result.record_count, 1);
    assert.equal(result.records[0].record_id, 4);
    assert.equal(result.estimated_land_rate.value_per_sqft, 2500);
    assert.equal(result.historical_land_prices[0].year, 2025);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('surfaces API failures and rejects malformed successful payloads', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(
      JSON.stringify({ detail: 'Processed dataset unavailable.' }),
      { status: 503 },
    );
    await assert.rejects(
      fetchLandAnalysisLocality('Madhapur'),
      { message: 'Processed dataset unavailable.' },
    );

    globalThis.fetch = async () => new Response(
      JSON.stringify({
        locality: 'Madhapur',
        record_count: 1,
        records: [],
        historical_land_prices: [],
        estimated_land_rate: { available: false },
      }),
      { status: 200 },
    );
    await assert.rejects(
      fetchLandAnalysisLocality('Madhapur'),
      /invalid locality records/i,
    );

    globalThis.fetch = async () => new Response(
      JSON.stringify({
        locality: 'Madhapur',
        record_count: 0,
        records: [],
        historical_land_prices: [{ year: 2025, value_per_sqft: -1 }],
        estimated_land_rate: { available: false },
      }),
      { status: 200 },
    );
    await assert.rejects(
      fetchLandAnalysisLocality('Madhapur'),
      /invalid locality records/i,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
