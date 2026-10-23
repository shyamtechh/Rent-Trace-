import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Circle,
  CircleMarker,
  MapContainer,
  Polygon,
  Rectangle,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import 'leaflet/dist/leaflet.css';
import LandBoundaryLayer from './LandBoundaryLayer';
import LocalityMarker from './LocalityMarker';
import useLocalitySearch from '../../hooks/useLocalitySearch';
import { createLeafletBounds } from '../../services/mapBounds';
import { searchHyderabadArea } from '../../services/hyderabadAreaSearch';
import { getRentLevel, RENT_LEVELS } from '../../services/rentHeatmap';
import {
  getHyderabadRentSummary,
  getOneBedroomRentEstimate,
} from '../../services/hyderabadRentData';
import { calculatePolygonArea } from '../../services/polygonArea';
import { detectPolygonLocality, getPolygonCentroid } from '../../services/localityDetection';
import { fetchLandAnalysisLocality } from '../../services/landAnalysisDataset';
import { fetchLocationSuggestion } from '../../services/locationSuggestion';
import { identifyLandAtPoint } from '../../services/landIdentification';
import { summarizeRentalForecast } from '../../services/rentalForecast';
import {
  calculateGovernmentRateValue,
  calculateEstimatedLandValue,
  formatIndianCurrency,
  formatIndianValueApproximation,
} from '../../services/landValue';
import {
  BHUBHARATI_MARKET_VALUE_URL,
  BHUBHARATI_GIS_URL,
  fetchCadastralParcel,
  submitLandValuation,
} from '../../services/telanganaLandValuation';
import {
  MAP_TILE_ATTRIBUTION,
  MAP_TILE_MAX_ZOOM,
  MAP_TILE_URL,
} from '../../config/mapTiles';

const DEFAULT_CENTER = [17.385, 78.4867];
const DEFAULT_ZOOM = 11;
const LOCALITY_FOCUS_RADIUS_METERS = 450;

function formatRent(value) {
  return value == null ? 'Not listed' : `₹${Math.round(value).toLocaleString('en-IN')}`;
}

function RentHeatmapLegend({ cityName, localities, selectedName, onSelect, className = '' }) {
  return (
    <aside className={`min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm lg:max-h-[620px] lg:overflow-y-auto ${className}`}>
      <h3 className="text-lg font-semibold text-slate-900">{cityName}</h3>
      <p className="mt-1 text-sm text-slate-500">Average rent by area</p>
      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 lg:grid-cols-1">
        {RENT_LEVELS.map((level) => (
          <li key={level.id} className="flex items-center gap-2 text-sm text-slate-700">
            <span
              aria-hidden="true"
              className="h-3 w-3 shrink-0 rounded-full ring-2 ring-white shadow"
              style={{ backgroundColor: level.color }}
            />
            <span>{level.label}</span>
            <span className="ml-auto whitespace-nowrap text-xs text-slate-500">{level.range}</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 border-t border-slate-200 pt-3">
        <h4 className="mb-2 text-sm font-semibold text-slate-800">Areas</h4>
        <ul className="space-y-1">
          {localities.map((locality) => {
            const rent = getHyderabadRentSummary(locality.name)?.averageRent ?? null;
            const level = getRentLevel(rent);
            const selected = locality.name === selectedName;
            return (
              <li key={locality.id ?? locality.name}>
                <button
                  type="button"
                  onClick={() => onSelect(locality)}
                  aria-label={`Show ${locality.name} on the map`}
                  aria-current={selected ? 'location' : undefined}
                  className={`flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition hover:bg-emerald-50 focus:outline-none focus:ring-2 focus:ring-emerald-600 ${
                    selected ? 'bg-emerald-50 font-semibold text-emerald-900' : 'text-slate-700'
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className="h-3 w-3 shrink-0 rounded-full"
                    style={{ backgroundColor: level?.color ?? '#94a3b8' }}
                  />
                  <span className="min-w-0 flex-1 truncate">{locality.name}</span>
                  <span className="shrink-0 text-xs text-slate-500">{formatRent(rent)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
      <p className="mt-3 text-xs text-slate-500">Colors use each area&apos;s latest available average rent.</p>
    </aside>
  );
}

function normalizeLocalityName(name) {
  return name.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
}

function MapViewSync({
  center,
  zoom,
  bounds,
  selectedId,
  selectedPosition,
  selectedBounds,
}) {
  const map = useMap();

  useEffect(() => {
    if (bounds) {
      try {
        const cityBounds = createLeafletBounds(bounds);
        map.fitBounds(cityBounds, { padding: [48, 48], maxZoom: 14 });
      } catch (error) {
        console.error('Unable to fit city bounds:', error);
        map.setView(center, zoom, { animate: false });
      }
    } else {
      map.setView(center, zoom, { animate: false });
    }
  }, [bounds, center, map, zoom]);

  useEffect(() => {
    if (selectedPosition) {
      if (selectedBounds) {
        try {
          map.fitBounds(createLeafletBounds(selectedBounds), {
            padding: [64, 64],
            maxZoom: 15,
            animate: true,
          });
        } catch (error) {
          console.error('Unable to fit locality bounds:', error);
          map.flyTo(selectedPosition, Math.max(map.getZoom(), 14), { duration: 0.5 });
        }
      } else {
        map.flyTo(selectedPosition, Math.max(map.getZoom(), 14), { duration: 0.5 });
      }
    }
  }, [map, selectedBounds, selectedId, selectedPosition]);

  return null;
}

function LandIdentificationMapEvents({ enabled, onSelectPoint }) {
  useMapEvents({
    click(event) {
      if (enabled) {
        onSelectPoint([event.latlng.lat, event.latlng.lng]);
      }
    },
  });

  return null;
}

function markerPosition(marker) {
  if (Array.isArray(marker.position) && marker.position.length === 2) {
    const [latitude, longitude] = marker.position.map(Number);
    return Number.isFinite(latitude) && Number.isFinite(longitude)
      ? [latitude, longitude]
      : null;
  }

  if (marker.latitude == null || marker.longitude == null) {
    return null;
  }

  const latitude = Number(marker.latitude);
  const longitude = Number(marker.longitude);
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    ? [latitude, longitude]
    : null;
}

function localDateInputValue() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 10);
}

function RentTraceMap({
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  bounds = null,
  cityName = 'Selected city',
  selectedLocality,
  onLocalitySelect = () => {},
  onViewLocalityAnalysis = () => {},
  onLandAnalysisAction = () => {},
  onChatContextChange = () => {},
}) {
  const {
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
  } = useLocalitySearch(cityName);
  const [internalSelection, setInternalSelection] = useState(null);
  const [areaError, setAreaError] = useState('');
  const [areaLoading, setAreaLoading] = useState(false);
  const [areaSelection, setAreaSelection] = useState(null);
  const [isDrawingLand, setIsDrawingLand] = useState(false);
  const [landDraftPoints, setLandDraftPoints] = useState([]);
  const [landBoundaryPoints, setLandBoundaryPoints] = useState([]);
  const [detectedLandLocality, setDetectedLandLocality] = useState(null);
  const [landDataset, setLandDataset] = useState(null);
  const [landDatasetLoading, setLandDatasetLoading] = useState(false);
  const [landDatasetError, setLandDatasetError] = useState('');
  const [landPanelAction, setLandPanelAction] = useState(null);
  const [selectedLandPanelOpen, setSelectedLandPanelOpen] = useState(
    () => typeof window === 'undefined' || window.matchMedia('(min-width: 1024px)').matches,
  );
  const [cadastralLookup, setCadastralLookup] = useState(null);
  const [cadastralLookupLoading, setCadastralLookupLoading] = useState(false);
  const [cadastralLookupError, setCadastralLookupError] = useState('');
  const [locationSuggestion, setLocationSuggestion] = useState(null);
  const [locationSuggestionLoading, setLocationSuggestionLoading] = useState(false);
  const [locationSuggestionError, setLocationSuggestionError] = useState('');
  const [landIdentifyMode, setLandIdentifyMode] = useState(false);
  const [landIdentifyPoint, setLandIdentifyPoint] = useState(null);
  const [landIdentification, setLandIdentification] = useState(null);
  const [landIdentificationLoading, setLandIdentificationLoading] = useState(false);
  const [landIdentificationError, setLandIdentificationError] = useState('');
  const [manualSurveyNumber, setManualSurveyNumber] = useState('');
  const [valuationRate, setValuationRate] = useState('');
  const [valuationCategory, setValuationCategory] = useState('Residential');
  const [valuationRateDate, setValuationRateDate] = useState('');
  const [valuationVerifiedDate, setValuationVerifiedDate] = useState('');
  const [valuationDistrict, setValuationDistrict] = useState('');
  const [valuationMandal, setValuationMandal] = useState('');
  const [valuationVillage, setValuationVillage] = useState('');
  const [valuationSurveyNumber, setValuationSurveyNumber] = useState('');
  const [valuationSurveyVerified, setValuationSurveyVerified] = useState(false);
  const [valuationConfirmed, setValuationConfirmed] = useState(false);
  const [valuation, setValuation] = useState(null);
  const [valuationLoading, setValuationLoading] = useState(false);
  const [valuationError, setValuationError] = useState('');
  const landArea = useMemo(
    () => calculatePolygonArea(landBoundaryPoints),
    [landBoundaryPoints],
  );
  const lookupPoint = useMemo(() => {
    return getPolygonCentroid(landBoundaryPoints);
  }, [landBoundaryPoints]);
  const cadastralPositions = useMemo(
    () => cadastralLookup?.found
      ? cadastralLookup.parcel.geometry.rings
        .filter((ring) => Array.isArray(ring))
        .map((ring) => ring
          .filter((coordinate) => (
            Array.isArray(coordinate)
            && coordinate.length >= 2
            && Number.isFinite(coordinate[0])
            && Number.isFinite(coordinate[1])
          ))
          .map(([longitude, latitude]) => [latitude, longitude]))
        .filter((ring) => ring.length >= 4)
      : [],
    [cadastralLookup],
  );
  const identifiedGisPositions = useMemo(
    () => landIdentification?.gis_feature_boundary?.rings
      ?.filter((ring) => Array.isArray(ring))
      .map((ring) => ring
        .filter((coordinate) => (
          Array.isArray(coordinate)
          && coordinate.length >= 2
          && Number.isFinite(coordinate[0])
          && Number.isFinite(coordinate[1])
        ))
        .map(([longitude, latitude]) => [latitude, longitude]))
      .filter((ring) => ring.length >= 4) ?? [],
    [landIdentification],
  );
  const governmentRateValue = useMemo(
    () => valuation
      ? Number(valuation.total_value)
      : calculateGovernmentRateValue(
        landArea?.squareFeet,
        Number(valuationRate),
      ),
    [landArea?.squareFeet, valuation, valuationRate],
  );
  const landDatasetMatchesSelection = (
    landDataset?.locality?.trim().toLocaleLowerCase()
    === detectedLandLocality?.name.trim().toLocaleLowerCase()
  );
  const landRate = landDatasetMatchesSelection && landDataset?.estimated_land_rate?.available
    ? landDataset.estimated_land_rate.value_per_sqft
    : null;
  const estimatedLandValue = useMemo(
    () => calculateEstimatedLandValue(landArea?.squareFeet, landRate),
    [landArea?.squareFeet, landRate],
  );
  const rentalSummary = useMemo(
    () => detectedLandLocality
      ? getHyderabadRentSummary(detectedLandLocality.name)
      : null,
    [detectedLandLocality],
  );
  const oneBedroomRentEstimate = useMemo(
    () => rentalSummary?.oneBedroomRent == null && detectedLandLocality
      ? getOneBedroomRentEstimate(detectedLandLocality.name)
      : null,
    [detectedLandLocality, rentalSummary],
  );
  const landAnalysisLocality = useMemo(
    () => searchableLocalities.find(
      (locality) => normalizeLocalityName(locality.name)
        === normalizeLocalityName(detectedLandLocality?.name ?? ''),
    ) ?? null,
    [searchableLocalities, detectedLandLocality],
  );
  const rentalForecast = useMemo(
    () => landDatasetMatchesSelection
      ? summarizeRentalForecast(landDataset?.records)
      : [],
    [landDatasetMatchesSelection, landDataset?.records],
  );
  const landPriceHistory = landDatasetMatchesSelection
    ? landDataset?.historical_land_prices ?? []
    : [];
  const areaSearchRequest = useRef(null);
  const cadastralLookupRequest = useRef(null);
  const locationSuggestionRequest = useRef(null);
  const landIdentificationRequest = useRef(null);
  const mappedLocalities = localities.filter((locality) => markerPosition(locality));
  const selectedId = selectedLocality === undefined
    ? internalSelection?.id
    : typeof selectedLocality === 'object'
        ? selectedLocality?.id
        : selectedLocality;
  const selectedMarker = mappedLocalities.find((locality, index) =>
    (locality.id ?? locality.key ?? index) === selectedId);
  const selectedPosition = useMemo(
    () => areaSelection
      ? [areaSelection.latitude, areaSelection.longitude]
      : selectedMarker ? markerPosition(selectedMarker) : null,
    [areaSelection, selectedMarker],
  );
  const selectedBounds = areaSelection?.bounds ?? null;

  useEffect(() => {
    const desktopViewport = window.matchMedia('(min-width: 1024px)');
    const updatePanelForViewport = (event) => {
      setSelectedLandPanelOpen(event.matches);
    };
    desktopViewport.addEventListener('change', updatePanelForViewport);
    return () => desktopViewport.removeEventListener('change', updatePanelForViewport);
  }, []);

  useEffect(() => () => areaSearchRequest.current?.abort(), []);

  useEffect(() => () => cadastralLookupRequest.current?.abort(), []);
  useEffect(() => () => locationSuggestionRequest.current?.abort(), []);
  useEffect(() => () => landIdentificationRequest.current?.abort(), []);

  const identifySelectedPoint = (point) => {
    const [latitude, longitude] = point;
    const controller = new AbortController();
    landIdentificationRequest.current?.abort();
    landIdentificationRequest.current = controller;
    setLandIdentifyPoint(point);
    setLandIdentifyMode(false);
    onChatContextChange({
      locality_name: detectedLandLocality?.name ?? areaSelection?.name ?? selectedMarker?.name ?? null,
      latitude,
      longitude,
      polygon_area_square_feet: null,
      area_method: null,
    });
    setLandIdentification(null);
    setLandIdentificationError('');
    setLandIdentificationLoading(true);
    setManualSurveyNumber('');
    identifyLandAtPoint(latitude, longitude, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setLandIdentification(result);
        }
      })
      .catch((identifyError) => {
        if (identifyError.name !== 'AbortError') {
          setLandIdentificationError(
            identifyError.message || 'Land-record lookup is unavailable.',
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLandIdentificationLoading(false);
        }
      });
  };

  useEffect(() => {
    if (!lookupPoint) {
      cadastralLookupRequest.current?.abort();
      setCadastralLookup(null);
      setCadastralLookupLoading(false);
      setCadastralLookupError('');
      return undefined;
    }

    const controller = new AbortController();
    cadastralLookupRequest.current?.abort();
    cadastralLookupRequest.current = controller;
    setCadastralLookup(null);
    setCadastralLookupError('');
    setCadastralLookupLoading(true);
    setValuation(null);
    fetchCadastralParcel(lookupPoint[0], lookupPoint[1], controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setCadastralLookup(result);
          if (result.parcel) {
            setValuationDistrict((current) => current || result.parcel.district || '');
            setValuationMandal((current) => current || result.parcel.mandal || '');
            setValuationVillage((current) => current || result.parcel.village || '');
          }
        }
      })
      .catch((lookupError) => {
        if (lookupError.name !== 'AbortError') {
          setCadastralLookupError(lookupError.message || 'Unable to query the TGRAC cadastral layer.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setCadastralLookupLoading(false);
        }
      });

    return () => controller.abort();
  }, [lookupPoint]);

  useEffect(() => {
    if (!lookupPoint) {
      locationSuggestionRequest.current?.abort();
      setLocationSuggestion(null);
      setLocationSuggestionLoading(false);
      setLocationSuggestionError('');
      return undefined;
    }

    const controller = new AbortController();
    locationSuggestionRequest.current?.abort();
    locationSuggestionRequest.current = controller;
    setLocationSuggestion(null);
    setLocationSuggestionError('');
    setLocationSuggestionLoading(true);
    fetchLocationSuggestion(lookupPoint[0], lookupPoint[1], controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) {
          setLocationSuggestion(result);
        }
      })
      .catch((suggestionError) => {
        if (suggestionError.name !== 'AbortError') {
          setLocationSuggestionError(
            suggestionError.message || 'Address suggestion is unavailable.',
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLocationSuggestionLoading(false);
        }
      });

    return () => controller.abort();
  }, [lookupPoint]);

  useEffect(() => {
    const localityName = detectedLandLocality?.name;
    if (!localityName) {
      setLandDataset(null);
      setLandDatasetError('');
      setLandDatasetLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    setLandDataset(null);
    setLandDatasetError('');
    setLandDatasetLoading(true);
    fetchLandAnalysisLocality(localityName, controller.signal)
      .then(setLandDataset)
      .catch((datasetError) => {
        if (datasetError.name !== 'AbortError') {
          setLandDatasetError(datasetError.message || 'Unable to load validated locality dataset.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLandDatasetLoading(false);
        }
      });

    return () => controller.abort();
  }, [detectedLandLocality?.name]);

  const cancelLandDrawing = () => {
    setIsDrawingLand(false);
    setLandDraftPoints([]);
  };

  const addLandBoundaryPoint = (point) => {
    setLandDraftPoints((points) => [...points, point]);
  };

  const finishLandDrawing = () => {
    if (landDraftPoints.length < 3) {
      return;
    }
    const localityCandidates = [
      ...mappedLocalities,
      areaSelection,
      selectedMarker,
      internalSelection,
    ].filter(Boolean);
    const locality = detectPolygonLocality(landDraftPoints, localityCandidates);
    const centroid = getPolygonCentroid(landDraftPoints);
    const selectedArea = calculatePolygonArea(landDraftPoints);
    setLandBoundaryPoints(landDraftPoints);
    setDetectedLandLocality(locality);
    onChatContextChange({
      locality_name: locality?.name ?? null,
      latitude: centroid?.[0] ?? null,
      longitude: centroid?.[1] ?? null,
      polygon_area_square_feet: selectedArea?.squareFeet ?? null,
      area_method: 'RentTrace calculated area of the user-drawn map polygon',
    });
    setLandPanelAction(null);
    setValuationRate('');
    setValuationCategory('Residential');
    setValuationRateDate('');
    setValuationVerifiedDate('');
    setValuationDistrict('');
    setValuationMandal('');
    setValuationVillage('');
    setValuationSurveyNumber('');
    setValuationSurveyVerified(false);
    setValuationConfirmed(false);
    setValuation(null);
    setValuationError('');
    setLandDraftPoints([]);
    setIsDrawingLand(false);
  };

  const clearLandBoundary = () => {
    cancelLandDrawing();
    setLandBoundaryPoints([]);
    setDetectedLandLocality(null);
    setLandPanelAction(null);
    setCadastralLookup(null);
    setCadastralLookupError('');
    setValuation(null);
    setValuationError('');
    setValuationRate('');
    setValuationCategory('Residential');
    setValuationRateDate('');
    setValuationVerifiedDate('');
    setValuationSurveyNumber('');
    setValuationSurveyVerified(false);
    setValuationConfirmed(false);
    const position = markerPosition(areaSelection ?? selectedMarker ?? internalSelection ?? {});
    onChatContextChange(position ? {
      locality_name: areaSelection?.name ?? selectedMarker?.name ?? internalSelection?.name ?? null,
      latitude: position[0],
      longitude: position[1],
      polygon_area_square_feet: null,
      area_method: null,
    } : null);
  };

  const handleGovernmentRateSubmit = async (event) => {
    event.preventDefault();
    if (!lookupPoint || !landArea || !valuationConfirmed) {
      return;
    }

    setValuationLoading(true);
    setValuationError('');
    setValuation(null);
    try {
      const result = await submitLandValuation({
        latitude: lookupPoint[0],
        longitude: lookupPoint[1],
        area_square_feet: landArea.squareFeet,
        rate_per_sq_yard: Number(valuationRate),
        rate_unit: 'INR/sq_yd',
        property_category: valuationCategory,
        rate_date: valuationRateDate,
        verified_date: valuationVerifiedDate,
        user_confirmed_rate: valuationConfirmed,
        survey_subdivision_verified: valuationSurveyVerified,
        source_url: BHUBHARATI_MARKET_VALUE_URL,
        district: valuationDistrict.trim() || null,
        mandal: valuationMandal.trim() || null,
        village: valuationVillage.trim() || null,
        survey_subdivision: valuationSurveyNumber.trim() || null,
      });
      setValuation(result);
    } catch (submitError) {
      setValuationError(submitError.message || 'Unable to save the rate-based calculation.');
    } finally {
      setValuationLoading(false);
    }
  };

  const handleLandPanelAction = (action) => {
    setLandPanelAction(action);
    if (action !== 'rent-history' && action !== 'rent-insight') {
      return;
    }

    if (landAnalysisLocality) {
      onLandAnalysisAction(action, landAnalysisLocality);
    }
  };

  const chooseLocality = (locality) => {
    areaSearchRequest.current?.abort();
    areaSearchRequest.current = null;
    setAreaSelection(null);
    setAreaLoading(false);
    selectLocality(locality);
    setSuggestionsOpen(false);
    setInternalSelection(locality);
    const position = markerPosition(locality);
    onChatContextChange(position ? {
      locality_name: locality.name,
      latitude: position[0],
      longitude: position[1],
      polygon_area_square_feet: null,
      area_method: null,
    } : { locality_name: locality.name });
    onLocalitySelect(locality);
  };

  const focusDatasetArea = async (locality) => {
    areaSearchRequest.current?.abort();
    const controller = new AbortController();
    areaSearchRequest.current = controller;
    selectLocality(locality);
    setAreaSelection(null);
    setAreaError('');
    setAreaLoading(true);
    setSuggestionsOpen(false);
    setInternalSelection(null);
    onChatContextChange({ locality_name: locality.name });
    onLocalitySelect(locality);

    try {
      const searchCity = cityName === 'Selected city' ? 'Hyderabad' : cityName;
      const result = await searchHyderabadArea(locality.name, searchCity, controller.signal);
      if (!controller.signal.aborted) {
        setAreaSelection({
          id: `area-${result.id}`,
          name: locality.name,
          latitude: result.latitude,
          longitude: result.longitude,
          bounds: result.bounds,
          displayName: result.displayName,
        });
        onLocalitySelect({
          ...locality,
          latitude: result.latitude,
          longitude: result.longitude,
          datasetBacked: true,
        });
        onChatContextChange({
          locality_name: locality.name,
          latitude: result.latitude,
          longitude: result.longitude,
          polygon_area_square_feet: null,
          area_method: null,
        });
      }
    } catch (searchError) {
      if (!controller.signal.aborted) {
        const message = searchError.message?.startsWith('Area not found.')
          ? `${locality.name} is in the dataset, but map coordinates could not be found. Rental data is still available below.`
          : searchError.message || `Unable to locate ${locality.name} on the map.`;
        setAreaError(message);
      }
    } finally {
      if (!controller.signal.aborted) {
        setAreaLoading(false);
        areaSearchRequest.current = null;
      }
    }
  };

  const chooseSuggestion = (locality) => {
    if (markerPosition(locality)) {
      chooseLocality(locality);
    } else {
      void focusDatasetArea(locality);
    }
  };

  const clearLocalitySearch = () => {
    areaSearchRequest.current?.abort();
    setAreaSelection(null);
    setAreaLoading(false);
    clearSearch();
    setAreaError('');
    setInternalSelection(null);
    onChatContextChange(null);
    onLocalitySelect(null);
  };

  const handleLocalitySearch = (event) => {
    event.preventDefault();
    const searchQuery = query.trim();
    if (!searchQuery) {
      return;
    }

    const exactLocality = searchableLocalities.find(
      (locality) => normalizeLocalityName(locality.name) === normalizeLocalityName(searchQuery),
    );
    if (!exactLocality) {
      areaSearchRequest.current?.abort();
      areaSearchRequest.current = null;
      setAreaSelection(null);
      setAreaLoading(false);
      setInternalSelection(null);
      setAreaError(`Area not found. ${searchQuery} is not in the ${cityName} dataset.`);
      setSuggestionsOpen(false);
      onLocalitySelect(null);
      return;
    }

    setSuggestionsOpen(false);
    chooseSuggestion(exactLocality);
  };

  return (
    <section className="mb-8 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">RentTrace Geographic Explorer</p>
            <h2 className="mt-1 text-xl font-semibold text-slate-900">{cityName}</h2>
            <p className="mt-1 text-sm text-slate-500">Explore housing and rental markets</p>
          </div>
          <span className="text-sm text-slate-500">{loading ? 'Loading localities...' : `${mappedLocalities.length} mapped localities`}</span>
        </div>
        <div className="relative mt-4">
          <form onSubmit={handleLocalitySearch}>
            <label htmlFor="renttrace-locality-search" className="sr-only">Search localities</label>
            <div className="flex flex-col gap-2 rounded-lg border border-slate-300 bg-white p-2 focus-within:border-emerald-600 focus-within:ring-2 focus-within:ring-emerald-100 sm:flex-row sm:items-center sm:px-3 sm:py-0">
            <input
              id="renttrace-locality-search"
              type="search"
              role="combobox"
              aria-autocomplete="list"
              aria-expanded={suggestionsOpen && Boolean(query.trim())}
              aria-controls="renttrace-locality-suggestions"
              value={query}
              onFocus={() => setSuggestionsOpen(true)}
              onChange={(event) => {
                areaSearchRequest.current?.abort();
                areaSearchRequest.current = null;
                setQuery(event.target.value);
                setSuggestionsOpen(true);
                setAreaError('');
                setAreaSelection(null);
                setAreaLoading(false);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  setSuggestionsOpen(false);
                }
              }}
              placeholder={`Type a locality in ${cityName === 'Selected city' ? 'Hyderabad' : cityName}`}
              className="min-h-11 w-full min-w-0 flex-1 border-0 bg-transparent px-2 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:ring-0 sm:px-1 sm:py-3"
            />
            {query && (
              <button
                type="button"
                onClick={clearLocalitySearch}
                className="min-h-11 rounded-md px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 sm:min-h-0 sm:px-2 sm:py-1"
                aria-label="Clear locality search"
              >
                Clear
              </button>
            )}
              <button
                type="submit"
                disabled={areaLoading || !query.trim()}
                className="min-h-11 w-full rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-55 sm:w-auto sm:px-3"
              >
                {areaLoading ? 'Locating...' : 'Search area'}
              </button>
            </div>
          </form>
          {areaError && <p role="alert" className="mt-2 text-sm text-rose-700">{areaError}</p>}

          {suggestionsOpen && query.trim() && (
            <div
              id="renttrace-locality-suggestions"
              role="listbox"
              className="absolute inset-x-0 top-full z-[1000] mt-1 max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-white py-1 shadow-lg"
            >
              {suggestions.length > 0 ? (
                suggestions.map((locality) => (
                  <button
                    key={locality.id}
                    type="button"
                    role="option"
                    aria-selected={locality.id === selectedId}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => chooseSuggestion(locality)}
                    className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left text-sm transition hover:bg-emerald-50 focus:bg-emerald-50 focus:outline-none"
                  >
                    <span className="font-medium text-slate-900">{locality.name}</span>
                    <span className="text-right text-xs text-slate-500">{locality.city}, {locality.state}</span>
                  </button>
                ))
              ) : query.trim().length < 3 ? (
                <p className="px-4 py-3 text-sm text-slate-500">Type at least 3 letters to see Hyderabad dataset areas.</p>
              ) : loading && error ? (
                <p className="px-4 py-3 text-sm text-rose-700">Unable to load saved map coordinates. Dataset areas are still searchable.</p>
              ) : (
                <p className="px-4 py-3 text-sm text-slate-500">No dataset areas start with “{query.trim()}”.</p>
              )}
            </div>
          )}
        </div>
      </div>

      {error && (
        <p role="status" className="border-b border-rose-200 bg-rose-50 px-5 py-3 text-sm text-rose-800 sm:px-6">
          {error}
        </p>
      )}

      {!loading && !error && mappedLocalities.length === 0 && (
        <p role="status" className="border-b border-amber-200 bg-amber-50 px-5 py-3 text-sm text-amber-900 sm:px-6">
          {query.trim()
            ? `No mapped localities match “${query.trim()}”.`
            : 'No localities with coordinates are available yet.'}
        </p>
      )}

      <div className="grid min-w-0 gap-3 p-2 sm:gap-4 sm:p-4 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="min-w-0">
          <div className="mb-3 flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2.5 sm:gap-3 sm:p-3">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              {!isDrawingLand && landBoundaryPoints.length === 0 && (
                <button
                  type="button"
                  onClick={() => {
                    setLandDraftPoints([]);
                    setLandIdentifyMode(false);
                    setIsDrawingLand(true);
                  }}
                  className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-800 focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2"
                >
                  <span aria-hidden="true">📐</span>
                  Draw Land
                </button>
              )}
              {!isDrawingLand && (
                <button
                  type="button"
                  onClick={() => setLandIdentifyMode((active) => !active)}
                  aria-pressed={landIdentifyMode}
                  className={`inline-flex min-h-11 items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-semibold transition focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2 ${
                    landIdentifyMode
                      ? 'border-emerald-800 bg-emerald-800 text-white'
                      : 'border-emerald-700 bg-white text-emerald-900 hover:bg-emerald-50'
                  }`}
                >
                  {landIdentifyMode ? 'Click map to identify…' : 'Identify by map point'}
                </button>
              )}
              {isDrawingLand && (
                <>
                  <span className="w-full text-sm font-medium text-slate-700 sm:w-auto" role="status">
                    Click the map to add boundary points ({landDraftPoints.length} selected)
                  </span>
                  <button
                    type="button"
                    onClick={finishLandDrawing}
                    disabled={landDraftPoints.length < 3}
                    className="min-h-11 min-w-20 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Finish
                  </button>
                  <button
                    type="button"
                    onClick={cancelLandDrawing}
                    className="min-h-11 min-w-20 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
                  >
                    Cancel
                  </button>
                </>
              )}
              {!isDrawingLand && landBoundaryPoints.length > 0 && (
                <>
                  <span className="inline-flex items-center gap-2 text-sm font-semibold text-emerald-800" role="status">
                    <span aria-hidden="true">✓</span>
                    Land boundary selected
                  </span>
                  <button
                    type="button"
                    onClick={clearLandBoundary}
                    className="min-h-11 rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-semibold text-rose-700 transition hover:bg-rose-50 focus:outline-none focus:ring-2 focus:ring-rose-500 focus:ring-offset-2"
                  >
                    Clear / Delete
                  </button>
                </>
              )}
            </div>
            {isDrawingLand && (
              <p className="w-full text-xs text-slate-500 sm:w-auto">At least 3 points are needed to finish. Press Escape to cancel.</p>
            )}
          </div>
            <div className="h-[58vh] min-h-[360px] w-full max-h-[520px] sm:h-[min(62vh,560px)] sm:min-h-[420px] lg:h-[620px] lg:max-h-none">
            <MapContainer
              center={center}
              zoom={zoom}
              minZoom={3}
              maxZoom={MAP_TILE_MAX_ZOOM}
              scrollWheelZoom
              className={`h-full w-full bg-slate-100${isDrawingLand || landIdentifyMode ? ' cursor-crosshair' : ''}`}
              aria-label={`Interactive map of ${cityName}`}
            >
          <MapViewSync
            center={center}
            zoom={zoom}
            bounds={bounds}
            selectedId={selectedId}
            selectedPosition={selectedPosition}
            selectedBounds={selectedBounds}
          />
          <LandIdentificationMapEvents
            enabled={landIdentifyMode && !isDrawingLand}
            onSelectPoint={identifySelectedPoint}
          />
          <TileLayer
            attribution={MAP_TILE_ATTRIBUTION}
            url={MAP_TILE_URL}
            maxZoom={MAP_TILE_MAX_ZOOM}
          />
          {selectedBounds && (
            <Rectangle
              bounds={createLeafletBounds(selectedBounds)}
              pathOptions={{
                color: '#047857',
                fillColor: '#34d399',
                fillOpacity: 0.18,
                weight: 3,
              }}
            />
          )}
          {selectedPosition && !selectedBounds && (
            <Circle
              center={selectedPosition}
              radius={LOCALITY_FOCUS_RADIUS_METERS}
              pathOptions={{
                color: '#047857',
                fillColor: '#34d399',
                fillOpacity: 0.22,
                weight: 2,
              }}
            />
          )}
          {cadastralPositions.length > 0 && (
            <Polygon
              positions={cadastralPositions}
              pathOptions={{
                color: '#2563eb',
                fillColor: '#60a5fa',
                fillOpacity: 0.12,
                weight: 2,
                dashArray: '6 5',
              }}
              interactive={false}
            />
          )}
          {identifiedGisPositions.length > 0 && (
            <Polygon
              positions={identifiedGisPositions}
              pathOptions={{
                color: '#7c3aed',
                fillColor: '#a78bfa',
                fillOpacity: 0.1,
                weight: 2,
                dashArray: '4 5',
              }}
              interactive={false}
            />
          )}
          {landIdentifyPoint && (
            <CircleMarker
              center={landIdentifyPoint}
              radius={8}
              pathOptions={{
                color: '#ffffff',
                weight: 3,
                fillColor: '#7c3aed',
                fillOpacity: 1,
              }}
              interactive={false}
            />
          )}
          {areaSelection && (
            <LocalityMarker
              locality={areaSelection}
              selected
              onSelect={() => {}}
              onViewAnalysis={() => {}}
            />
          )}
          {mappedLocalities.map((marker, index) => {
            const position = markerPosition(marker);
            if (!position) {
              return null;
            }

            const markerId = marker.id ?? marker.key ?? index;
            const isSelected = markerId === selectedId;

            return (
              <LocalityMarker
                key={markerId}
                locality={{ ...marker, latitude: position[0], longitude: position[1] }}
                selected={isSelected}
                onSelect={(locality) => {
                  setInternalSelection(locality);
                  onLocalitySelect(locality);
                }}
                onViewAnalysis={onViewLocalityAnalysis}
              />
            );
          })}
            <LandBoundaryLayer
              drawing={isDrawingLand}
              draftPoints={landDraftPoints}
              boundaryPoints={landBoundaryPoints}
              onAddPoint={addLandBoundaryPoint}
              onCancel={cancelLandDrawing}
            />
            </MapContainer>
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-3 sm:gap-4">
          {landIdentifyPoint && (
            <section
              aria-label="Parcel identification"
              className="order-1 min-w-0 rounded-xl border border-violet-200 bg-white p-4 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 className="text-base font-semibold text-slate-900">Land-record identification</h3>
                  <p className="mt-1 text-xs text-slate-600">
                    {landIdentifyPoint[0].toFixed(6)}, {landIdentifyPoint[1].toFixed(6)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => identifySelectedPoint(landIdentifyPoint)}
                  disabled={landIdentificationLoading}
                  className="min-h-10 rounded-lg border border-violet-300 px-3 py-2 text-sm font-semibold text-violet-900 hover:bg-violet-50 disabled:opacity-50"
                >
                  Retry lookup
                </button>
              </div>
              {landIdentificationLoading && (
                <p className="mt-3 text-sm text-slate-600" role="status">Checking configured official GIS source…</p>
              )}
              {landIdentificationError && (
                <p className="mt-3 text-sm text-rose-800" role="alert">
                  Official source unavailable: {landIdentificationError}
                </p>
              )}
              {landIdentification && (
                <>
                  <p className={`mt-3 rounded-lg px-3 py-2 text-sm ${
                    landIdentification.status === 'administrative_match_only'
                      ? 'bg-amber-50 text-amber-900'
                      : landIdentification.status === 'ambiguous'
                        ? 'bg-rose-50 text-rose-900'
                        : 'bg-slate-100 text-slate-800'
                  }`} role="status">
                    {landIdentification.status === 'administrative_match_only'
                      ? 'Administrative GIS match only — official survey number not available.'
                      : landIdentification.status === 'ambiguous'
                        ? 'Multiple GIS features match this point. No feature or survey number was selected.'
                        : landIdentification.status === 'source_not_configured'
                          ? 'Official data source not configured for verified parcel lookup.'
                          : 'Verified parcel and survey data unavailable for this point.'}
                  </p>
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                    <div><dt className="text-slate-500">Survey number</dt><dd className="font-medium">{landIdentification.survey_number ?? 'Unavailable / not verified'}</dd></div>
                    <div><dt className="text-slate-500">Sub-division</dt><dd className="font-medium">{landIdentification.subdivision_number ?? 'Unavailable / not verified'}</dd></div>
                    <div><dt className="text-slate-500">State</dt><dd>{landIdentification.state ?? 'Not available'}</dd></div>
                    <div><dt className="text-slate-500">District</dt><dd>{landIdentification.district ?? 'Not available'}</dd></div>
                    <div><dt className="text-slate-500">Mandal / Taluk</dt><dd>{landIdentification.mandal_taluk ?? 'Not available'}</dd></div>
                    <div><dt className="text-slate-500">Village / locality</dt><dd>{landIdentification.village ?? landIdentification.locality ?? 'Not available'}</dd></div>
                    <div className="col-span-2"><dt className="text-slate-500">Official parcel boundary / land area</dt><dd>{landIdentification.parcel_boundary ? 'Available' : 'Unavailable from configured source'}</dd></div>
                    <div className="col-span-2"><dt className="text-slate-500">Government guideline rate</dt><dd>{landIdentification.government_guideline_rate ?? 'Unavailable'}</dd></div>
                    <div className="col-span-2"><dt className="text-slate-500">Estimated market rate / total value</dt><dd>{landIdentification.estimated_market_rate ?? 'Unavailable'} / {landIdentification.estimated_total_land_value ?? 'Unavailable'}</dd></div>
                    <div className="col-span-2"><dt className="text-slate-500">Data provider / updated</dt><dd>{landIdentification.provider ?? 'None configured'} · {landIdentification.last_updated ?? 'Date not supplied'}</dd></div>
                  </dl>
                  <p className="mt-3 text-xs text-slate-600">{landIdentification.notice}</p>
                  {landIdentification.gis_feature_boundary && (
                    <p className="mt-2 text-xs text-violet-900">
                      Dashed map outline is a GIS feature only; it is not verified as this plot&apos;s cadastral boundary.
                    </p>
                  )}
                  {landIdentification.source_url && (
                    <a
                      href={landIdentification.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex min-h-9 items-center text-xs font-medium text-emerald-800 underline"
                    >
                      Open configured data source
                    </a>
                  )}
                </>
              )}
              <div className="mt-3 border-t border-slate-100 pt-3">
                <label htmlFor="manual-survey-number" className="text-xs font-medium text-slate-700">
                  Known survey / sub-division number (manual, unverified)
                </label>
                <div className="mt-1 flex gap-2">
                  <input
                    id="manual-survey-number"
                    value={manualSurveyNumber}
                    onChange={(event) => setManualSurveyNumber(event.target.value)}
                    maxLength={150}
                    className="min-w-0 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
                    placeholder="Enter only if known"
                  />
                  <a
                    href={BHUBHARATI_GIS_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex min-h-10 shrink-0 items-center rounded-md border border-emerald-700 px-3 text-xs font-semibold text-emerald-900"
                  >
                    Verify
                  </a>
                </div>
                {manualSurveyNumber.trim() && (
                  <p className="mt-1 text-xs text-amber-800">
                    Entered by user: {manualSurveyNumber.trim()} — not verified by RentTrace.
                  </p>
                )}
              </div>
            </section>
          )}
          <RentHeatmapLegend
            cityName={cityName}
            localities={searchableLocalities}
            selectedName={areaSelection?.name ?? selectedMarker?.name ?? internalSelection?.name}
            onSelect={chooseSuggestion}
            className="order-2 lg:order-1"
          />
          {!isDrawingLand && landArea && (
            <section
              aria-label="Selected Land Analysis"
              className="order-1 min-w-0 overflow-hidden rounded-xl border border-emerald-200 bg-white shadow-sm lg:order-2"
            >
              <details
                open={selectedLandPanelOpen}
                onToggle={(event) => setSelectedLandPanelOpen(event.currentTarget.open)}
              >
                <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 bg-emerald-50 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-emerald-600">
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold uppercase tracking-wide text-emerald-800">
                    Selected Land Analysis
                    </span>
                    <span className="mt-1 block truncate text-base font-semibold text-slate-900 sm:text-lg">
                      {detectedLandLocality?.name ?? 'Locality could not be determined.'}
                    </span>
                    {!selectedLandPanelOpen && (
                      <span className="mt-1 block text-xs text-slate-600">
                        {Math.round(landArea.squareFeet).toLocaleString('en-IN')} sq.ft · Tap to view analysis
                      </span>
                    )}
                  </span>
                  <span aria-hidden="true" className="shrink-0 text-lg text-emerald-800">
                    {selectedLandPanelOpen ? '−' : '+'}
                  </span>
                </summary>
                <div className="min-w-0 space-y-4 p-3 sm:p-4">
                  <section>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Selected land</h3>
                    <dl className="mt-2 grid grid-cols-2 gap-3 text-sm">
                      <div className="col-span-2">
                        <dt className="text-slate-500">Suggested locality</dt>
                        <dd className="font-semibold text-slate-900">
                          {detectedLandLocality?.name
                            ?? locationSuggestion?.suggested_locality
                            ?? 'Not available'}
                        </dd>
                        <dd className="mt-1 text-xs text-slate-600">
                          {detectedLandLocality
                            ? 'Nearest available RentTrace locality coordinate; not an administrative boundary match.'
                            : locationSuggestion
                              ? 'Suggested by OpenStreetMap reverse geocoding; not an official boundary result.'
                              : 'No locality suggestion is currently available.'}
                        </dd>
                      </div>
                      <div className="col-span-2">
                        <dt className="text-slate-500">Land area</dt>
                        <dd className="text-xl font-bold text-slate-900">
                          {Math.round(landArea.squareFeet).toLocaleString('en-IN')} sq.ft
                        </dd>
                        <dd className="text-xs text-slate-600">
                          {(landArea.squareFeet / 9).toLocaleString('en-IN', { maximumFractionDigits: 4 })} sq.yd
                          {' · '}
                          {landArea.squareMeters.toLocaleString('en-IN', { maximumFractionDigits: 2 })} sq.m
                          {' · '}{landArea.acres.toLocaleString('en-IN', { maximumFractionDigits: 3 })} acres
                        </dd>
                      </div>
                      <div className="col-span-2 border-t border-slate-100 pt-3">
                        <dt className="text-slate-500">RentTrace dataset land-price rate</dt>
                        {landDatasetLoading && (
                          <dd className="mt-1 text-sm text-slate-600" role="status">Loading validated land-rate data…</dd>
                        )}
                        {landDatasetError && (
                          <dd className="mt-1 text-sm text-rose-700" role="alert">
                            Land-rate lookup failed: {landDatasetError}
                          </dd>
                        )}
                        {!landDatasetLoading && !landDatasetError && (
                          <dd className="mt-1 font-semibold text-slate-900">
                            {landRate == null
                              ? 'Not available — the current validated workbook has no land-price-per-sq.ft field.'
                              : `${formatIndianCurrency(landRate)} / sq.ft`}
                          </dd>
                        )}
                        {landRate != null && landDataset?.estimated_land_rate && (
                          <dd className="mt-1 text-xs text-slate-500">
                            Source field: {landDataset.estimated_land_rate.source_field ?? 'not reported'}
                            {landDataset.estimated_land_rate.year
                              ? ` · Year: ${landDataset.estimated_land_rate.year}`
                              : ''}
                            {' · This dataset value is not a verified market quote or government rate.'}
                          </dd>
                        )}
                      </div>
                      <div className="col-span-2 border-t border-slate-100 pt-3">
                        <dt className="text-slate-500">Dataset-rate calculation</dt>
                        {estimatedLandValue == null ? (
                          <dd className="mt-1 text-sm text-slate-700">Data unavailable</dd>
                        ) : (
                          <>
                            <dd className="mt-1 text-lg font-bold text-slate-900">
                              {formatIndianCurrency(estimatedLandValue)}
                            </dd>
                            {formatIndianValueApproximation(estimatedLandValue) && (
                              <dd className="text-sm font-medium text-emerald-800">
                                {formatIndianValueApproximation(estimatedLandValue)}
                              </dd>
                            )}
                            <dd className="mt-1 text-xs text-slate-500">
                              Arithmetic from a RentTrace dataset field only; not a verified market estimate, government guideline value, or legal valuation.
                            </dd>
                          </>
                        )}
                      </div>
                    </dl>
                    <section className="mt-3 border-t border-slate-100 pt-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Administrative GIS match
                      </h4>
                      {cadastralLookupLoading ? (
                        <p className="mt-1 text-sm text-slate-600" role="status">
                          Checking whether the polygon centroid lies inside an available TGRAC HMDA GIS feature…
                        </p>
                      ) : cadastralLookup?.administrative_status === 'matched' ? (
                        <>
                          <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
                            <div><dt className="text-slate-500">District</dt><dd>{cadastralLookup.parcel.district ?? 'Not available'}</dd></div>
                            <div><dt className="text-slate-500">Mandal</dt><dd>{cadastralLookup.parcel.mandal ?? 'Not available'}</dd></div>
                            <div className="col-span-2"><dt className="text-slate-500">Village / town</dt><dd>{cadastralLookup.parcel.village ?? 'Not available'}</dd></div>
                          </dl>
                          <p className="mt-2 text-xs text-slate-600">
                            Matched to a containing polygon from TGRAC HMDA GIS. This is an administrative GIS result, not legal confirmation of a plot boundary or ownership.
                          </p>
                          <a
                            href={cadastralLookup.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 inline-flex min-h-9 items-center text-xs font-medium text-emerald-800 underline"
                          >
                            View TGRAC GIS source
                          </a>
                        </>
                      ) : cadastralLookup?.administrative_status === 'ambiguous' ? (
                        <p className="mt-1 text-sm text-amber-800">
                          Multiple GIS polygons contain this centroid; district, mandal, and village were not selected automatically.
                        </p>
                      ) : cadastralLookup ? (
                        <p className="mt-1 text-sm text-slate-600">
                          No containing feature was returned in the available HMDA layer. Administrative coverage may be limited.
                        </p>
                      ) : cadastralLookupError ? (
                        <p className="mt-1 text-sm text-amber-800">
                          TGRAC GIS could not be reached; administrative fields are not verified.
                        </p>
                      ) : (
                        <p className="mt-1 text-sm text-slate-600">Administrative result not available.</p>
                      )}
                      <p className="mt-2 text-sm text-slate-700">
                        Survey / subdivision: {valuationSurveyVerified
                          ? 'User-confirmed in Bhu Bharati'
                          : 'Not verified'}
                      </p>
                      <a
                        href={BHUBHARATI_GIS_URL}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1 inline-flex min-h-9 items-center text-xs font-medium text-emerald-800 underline"
                      >
                        Verify survey number in Bhu Bharati GIS
                      </a>
                    </section>
                    <section className="mt-3 border-t border-slate-100 pt-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Address suggestion
                      </h4>
                      {locationSuggestionLoading ? (
                        <p className="mt-1 text-sm text-slate-600" role="status">Looking up an approximate address…</p>
                      ) : locationSuggestion ? (
                        <>
                          <p className="mt-1 text-sm text-slate-800">{locationSuggestion.display_name}</p>
                          <p className="mt-1 text-xs text-slate-600">
                            OpenStreetMap Nominatim suggestion only; it is not verified administrative data.
                          </p>
                        </>
                      ) : locationSuggestionError ? (
                        <p className="mt-1 text-sm text-slate-600">Address suggestion unavailable. {locationSuggestionError}</p>
                      ) : (
                        <p className="mt-1 text-sm text-slate-600">Address suggestion not available.</p>
                      )}
                    </section>
                  </section>

                  <section className="border-t border-slate-200 pt-4">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Government guidance-rate calculation
                    </h3>
                    <a
                      href={BHUBHARATI_MARKET_VALUE_URL}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2 inline-flex min-h-11 items-center text-sm font-medium text-emerald-800 underline decoration-emerald-300 underline-offset-2 hover:text-emerald-950"
                    >
                      Open Bhu Bharati market-value lookup
                    </a>
                    <a
                      href={BHUBHARATI_GIS_URL}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-3 inline-flex min-h-11 items-center text-sm font-medium text-emerald-800 underline decoration-emerald-300 underline-offset-2 hover:text-emerald-950"
                    >
                      Open Bhu Bharati GIS
                    </a>
                    <p className="mt-2 text-xs leading-relaxed text-slate-600">
                      Government rates are not available through a documented public API here. Check the official portal manually, then enter its guideline rate and effective date. This is a government guidance rate, not a market selling price.
                    </p>
                    <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs leading-relaxed text-blue-950">
                      {cadastralLookupLoading ? (
                        <p role="status">Checking the polygon centroid against TGRAC HMDA GIS geometry…</p>
                      ) : cadastralLookupError ? (
                        <p role="alert">TGRAC lookup could not be completed: {cadastralLookupError}</p>
                      ) : cadastralLookup?.found ? (
                        <>
                          <p className="font-semibold">TGRAC GIS feature contains the centroid</p>
                          <p className="mt-1">
                            {[
                              cadastralLookup.parcel.district,
                              cadastralLookup.parcel.mandal,
                              cadastralLookup.parcel.village,
                            ].filter(Boolean).join(' · ') || 'Feature attributes are available.'}
                          </p>
                          <p className="mt-1">Administrative GIS attributes only. The GIS Parcels attribute is not used as a survey number, and this feature does not confirm the legal plot boundary or ownership.</p>
                        </>
                      ) : cadastralLookup ? (
                        <p>{cadastralLookup.notice}</p>
                      ) : (
                        <p>The TGRAC cadastral lookup has not returned a result yet.</p>
                      )}
                      <p className="mt-1">
                        The lookup uses the polygon area centroid. Administrative matching uses the returned polygon geometry; the user-drawn boundary is not treated as an official parcel.
                      </p>
                    </div>
                    <form onSubmit={handleGovernmentRateSubmit} className="mt-3 space-y-3">
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <label className="block text-xs font-medium text-slate-700">
                          Government guideline rate (INR / sq.yd)
                          <input
                            type="number"
                            min="0.01"
                            step="any"
                            required
                            value={valuationRate}
                            onChange={(event) => {
                              setValuationRate(event.target.value);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          />
                        </label>
                        <label className="block text-xs font-medium text-slate-700">
                          Property category
                          <select
                            value={valuationCategory}
                            onChange={(event) => {
                              setValuationCategory(event.target.value);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          >
                            <option>Residential</option>
                            <option>Commercial</option>
                            <option>Agricultural</option>
                            <option>Industrial</option>
                            <option>Other</option>
                          </select>
                        </label>
                        <label className="block text-xs font-medium text-slate-700">
                          Rate date shown in Bhu Bharati
                          <input
                            type="date"
                            required
                            max={localDateInputValue()}
                            value={valuationRateDate}
                            onChange={(event) => {
                              setValuationRateDate(event.target.value);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          />
                        </label>
                        <label className="block text-xs font-medium text-slate-700">
                          Date you checked the rate
                          <input
                            type="date"
                            required
                            max={localDateInputValue()}
                            value={valuationVerifiedDate}
                            onChange={(event) => {
                              setValuationVerifiedDate(event.target.value);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          />
                        </label>
                        <label className="block text-xs font-medium text-slate-700">
                          Survey / sub-division number (manual entry)
                          <input
                            type="text"
                            maxLength={150}
                            value={valuationSurveyNumber}
                            onChange={(event) => {
                              setValuationSurveyNumber(event.target.value);
                              setValuationSurveyVerified(false);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          />
                          <span className="mt-1 block font-normal leading-relaxed text-amber-800">
                            {valuationSurveyVerified
                              ? 'You confirmed this survey/sub-division number against Bhu Bharati. RentTrace has not independently verified it.'
                              : 'Survey number not verified. TGRAC GIS parcel references are not copied into this field.'}
                          </span>
                          <label className="mt-2 flex items-start gap-2 font-normal">
                            <input
                              type="checkbox"
                              checked={valuationSurveyVerified}
                              disabled={!valuationSurveyNumber.trim()}
                              onChange={(event) => {
                                setValuationSurveyVerified(event.target.checked);
                                setValuation(null);
                              }}
                              className="mt-0.5 h-4 w-4 shrink-0"
                            />
                            I checked this number in Bhu Bharati GIS
                          </label>
                        </label>
                        <label className="block text-xs font-medium text-slate-700">
                          District
                          <input
                            type="text"
                            maxLength={150}
                            value={valuationDistrict}
                            onChange={(event) => {
                              setValuationDistrict(event.target.value);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          />
                        </label>
                        <label className="block text-xs font-medium text-slate-700">
                          Mandal
                          <input
                            type="text"
                            maxLength={150}
                            value={valuationMandal}
                            onChange={(event) => {
                              setValuationMandal(event.target.value);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          />
                        </label>
                        <label className="block text-xs font-medium text-slate-700 sm:col-span-2">
                          Village / city / town
                          <input
                            type="text"
                            maxLength={150}
                            value={valuationVillage}
                            onChange={(event) => {
                              setValuationVillage(event.target.value);
                              setValuation(null);
                            }}
                            className="mt-1 min-h-11 w-full min-w-0 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-100"
                          />
                        </label>
                      </div>
                      <label className="flex min-h-11 items-start gap-2 py-2 text-xs leading-relaxed text-slate-700">
                        <input
                          type="checkbox"
                          checked={valuationConfirmed}
                          onChange={(event) => {
                            setValuationConfirmed(event.target.checked);
                            setValuation(null);
                          }}
                          required
                          className="mt-0.5 h-5 w-5 shrink-0 rounded border-slate-300 text-emerald-700 focus:ring-emerald-600"
                        />
                        <span>I manually checked the government guideline rate, category, effective date, and entered location details in Bhu Bharati. The survey number is verified only if I separately check that box above. RentTrace has not independently verified these entries.</span>
                      </label>
                      {valuationError && (
                        <p role="alert" className="text-sm text-rose-700">{valuationError}</p>
                      )}
                      <button
                        type="submit"
                        disabled={valuationLoading || !valuationConfirmed}
                        className="min-h-11 w-full rounded-lg bg-emerald-700 px-3 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {valuationLoading ? 'Calculating…' : 'Calculate guidance-rate value'}
                      </button>
                    </form>
                    {valuation && (
                      <dl className="mt-3 space-y-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm">
                        <div>
                          <dt className="text-xs text-slate-600">Government guideline-rate-based calculation</dt>
                          <dd className="font-bold text-emerald-950">{formatIndianCurrency(governmentRateValue)}</dd>
                          {formatIndianValueApproximation(governmentRateValue) && (
                            <dd className="text-sm font-medium text-emerald-800">
                              {formatIndianValueApproximation(governmentRateValue)}
                            </dd>
                          )}
                        </div>
                        <div className="text-xs leading-relaxed text-slate-700">
                          {valuation.area_square_yards} sq.yd × {formatIndianCurrency(Number(valuation.rate_per_sq_yard))} / {valuation.rate_unit === 'INR/sq_yd' ? 'sq.yd' : valuation.rate_unit}
                        </div>
                        <div className="text-xs leading-relaxed text-slate-600">
                          Category: {valuation.property_category} · Source type: government guideline rate (manually entered)
                        </div>
                        <div className="text-xs leading-relaxed text-slate-600">
                          Rate date: {valuation.rate_date} · Checked: {valuation.verified_date}
                          {valuation.survey_subdivision
                            ? ` · Survey: ${valuation.survey_subdivision} (${valuation.survey_subdivision_verified ? 'user-confirmed in Bhu Bharati' : 'not verified'})`
                            : ' · Survey: not verified'}
                        </div>
                        <div className="text-xs leading-relaxed text-slate-600">
                          Source: <a className="underline" href={valuation.source_url} target="_blank" rel="noreferrer">Bhu Bharati official portal</a>
                        </div>
                        <p className="text-xs leading-relaxed text-slate-700">{valuation.confidence_note}</p>
                        <p className="text-xs font-medium text-amber-900">
                          This is an arithmetic result based on a user-confirmed government guidance rate, not a market estimate or legal valuation.
                        </p>
                      </dl>
                    )}
                  </section>

                  <section className="border-t border-slate-200 pt-4">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Rental information</h3>
                    <dl className="mt-2 grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <dt className="text-slate-500">1 BHK</dt>
                        <dd className="font-semibold text-slate-900">
                          {rentalSummary?.oneBedroomRent != null
                            ? `${formatRent(rentalSummary.oneBedroomRent)}/month`
                            : oneBedroomRentEstimate
                              ? `≈ ${formatRent(oneBedroomRentEstimate.rent)}/month`
                              : 'Data unavailable'}
                        </dd>
                        {oneBedroomRentEstimate && (
                          <dd className="mt-1 text-xs leading-relaxed text-amber-800">
                            Estimated for {oneBedroomRentEstimate.year} using the median 1 BHK-to-2 BHK rent ratio from {oneBedroomRentEstimate.peerLocalityCount} localities in the Hyderabad dataset; not a direct listing.
                          </dd>
                        )}
                      </div>
                      <div>
                        <dt className="text-slate-500">2 BHK</dt>
                        <dd className="font-semibold text-slate-900">
                          {rentalSummary?.twoBedroomRent == null
                            ? 'Data unavailable'
                            : `${formatRent(rentalSummary.twoBedroomRent)}/month`}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Average rent · 2026</dt>
                        <dd className="font-semibold text-slate-900">
                          {rentalSummary?.averageRent == null
                            ? 'Data unavailable'
                            : `${formatRent(rentalSummary.averageRent)}/month`}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Rental growth · 2017–2026</dt>
                        <dd className="font-semibold text-slate-900">
                          {rentalSummary?.trendPercent == null
                            ? 'Data unavailable'
                            : `${rentalSummary.trendPercent >= 0 ? '+' : '−'}${Math.abs(rentalSummary.trendPercent).toFixed(1)}%`}
                        </dd>
                      </div>
                    </dl>
                  </section>

                  <section className="border-t border-slate-200 pt-4">
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Actions</h3>
                    <div className="mt-2 grid grid-cols-1 gap-2">
                      <button
                        type="button"
                        onClick={() => handleLandPanelAction('rent-history')}
                        className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-left text-sm font-medium text-slate-800 transition hover:border-emerald-300 hover:bg-emerald-50"
                      >
                        📈 Rent History
                      </button>
                      <button
                        type="button"
                        onClick={() => handleLandPanelAction('land-price-history')}
                        className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-left text-sm font-medium text-slate-800 transition hover:border-emerald-300 hover:bg-emerald-50"
                      >
                        📈 Land Price History
                      </button>
                      <button
                        type="button"
                        onClick={() => handleLandPanelAction('rent-insight')}
                        className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-left text-sm font-medium text-slate-800 transition hover:border-emerald-300 hover:bg-emerald-50"
                      >
                        🤖 Why did rent change?
                      </button>
                      <button
                        type="button"
                        onClick={() => handleLandPanelAction('forecast')}
                        className="min-h-11 rounded-lg border border-slate-200 px-3 py-2 text-left text-sm font-medium text-slate-800 transition hover:border-emerald-300 hover:bg-emerald-50"
                      >
                        🔮 Forecast
                      </button>
                    </div>
                    {landPanelAction === 'rent-history' && (
                      <p className="mt-2 text-xs text-slate-600" role="status">
                        {landAnalysisLocality
                          ? 'Rent history is shown in the locality rental analysis below.'
                          : 'Rent history is unavailable for this locality.'}
                      </p>
                    )}
                    {landPanelAction === 'land-price-history' && (
                      landDatasetLoading ? (
                        <p className="mt-2 text-sm text-slate-600" role="status">
                          Loading historical land prices for {detectedLandLocality?.name ?? 'this locality'}…
                        </p>
                      ) : landDatasetError ? (
                        <p className="mt-2 text-sm text-rose-700" role="alert">
                          Historical land-price data could not be loaded: {landDatasetError}
                        </p>
                      ) : landPriceHistory.length > 0 ? (
                        <div
                          className="mt-3 h-56 w-full min-w-0"
                          aria-label={`${detectedLandLocality?.name ?? 'Selected locality'} land-price history chart`}
                        >
                          <ResponsiveContainer width="100%" height="100%">
                            <LineChart
                              data={landPriceHistory}
                              margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                              <XAxis
                                dataKey="year"
                                type="number"
                                domain={['dataMin', 'dataMax']}
                                tick={{ fontSize: 11 }}
                                tickFormatter={(year) => String(year)}
                              />
                              <YAxis
                                width={64}
                                tick={{ fontSize: 11 }}
                                tickFormatter={(value) => `₹${Number(value).toLocaleString('en-IN')}`}
                              />
                              <Tooltip
                                labelFormatter={(year) => `Year: ${year}`}
                                formatter={(value, _name, item) => [
                                  `₹${Number(value).toLocaleString('en-IN')} / sq.ft`,
                                  `Land price${item?.payload?.sample_count > 1
                                    ? ` (n=${item.payload.sample_count})`
                                    : ''}`,
                                ]}
                              />
                              <Line
                                type="monotone"
                                dataKey="value_per_sqft"
                                name="Land Price / sq.ft"
                                stroke="#047857"
                                strokeWidth={2.5}
                                activeDot={{ r: 5 }}
                              />
                            </LineChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <p className="mt-2 text-sm text-slate-600" role="status">
                          Historical land-price data unavailable.
                        </p>
                      )
                    )}
                    {landPanelAction === 'rent-insight' && !landAnalysisLocality && (
                      <p className="mt-2 text-xs text-slate-600" role="status">
                        Rent insight is unavailable for this locality.
                      </p>
                    )}
                    {landPanelAction === 'forecast' && (
                      rentalForecast.length > 0 ? (
                        <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                          <table className="min-w-full text-left text-xs">
                            <thead className="bg-slate-50 text-slate-600">
                              <tr>
                                <th scope="col" className="px-3 py-2">Rental forecast</th>
                                <th scope="col" className="px-3 py-2">Year</th>
                                <th scope="col" className="px-3 py-2">Average / month</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {rentalForecast.map((row) => (
                                <tr key={`${row.bedrooms}-${row.year}`}>
                                  <th scope="row" className="px-3 py-2 font-medium text-slate-800">{row.bedrooms}</th>
                                  <td className="px-3 py-2 text-slate-700">{row.year} · predicted</td>
                                  <td className="px-3 py-2 text-slate-700">
                                    ₹{Math.round(row.averageRent).toLocaleString('en-IN')}
                                    <span className="block text-slate-500">n={row.sampleCount}</span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <p className="px-3 py-2 text-xs text-slate-500">
                            Predicted rental amounts from the validated dataset; not a land-price forecast.
                          </p>
                        </div>
                      ) : (
                        <p className="mt-2 text-xs text-slate-600" role="status">
                          Rental forecast data unavailable for this locality.
                        </p>
                      )
                    )}
                  </section>

                  {detectedLandLocality && (
                    <details className="border-t border-slate-200 pt-3">
                      <summary className="cursor-pointer text-sm font-medium text-emerald-800">
                        Validated dataset records
                      </summary>
                      {landDatasetLoading && (
                        <p className="mt-2 text-sm text-slate-600" role="status">
                          Loading records for {detectedLandLocality.name}…
                        </p>
                      )}
                      {landDatasetError && (
                        <p className="mt-2 text-sm text-rose-700" role="alert">
                          Dataset could not be loaded: {landDatasetError}
                        </p>
                      )}
                      {landDatasetMatchesSelection && landDataset?.records.length === 0 && (
                        <p className="mt-2 text-sm text-slate-600">
                          No validated dataset records are available for {landDataset.locality}.
                        </p>
                      )}
                      {landDatasetMatchesSelection && landDataset?.records.map((record) => (
                        <article
                          key={record.record_id}
                          className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3"
                        >
                          <p className="text-sm font-semibold text-slate-900">
                            {record.bedrooms} · {record.area_sqft.toLocaleString('en-IN')} sq.ft
                          </p>
                          <p className="mt-1 text-xs text-slate-600">{record.property_type}</p>
                          <details className="mt-2">
                            <summary className="cursor-pointer text-sm font-medium text-emerald-800">
                              Annual recorded and predicted prices
                            </summary>
                            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs sm:grid-cols-3">
                              {record.historical_prices.map((price) => (
                                <div key={price.source_field}>
                                  <dt className="text-slate-600">{price.year} · recorded</dt>
                                  <dd className="font-medium text-slate-900">
                                    ₹{Number(price.value).toLocaleString('en-IN')}
                                  </dd>
                                </div>
                              ))}
                              {record.predicted_prices.map((price) => (
                                <div key={price.source_field}>
                                  <dt className="text-slate-600">{price.year} · predicted</dt>
                                  <dd className="font-medium text-slate-900">
                                    ₹{Number(price.value).toLocaleString('en-IN')}
                                  </dd>
                                </div>
                              ))}
                            </dl>
                          </details>
                        </article>
                      ))}
                    </details>
                  )}
                </div>
              </details>
            </section>
          )}
        </div>
      </div>
      {selectedMarker && (
        <p className="border-t border-slate-200 px-5 py-3 text-xs text-slate-500 sm:px-6">
          The green circle marks an approximate focus around {selectedMarker.name}; locality boundary data is not available.
        </p>
      )}
      {areaSelection?.bounds && (
        <p className="border-t border-slate-200 px-5 py-3 text-xs text-slate-500 sm:px-6">
          The green outline is the geocoder&apos;s approximate bounding box for {areaSelection.name}, not an official locality boundary.
        </p>
      )}
    </section>
  );
}

export default RentTraceMap;
