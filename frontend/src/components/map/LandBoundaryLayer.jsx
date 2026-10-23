import { useEffect } from 'react';
import { CircleMarker, Polygon, Polyline, useMap, useMapEvents } from 'react-leaflet';

const LAND_BOUNDARY_STYLE = {
  color: '#047857',
  fillColor: '#34d399',
  fillOpacity: 0.28,
  weight: 4,
};

const DRAWING_BOUNDARY_STYLE = {
  color: '#059669',
  fillColor: '#6ee7b7',
  fillOpacity: 0.16,
  weight: 3,
  dashArray: '8 6',
};

function LandBoundaryMapEvents({ drawing, onAddPoint, onCancel }) {
  const map = useMap();

  useEffect(() => {
    if (!drawing) {
      return undefined;
    }

    const container = map.getContainer();
    const previousCursor = container.style.cursor;
    const doubleClickZoomWasEnabled = map.doubleClickZoom.enabled();
    container.style.cursor = 'crosshair';
    map.doubleClickZoom.disable();

    const cancelOnEscape = (event) => {
      if (event.key === 'Escape') {
        onCancel();
      }
    };
    window.addEventListener('keydown', cancelOnEscape);

    return () => {
      container.style.cursor = previousCursor;
      if (doubleClickZoomWasEnabled) {
        map.doubleClickZoom.enable();
      }
      window.removeEventListener('keydown', cancelOnEscape);
    };
  }, [drawing, map, onCancel]);

  useMapEvents({
    click(event) {
      if (drawing) {
        onAddPoint([event.latlng.lat, event.latlng.lng]);
      }
    },
  });

  return null;
}

function LandBoundaryLayer({
  drawing,
  draftPoints,
  boundaryPoints,
  onAddPoint,
  onCancel,
}) {
  const activePoints = drawing ? draftPoints : boundaryPoints;

  return (
    <>
      <LandBoundaryMapEvents
        drawing={drawing}
        onAddPoint={onAddPoint}
        onCancel={onCancel}
      />
      {activePoints.length >= 3 ? (
        <Polygon
          positions={activePoints}
          pathOptions={drawing ? DRAWING_BOUNDARY_STYLE : LAND_BOUNDARY_STYLE}
          interactive={false}
        />
      ) : activePoints.length >= 2 ? (
        <Polyline
          positions={activePoints}
          pathOptions={DRAWING_BOUNDARY_STYLE}
          interactive={false}
        />
      ) : null}
      {drawing && draftPoints.map((position, index) => (
        <CircleMarker
          key={`${position[0]}-${position[1]}-${index}`}
          center={position}
          radius={5}
          pathOptions={{
            color: '#ffffff',
            weight: 2,
            fillColor: '#047857',
            fillOpacity: 1,
          }}
          interactive={false}
        />
      ))}
    </>
  );
}

export default LandBoundaryLayer;
