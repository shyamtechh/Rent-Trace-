const EARTH_RADIUS_METERS = 6_371_008.8;
const SQUARE_METERS_PER_ACRE = 4_046.8564224;
const SQUARE_FEET_PER_SQUARE_METER = 10.76391041671;

function normalizeLongitudeDelta(delta) {
  const fullCircle = 2 * Math.PI;
  return ((delta + Math.PI) % fullCircle + fullCircle) % fullCircle - Math.PI;
}

export function calculatePolygonArea(coordinates) {
  if (!Array.isArray(coordinates)) {
    throw new TypeError('Polygon coordinates must be an array of [latitude, longitude] pairs.');
  }
  if (coordinates.length === 0) {
    return null;
  }
  if (coordinates.length < 3) {
    throw new RangeError('A polygon requires at least three coordinates.');
  }

  const points = coordinates.map((coordinate) => {
    if (
      !Array.isArray(coordinate)
      || coordinate.length < 2
      || !Number.isFinite(coordinate[0])
      || !Number.isFinite(coordinate[1])
      || coordinate[0] < -90
      || coordinate[0] > 90
      || coordinate[1] < -180
      || coordinate[1] > 180
    ) {
      throw new TypeError('Each polygon coordinate must contain a valid latitude and longitude.');
    }

    return [coordinate[0] * Math.PI / 180, coordinate[1] * Math.PI / 180];
  });

  let sphericalSum = 0;
  for (let index = 0; index < points.length; index += 1) {
    const [latitude1, longitude1] = points[index];
    const [latitude2, longitude2] = points[(index + 1) % points.length];
    const longitudeDelta = normalizeLongitudeDelta(longitude2 - longitude1);
    sphericalSum += longitudeDelta * (2 + Math.sin(latitude1) + Math.sin(latitude2));
  }

  const squareMeters = Math.abs(sphericalSum) * EARTH_RADIUS_METERS ** 2 / 2;
  return {
    squareMeters,
    squareFeet: squareMeters * SQUARE_FEET_PER_SQUARE_METER,
    acres: squareMeters / SQUARE_METERS_PER_ACRE,
  };
}
