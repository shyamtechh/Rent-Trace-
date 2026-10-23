import insightCsv from '../data/hyderabad_rental_insights_2016_2025.csv?raw';
import methodsCsv from '../data/hyderabad_rental_insights_sources_and_method.csv?raw';

const DATA_START_YEAR = 2016;
const DATA_END_YEAR = 2025;
const RENT_SOURCE_NOTES = [
  'rent_2bhk_inr_verified',
  'rent_2bhk_inr_estimated',
  'rent_2bhk_inr_best',
  'it_hub_proximity_tier_est',
  'new_construction_tier_est',
  'metro_access_status / level',
  'telangana_it_employment_*',
  'telangana_real_gsdp_growth_pct_verified',
  'hyderabad_ua_population_million_estimated',
  'hyderabad_housing_sales_units_verified',
];

function parseCsv(csv) {
  const records = [];
  let record = [];
  let field = '';
  let quoted = false;

  for (let index = 0; index < csv.length; index += 1) {
    const character = csv[index];
    if (quoted) {
      if (character === '"' && csv[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"' && field.length === 0) {
      quoted = true;
    } else if (character === ',') {
      record.push(field);
      field = '';
    } else if (character === '\n' || character === '\r') {
      if (character === '\r' && csv[index + 1] === '\n') {
        index += 1;
      }
      record.push(field);
      if (record.some((value) => value.length > 0)) {
        records.push(record);
      }
      record = [];
      field = '';
    } else {
      field += character;
    }
  }

  record.push(field);
  if (record.some((value) => value.length > 0)) {
    records.push(record);
  }

  const [headers, ...rows] = records;
  if (!headers) {
    return [];
  }
  return rows.map((values) => Object.fromEntries(
    headers.map((header, index) => [header.trim(), (values[index] ?? '').trim()]),
  ));
}

function normalizeArea(name) {
  return name.trim().replace(/[^a-z0-9]/gi, '').toLocaleLowerCase();
}

function numberOrNull(value) {
  if (value == null || value.trim() === '') {
    return null;
  }
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}

function compactNumber(value, maximumFractionDigits = 0) {
  return value == null
    ? null
    : Number(value).toLocaleString('en-IN', { maximumFractionDigits });
}

const insightRows = parseCsv(insightCsv);
const methodRows = parseCsv(methodsCsv);
const aliases = new Map([
  ['hitechcity', 'hiteccity'],
  ['kukatpally', 'kukatpallykphb'],
  ['kphb', 'kukatpallykphb'],
]);
const insightsByArea = new Map();
for (const row of insightRows) {
  const areaKey = normalizeArea(row.area);
  const areaRows = insightsByArea.get(areaKey) ?? [];
  areaRows.push(row);
  insightsByArea.set(areaKey, areaRows);
}
for (const rows of insightsByArea.values()) {
  rows.sort((left, right) => Number(left.year) - Number(right.year));
}

const cityRowsByYear = new Map();
for (const row of insightRows) {
  const year = Number(row.year);
  if (!cityRowsByYear.has(year)) {
    cityRowsByYear.set(year, row);
  }
}

function rowAt(rows, year) {
  return rows.find((row) => Number(row.year) === year) ?? null;
}

function firstAvailableNumber(row, ...keys) {
  for (const key of keys) {
    const value = numberOrNull(row?.[key]);
    if (value != null) {
      return value;
    }
  }
  return null;
}

function changeBetween(first, last) {
  return first != null && last != null && first !== 0
    ? ((last - first) / first) * 100
    : null;
}

function showChange(first, last, digits = 1) {
  const change = changeBetween(first, last);
  if (change == null) {
    return 'Not available';
  }
  return `${change >= 0 ? '+' : ''}${change.toFixed(digits)}%`;
}

function areaNameFor(name) {
  const key = normalizeArea(name);
  return aliases.get(key) ?? key;
}

function getFallbackRentPeriod(summary) {
  const observations = (summary?.trend ?? [])
    .map((observation) => ({
      year: Number(observation.year ?? observation.observation_date?.slice(0, 4)),
      rent: numberOrNull(String(observation.averageRent ?? observation.average_rent ?? '')),
    }))
    .filter((observation) => Number.isInteger(observation.year) && observation.rent != null)
    .sort((left, right) => left.year - right.year);

  if (observations.length < 2) {
    return null;
  }
  return { start: observations[0], end: observations.at(-1) };
}

function factor(label, evidence, coverage) {
  return { label, evidence, coverage };
}

export function getHyderabadRentalInsight(name, fallbackSummary = null) {
  const areaRows = insightsByArea.get(areaNameFor(name)) ?? [];
  const startRow = rowAt(areaRows, DATA_START_YEAR);
  const endRow = rowAt(areaRows, DATA_END_YEAR);
  const areaSpecific = Boolean(
    startRow
    && endRow
    && numberOrNull(startRow.rent_2bhk_inr_best) != null
    && numberOrNull(endRow.rent_2bhk_inr_best) != null,
  );
  const fallbackPeriod = areaSpecific ? null : getFallbackRentPeriod(fallbackSummary);
  const rentStart = areaSpecific
    ? numberOrNull(startRow.rent_2bhk_inr_best)
    : fallbackPeriod?.start.rent ?? null;
  const rentEnd = areaSpecific
    ? numberOrNull(endRow.rent_2bhk_inr_best)
    : fallbackPeriod?.end.rent ?? null;
  const trendPercent = changeBetween(rentStart, rentEnd);
  const period = areaSpecific
    ? `${DATA_START_YEAR}–${DATA_END_YEAR}`
    : fallbackPeriod
      ? `${fallbackPeriod.start.year}–${fallbackPeriod.end.year}`
      : 'Not available';
  const rentConfidence = areaSpecific
    ? `${startRow.rent_confidence || 'Not stated'} → ${endRow.rent_confidence || 'Not stated'}`
    : fallbackPeriod ? 'RentTrace historical locality averages' : 'Not available';
  const startRent = compactNumber(rentStart);
  const endRent = compactNumber(rentEnd);
  const cityStart = cityRowsByYear.get(DATA_START_YEAR);
  const cityEnd = cityRowsByYear.get(DATA_END_YEAR);
  const metroStart = startRow?.metro_access_status || null;
  const metroEnd = endRow?.metro_access_status || null;

  const employmentStart = firstAvailableNumber(
    cityStart,
    'telangana_it_employment_verified',
    'telangana_it_employment_estimated',
  );
  const employmentEnd = firstAvailableNumber(
    cityEnd,
    'telangana_it_employment_verified',
    'telangana_it_employment_estimated',
  );
  const employmentStartEstimated = numberOrNull(cityStart?.telangana_it_employment_verified) == null;
  const employmentEndEstimated = numberOrNull(cityEnd?.telangana_it_employment_verified) == null;
  const populationStart = numberOrNull(cityStart?.hyderabad_ua_population_million_estimated);
  const populationEnd = numberOrNull(cityEnd?.hyderabad_ua_population_million_estimated);
  const metroKmStart = numberOrNull(cityStart?.city_metro_network_km_verified);
  const metroKmEnd = numberOrNull(cityEnd?.city_metro_network_km_verified);
  const gsdPStart = numberOrNull(cityStart?.telangana_real_gsdp_growth_pct_verified);
  const gsdPEnd = numberOrNull(cityEnd?.telangana_real_gsdp_growth_pct_verified);
  const housingSalesStart = firstAvailableNumber(cityRowsByYear.get(2022), 'hyderabad_housing_sales_units_verified');
  const housingSalesEnd = firstAvailableNumber(cityRowsByYear.get(2023), 'hyderabad_housing_sales_units_verified');
  const constructionTier = startRow?.new_construction_tier_est || null;
  const itTier = startRow?.it_hub_proximity_tier_est || null;

  const factors = [
    factor(
      'IT and employment growth',
      `${areaSpecific && itTier ? `Area IT-corridor proximity tier ${itTier} (estimated). ` : ''}Telangana IT employment: ${compactNumber(employmentStart)} (${DATA_START_YEAR}${employmentStartEstimated ? ', estimated' : ', reported'}) → ${compactNumber(employmentEnd)} (${DATA_END_YEAR}${employmentEndEstimated ? ', estimated' : ', reported'}); change ${showChange(employmentStart, employmentEnd)}. Statewide, not locality employment.`,
      areaSpecific && itTier ? 'Area estimate + statewide data' : 'Statewide data',
    ),
    factor(
      'Transportation / metro accessibility',
      areaSpecific && metroEnd
        ? `${metroStart && metroStart !== metroEnd ? `${metroStart} (${DATA_START_YEAR}) → ` : ''}${metroEnd} (${DATA_END_YEAR}). Opening dates are sourced; area-to-station proximity is an analyst judgement.`
        : 'No matching area-level metro-access record in the supplied CSV.',
      areaSpecific ? 'Area record; proximity partly estimated' : 'Not available for this area',
    ),
    factor(
      'Infrastructure development',
      metroKmStart != null && metroKmEnd != null
        ? `City metro network length: ${compactNumber(metroKmStart, 1)} km (${DATA_START_YEAR}) → ${compactNumber(metroKmEnd, 1)} km (${DATA_END_YEAR}); citywide, not locality-specific.`
        : 'Comparable citywide metro-network observations are not available in this CSV.',
      'Citywide reported figures',
    ),
    factor(
      'Population and migration',
      populationStart != null && populationEnd != null
        ? `Hyderabad urban-area population estimate: ${compactNumber(populationStart, 2)}M (${DATA_START_YEAR}) → ${compactNumber(populationEnd, 2)}M (${DATA_END_YEAR}). Net migration data is not available.`
        : 'Comparable population estimates are not available in this CSV; net migration is not reported.',
      'Citywide estimate; migration unavailable',
    ),
    factor(
      'New construction',
      areaSpecific && constructionTier
        ? `Area construction tier: ${constructionTier} (qualitative estimate; not an area-level measured percentage).`
        : 'No matching area-level construction tier in the supplied CSV.',
      areaSpecific ? 'Area estimate' : 'Not available for this area',
    ),
    factor(
      'Economic conditions',
      gsdPStart != null || gsdPEnd != null
        ? `Telangana real GSDP growth: ${gsdPStart == null ? 'not reported' : `${gsdPStart}% (${DATA_START_YEAR})`} → ${gsdPEnd == null ? 'not reported' : `${gsdPEnd}% (${DATA_END_YEAR})`}; state-level figures.`
        : 'Comparable state-level real GSDP observations are not available in this CSV.',
      'Statewide reported figures',
    ),
    factor(
      'Housing demand',
      housingSalesStart != null && housingSalesEnd != null
        ? `Hyderabad housing sales: ${compactNumber(housingSalesStart)} units (2022) → ${compactNumber(housingSalesEnd)} units (2023); citywide.`
        : 'Comparable citywide housing-sales observations are not available in this CSV.',
      'Citywide reported figures',
    ),
    factor(
      'Local connectivity',
      'A separate locality connectivity score is not present in the supplied CSV. Metro access is shown above, not inferred here.',
      'Not available',
    ),
  ];

  const methodNotes = methodRows.filter((row) => RENT_SOURCE_NOTES.includes(row.column));
  const rentDirection = trendPercent == null
    ? 'cannot be calculated from the available rent records'
    : `${trendPercent >= 0 ? 'increased' : 'decreased'} by ${Math.abs(trendPercent).toFixed(1)}%`;
  const formattedRentStart = rentStart == null ? null : `₹${startRent}`;
  const formattedRentEnd = rentEnd == null ? null : `₹${endRent}`;
  const explanation = areaSpecific
    ? `${name}'s supplied 2-BHK series ${rentDirection} from ${formattedRentStart} in ${DATA_START_YEAR} to ${formattedRentEnd} in ${DATA_END_YEAR} (confidence: ${rentConfidence}). The CSV also records ${itTier ? `an estimated IT-corridor tier of ${itTier}` : 'no IT-corridor tier'}${metroEnd ? ` and ${metroEnd.toLowerCase()}` : ''}. These indicators overlap in time; the supplied data does not establish that they caused the rent change.`
    : `${name}'s RentTrace historical locality averages ${rentDirection}${fallbackPeriod ? ` from ${formattedRentStart} in ${fallbackPeriod.start.year} to ${formattedRentEnd} in ${fallbackPeriod.end.year}` : ''}. The supplied factor CSV does not include a matching area record, so its citywide context cannot establish what caused this locality's change.`;

  return {
    areaSpecific,
    period,
    rentStart,
    rentEnd,
    rentConfidence,
    trendPercent,
    factors,
    explanation,
    methodNotes,
  };
}
