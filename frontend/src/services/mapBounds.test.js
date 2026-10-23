import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeProviderBounds } from './mapBoundsData.js';

test('normalizes provider southwest and northeast coordinates', () => {
  assert.deepEqual(
    normalizeProviderBounds([
      [17.0, 78.0],
      [17.8, 79.0],
    ]),
    [
      [17, 78],
      [17.8, 79],
    ],
  );
});

test('rejects malformed city bounds', () => {
  assert.throws(
    () => normalizeProviderBounds([[17, 78]]),
    /valid southwest and northeast coordinates/i,
  );
});
