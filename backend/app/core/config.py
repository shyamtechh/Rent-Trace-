import logging
import os
import secrets
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
ENV_FILE = PROJECT_DIR / ".env"
_PROJECT_DOTENV_VALUES = dotenv_values(ENV_FILE)
_PRE_DOTENV_ENVIRONMENT = dict(os.environ)
load_dotenv(ENV_FILE)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{(BACKEND_DIR / 'data' / 'renttrace.db').as_posix()}",
)
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(48)
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REMEMBER_TOKEN_EXPIRE_DAYS = int(os.getenv("REMEMBER_TOKEN_EXPIRE_DAYS", "30"))
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax").lower()
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175,"
        "http://localhost:5176,http://127.0.0.1:5176",
    ).split(",")
    if origin.strip()
]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:5173/api/auth/oauth/google/callback",
)
logger.info(
    "Google OAuth configuration loaded from %s: client_id_present=%s "
    "client_secret_present=%s redirect_uri_present=%s",
    ENV_FILE,
    bool(GOOGLE_CLIENT_ID.strip()),
    bool(GOOGLE_CLIENT_SECRET.strip()),
    bool(GOOGLE_REDIRECT_URI.strip()),
)
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI",
    "http://127.0.0.1:8000/api/auth/oauth/github/callback",
)
GEOCODER_SEARCH_URL = os.getenv(
    "GEOCODER_SEARCH_URL",
    "https://nominatim.openstreetmap.org/search",
)
GEOCODER_REVERSE_URL = os.getenv(
    "GEOCODER_REVERSE_URL",
    "https://nominatim.openstreetmap.org/reverse",
)
GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "RentTrace/1.0")
TGRAC_CADASTRAL_LAYER_URL = os.getenv(
    "TGRAC_CADASTRAL_LAYER_URL",
    "https://tgrac.telangana.gov.in/arcgis/rest/services/HMDA_Folder/HMDA/MapServer/5/query",
)
BHUBHARATI_MARKET_VALUE_URL = os.getenv(
    "BHUBHARATI_MARKET_VALUE_URL",
    "https://bhubharati.telangana.gov.in/viewMarketValueLandStampDuty?lang=en",
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
CHAT_RATE_LIMIT_PER_MINUTE = int(os.getenv("CHAT_RATE_LIMIT_PER_MINUTE", "20"))
CHAT_RATE_LIMIT_PER_HOUR = int(os.getenv("CHAT_RATE_LIMIT_PER_HOUR", "100"))
OPENAI_MAX_RETRIES = min(max(int(os.getenv("OPENAI_MAX_RETRIES", "2")), 0), 2)


def _openai_key_source() -> str:
    if _PRE_DOTENV_ENVIRONMENT.get("OPENAI_API_KEY", "").strip():
        return "process_environment"
    if str(_PROJECT_DOTENV_VALUES.get("OPENAI_API_KEY") or "").strip():
        return "project_dotenv"
    return "missing"


def _openai_key_matches_project_dotenv() -> bool:
    dotenv_key = str(_PROJECT_DOTENV_VALUES.get("OPENAI_API_KEY") or "").strip()
    return bool(OPENAI_API_KEY.strip() and OPENAI_API_KEY.strip() == dotenv_key)


logger.info(
    "RentTrace OpenAI runtime configuration: env_file=%s env_file_exists=%s "
    "api_key_present=%s api_key_source=%s api_key_matches_project_dotenv=%s "
    "model=%s",
    ENV_FILE,
    ENV_FILE.is_file(),
    bool(OPENAI_API_KEY.strip()),
    _openai_key_source(),
    _openai_key_matches_project_dotenv(),
    OPENAI_MODEL,
)
