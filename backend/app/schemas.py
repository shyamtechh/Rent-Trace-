from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Name must contain at least two non-whitespace characters.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_signup_email(cls, value: str) -> str:
        return value.strip().lower()


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False

    @field_validator("email")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        return value.strip().lower()


class UserPublic(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    message: str
    user: UserPublic


class LocalityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    city: str = Field(min_length=1, max_length=150)
    state: str = Field(min_length=1, max_length=150)
    country: str = Field(min_length=1, max_length=100)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    description: str | None = None


class LocalityRead(LocalityCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CitySearchResult(BaseModel):
    id: str
    name: str
    display_name: str
    center: tuple[float, float]
    bounds: tuple[tuple[float, float], tuple[float, float]] | None = None


class ReverseGeocodeResult(BaseModel):
    display_name: str
    suggested_locality: str | None
    suggested_district: str | None
    source_name: str
    source_url: str
    verification_status: Literal["suggestion_only"]


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def trim_chat_history(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Conversation messages cannot be blank.")
        return value


class ChatSelectedContext(BaseModel):
    locality_name: str | None = Field(default=None, max_length=150)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    polygon_area_square_feet: Decimal | None = Field(default=None, gt=0, le=Decimal("100000000"))
    area_method: str | None = Field(default=None, max_length=120)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1200)
    history: list[ChatHistoryMessage] = Field(default_factory=list, max_length=10)
    selected_context: ChatSelectedContext | None = None

    @field_validator("message")
    @classmethod
    def trim_chat_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank.")
        return value


class PropertyCreate(BaseModel):
    locality_id: int
    property_type: str = Field(min_length=1, max_length=80)
    bedrooms: int | None = Field(default=None, ge=0)
    bathrooms: Decimal | None = Field(default=None, ge=0)
    area_sqft: Decimal | None = Field(default=None, gt=0)
    furnishing: str | None = Field(default=None, max_length=80)
    floor: int | None = Field(default=None, ge=0)
    total_floors: int | None = Field(default=None, gt=0)


class PropertyRead(PropertyCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RentalCreate(BaseModel):
    property_id: int
    locality_id: int
    rent: Decimal = Field(ge=0)
    security_deposit: Decimal | None = Field(default=None, ge=0)
    price_per_sqft: Decimal | None = Field(default=None, ge=0)
    observation_date: date
    source_id: int


class RentalRead(RentalCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DataSourceCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=180)
    source_url: str | None = Field(default=None, max_length=1000)
    dataset_name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    collected_at: datetime | None = None


class DataSourceRead(DataSourceCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceHistoryRead(BaseModel):
    id: int
    locality_id: int
    observation_date: date
    average_property_price: Decimal | None
    average_rent: Decimal | None
    average_price_per_sqft: Decimal | None
    median_rent: Decimal | None
    median_price: Decimal | None
    sample_size: int | None

    model_config = ConfigDict(from_attributes=True)


class LandValuationCreate(BaseModel):
    latitude: Decimal = Field(ge=-90, le=90)
    longitude: Decimal = Field(ge=-180, le=180)
    area_square_feet: Decimal = Field(gt=0, le=Decimal("100000000"))
    rate_per_sq_yard: Decimal = Field(gt=0, le=Decimal("1000000000000"))
    rate_unit: Literal["INR/sq_yd"] = "INR/sq_yd"
    property_category: str = Field(min_length=1, max_length=80)
    rate_date: date
    verified_date: date
    user_confirmed_rate: bool
    survey_subdivision_verified: bool = False
    source_url: str = Field(min_length=20, max_length=1000)
    district: str | None = Field(default=None, max_length=150)
    mandal: str | None = Field(default=None, max_length=150)
    village: str | None = Field(default=None, max_length=150)
    survey_subdivision: str | None = Field(default=None, max_length=150)
    parcel_reference: str | None = Field(default=None, max_length=150)
    parcel_feature_id: str | None = Field(default=None, max_length=120)
    parcel_attributes: dict[str, object] | None = None
    parcel_geometry: dict[str, object] | None = None
    area_method: str = Field(default="Spherical polygon area; converted from sq.ft", max_length=120)

    @field_validator("source_url")
    @classmethod
    def require_bhubharati_source(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or parsed.hostname != "bhubharati.telangana.gov.in":
            raise ValueError("The source URL must be the official Bhu Bharati domain.")
        return value.strip()

    @field_validator("verified_date")
    @classmethod
    def verification_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Verification date cannot be in the future.")
        return value

    @field_validator("rate_date")
    @classmethod
    def rate_date_not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Rate date cannot be in the future.")
        return value

    @field_validator("user_confirmed_rate")
    @classmethod
    def require_user_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Confirm that the rate was manually checked on Bhu Bharati.")
        return value

    @model_validator(mode="after")
    def validate_survey_verification(self) -> "LandValuationCreate":
        if self.survey_subdivision_verified and not (self.survey_subdivision or "").strip():
            raise ValueError("A survey number is required when marked as verified.")
        return self

    @field_validator("property_category")
    @classmethod
    def normalize_property_category(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Property category cannot be blank.")
        return value


class LandValuationRead(BaseModel):
    valuation_id: int
    latitude: Decimal
    longitude: Decimal
    area_square_feet: Decimal
    area_square_yards: Decimal
    rate_per_sq_yard: Decimal
    rate_unit: Literal["INR/sq_yd"]
    property_category: str
    source_type: str
    survey_subdivision_verified: bool
    total_value: Decimal
    source_url: str
    rate_date: date
    verified_date: date
    area_method: str
    estimation_method: str
    confidence_note: str
