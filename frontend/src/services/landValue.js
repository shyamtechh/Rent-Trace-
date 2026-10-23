const RUPEES_PER_LAKH = 100_000;
const RUPEES_PER_CRORE = 10_000_000;

export function calculateEstimatedLandValue(areaSquareFeet, ratePerSquareFoot) {
  if (
    !Number.isFinite(areaSquareFeet)
    || areaSquareFeet <= 0
    || !Number.isFinite(ratePerSquareFoot)
    || ratePerSquareFoot <= 0
  ) {
    return null;
  }

  const value = areaSquareFeet * ratePerSquareFoot;
  return Number.isFinite(value) ? value : null;
}

export function calculateGovernmentRateValue(areaSquareFeet, ratePerSquareYard) {
  if (
    !Number.isFinite(areaSquareFeet)
    || areaSquareFeet <= 0
    || !Number.isFinite(ratePerSquareYard)
    || ratePerSquareYard <= 0
  ) {
    return null;
  }

  const value = (areaSquareFeet / 9) * ratePerSquareYard;
  return Number.isFinite(value) ? value : null;
}

export function formatIndianCurrency(amount) {
  if (!Number.isFinite(amount)) {
    return null;
  }

  return `₹${amount.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export function formatIndianValueApproximation(amount) {
  if (!Number.isFinite(amount) || amount < RUPEES_PER_LAKH) {
    return null;
  }

  if (amount >= RUPEES_PER_CRORE) {
    return `≈ ₹${(amount / RUPEES_PER_CRORE).toLocaleString('en-IN', {
      maximumFractionDigits: 2,
    })} Cr`;
  }

  return `≈ ₹${(amount / RUPEES_PER_LAKH).toLocaleString('en-IN', {
    maximumFractionDigits: 2,
  })} Lakh`;
}
