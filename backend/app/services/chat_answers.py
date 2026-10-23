import re
from typing import Any


_COMPLEX_QUESTION = re.compile(
    r"\b(why|explain|interpret|summari[sz]e|analy[sz]e|reason|recommend|forecast|predict)\b",
    re.IGNORECASE,
)
_RENT_QUESTION = re.compile(
    r"\b(rent|rental|bhk|bedroom|cheaper|cheapest|lower rent|lowest rent)\b",
    re.IGNORECASE,
)
_COMPARISON_QUESTION = re.compile(
    r"\b(compare|comparison|lower|lowest|cheaper|cheapest)\b",
    re.IGNORECASE,
)
_BHK_PATTERN = re.compile(r"\b([1-9])\s*(?:bhk|bedrooms?)\b", re.IGNORECASE)
_PROPERTY_PRICE_QUESTION = re.compile(
    r"\b(housing|property|house|home)\s+(price|value)\b|\bprice trend\b",
    re.IGNORECASE,
)
_LAND_PRICE_QUESTION = re.compile(
    r"\b(land rate|land price|guideline rate|plot price|rate per square foot)\b",
    re.IGNORECASE,
)


def _money(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f"₹{value:,.0f}"


def _mentioned_context_localities(message: str, localities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = message.casefold()
    return [
        item
        for item in localities
        if re.search(
            rf"(?<![\w]){re.escape(str(item.get('location', {}).get('name', '')).casefold())}(?![\w])",
            normalized,
        )
    ]


def _rent_entries(
    locality: dict[str, Any],
    bhk: int | None,
) -> list[tuple[str, float, str | None, int | None]]:
    entries: list[tuple[str, float, str | None, int | None]] = []
    for key, value in locality.get("rentals_by_bhk", {}).items():
        if bhk is not None and key != f"{bhk}_bhk":
            continue
        if not isinstance(value, dict):
            continue
        amount = value.get("average_monthly_rent")
        if isinstance(amount, (int, float)) and not isinstance(amount, bool):
            entries.append(
                (
                    f"{key.replace('_', ' ').upper()} · RentTrace database average",
                    amount,
                    value.get("latest_observation"),
                    value.get("sample_count"),
                )
            )

    workbook = locality.get("workbook_rental_data", {}).get("rentals_by_bhk", {})
    for key, value in workbook.items():
        if bhk is not None and key != f"{bhk}_bhk":
            continue
        latest = value.get("latest") if isinstance(value, dict) else None
        if isinstance(latest, dict) and isinstance(latest.get("average_monthly_rent"), (int, float)):
            entries.append(
                (
                    f"{key.replace('_', ' ').upper()} · processed RentTrace workbook",
                    latest["average_monthly_rent"],
                    str(latest.get("year")) if latest.get("year") is not None else None,
                    None,
                )
            )
    return entries


def _unavailable(subject: str) -> str:
    return (
        f"{subject} is not currently available in the RentTrace data for this request. "
        "No value has been estimated."
    )


def answer_from_renttrace_data(
    message: str,
    history: list[dict[str, str]],
    context: dict[str, Any],
) -> str | None:
    prior_user_messages = [
        item["content"] for item in history if item.get("role") == "user"
    ][-2:]
    effective_question = " ".join([*prior_user_messages, message])
    is_comparison = bool(_COMPARISON_QUESTION.search(effective_question))
    is_rent_question = bool(_RENT_QUESTION.search(effective_question)) or bool(
        re.search(r"\b(compare|comparison)\b", effective_question, re.IGNORECASE)
    )
    is_property_price = bool(_PROPERTY_PRICE_QUESTION.search(effective_question))
    is_land_price = bool(_LAND_PRICE_QUESTION.search(effective_question))
    if not (is_rent_question or is_property_price or is_land_price):
        return None

    complex_question = bool(_COMPLEX_QUESTION.search(message))
    if complex_question and not is_comparison:
        return None

    localities = context.get("localities", [])
    current_matches = _mentioned_context_localities(message, localities)
    relevant_localities = current_matches or _mentioned_context_localities(
        " ".join(prior_user_messages), localities
    )
    if not relevant_localities:
        selected_locality = (context.get("selected_map_context") or {}).get("locality_name")
        if isinstance(selected_locality, str):
            relevant_localities = _mentioned_context_localities(selected_locality, localities)

    if is_property_price:
        if not relevant_localities:
            return _unavailable("Housing price history")
        lines = []
        for locality in relevant_localities:
            name = locality.get("location", {}).get("name", "This locality")
            price_rows = [
                item
                for item in locality.get("price_history", [])
                if item.get("average_property_price") is not None
            ]
            if not price_rows:
                lines.append(f"{name}: {_unavailable('Housing price history')}")
                continue
            lines.append(f"{name} — recorded average property price:")
            for item in price_rows[-5:]:
                amount = _money(item["average_property_price"])
                sample = (
                    f", sample size {item['sample_size']}"
                    if item.get("sample_size") is not None
                    else ""
                )
                lines.append(f"- {item['date']}: {amount}{sample}.")
        return "\n".join(lines)

    if is_land_price:
        if not relevant_localities:
            return _unavailable("Land-price information")
        lines = []
        for locality in relevant_localities:
            name = locality.get("location", {}).get("name", "This locality")
            land_data = locality.get("land_price_data", {})
            rate = land_data.get("guideline_or_market_rate")
            if isinstance(rate, dict) and rate.get("available"):
                value = rate.get("value_per_sqft")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    year = f", year {rate['year']}" if rate.get("year") else ""
                    lines.append(
                        f"{name}: {_money(value)} per sq. ft.{year}, "
                        f"{rate.get('sample_count', 0)} RentTrace dataset records. "
                        "This is not independently verified as an official guideline or sale rate."
                    )
                    continue
            lines.append(f"{name}: {_unavailable('Land-price information')}")
        return "\n".join(lines)

    bhk_match = _BHK_PATTERN.search(effective_question)
    bhk = int(bhk_match.group(1)) if bhk_match else None

    if is_comparison and not relevant_localities:
        aggregates = context.get("rental_aggregates") or {}
        if bhk is not None:
            values = [
                (name, data.get(f"{bhk}_bhk", {}).get("average_monthly_rent"))
                for name, data in aggregates.get("by_locality", {}).items()
                if data.get(f"{bhk}_bhk", {}).get("average_monthly_rent") is not None
            ]
            if len(values) >= 2:
                lower = min(values, key=lambda item: item[1])
                return (
                    f"The lowest recorded {bhk} BHK average rent in the available "
                    f"RentTrace database is {lower[0]} at {_money(lower[1])} per month. "
                    "This compares recorded locality averages, not every available property."
                )
        if bhk is None:
            candidates = []
            for name, bedroom_groups in aggregates.get("by_locality", {}).items():
                weighted_total = sum(
                    group["average_monthly_rent"] * group["sample_count"]
                    for group in bedroom_groups.values()
                    if group.get("average_monthly_rent") is not None
                    and group.get("sample_count")
                )
                sample_count = sum(
                    group["sample_count"]
                    for group in bedroom_groups.values()
                    if group.get("average_monthly_rent") is not None
                    and group.get("sample_count")
                )
                if sample_count:
                    candidates.append((name, weighted_total / sample_count))
            if candidates:
                name, amount = min(candidates, key=lambda item: item[1])
                return (
                    f"The lowest recorded average rent across available property "
                    f"records is {name} at {_money(amount)} per month in the "
                    "RentTrace database. BHK mix may differ by locality."
                )
        if aggregates:
            return _unavailable("A comparable locality rent")
        return _unavailable("A rent comparison")

    if not relevant_localities:
        aggregates = context.get("rental_aggregates") or {}
        if bhk is not None:
            overall = aggregates.get("overall_by_bhk", {}).get(f"{bhk}_bhk")
            if overall and overall.get("average_monthly_rent") is not None:
                return (
                    f"The recorded {bhk} BHK average monthly rent across the "
                    f"RentTrace database is {_money(overall['average_monthly_rent'])} "
                    f"({overall['sample_count']} rental records)."
                )
        elif aggregates.get("overall_by_bhk"):
            lines = [
                f"- {label.replace('_', ' ').upper()}: "
                f"{_money(value['average_monthly_rent'])} per month "
                f"({value['sample_count']} rental records)."
                for label, value in sorted(aggregates["overall_by_bhk"].items())
                if value.get("average_monthly_rent") is not None
            ]
            if lines:
                return "RentTrace database average monthly rents by BHK:\n" + "\n".join(lines)
        return _unavailable("Rental information")

    if is_comparison and len(relevant_localities) < 2:
        return _unavailable("A comparison with at least two localities")

    lines: list[str] = []
    for locality in relevant_localities:
        name = locality.get("location", {}).get("name", "This locality")
        entries = _rent_entries(locality, bhk)
        if entries:
            lines.append(f"{name}:")
            for label, amount, observed, sample_count in entries:
                suffix = f", observed {observed}" if observed else ""
                if sample_count is not None:
                    suffix += f", {sample_count} records"
                lines.append(f"- {label}: {_money(amount)} per month{suffix}.")
        else:
            lines.append(f"{name}: {_unavailable('The requested rental figure')}")

    if not any(line.startswith("- ") for line in lines):
        return "\n".join(lines)
    if is_comparison:
        lines.append("These are source-specific recorded averages; compare matching BHK groups and dates.")
    return "\n".join(lines)
