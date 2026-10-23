import assert from 'node:assert/strict';
import test from 'node:test';
import {
  getHyderabadRentSummary,
  getOneBedroomRentEstimate,
} from './hyderabadRentData.js';

test('uses a median observed locality BHK ratio when the selected locality has no 1 BHK rent', () => {
  const estimate = getOneBedroomRentEstimate('Madhapur');
  const summary = getHyderabadRentSummary('Madhapur');

  assert.equal(summary.oneBedroomRent, null);
  assert.ok(estimate);
  assert.equal(estimate.rent, 18_400);
  assert.equal(estimate.peerLocalityCount, 5);
  assert.equal(estimate.rent % 100, 0);
  assert.ok(estimate.rent > 0);
  assert.ok(estimate.peerLocalityCount > 1);
  assert.equal(estimate.year, 2026);
  assert.equal(estimate.method, 'median-locality-1BHK-to-2BHK-rent-ratio');
  assert.equal(estimate.source, 'Hyderabad_Rent_Trace_Complete_All_Localities.xlsx');
});

test('does not replace a listed 1 BHK rent with an estimate', () => {
  assert.equal(getOneBedroomRentEstimate('Gachibowli'), null);
});

test('does not estimate a locality without a usable 2 BHK rent', () => {
  assert.equal(getOneBedroomRentEstimate('unknown locality'), null);
  assert.equal(getOneBedroomRentEstimate('Lakshmi Nagar'), null);
});
