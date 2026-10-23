import assert from 'node:assert/strict';
import test from 'node:test';

import { MAP_TILE_URL, MAP_TILE_ATTRIBUTION } from './mapTiles.js';

test('uses an OpenStreetMap-compatible raster tile endpoint', () => {
  assert.match(MAP_TILE_URL, /^https:\/\/\{s\}\.tile\.openstreetmap\.org\/\{z\}\/\{x\}\/\{y\}\.png$/);
  assert.equal(MAP_TILE_ATTRIBUTION, '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>');
});

test('does not configure Google Maps or fabricated geographic features', () => {
  assert.doesNotMatch(MAP_TILE_URL, /google|maps/i);
  assert.doesNotMatch(MAP_TILE_ATTRIBUTION, /google|maps/i);
});
