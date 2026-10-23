from decimal import Decimal, ROUND_HALF_UP

SQUARE_FEET_PER_SQUARE_YARD = Decimal("9")
AREA_QUANTUM = Decimal("0.0001")
CURRENCY_QUANTUM = Decimal("0.01")


def calculate_land_value(
    area_square_feet: Decimal,
    rate_per_square_yard: Decimal,
) -> tuple[Decimal, Decimal]:
    if not area_square_feet.is_finite() or area_square_feet <= 0:
        raise ValueError("Plot area must be a positive finite number of square feet.")
    if not rate_per_square_yard.is_finite() or rate_per_square_yard <= 0:
        raise ValueError("Rate must be a positive finite INR per square yard.")

    area_square_yards = (
        area_square_feet / SQUARE_FEET_PER_SQUARE_YARD
    ).quantize(AREA_QUANTUM, rounding=ROUND_HALF_UP)
    total_value = (
        area_square_feet / SQUARE_FEET_PER_SQUARE_YARD * rate_per_square_yard
    ).quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)
    return area_square_yards, total_value
