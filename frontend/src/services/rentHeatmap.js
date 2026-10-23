export const RENT_LEVELS = [
  { id: 'low', label: 'Low Rent', range: '₹8k–₹15k', color: '#16a34a' },
  { id: 'medium', label: 'Medium Rent', range: '₹15k–₹20k', color: '#eab308' },
  { id: 'high', label: 'High Rent', range: '₹20k–₹30k', color: '#f97316' },
  { id: 'very-high', label: 'Very high Rent', range: '₹30k+', color: '#dc2626' },
];

export function getRentLevel(value) {
  if (value == null || !Number.isFinite(Number(value))) {
    return null;
  }

  const rent = Number(value);
  if (rent < 15000) return RENT_LEVELS[0];
  if (rent < 20000) return RENT_LEVELS[1];
  if (rent < 30000) return RENT_LEVELS[2];
  return RENT_LEVELS[3];
}
