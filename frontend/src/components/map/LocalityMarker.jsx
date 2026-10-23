import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { Marker, Popup } from 'react-leaflet';
import {
  getHyderabadRentSummary,
  getOneBedroomRentEstimate,
} from '../../services/hyderabadRentData';
import { getRentLevel } from '../../services/rentHeatmap';

function LocalityMarker({ locality, selected, onSelect, onViewAnalysis }) {
  const markerRef = useRef(null);
  const latitude = Number(locality.latitude);
  const longitude = Number(locality.longitude);
  const rentSummary = getHyderabadRentSummary(locality.name);
  const oneBedroomRentEstimate = rentSummary?.oneBedroomRent == null
    ? getOneBedroomRentEstimate(locality.name)
    : null;
  const rentLevel = getRentLevel(rentSummary?.averageRent);
  const localityIcon = L.divIcon({
    className: '',
    html: `<span style="display:block;width:18px;height:18px;border:3px solid white;border-radius:50%;background-color:${rentLevel?.color ?? '#64748b'};box-shadow:0 1px 5px rgba(15,23,42,.65)"></span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  });

  useEffect(() => {
    if (selected) {
      markerRef.current?.openPopup();
    }
  }, [selected]);

  return (
    <Marker
      ref={markerRef}
      position={[latitude, longitude]}
      icon={localityIcon}
      zIndexOffset={selected ? 1000 : 0}
      eventHandlers={{ click: () => onSelect(locality) }}
    >
      <Popup>
        <div className="min-w-44 space-y-2 text-sm text-slate-800">
          <h3 className="font-semibold text-slate-950">{locality.name}</h3>
          <p>Latitude: {latitude.toFixed(5)}</p>
          <p>Longitude: {longitude.toFixed(5)}</p>
          {rentSummary && (
            <div className="space-y-1 border-t border-slate-200 pt-2">
              {rentSummary.oneBedroomRent != null ? (
                <p>1 BHK: ₹{Math.round(rentSummary.oneBedroomRent).toLocaleString('en-IN')}</p>
              ) : oneBedroomRentEstimate ? (
                <p>
                  1 BHK estimate: ≈ ₹{oneBedroomRentEstimate.rent.toLocaleString('en-IN')}
                  {' '}({oneBedroomRentEstimate.year} dataset; peer locality ratio)
                </p>
              ) : null}
              {rentSummary.twoBedroomRent != null && (
                <p>2 BHK: ₹{Math.round(rentSummary.twoBedroomRent).toLocaleString('en-IN')}</p>
              )}
              <p>Avg. rent: ₹{Math.round(rentSummary.averageRent).toLocaleString('en-IN')}</p>
              {rentSummary.trendPercent != null && (
                <p>
                  Trend: {rentSummary.trendPercent >= 0 ? '↑' : '↓'}{' '}
                  {Math.abs(rentSummary.trendPercent).toFixed(1)}% (2017–2026)
                </p>
              )}
            </div>
          )}
          {onViewAnalysis && (
            <button
              type="button"
              onClick={() => onViewAnalysis(locality)}
              className="mt-1 rounded-md bg-emerald-700 px-3 py-2 font-medium text-white transition hover:bg-emerald-800 focus:outline-none focus:ring-2 focus:ring-emerald-400"
            >
              View locality analysis
            </button>
          )}
        </div>
      </Popup>
    </Marker>
  );
}

export default LocalityMarker;
