import assert from 'node:assert/strict';
import test from 'node:test';
import {
  calculateGovernmentRateValue,
  calculateEstimatedLandValue,
  formatIndianCurrency,
  formatIndianValueApproximation,
} from './landValue.js';

test('calculates government guidance-rate value after converting square feet to square yards', () => {
  assert.ok(Math.abs(calculateGovernmentRateValue(2450, 7550) - 2_055_277.7777777778) < 1e-8);
  assert.equal(calculateGovernmentRateValue(null, 7550), null);
  assert.equal(calculateGovernmentRateValue(2450, null), null);
  assert.equal(calculateGovernmentRateValue(2450, 0), null);
});

test('calculates estimated value using the supplied polygon area and dataset rate', () => {
  const value = calculateEstimatedLandValue(2450, 7550);

  assert.equal(value, 18_497_500);
  assert.equal(formatIndianCurrency(value), '₹1,84,97,500');
  assert.equal(formatIndianValueApproximation(value), '≈ ₹1.85 Cr');
});

test('formats large values below one crore in lakh', () => {
  const value = calculateEstimatedLandValue(100, 7550);

  assert.equal(formatIndianCurrency(value), '₹7,55,000');
  assert.equal(formatIndianValueApproximation(value), '≈ ₹7.55 Lakh');
});

test('recalculates directly when the polygon area or dataset rate changes', () => {
  assert.equal(calculateEstimatedLandValue(2450, 7550), 18_497_500);
  assert.equal(calculateEstimatedLandValue(3000, 7550), 22_650_000);
  assert.equal(calculateEstimatedLandValue(2450, 8000), 19_600_000);
});

test('does not fabricate a value when area or rate is unavailable or invalid', () => {
  assert.equal(calculateEstimatedLandValue(null, 7550), null);
  assert.equal(calculateEstimatedLandValue(2450, null), null);
  assert.equal(calculateEstimatedLandValue(0, 7550), null);
  assert.equal(calculateEstimatedLandValue(2450, 0), null);
  assert.equal(calculateEstimatedLandValue(Number.NaN, 7550), null);
  assert.equal(calculateEstimatedLandValue(2450, Number.POSITIVE_INFINITY), null);
  assert.equal(formatIndianValueApproximation(99_999), null);
});
