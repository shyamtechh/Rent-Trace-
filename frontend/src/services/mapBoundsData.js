export function normalizeProviderBounds(bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 2) {
    throw new TypeError('A valid southwest and northeast coordinates pair is required.');
  }

  const [southWest, northEast] = bounds;
  if (
    !Array.isArray(southWest) ||
    !Array.isArray(northEast) ||
    southWest.length !== 2 ||
    northEast.length !== 2
  ) {
    throw new TypeError('A valid southwest and northeast coordinates pair is required.');
  }

  const [south, west] = southWest.map(Number);
  const [north, east] = northEast.map(Number);
  if (
    !Number.isFinite(south) ||
    !Number.isFinite(west) ||
    !Number.isFinite(north) ||
    !Number.isFinite(east) ||
    south > north ||
    west > east ||
    south < -90 ||
    north > 90 ||
    west < -180 ||
    east > 180
  ) {
    throw new TypeError('A valid southwest and northeast coordinates pair is required.');
  }

  return [[south, west], [north, east]];
}
