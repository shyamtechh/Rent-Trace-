export async function searchCities(cityName, signal) {
  const parameters = new URLSearchParams({ city: cityName.trim() });
  const response = await fetch(`/api/geocoding/search?${parameters}`, { signal });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'City search is temporarily unavailable.');
  }

  const results = await response.json();
  if (!Array.isArray(results)) {
    throw new Error('The city search service returned an invalid response.');
  }
  return results;
}
