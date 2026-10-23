export function summarizeRentalForecast(records) {
  if (!Array.isArray(records)) {
    return [];
  }

  const groupedPrices = new Map();
  for (const record of records) {
    const bedroomMatch = /^(\d+)\s*BHK\b/i.exec(record?.bedrooms ?? '');
    if (!bedroomMatch || !Array.isArray(record.predicted_prices)) {
      continue;
    }

    const bedroomCount = Number(bedroomMatch[1]);
    for (const prediction of record.predicted_prices) {
      const year = Number(prediction?.year);
      const value = Number(prediction?.value);
      if (!Number.isInteger(year) || !Number.isFinite(value) || value <= 0) {
        continue;
      }

      const key = `${bedroomCount}-${year}`;
      const group = groupedPrices.get(key) ?? { bedroomCount, year, total: 0, count: 0 };
      group.total += value;
      group.count += 1;
      groupedPrices.set(key, group);
    }
  }

  return Array.from(groupedPrices.values())
    .map(({ bedroomCount, year, total, count }) => ({
      bedrooms: `${bedroomCount} BHK`,
      bedroomCount,
      year,
      averageRent: total / count,
      sampleCount: count,
    }))
    .sort((left, right) => (
      left.bedroomCount - right.bedroomCount || left.year - right.year
    ));
}
