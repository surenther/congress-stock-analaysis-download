# Web UI & Executive Analytics Portal (`services/web`)

[![Next.js](https://img.shields.io/badge/Next.js-14_App_Router-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-blue.svg)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3-38bdf8.svg)](https://tailwindcss.com/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

The **Web UI & Executive Analytics Portal** is the user-facing interface for the Congressional Stock Disclosures platform. Built with **Next.js 14 (App Router)** and **TypeScript**, it features a financial dashboard design language inspired by Meridian Financial Analytics, generative schema-driven UI widgets, Chamber-Based Access Control (CBAC), and an AI RAG Assistant with citation inspection.

---

## Port & Container

| Service | Container Name | Port | Base URL |
| :--- | :--- | :--- | :--- |
| `web-service` | `congress-web` | **3000** | `http://localhost:3000` |

---

## Key Features

1. **Schema-Driven UI Engine:**
   - React components act as pure presentation templates.
   - Layout, calculations, and widget configuration are evaluated by the backend RAG/Analytics engine (`POST /api/v1/rag/dashboard/analytics`).
   - Central [`WidgetRenderer`](components/dashboard/WidgetRenderer.tsx) mounts visual templates:
     - `<MetricCardWidget/>`: Upper-case category, big KPI number, trend pill badge with direction arrow.
     - `<BarChartWidget/>`: Recharts stacked/grouped bar chart (Purchases vs. Sales).
     - `<LineChartWidget/>`: Smooth curve area chart for volume timelines and trade momentum.
     - `<PieChartWidget/>`: Donut chart with inline percentage legend for sector distribution.
     - `<DataTableWidget/>`: Sortable grid with fallback badges for null cells (`—`).

2. **Executive Header & CBAC Chamber Scope:**
   - **Chamber Scope Tabs:** `House` | `Senate` | `Combined`.
   - **CBAC Lock:** Detects user's signed `allowed_chambers` JWT claim. If restricted to a single chamber (e.g. `["House"]`), the selector is locked with a lock icon tooltip.
   - **Time Horizon:** `30 Days`, `90 Days`, `YTD`, `1 Year`, `All Time`.
   - **Cluster Health Status:** Live green/red status dots monitoring backend microservices (`:8511`, `:8512`, `:8513`, `:8514`, `:8516`, `:4000`).
   - **User Scope Pill:** Displays active username, role badge (`admin` / `user`), and quick role-switch demo options.

3. **High-Performance Disclosure Records Grid (`/search`):**
   - Filter by Ticker, Filer Name, Action (`Purchase`, `Sale`, `Exchange`), Chamber, and Date Range.
   - Prominently displays `asset_name` when `ticker` is blank or unlisted (`—`).
   - One-click **CSV** and **PDF** export.

4. **Surveillance Watchlists (`/watchlists`):**
   - Pin high-conviction tickers (`NVDA`, `MSFT`) or members (`Nancy Pelosi`).
   - Dedicated activity timeline with live trade alerts and sentiment flags.

5. **Admin Command Center (`/admin`):**
   - Restricted strictly to accounts with the `admin` role.
   - Manual pipeline triggers with `Limit` and `Force` parameters for Downloader (`:8511`), Parser (`:8513`), and Vectorizer (`:8514`).
   - User account RBAC management table with chamber scope toggles and password reset triggers.

6. **Slide-Out AI Assistant (`ChatDrawer`):**
   - Floating bottom-right action button accessible across all views.
   - Queries `POST /api/v1/rag/query` with CBAC guardrails.
   - Expandable **Source Citation Cards** detailing Filer Name, Chamber, Ticker, Asset Name, Trade Date, Value Range, Similarity Score %, and Doc ID.
   - Instant visual toast if access is restricted by CBAC policy (`403 Forbidden`).

---

## Directory Structure

```text
services/web/
├── app/
│   ├── layout.tsx                     # Root layout with Header, Footer, and ChatDrawer
│   ├── globals.css                    # Tailwind design tokens and custom scrollbars
│   ├── page.tsx                       # Redirects to /dashboard
│   ├── dashboard/page.tsx             # Executive analytics dashboard
│   ├── search/page.tsx                # Disclosure records grid & export
│   ├── watchlists/page.tsx            # Pinned surveillance watchlists
│   ├── admin/page.tsx                 # Pipeline command center & user admin
│   └── api/                           # Next.js BFF route handlers
│       ├── health/                    # Container and cluster health probes
│       ├── disclosures/               # Search grid and CSV/PDF export endpoints
│       └── rag/                       # Dashboard schema and RAG query proxy
├── components/
│   ├── dashboard/                     # Pure presentation widget templates
│   │   ├── MetricCardWidget.tsx       # KPI cards with trend pill badges
│   │   ├── BarChartWidget.tsx         # Stacked/grouped bar charts
│   │   ├── LineChartWidget.tsx        # Trend velocity area curves
│   │   ├── PieChartWidget.tsx         # Asset sector donut chart
│   │   ├── DataTableWidget.tsx        # Sortable tables with null cell fallbacks
│   │   └── WidgetRenderer.tsx         # Dynamic schema layout renderer
│   ├── layout/                        # Header, Footer, and navigation
│   └── chat/                          # Slide-out AI RAG Assistant drawer
├── lib/
│   ├── auth-context.tsx               # Client-side auth, CBAC lock detection, and scope state
│   ├── query-provider.tsx             # TanStack React Query provider
│   └── utils.ts                       # Tailwind merge and currency/date formatters
├── types/                             # TypeScript schemas, disclosures, and auth models
├── Dockerfile                         # Node 20 Alpine multi-stage production build
└── package.json                       # Dependencies and build scripts
```

---

## Running Locally

### Option A: Via Docker Compose (Recommended)

From the project root:
```bash
docker compose up -d web-service
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

### Option B: Standalone Development

Inside `services/web/`:
```bash
# 1. Install dependencies
npm install

# 2. Start development server
npm run dev
```
Open [http://localhost:3000](http://localhost:3000).

### Build & Verify Production Bundle

```bash
npm run build
```
Confirms clean TypeScript compilation and creates standalone static and server assets.

---

## Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PORT` | `3000` | Port for the Next.js server. |
| `NODE_ENV` | `production` | Node environment (`development` or `production`). |
| `RAG_SERVICE_URL` | `http://localhost:8516` | URL for the RAG & Dashboard layout microservice. |
| `AUTH_SERVICE_URL` | `http://localhost:8512` | URL for the Auth microservice. |
| `ADMIN_SERVICE_URL` | `http://localhost:8515` | URL for the Admin orchestration microservice. |
| `SESSION_SECRET` | *(required in prod)* | Secret string for session cookies. |
