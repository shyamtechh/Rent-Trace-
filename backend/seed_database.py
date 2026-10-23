from datetime import date, datetime, timezone
from decimal import Decimal
import os

from sqlalchemy import select

from app.database import SessionLocal
from app.models import DataSource, Locality, LocalityFactor, PriceHistory, Property, RentalPrice

if os.getenv("APP_ENV", "development").lower() == "production":
    raise SystemExit("Refusing to load synthetic demo records when APP_ENV=production.")

source_name = "RentTrace synthetic development sample"
dataset_name = "Synthetic demo records"

with SessionLocal() as db:
    source = db.scalar(
        select(DataSource).where(
            DataSource.source_name == source_name,
            DataSource.dataset_name == dataset_name,
        )
    )
    if source is None:
        source = DataSource(
            source_name=source_name,
            dataset_name=dataset_name,
            description="Synthetic DEMO values generated for local development; not real-world observations.",
            collected_at=datetime.now(timezone.utc),
        )
        db.add(source)
        db.flush()

    samples = [
        {
            "locality": {
                "name": "Madhapur",
                "city": "Hyderabad",
                "state": "Telangana",
                "country": "India",
                "latitude": Decimal("17.440892"),
                "longitude": Decimal("78.391630"),
            },
            "property": {"property_type": "Apartment", "bedrooms": 2, "bathrooms": Decimal("2"), "area_sqft": Decimal("950"), "furnishing": "Semi-furnished"},
            "rents": [Decimal("26000"), Decimal("26500"), Decimal("27000"), Decimal("27500"), Decimal("28000"), Decimal("28500")],
            "prices": [Decimal("9500000"), Decimal("9600000"), Decimal("9700000"), Decimal("9800000"), Decimal("9900000"), Decimal("10000000")],
        },
        {
            "locality": {
                "name": "Gachibowli",
                "city": "Hyderabad",
                "state": "Telangana",
                "country": "India",
                "latitude": Decimal("17.443622"),
                "longitude": Decimal("78.351964"),
            },
            "property": {"property_type": "Apartment", "bedrooms": 2, "bathrooms": Decimal("2"), "area_sqft": Decimal("900"), "furnishing": "Unfurnished"},
            "rents": [Decimal("24500"), Decimal("25000"), Decimal("25500"), Decimal("26000"), Decimal("26500"), Decimal("27000")],
            "prices": [Decimal("8900000"), Decimal("9000000"), Decimal("9100000"), Decimal("9200000"), Decimal("9300000"), Decimal("9400000")],
        },
    ]
    observations = [date(2026, month, 1) for month in (5, 6, 7, 8, 9, 10)]

    for sample in samples:
        locality_values = sample["locality"]
        locality = db.scalar(
            select(Locality).where(
                Locality.name == locality_values["name"],
                Locality.city == locality_values["city"],
                Locality.state == locality_values["state"],
                Locality.country == locality_values["country"],
            )
        )
        if locality is None:
            locality = Locality(
                **locality_values,
                description="DEMO locality record. Coordinates are geocoded; associated rent and price metrics are synthetic.",
            )
            db.add(locality)
            db.flush()
        else:
            locality.latitude = locality_values["latitude"]
            locality.longitude = locality_values["longitude"]
            locality.description = "DEMO locality record. Coordinates are geocoded; associated rent and price metrics are synthetic."

        property_values = sample["property"]
        property_record = db.scalar(
            select(Property).where(
                Property.locality_id == locality.id,
                Property.property_type == property_values["property_type"],
                Property.bedrooms == property_values["bedrooms"],
                Property.area_sqft == property_values["area_sqft"],
            )
        )
        if property_record is None:
            property_record = Property(locality_id=locality.id, **property_values)
            db.add(property_record)
            db.flush()

        for observation_date, rent, price in zip(observations, sample["rents"], sample["prices"], strict=True):
            rental_exists = db.scalar(
                select(RentalPrice.id).where(
                    RentalPrice.property_id == property_record.id,
                    RentalPrice.observation_date == observation_date,
                    RentalPrice.source_id == source.id,
                )
            )
            if rental_exists is None:
                db.add(RentalPrice(
                    property_id=property_record.id,
                    locality_id=locality.id,
                    rent=rent,
                    security_deposit=rent * 2,
                    price_per_sqft=rent / property_record.area_sqft,
                    observation_date=observation_date,
                    source_id=source.id,
                ))

            history_exists = db.scalar(
                select(PriceHistory.id).where(
                    PriceHistory.locality_id == locality.id,
                    PriceHistory.observation_date == observation_date,
                )
            )
            if history_exists is None:
                db.add(PriceHistory(
                    locality_id=locality.id,
                    observation_date=observation_date,
                    average_property_price=price,
                    average_rent=rent,
                    average_price_per_sqft=price / property_record.area_sqft,
                    median_rent=rent,
                    median_price=price,
                    sample_size=1,
                ))

        factor_exists = db.scalar(
            select(LocalityFactor.id).where(
                LocalityFactor.locality_id == locality.id,
                LocalityFactor.observation_date == observations[-1],
            )
        )
        if factor_exists is None:
            db.add(LocalityFactor(
                locality_id=locality.id,
                observation_date=observations[-1],
                population=10000,
                population_growth=Decimal("2.5"),
                migration_rate=Decimal("1.8"),
                infrastructure_score=Decimal("7.5"),
                employment_score=Decimal("8.0"),
                education_score=Decimal("7.0"),
                healthcare_score=Decimal("6.8"),
                transport_score=Decimal("7.2"),
                construction_cost_index=Decimal("1.1"),
                economic_activity_index=Decimal("7.4"),
            ))

    db.commit()

print("Inserted or verified clearly labelled synthetic RentTrace DEMO records.")
