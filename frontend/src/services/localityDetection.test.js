import test from 'node:test';
import assert from 'node:assert/strict';
import { detectPolygonLocality, getPolygonCentroid } from './localityDetection.js';

const polygonAround = (latitude, longitude, offset = 0.0001) => [
  [latitude - offset, longitude - offset],
  [latitude - offset, longitude + offset],
  [latitude + offset, longitude + offset],
  [latitude + offset, longitude - offset],
];

const hyderabadLocalities = [
  { name: 'Madhapur', latitude: 17.4408924, longitude: 78.3916304 },
  { name: 'Gachibowli', latitude: 17.4436222, longitude: 78.3519638 },
  { name: 'Kondapur', latitude: 17.4587912, longitude: 78.3730556 },
];

test('detects Madhapur, Gachibowli, and Kondapur from their closest coordinate', () => {
  for (const locality of hyderabadLocalities) {
    const detected = detectPolygonLocality(
      polygonAround(locality.latitude, locality.longitude),
      hyderabadLocalities,
    );
    assert.equal(detected?.name, locality.name);
    assert.ok(detected.distanceMeters < 20);
  }
});

test('uses the closest valid coordinate regardless of candidate ordering', () => {
  const detected = detectPolygonLocality(
    polygonAround(17.4436222, 78.3519638),
    [...hyderabadLocalities].reverse(),
  );

  assert.equal(detected?.name, 'Gachibowli');
});

test('ignores candidates without valid coordinates and reports no match when none are nearby', () => {
  const polygon = polygonAround(17.45, 78.37);

  assert.equal(
    detectPolygonLocality(polygon, [{ name: 'Miyapur', latitude: null, longitude: null }]),
    null,
  );
  assert.equal(
    detectPolygonLocality(polygon, [{ name: 'Miyapur', latitude: 17.5, longitude: 78.5 }]),
    null,
  );
});

test('supports polygons crossing the antimeridian', () => {
  const detected = detectPolygonLocality(
    [[10, 179.99], [10, -179.99], [10.01, -179.99], [10.01, 179.99]],
    [{ name: 'Dateline locality', latitude: 10.005, longitude: 180 }],
  );

  assert.equal(detected?.name, 'Dateline locality');
});

test('rejects malformed polygons and invalid distance limits', () => {
  assert.equal(detectPolygonLocality([[17, 78], [17.1, 78.1]], hyderabadLocalities), null);
  assert.equal(
    detectPolygonLocality(
      [[17.44, 78.39], [17.44, 78.391], [17.441, 78.391], [91, 78.39]],
      hyderabadLocalities,
    ),
    null,
  );
  assert.equal(detectPolygonLocality(polygonAround(17.44, 78.39), hyderabadLocalities, -1), null);
});

test('calculates the polygon centroid rather than averaging its vertices', () => {
  const centroid = getPolygonCentroid([
    [17, 78],
    [17, 78.004],
    [17.002, 78.004],
    [17.002, 78],
  ]);

  assert.ok(Math.abs(centroid[0] - 17.001) < 1e-10);
  assert.ok(Math.abs(centroid[1] - 78.002) < 1e-10);
});

test('rejects invalid and degenerate polygon centroid inputs', () => {
  assert.equal(getPolygonCentroid([[17, 78], [17.1, 78.1]]), null);
  assert.equal(getPolygonCentroid([[17, 78], [17.1, 78.1], [91, 78]]), null);
  assert.equal(getPolygonCentroid([[17, 78], [17, 78.1], [17, 78.2]]), null);
});
