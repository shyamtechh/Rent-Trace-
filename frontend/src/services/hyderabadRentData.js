import { HYDERABAD_RENT_DATA } from '../data/hyderabadRentData.js';

const FIRST_HISTORICAL_YEAR = 2017;
const LAST_HISTORICAL_YEAR = 2026;

function normalizeLocality(name) {
  return name.trim().replace(/[^a-z0-9]/gi, '').toLocaleLowerCase();
}

const rentDataByLocality = new Map(
  Object.entries(HYDERABAD_RENT_DATA).map(([name, values]) => [normalizeLocality(name), values]),
);

export function getHyderabadRentSummary(name) {
  const values = rentDataByLocality.get(normalizeLocality(name));
  if (!values) {
    return null;
  }

  const [oneBedroomRent, twoBedroomRent, ...annualPrices] = values;
  const trend = annualPrices.map((averageRent, index) => ({
    year: FIRST_HISTORICAL_YEAR + index,
    averageRent,
  }));
  const firstPrice = trend.find((observation) => observation.year === FIRST_HISTORICAL_YEAR)?.averageRent;
  const latestPrice = trend.find((observation) => observation.year === LAST_HISTORICAL_YEAR)?.averageRent;
  const trendPercent = firstPrice && latestPrice
    ? ((latestPrice - firstPrice) / firstPrice) * 100
    : null;

  return {
    oneBedroomRent,
    twoBedroomRent,
    averageRent: latestPrice ?? null,
    trendPercent,
    trend,
    listingCount: null,
    source: 'Hyderabad_Rent_Trace_Complete_All_Localities.xlsx',
  };
}

export function getOneBedroomRentEstimate(name) {
  const localityValues = rentDataByLocality.get(normalizeLocality(name));
  const localityOneBedroomRent = localityValues?.[0];
  const localityTwoBedroomRent = localityValues?.[1];
  if (
    localityOneBedroomRent != null
    || !Number.isFinite(localityTwoBedroomRent)
    || localityTwoBedroomRent <= 0
  ) {
    return null;
  }

  const peerRentRatios = Object.values(HYDERABAD_RENT_DATA)
    .map(([oneBedroomRent, twoBedroomRent]) => (
      Number.isFinite(oneBedroomRent)
      && oneBedroomRent > 0
      && Number.isFinite(twoBedroomRent)
      && twoBedroomRent > 0
        ? oneBedroomRent / twoBedroomRent
        : null
    ))
    .filter((ratio) => ratio != null)
    .sort((left, right) => left - right);

  if (peerRentRatios.length === 0) {
    return null;
  }

  const middleIndex = Math.floor(peerRentRatios.length / 2);
  const medianRatio = peerRentRatios.length % 2 === 0
    ? (peerRentRatios[middleIndex - 1] + peerRentRatios[middleIndex]) / 2
    : peerRentRatios[middleIndex];
  const unroundedRent = localityTwoBedroomRent * medianRatio;

  return {
    rent: Math.round(unroundedRent / 100) * 100,
    ratio: medianRatio,
    peerLocalityCount: peerRentRatios.length,
    year: LAST_HISTORICAL_YEAR,
    method: 'median-locality-1BHK-to-2BHK-rent-ratio',
    source: 'Hyderabad_Rent_Trace_Complete_All_Localities.xlsx',
  };
}
