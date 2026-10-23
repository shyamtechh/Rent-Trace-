const EARTH_RADIUS_METERS = 6_371_008.8;
const MAX_LOCALITY_DISTANCE_METERS = 5_000;

function getPolygonCenter(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 3) {
    return null;
  }

  const points = coordinates.filter((point) => (
    Array.isArray(point)
    && Number.isFinite(point[0])
    && Number.isFinite(point[1])
    && point[0] >= -90
    && point[0] <= 90
    && point[1] >= -180
    && point[1] <= 180
  ));
  if (points.length !== coordinates.length || points.length < 3) {
    return null;
  }

  if (
    points.length > 3
    && points[0][0] === points[points.length - 1][0]
    && points[0][1] === points[points.length - 1][1]
  ) {
    points.pop();
  }
  if (points.length < 3) {
    return null;
  }

  const vector = points.reduce((center, [latitude, longitude]) => {
    const latitudeRadians = latitude * Math.PI / 180;
    const longitudeRadians = longitude * Math.PI / 180;
    const latitudeScale = Math.cos(latitudeRadians);
    center.x += latitudeScale * Math.cos(longitudeRadians);
    center.y += latitudeScale * Math.sin(longitudeRadians);
    center.z += Math.sin(latitudeRadians);
    return center;
  }, { x: 0, y: 0, z: 0 });

  const magnitude = Math.hypot(vector.x, vector.y, vector.z);
  if (magnitude === 0) {
    return null;
  }

  return [
    Math.atan2(vector.z, Math.hypot(vector.x, vector.y)) * 180 / Math.PI,
    Math.atan2(vector.y, vector.x) * 180 / Math.PI,
  ];
}

export function getPolygonCentroid(coordinates) {
  if (!Array.isArray(coordinates) || coordinates.length < 3) {
    return null;
  }

  const points = coordinates.map((point) => {
    if (
      !Array.isArray(point)
      || point.length < 2
      || !Number.isFinite(point[0])
      || !Number.isFinite(point[1])
      || point[0] < -90
      || point[0] > 90
      || point[1] < -180
      || point[1] > 180
    ) {
      return null;
    }
    return [point[1], point[0]];
  });
  if (points.some((point) => point === null)) {
    return null;
  }

  if (
    points.length > 3
    && points[0][0] === points[points.length - 1][0]
    && points[0][1] === points[points.length - 1][1]
  ) {
    points.pop();
  }
  if (points.length < 3) {
    return null;
  }

  let twiceArea = 0;
  let weightedLongitude = 0;
  let weightedLatitude = 0;
  const originLongitude = points[0][0];
  const originLatitude = points[0][1];
  for (let index = 0; index < points.length; index += 1) {
    const [absoluteLongitude1, absoluteLatitude1] = points[index];
    const [absoluteLongitude2, absoluteLatitude2] = points[(index + 1) % points.length];
    const longitude1 = absoluteLongitude1 - originLongitude;
    const latitude1 = absoluteLatitude1 - originLatitude;
    const longitude2 = absoluteLongitude2 - originLongitude;
    const latitude2 = absoluteLatitude2 - originLatitude;
    const cross = longitude1 * latitude2 - longitude2 * latitude1;
    twiceArea += cross;
    weightedLongitude += (longitude1 + longitude2) * cross;
    weightedLatitude += (latitude1 + latitude2) * cross;
  }

  if (Math.abs(twiceArea) < Number.EPSILON) {
    return null;
  }
  return [
    originLatitude + weightedLatitude / (3 * twiceArea),
    originLongitude + weightedLongitude / (3 * twiceArea),
  ];
}

function distanceBetweenCoordinatesMeters([latitude1, longitude1], [latitude2, longitude2]) {
  const radians = Math.PI / 180;
  const latitudeDelta = (latitude2 - latitude1) * radians;
  const longitudeDelta = (longitude2 - longitude1) * radians;
  const haversine = Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(latitude1 * radians)
    * Math.cos(latitude2 * radians)
    * Math.sin(longitudeDelta / 2) ** 2;

  return 2 * EARTH_RADIUS_METERS * Math.asin(Math.sqrt(Math.min(1, haversine)));
}

function getValidLocality(locality) {
  if (typeof locality?.name !== 'string' || !locality.name.trim()) {
    return null;
  }

  const latitude = Number(locality.latitude);
  const longitude = Number(locality.longitude);
  if (
    locality.latitude == null
    || locality.longitude == null
    || !Number.isFinite(latitude)
    || !Number.isFinite(longitude)
    || latitude < -90
    || latitude > 90
    || longitude < -180
    || longitude > 180
  ) {
    return null;
  }

  return { name: locality.name.trim(), latitude, longitude };
}

export function detectPolygonLocality(
  polygonCoordinates,
  localities,
  maxDistanceMeters = MAX_LOCALITY_DISTANCE_METERS,
) {
  const center = getPolygonCenter(polygonCoordinates);
  if (!center || !Array.isArray(localities) || !Number.isFinite(maxDistanceMeters) || maxDistanceMeters < 0) {
    return null;
  }

  const candidates = new Map();
  for (const locality of localities) {
    const validLocality = getValidLocality(locality);
    if (validLocality) {
      const key = validLocality.name.toLocaleLowerCase();
      if (!candidates.has(key)) {
        candidates.set(key, validLocality);
      }
    }
  }

  const closest = Array.from(candidates.values())
    .map((locality) => ({
      ...locality,
      distanceMeters: distanceBetweenCoordinatesMeters(
        center,
        [locality.latitude, locality.longitude],
      ),
    }))
    .sort((first, second) => first.distanceMeters - second.distanceMeters)[0];

  if (!closest || closest.distanceMeters > maxDistanceMeters) {
    return null;
  }

  return { name: closest.name, distanceMeters: closest.distanceMeters };
}
