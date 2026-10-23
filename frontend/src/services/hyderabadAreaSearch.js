export async function searchHyderabadArea(area, city = 'Hyderabad', signal) {
  const parameters = new URLSearchParams({ area: area.trim(), city: city.trim() });
  const response = await fetch(`/api/geocoding/area-search?${parameters}`, { signal });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 404) {
      throw new Error(`Area not found. Please enter a valid ${city} locality.`);
    }
    throw new Error(data.detail || 'Area search is temporarily unavailable.');
  }

  const result = await response.json();
  if (!result?.center || !Array.isArray(result.center) || result.center.length !== 2) {
    throw new Error('Area search returned invalid coordinates.');
  }

  return {
    id: result.id,
    name: result.name || area.trim(),
    latitude: Number(result.center[0]),
    longitude: Number(result.center[1]),
    bounds: Array.isArray(result.bounds)
      ? result.bounds.map((point) => point.map(Number))
      : null,
    displayName: result.display_name,
  };
}
