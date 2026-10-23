const LOCALITIES_URL = '/api/localities';

function hasValidCoordinates(locality) {
  const latitude = Number(locality.latitude);
  const longitude = Number(locality.longitude);
  return (
    locality.latitude != null
    && locality.longitude != null
    && Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && latitude >= -90
    && latitude <= 90
    && longitude >= -180
    && longitude <= 180
  );
}

export async function fetchCityLocalities(cityName, signal) {
  const pageSize = 500;
  const localities = [];
  let skip = 0;

  while (true) {
    const parameters = new URLSearchParams({
      city: cityName,
      skip: String(skip),
      limit: String(pageSize),
    });
    const response = await fetch(`${LOCALITIES_URL}?${parameters}`, { signal });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || 'Unable to load localities for this city.');
    }

    const data = await response.json();
    if (!Array.isArray(data)) {
      throw new Error('The locality API returned an invalid response.');
    }

    localities.push(...data);
    if (data.length < pageSize) {
      break;
    }
    skip += pageSize;
  }

  return localities
    .filter((locality) => locality.city?.trim().toLowerCase() === cityName.trim().toLowerCase() && hasValidCoordinates(locality))
    .map((locality) => ({
      ...locality,
      latitude: Number(locality.latitude),
      longitude: Number(locality.longitude),
    }));
}

export async function fetchLocalityAnalysis(localityId, signal) {
  const response = await fetch(`/api/analytics/locality/${encodeURIComponent(localityId)}`, { signal });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Unable to load locality analysis.');
  }
  return response.json();
}

export async function fetchLocalityRentalData(localityId, signal) {
  const [analysisResponse, trendResponse, rentalsResponse] = await Promise.all([
    fetch(`/api/analytics/locality/${encodeURIComponent(localityId)}`, { signal }),
    fetch(`/api/analytics/locality/${encodeURIComponent(localityId)}/rent-trend`, { signal }),
    fetch(`/api/rentals?locality_id=${encodeURIComponent(localityId)}&limit=500`, { signal }),
  ]);

  const responses = [
    [analysisResponse, 'Unable to load locality analysis.'],
    [trendResponse, 'Unable to load the locality rent trend.'],
    [rentalsResponse, 'Unable to load locality rental records.'],
  ];
  const payloads = await Promise.all(responses.map(async ([response, message]) => {
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || message);
    }
    return response.json();
  }));
  const [analysis, trend, rentals] = payloads;

  if (
    !analysis ||
    typeof analysis !== 'object' ||
    !trend ||
    typeof trend !== 'object' ||
    !Array.isArray(trend.observations) ||
    !Array.isArray(rentals)
  ) {
    throw new Error('The locality rental API returned invalid data.');
  }

  return { analysis, trend: trend.observations, rentals };
}
