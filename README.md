# RentTrace

RentTrace keeps its existing React + Vite frontend and FastAPI backend. The backend now provides SQLAlchemy 2, Alembic migrations, PostgreSQL support, cookie-based JWT authentication, password hashing, locality/property/rental APIs, historical analytics, and validated CSV import.

## Existing database safety

The existing `backend/data/renttrace.db` was inspected and migrated in place. Its existing user rows were retained, and the schema was upgraded without dropping records. That SQLite file remains available and ignored by Git. If you switch `DATABASE_URL` to PostgreSQL, copy its existing accounts after running the migration with `python -m scripts.migrate_sqlite_users` from `backend`; the script opens SQLite read-only and never deletes or overwrites PostgreSQL accounts.

## Requirements

- Python 3.11 or newer
- Node.js 18 or newer
- PostgreSQL 16+ or Docker Desktop with Compose

SQLite is the no-configuration local-development fallback when no root `.env` file is present. For PostgreSQL, configure `.env` and start a PostgreSQL server before running migrations.

## PostgreSQL setup on Windows

1. Install and start Docker Desktop, or install PostgreSQL using the official Windows installer.
2. At the project root, copy the example environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Edit `.env`. Set a private PostgreSQL password in both `POSTGRES_PASSWORD` and `DATABASE_URL`, and replace `SECRET_KEY` with a newly generated secret. Generate one with:

   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   The `.env` file is ignored by Git. Do not commit it or reuse the example values.

4. If using Docker Desktop, start PostgreSQL from the project root:

   ```powershell
   docker compose up -d postgres
   docker compose ps
   ```

   The Compose service creates the `renttrace` database and persists its data in a named volume. For an existing PostgreSQL installation, create a database named `renttrace` and ensure the `.env` database user has access.

5. Install the backend dependencies and apply the initial migration:

   ```powershell
   Set-Location backend
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

   The migrations create the application tables and add a soft-delete timestamp for rental observations. They fail safely if they encounter an incompatible existing schema; they do not drop or overwrite that schema.

6. Copy the existing SQLite accounts to PostgreSQL without changing the original SQLite file:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.migrate_sqlite_users
   ```

7. Create or promote your administrator account. The password is entered through a hidden prompt:

   ```powershell
   .\.venv\Scripts\python.exe -m scripts.create_admin
   ```

8. Optional: load clearly labelled synthetic development records. The script is repeatable and refuses to run when `APP_ENV=production`:

   ```powershell
   .\.venv\Scripts\python.exe seed_database.py
   ```

9. Start FastAPI:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

10. In a second terminal, start the unchanged Vite frontend:

    ```powershell
    Set-Location frontend
    npm install
    npm run dev -- --port 5173 --strictPort
    ```

   Open http://localhost:5173. Vite proxies `/api` to `VITE_API_URL` from the project-root `.env`, defaulting to `http://127.0.0.1:8000`. Local origins on ports 5173–5176 are explicitly allowed for credentialed API requests. For deployment, add the exact HTTPS website origin to `CORS_ORIGINS` in the backend environment and restart FastAPI; do not use `*` when credentials are enabled.

## Authentication

- `POST /api/signup` registers a regular user; passwords are stored using Argon2id hashes.
- `POST /api/login` sets an HttpOnly JWT cookie. The `remember_me` option controls its expiry.
- Google and GitHub sign-in use OAuth authorization-code flows and require provider credentials in the root `.env` file. With the local Vite server on port 5173, register `http://localhost:5173/api/auth/oauth/google/callback` as the Google authorized redirect URI and set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, and `FRONTEND_URL` in `.env`. Check the active backend's non-secret settings at `/api/auth/oauth/google/config-status`. The callback goes through Vite's `/api` proxy so the OAuth state and session cookies stay on the same `localhost` host as the frontend. Docker Compose currently starts only PostgreSQL; FastAPI must be run separately. For deployment, register an HTTPS callback on the same site as the frontend and configure matching redirect URI, frontend URL, CORS origins, and secure cookies.
- `GET /api/me` restores the signed-in user without exposing the token to JavaScript.
- `POST /api/logout` clears the session cookie.
- Admin endpoints require a valid session for an account whose database role is `admin`. Public signup cannot grant admin access.
- Set `COOKIE_SECURE=true` behind HTTPS in production. Set a strong `SECRET_KEY` and production-specific `CORS_ORIGINS` before deployment.

Legacy PBKDF2 password hashes are verified and upgraded to Argon2id at the next successful login.

## Database model

`users` stores accounts. `localities` connects to `properties`, `rental_prices`, `price_history`, `locality_factors`, `predictions`, and `analytics_snapshots`. `rental_prices` also references `data_sources`; `model_runs` connects to `feature_importance`. Historical foreign keys use restrictive deletion behavior. Rental DELETE sets `deleted_at` and hides the record from normal queries; it does not erase the observation. Model run metrics and parameters use PostgreSQL JSONB.

## APIs

- Health: `GET /api/health` checks the configured database and returns `{"status":"ok","database":"connected"}`.
- Authentication: `POST /api/signup`, `POST /api/login`, `GET /api/me`, `POST /api/logout`.
- Localities: `GET/POST /api/localities`, `GET/PUT/DELETE /api/localities/{id}`.
- Properties: `GET/POST /api/properties`, `GET/PUT/DELETE /api/properties/{id}`.
- Rentals: `GET/POST /api/rentals`, `GET/PUT/DELETE /api/rentals/{id}`.
- Analytics: `/api/analytics/locality/{id}`, `/rent-trend`, `/price-trend`, `/factors`, and `/api/analytics/compare?locality_ids=1&locality_ids=2`.
- Data sources: `GET/POST /api/data-sources`.
- City geocoding: `GET /api/geocoding/search?city=Hyderabad` returns provider results with a real center and optional bounding box. The frontend calls it only after the user submits a search.
- Reverse geocoding: `GET /api/geocoding/reverse?latitude=17.44&longitude=78.39` returns an OpenStreetMap address/locality suggestion clearly marked as unverified.
- Admin CSV import: `POST /api/import/{localities|properties|rentals|price_history|locality_factors}` using multipart field `file`. The JSON report includes total, successful, and failed row counts plus row-specific errors.

All writes to market data and all CSV imports require an administrator session. API docs are available at `/docs` and `/redoc`.

## Hyderabad land-analysis dataset

The original workbook belongs in `data/raw/hyderabad_renttrace_dataset.xlsx`. Keep raw files unchanged. Process the workbook from the project root with:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe process_renttrace_dataset.py
```

The processor writes validated records and a validation report under `data/processed/`; it excludes invalid rows, reports missing values and duplicate keys, and does not fill missing values. The land-analysis API reads only the processed JSON file:

- `GET /api/land-analysis/locality/{locality_name}` returns validated housing records, their historical/predicted price fields, and a locality land-rate lookup. When validated land-price-per-square-foot fields exist, the lookup uses the latest non-predicted year not later than the current year and averages that field across matching locality records. It never derives a land rate from rent. If the processed dataset has no applicable rate, the map displays `Land price data unavailable for this locality.` and does not calculate a land value.

The current workbook has 116 records and fields `ID`, `Bedrooms`, `Area`, `Locality`, `Price_2017`–`Price_2026`, and `Price_2027_Predicted`–`Price_2030_Predicted`. It contains no land price, land price per square foot, street/road, latitude, or longitude fields. Consequently, no land rate or land value is available for any locality from this dataset. The yearly `Price_*` fields are preserved by their source column names; predicted years remain separate from historical years and are not used for current land rates.

Some localities have no 1 BHK rent in the workbook. For those localities only, the map may show a clearly labeled 1 BHK estimate calculated from that locality's available 2 BHK rent and the median observed 1 BHK-to-2 BHK rent ratio across localities that have both values. It is rounded to the nearest ₹100, retains the 2026 dataset reference year, and is explicitly distinguished from a direct listing. If the locality has no usable 2 BHK rent or the dataset has no paired comparison values, the map reports the 1 BHK value as unavailable rather than fabricating one.

## Government guidance-rate land calculation

The existing map and polygon-area calculation are reused. When a polygon is finished, RentTrace calculates its planar coordinate centroid and queries the configured TGRAC HMDA GIS layer. Candidate ESRI rings are checked with a point-in-polygon test; District, Mandal, and Village are shown as a TGRAC administrative GIS match only when one returned polygon contains the centroid. An out-of-coverage point, overlapping match, or upstream outage is not presented as a verified location.

TGRAC's `Parcels` attribute is retained only as a source GIS reference and is never used to populate a survey/sub-division number. Survey information remains “not verified” unless the user manually checks and confirms it in the official [Bhu Bharati GIS portal](https://bhubharati.telangana.gov.in/gis/). The market-value portal requires manual interaction; RentTrace does not scrape it, bypass CAPTCHA, or claim a public API. The official [Bhu Bharati market-value lookup](https://bhubharati.telangana.gov.in/viewMarketValueLandStampDuty?lang=en) should be used to manually verify a rate, effective date, category, and administrative details.

The rate entry is explicitly INR per square yard, with a property category, source URL, effective date, verification date, manual-entry method, and survey-verification flag persisted in the database. Migration `0004_land_rate_provenance` adds these provenance fields; apply it with `Set-Location backend; .\.venv\Scripts\python.exe -m alembic upgrade head`.

## Point-based land-record identification

The map's **Identify by map point** mode calls `GET /api/land/identify?latitude={latitude}&longitude={longitude}`. It uses a provider registry in `backend/app/services/land_identification.py`; the only configured provider is the existing TGRAC HMDA ArcGIS layer. Its coordinate request uses WGS84 (EPSG:4326), which is the service's configured input/output spatial reference.

The configured TGRAC response can provide an administrative GIS feature and District/Mandal/Village attributes when a single returned geometry contains the point. It does **not** currently supply a survey number that RentTrace has verified, an official user-plot boundary, an authoritative parcel area, or a current land rate. The UI marks this as an administrative match only and displays those cadastral/value fields as unavailable. A missing feature is not proof that the location is outside Telangana or that no parcel exists. Multiple matches are reported without selecting a feature. Provider failures return HTTP 503 rather than an invented result.

Bhu Bharati's GIS page provides a manual district/division/mandal/village selection and a Survey No field, and instructs users to click the map for parcel information. No authorized public coordinate-query API or downloadable cadastral dataset has been integrated or confirmed. RentTrace links users to [Bhu Bharati GIS](https://bhubharati.telangana.gov.in/gis/) for manual verification; it does not automate protected UI, bypass access controls, or claim that manual entry is verified by RentTrace. TGRAC metadata could not be reached from the development environment during this implementation, so live field meanings and coverage are not independently confirmed.

There is no parcel geometry table, PostGIS extension, or spatial database index in the current schema. The API calls the external ArcGIS provider and does not persist or substitute its GIS features as official parcels. The application supports PostgreSQL through SQLAlchemy, but the current local runtime may use SQLite; adding PostGIS is deferred until an authorized parcel dataset and its coordinate system/coverage are established. Other states have no configured provider, so nationwide coverage is not claimed.

To add an authorized state/provider, implement the `LandRecordProvider` interface, verify its supported geography, coordinate reference system, record identifiers, survey-field semantics, update dates, and use permissions, then register it in `LAND_RECORD_PROVIDERS`. Add a provider-specific data source/configuration only after those facts are documented. Test it against authoritative sample parcels before returning `survey_number_status="found"`; until then the UI must keep survey and valuation data unavailable.

The map supports a user-entered known survey/sub-division number for reference, but labels it unverified and does not store or treat it as an official match. Government guideline rates and market estimates remain unavailable through automatic point lookup until a permitted source is integrated; no value is calculated without a compatible verified area and rate.

## RentTrace AI chat

The authenticated dashboard includes a floating RentTrace AI assistant. Its existing `/api/chat` endpoint first retrieves only the mentioned/selected localities' data from the processed workbook and the existing SQLAlchemy rental, property-history, forecast, and locality-factor tables. Simple factual rental questions are answered directly from those records without calling OpenAI; missing facts are returned as unavailable rather than estimated. Explanations, interpretation, and other questions that need natural-language reasoning go to the configured provider with the relevant retrieved facts and at most six recent conversation messages (800 characters each). Responses identify whether they came directly from RentTrace data, are an AI interpretation, or are unavailable. A numeric-response guard suppresses generated numerical claims that are not present in the retrieved context (except BHK labels explicitly asked about). User-drawn geometry is map context only, not a verified plot boundary. The assistant does not create guideline values or market prices from missing data.

No AI provider credentials or model are configured by default. To enable responses, set the following in the project-root `.env` and restart FastAPI:

```dotenv
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5.5
OPENAI_TIMEOUT_SECONDS=20
CHAT_RATE_LIMIT_PER_MINUTE=20
CHAT_RATE_LIMIT_PER_HOUR=100
OPENAI_MAX_RETRIES=2
```

RentTrace uses the official OpenAI Python SDK and Responses API (`AsyncOpenAI.responses.create`). The existing account's permitted model must be configured with `OPENAI_MODEL`; `gpt-5.5` is the documented default, but model availability depends on the OpenAI API account and project. Choose a model enabled for that account if the default returns a model-access error. `OPENAI_MAX_RETRIES` defaults to two SDK retries and is capped at two; timeout defaults to 20 seconds. OpenAI API keys are read only from the backend's project-root `.env` or backend process environment. Never put the key in a `VITE_` variable. The authenticated `/api/chat/status` endpoint reports configuration readiness without returning secret values. Startup diagnostics report the resolved `.env` path, key-presence/source-match booleans, and model; errors log HTTP status, safe provider error code, and exception type only. Authentication, permission/model access, quota/rate limit, timeout, and network errors map to user-safe messages without returning raw provider details or stack traces. Per-user limits default to 20 requests per minute and 100 per hour. The limiter is process-local, so use a shared limiter before deploying multiple FastAPI worker processes. Existing data-first responses continue to use RentTrace database/workbook records and do not call OpenAI for simple factual rental queries. Chat endpoints require an authenticated RentTrace session.

Windows setup (after configuring `.env`):

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q tests\test_chat.py
```

In another PowerShell terminal:

```powershell
Set-Location frontend
node --test src\services\chat.test.js
npm.cmd run build
```

The calculation is:

```text
area in square yards = geographically calculated polygon area in square feet / 9
guidance-rate-based value = area in square yards × user-confirmed INR per square yard
```

RentTrace persists the entered rate, source type, rate unit, category, dates, source URL, survey-verification status, area method, and result. This is arithmetic based on a user-entered government guideline rate; it is not a verified quote, market selling price, or legal valuation. The current validated workbook has no land-price-per-square-foot field, so market rate and market value are shown as unavailable instead of being inferred from rent or housing prices. Nominatim supplies only approximate address suggestions and is subject to its public usage policy; requests are rate-limited and identified with `GEOCODER_USER_AGENT`.

## City geocoding policy

City search uses the public OpenStreetMap Nominatim service by default, configured by `GEOCODER_SEARCH_URL`. Requests are proxied through FastAPI, identified by `GEOCODER_USER_AGENT`, cached for 15 minutes, and serialized to at most one provider request per second per backend process. The frontend searches only on form submission; it does not send keystrokes to Nominatim or implement autocomplete. Public Nominatim has limited capacity: keep use moderate, replace the example User-Agent contact value before deployment, retain OpenStreetMap attribution, and switch `GEOCODER_SEARCH_URL` to a suitable provider or hosted instance if usage grows. Review the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/) before deploying.

## CSV required columns

- `localities`: `name,city,state,country`; optional coordinates and description.
- `properties`: `locality_id,property_type`; optional bedrooms, bathrooms, area, furnishing, and floor fields.
- `rentals`: `property_id,locality_id,rent,observation_date,source_id`.
- `price_history`: `locality_id,observation_date`; at least one metric or `sample_size` is also required.
- `locality_factors`: `locality_id,observation_date`; at least one factor value is also required.

Dates use `YYYY-MM-DD`. Invalid rows, duplicates, missing fields, invalid numbers, and unknown foreign keys are included in the response report.

## Verification

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m pytest -q
```

For the real PostgreSQL connection test, ensure PostgreSQL is running and `DATABASE_URL` is set in the project-root `.env`, then run:

```powershell
.\.venv\Scripts\python.exe -m pytest -m postgres -q
```

Check the live API at http://127.0.0.1:8000/api/health and Swagger at http://127.0.0.1:8000/docs.

## Troubleshooting

- Connection refused: start the PostgreSQL Windows service or `docker compose up -d postgres`; confirm port 5432 is available.
- Password authentication failed: match `DATABASE_URL` credentials with the PostgreSQL user/password; URL-encode reserved password characters.
- Database does not exist: create `renttrace`, or use the Compose service which creates it.
- Missing table: run `alembic upgrade head` from `backend` after setting `.env`.
- Login fails after switching to PostgreSQL: run `scripts/migrate_sqlite_users.py` once after migration to copy existing account hashes.
- Cookie not retained: use the same frontend hostname consistently, keep `COOKIE_SECURE=false` for local HTTP, and include the frontend URL in `CORS_ORIGINS`.
- Frontend cannot reach API: confirm FastAPI is on port 8000 or set `VITE_API_URL` before starting Vite.
