import assert from 'node:assert/strict';
import test from 'node:test';
import { fetchLocationSuggestion } from './locationSuggestion.js';

test('requests and validates an address suggestion for selected coordinates', async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl;
  globalThis.fetch = async (url) => {
    requestUrl = url;
    return new Response(JSON.stringify({
      display_name: 'Madhapur, Hyderabad, Telangana, India',
      suggested_locality: 'Madhapur',
      suggested_district: 'Rangareddy',
      source_name: 'OpenStreetMap Nominatim',
      source_url: 'https://nominatim.openstreetmap.org/reverse',
      verification_status: 'suggestion_only',
    }), { status: 200 });
  };
  try {
    const suggestion = await fetchLocationSuggestion(17.44, 78.39);
    assert.equal(requestUrl, '/api/geocoding/reverse?latitude=17.44&longitude=78.39');
    assert.equal(suggestion.suggested_locality, 'Madhapur');
    assert.equal(suggestion.verification_status, 'suggestion_only');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('does not fabricate an address suggestion when the provider has no result', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('null', { status: 200 });
  try {
    assert.equal(await fetchLocationSuggestion(17.44, 78.39), null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
