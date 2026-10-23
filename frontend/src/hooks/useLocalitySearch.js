import { useEffect, useMemo, useState } from 'react';
import { fetchCityLocalities } from '../services/localities';
import { HYDERABAD_LOCALITIES } from '../data/hyderabadLocalities';

const SUGGESTION_LIMIT = 8;
const MIN_SUGGESTION_LENGTH = 3;

function normalizeLocalityName(name) {
  return name.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
}

function normalizeLocalityPrefix(name) {
  return normalizeLocalityName(name).replace(/[^a-z0-9]/g, '');
}

function useLocalitySearch(cityName) {
  const [localities, setLocalities] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setLocalities([]);

    const loadLocalities = async () => {
      try {
        setLocalities(await fetchCityLocalities(cityName, controller.signal));
      } catch (loadError) {
        if (loadError.name !== 'AbortError') {
          setError(loadError.message || 'Unable to load localities for this city.');
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    loadLocalities();
    return () => controller.abort();
  }, [cityName]);

  const searchableLocalities = useMemo(() => {
    const databaseLocalities = new Map(
      localities.map((locality) => [normalizeLocalityName(locality.name), locality]),
    );
    return cityName.trim().toLocaleLowerCase() === 'hyderabad'
      ? HYDERABAD_LOCALITIES.map((name) => databaseLocalities.get(normalizeLocalityName(name)) || ({
          id: `dataset:${normalizeLocalityName(name)}`,
          name,
          city: 'Hyderabad',
          state: 'Telangana',
          country: 'India',
          latitude: null,
          longitude: null,
        }))
      : localities;
  }, [cityName, localities]);

  const suggestions = useMemo(() => {
    const normalizedQuery = normalizeLocalityPrefix(query);
    if (normalizedQuery.length < MIN_SUGGESTION_LENGTH) {
      return [];
    }

    return searchableLocalities
      .filter((locality) => normalizeLocalityPrefix(locality.name).startsWith(normalizedQuery))
      .slice(0, SUGGESTION_LIMIT);
  }, [query, searchableLocalities]);

  const selectLocality = (locality) => {
    setQuery(locality.name);
    setSuggestionsOpen(false);
  };

  const clearSearch = () => {
    setQuery('');
    setSuggestionsOpen(false);
  };

  return {
    clearSearch,
    error,
    loading,
    query,
    selectLocality,
    setQuery,
    setSuggestionsOpen,
    suggestions,
    suggestionsOpen,
    localities,
    searchableLocalities,
  };
}

export default useLocalitySearch;
