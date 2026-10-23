import assert from 'node:assert/strict';
import test from 'node:test';
import { summarizeRentalForecast } from './rentalForecast.js';

test('summarizes available predicted rents by BHK and year', () => {
  const rows = summarizeRentalForecast([
    {
      bedrooms: '2 BHK Apartment',
      predicted_prices: [
        { year: 2028, value: 28000 },
        { year: 2027, value: 27000 },
      ],
    },
    {
      bedrooms: '2 BHK Apartment',
      predicted_prices: [{ year: 2027, value: 29000 }],
    },
    {
      bedrooms: '1 BHK Apartment',
      predicted_prices: [{ year: 2027, value: 18000 }],
    },
  ]);

  assert.deepEqual(rows, [
    { bedrooms: '1 BHK', bedroomCount: 1, year: 2027, averageRent: 18000, sampleCount: 1 },
    { bedrooms: '2 BHK', bedroomCount: 2, year: 2027, averageRent: 28000, sampleCount: 2 },
    { bedrooms: '2 BHK', bedroomCount: 2, year: 2028, averageRent: 28000, sampleCount: 1 },
  ]);
});

test('ignores invalid, missing, and non-rental prediction records', () => {
  assert.deepEqual(summarizeRentalForecast([
    { bedrooms: 'Apartment', predicted_prices: [{ year: 2027, value: 20000 }] },
    { bedrooms: '1 BHK Apartment', predicted_prices: [{ year: 'unknown', value: 20000 }] },
    { bedrooms: '1 BHK Apartment', predicted_prices: [{ year: 2027, value: 0 }] },
    { bedrooms: '1 BHK Apartment', predicted_prices: [] },
  ]), []);
  assert.deepEqual(summarizeRentalForecast(null), []);
});
