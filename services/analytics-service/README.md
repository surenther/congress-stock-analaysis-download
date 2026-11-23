# Analytics Service

Chamber-scoped, read-only analytics microservice for the congressional
disclosure dataset. It powers the schema-driven dashboard, top traded assets,
volume trends, late-filing compliance, committee/sector correlation, the
interactive data grid, exports, and per-user watchlists.

## Port

| Service | Port |
| :--- | :--- |
| analytics-service | `8517` |

## Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Liveness probe (unauthenticated). |
| `GET` | `/api/v1/analytics/scope` | The caller's resolved roles and chamber scope. |
| `GET` | `/api/v1/analytics/dashboard` | Schema-driven dashboard layout. |
| `GET` | `/api/v1/analytics/top-assets` | Top purchased/sold assets. |
| `GET` | `/api/v1/analytics/volume-trends` | Trading volume time series. |
| `GET` | `/api/v1/analytics/late-filings` | Filings beyond the 45-day window. |
| `GET` | `/api/v1/analytics/committee-sector` | Committee vs sector correlation. |
| `GET` | `/api/v1/analytics/disclosures` | Filtered, sorted, paginated grid. |
| `GET` | `/api/v1/analytics/export` | CSV/PDF export of grid data. |
| `GET/POST/DELETE` | `/api/v1/watchlists` | Watchlist CRUD. |
| `GET` | `/api/v1/watchlists/feed` | Personalized monitoring stream. |

All data endpoints require the `admin` or `user` role and enforce
Chamber-Based Access Control (CBAC) via the signed `allowed_chambers` claim.

## Data model

The service creates and uses these tables (idempotent, on startup):

- `members` — normalized member reference data.
- `committees` — congressional committees.
- `member_committees` — member-to-committee assignments.
- `ticker_sectors` — ticker-to-sector/industry mapping.
- `user_watchlists` — per-user member/ticker bookmarks.

When the vectorizer's `disclosure_embeddings` table exists, the service also
creates the `disclosure_facts` materialized view, which pre-joins disclosures
with member and sector metadata for fast dashboard queries.

## Environment variables

| Variable | Required | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | Yes | PostgreSQL connection string. |
| `JWT_SECRET_KEY` | Yes | Shared HS256 signing key (>= 32 chars). |
| `JWT_ISSUER` | No | Expected `iss` claim (default `congress-auth`). |
| `JWT_AUDIENCE` | No | Expected `aud` claim (default `congress-platform`). |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default `INFO`). |
