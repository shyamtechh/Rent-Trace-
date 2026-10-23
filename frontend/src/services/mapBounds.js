import L from 'leaflet';
import { normalizeProviderBounds } from './mapBoundsData.js';

export function createLeafletBounds(bounds) {
  const normalizedBounds = normalizeProviderBounds(bounds);
  return L.latLngBounds(normalizedBounds);
}
