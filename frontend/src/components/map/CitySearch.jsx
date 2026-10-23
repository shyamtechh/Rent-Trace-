import { useEffect, useRef, useState } from 'react';
import { searchCities } from '../../services/geocoding';

function CitySearch({ onCitySelect }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [searched, setSearched] = useState(false);
  const requestRef = useRef(null);

  useEffect(() => () => requestRef.current?.abort(), []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const cityName = query.trim();
    if (cityName.length < 2) {
      setError('Enter at least two characters to search.');
      setResults([]);
      setSearched(false);
      return;
    }

    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError('');
    setResults([]);
    setSearched(true);

    try {
      setResults(await searchCities(cityName, controller.signal));
    } catch (searchError) {
      if (searchError.name !== 'AbortError') {
        setError(searchError.message || 'City search is temporarily unavailable.');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  };

  const selectResult = (result) => {
    setQuery(result.name);
    setResults([]);
    setSearched(false);
    setError('');
    onCitySelect(result);
  };

  return (
    <section className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="renttrace-city-search" className="sr-only">Search for a city</label>
        <input
          id="renttrace-city-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search city, e.g. Hyderabad"
          autoComplete="off"
          minLength={2}
          className="min-w-0 flex-1 rounded-lg border border-slate-300 px-4 py-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100"
        />
        <button
          type="submit"
          disabled={loading || query.trim().length < 2}
          className="rounded-lg bg-emerald-700 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-55"
        >
          {loading ? 'Searching...' : 'Search city'}
        </button>
      </form>

      {error && <p role="alert" className="mt-3 text-sm text-rose-700">{error}</p>}
      {loading && <p role="status" className="mt-3 text-sm text-slate-500">Searching geographic places...</p>}
      {searched && !loading && !error && results.length === 0 && (
        <p role="status" className="mt-3 text-sm text-slate-500">No matching city locations were found.</p>
      )}
      {results.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 overflow-hidden rounded-lg border border-slate-200" aria-label="City search results">
          {results.map((result) => (
            <li key={result.id}>
              <button
                type="button"
                onClick={() => selectResult(result)}
                className="flex w-full flex-col gap-1 px-4 py-3 text-left transition hover:bg-emerald-50 focus:bg-emerald-50 focus:outline-none sm:flex-row sm:items-center sm:justify-between"
              >
                <span className="text-sm font-semibold text-slate-900">{result.name}</span>
                <span className="text-xs text-slate-500">{result.display_name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-slate-500">Geographic search via OpenStreetMap Nominatim</p>
    </section>
  );
}

export default CitySearch;
