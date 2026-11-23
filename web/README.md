# Web App (Next.js 14)

The user interface for the Congressional Disclosure Analytics platform. Built
with Next.js 14 (App Router, TypeScript), Tailwind CSS, shadcn/ui,
`lucide-react`, `recharts`, TanStack Query, `react-hook-form`, and `zod`.

## Port

| Service | Port |
| :--- | :--- |
| web | `3000` |

## Architecture

The browser never talks to the backend microservices directly. All requests go
through **Next.js route handlers** (a Backend-for-Frontend) that:

- Keep the access and refresh tokens in `httpOnly`, `Secure`, `SameSite=Lax`
  cookies (never in `localStorage`).
- Attach the `Authorization: Bearer` header when proxying to the backend.
- Enforce CSRF protection on mutating requests.
- Transparently refresh expired access tokens.

Backend services proxied by the BFF:

| Service | Default URL |
| :--- | :--- |
| auth-service | `http://auth-service:8512` |
| analytics-service | `http://analytics-service:8517` |
| admin-service | `http://admin-service:8515` |
| rag-service | `http://rag-service:8516` |

## Routes

| Route | Purpose |
| :--- | :--- |
| `/login` | Username/password sign-in. |
| `/mfa` | TOTP verification. |
| `/setup-2fa` | First-login QR code enrollment. |
| `/change-password` | Mandatory first-login and self-service password change. |
| `/forgot-password`, `/reset-password` | Self-service password reset. |
| `/dashboard` | Role/scope-based landing (House, Senate, or Combined). |
| `/search` | Interactive disclosure data grid. |
| `/watchlists` | Member and ticker watchlists. |
| `/admin` | Admin command center (pipeline, users, health). |

## Local development

```bash
cp .env.example .env.local
npm install
npm run dev
```

## Environment variables

| Variable | Required | Description |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_APP_URL` | Yes | Public base URL of the web app. |
| `AUTH_SERVICE_URL` | Yes | Auth service base URL (server-side). |
| `ANALYTICS_SERVICE_URL` | Yes | Analytics service base URL (server-side). |
| `ADMIN_SERVICE_URL` | Yes | Admin service base URL (server-side). |
| `RAG_SERVICE_URL` | Yes | RAG service base URL (server-side). |
| `SESSION_SECRET` | Yes | Signs the httpOnly session cookie (>= 32 chars). |
