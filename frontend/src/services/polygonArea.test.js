import test from 'node:test';
import assert from 'node:assert/strict';
import { calculatePolygonArea } from './polygonArea.js';

test('calculates area from geographic coordinates and returns converted units', () => {
  const area = calculatePolygonArea([
    [0, 0],
    [0, 0.01],
    [0.01, 0.01],
    [0.01, 0],
  ]);

  assert.ok(area.squareMeters > 1_230_000 && area.squareMeters < 1_240_000);
  assert.equal(area.squareFeet, area.squareMeters * 10.76391041671);
  assert.equal(area.acres, area.squareMeters / 4_046.8564224);
});

test('returns the same area when vertex order is reversed or the ring is explicitly closed', () => {
  const points = [
    [17.38, 78.48],
    [17.38, 78.49],
    [17.39, 78.49],
    [17.39, 78.48],
  ];
  const expectedArea = calculatePolygonArea(points).squareMeters;

  assert.ok(Math.abs(calculatePolygonArea([...points].reverse()).squareMeters - expectedArea) < 1e-6);
  assert.ok(Math.abs(calculatePolygonArea([...points, points[0]]).squareMeters - expectedArea) < 1e-6);
});

test('calculates a smaller polygon independently from its geographic vertices', () => {
  const largeArea = calculatePolygonArea([
    [17.38, 78.48],
    [17.38, 78.49],
    [17.39, 78.49],
    [17.39, 78.48],
  ]);
  const smallArea = calculatePolygonArea([
    [17.38, 78.48],
    [17.38, 78.485],
    [17.385, 78.485],
    [17.385, 78.48],
  ]);

  assert.ok(smallArea.squareMeters > 0);
  assert.ok(smallArea.squareMeters < largeArea.squareMeters);
});

test('handles a polygon crossing the antimeridian using the shorter longitude arc', () => {
  const area = calculatePolygonArea([
    [10, 179.9],
    [10, -179.9],
    [10.1, -179.9],
    [10.1, 179.9],
  ]);

  assert.ok(area.squareMeters > 0);
  assert.ok(area.squareMeters < 1_000_000_000);
});

test('returns null when no completed polygon is present', () => {
  assert.equal(calculatePolygonArea([]), null);
});

test('rejects malformed or underspecified polygons', () => {
  assert.throws(() => calculatePolygonArea([[17, 78], [17.1, 78.1]]), /at least three/i);
  assert.throws(() => calculatePolygonArea([[91, 78], [17.1, 78.1], [17.2, 78.2]]), /valid latitude and longitude/i);
});
