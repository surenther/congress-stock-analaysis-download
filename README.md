# Congressional Financial Disclosures Downloader & Microservice

[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-microservice-009688.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An automated Python pipeline and Dockerized microservice to download, organize, and monitor official U.S. Congressional Financial Disclosures (including STOCK Act Periodic Transaction Reports and Annual Reports) for both the **House of Representatives** and the **Senate**.

Stores all downloaded filings **outside the Docker container** in a host folder of your choice.

---

## Features

- **Dual-Chamber Support**:
  - **U.S. House of Representatives**: Ingests annual disclosure bulk ZIP archives (`disclosures-clerk.house.gov`), extracts master XML indexes, and downloads PDFs.
  - **U.S. Senate**: Automates the statutory agreement splash screen on `efdsearch.senate.gov`, navigates to `/search/`, selects **Annual** and **Periodic Transactions** reports, applies dynamic date ranges (`Jan 1` to `current date`), and queries the DataTables search API.
- **Microservice Architecture**: Built-in FastAPI REST API with background task execution, job status monitoring, healthcheck probes, and interactive Swagger documentation (`/docs`).
- **External Host Storage**: Configurable host volume mounting (`OUTPUT_BASE_DIR` -> `/data`) so all files reside directly on your external hard drive or host directory.
- **Smart Deduplication & Skip Logic**: Checks if ZIP archives, XML indexes, or PDFs already exist locally before fetching, saving network bandwidth and enabling safe, rapid re-runs.
- **Zero Hardcoded URLs**: All endpoints, URL patterns, date ranges, and paths are completely configurable via environment files (`.env.house` and `.env.senate`).
- **Standardized Folder Hierarchy**: Organizes filings cleanly by year, month filed, and representative/senator name.

---

## Folder Hierarchy

All downloaded filings are structured in your external storage directory as follows:

```text
/your/external/storage/                  # Configured via OUTPUT_BASE_DIR
├── house_rep/
│   └── 2026/
│       ├── 2026FD.zip                   # Bulk annual archive
│       ├── 2026FD.xml                   # Master XML index
│       └── 01_January/                  # Month filed
│           └── Pelosi_Nancy/            # Representative folder
│               ├── 20026123.pdf         # Individual filing PDF (DocID.pdf)
│               └── 20026456.pdf
└── senate/
    └── 2026/
        └── 01_January/                  # Month filed
            └── Schumer_Chuck/           # Senator folder
                ├── 10023456.pdf         # Scanned Paper PDF
                └── 10023789.html        # Electronic Disclosure Table
```

---

## Project Structure

This repository is organized as a multi-service monorepo. Each service lives in its own directory under `services/` with its own `Dockerfile`, dependencies, and configuration:

```text
.
├── .gitea/workflows/          # Gitea Actions CI/CD workflows
├── docker-compose.yml         # Orchestrates all services
├── services/
│   └── downloader/            # Congressional filings downloader + FastAPI microservice
│       ├── app.py             # FastAPI microservice (port 8511)
│       ├── download_filings.py# House/Senate ingestion pipeline
│       ├── Dockerfile
│       ├── requirements.txt
│       └── .env.house / .env.senate
└── README.md
```

> `services/ocr_processor/` and `services/vector_indexer/` are planned for future releases.

---

## Quick Start with Docker

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/congress-stock-analysis.git
cd congress-stock-analysis
```

### 2. Configure Host Storage Location
Specify where you want the filings stored on your host machine:

```bash
# Example: Store inside ./data or an external hard drive
export OUTPUT_BASE_DIR="./data"
```

### 3. Start the Microservice API
```bash
docker compose up -d --build
```

The service will start on `http://localhost:8511`.
Open your browser to view the interactive Swagger documentation:
👉 **`http://localhost:8511/docs`**

---

## Automatic Deployment with Gitea Actions

This repository includes a [Gitea Actions](https://docs.gitea.com/usage/actions/overview) workflow (`.gitea/workflows/deploy.yml`) that automatically builds and deploys the Docker service to your server whenever you push to the `main` branch.

### Prerequisites

- A Gitea Actions runner registered on the server with the label `ubuntu-latest` (e.g. `app-vm-runner`).
- Docker and the Docker Compose plugin installed on the server.
- The runner user must have permission to run `docker` commands (add it to the `docker` group).

### How it works

1. You commit and push to `main` (or create a `v*` tag).
2. The runner checks out the code.
3. The workflow builds the downloader image and pushes it to the container registry (`registry.surenther.xyz/congress-downloader`) tagged with `latest` and the short commit SHA (or the tag name).
4. The workflow SSHes into the server and runs `docker compose pull && docker compose up -d` inside the deploy directory.
5. The `congress-service` container is recreated with the new image.

### Server setup (one-time)

1. Clone the repository on the server:
   ```bash
   git clone https://git.surenther.xyz/surenther/congress-stock-analaysis-download.git /opt/congress-filings
   cd /opt/congress-filings
   ```
2. *(Optional)* Configure the environment files. The env files are **mounted from the host** (`services/downloader/.env.house` and `.env.senate`), so editing them on the host is picked up the next time the container is created. The deploy workflow creates them from the `.example` templates if they don't exist yet:

   ```bash
   cd services/downloader
   cp .env.house.example .env.house
   cp .env.senate.example .env.senate
   # edit both files with your real configuration
   cd ../..
   ```

   > **Important**: Inside the container, `OUTPUT_BASE_DIR` must be `/data` (the mounted volume path). Do **not** change it to a host path in these files.

3. Choose where filings are stored on the host by setting **`OUTPUT_BASE_DIR`** in a `.env` file next to `docker-compose.yml`:

   ```bash
   # in the repo root, create a .env file:
   OUTPUT_BASE_DIR=/home/surenther/unraid/stock-ai
   ```

   - `OUTPUT_BASE_DIR=/data` → stores in `./data` next to the compose file
   - `OUTPUT_BASE_DIR=/home/surenther/unraid/stock-ai` → stores in that host folder

   This **single variable** controls the host storage location. The app always writes to `/data` inside the container, which maps to this host folder.

### Required secrets

Add these secrets in **Gitea → Repository → Settings → Actions → Secrets**:

| Secret | Description |
| :--- | :--- |
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_USER` | SSH user on the server |
| `DEPLOY_SSH_KEY` | SSH private key (newlines preserved) |
| `DEPLOY_PORT` | SSH port (defaults to `22` if unset) |
| `DEPLOY_PATH` | Absolute path to the repo/compose directory on the server (e.g. `/opt/congress-filings`) |

### Manual trigger

You can also run the deployment manually from the Gitea **Actions** tab using the **Run workflow** button.

---

## REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Container healthcheck (verifies storage mount is writable). |
| `GET` | `/status` | Real-time status and statistics of running and completed ingestion jobs. |
| `POST` | `/download/house` | Triggers House disclosure download in background. |
| `POST` | `/download/senate` | Triggers Senate disclosure download (auto-accepts agreement gate). |
| `POST` | `/download/all` | Sequentially queues both House and Senate downloads. |

### API Examples:

#### Trigger Senate Download:
```bash
curl -X POST "http://localhost:8511/download/senate" \
     -H "Content-Type: application/json" \
     -d '{"year": "2026", "max_downloads": 0}'
```

#### Trigger House Download:
```bash
curl -X POST "http://localhost:8511/download/house" \
     -H "Content-Type: application/json" \
     -d '{"year": "2026", "max_downloads": 50}'
```

#### Poll Ingestion Progress:
```bash
curl "http://localhost:8511/status"
```

---

## One-Off Batch Execution via Docker

If you prefer running standalone one-shot containers without keeping the web server running:

```bash
# Download House filings
docker compose run --rm house-job

# Download Senate filings
docker compose run --rm senate-job
```

---

## Running Locally (Without Docker)

You can run the script directly on your machine using Python 3.10+:

```bash
# 1. Navigate to the downloader service
cd services/downloader

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run House ingestion (e.g. download all or set a test limit)
python3 download_filings.py house
# Or limit downloads: MAX_DOWNLOADS=10 python3 download_filings.py house

# 5. Run Senate ingestion (e.g. download all or set a test limit)
python3 download_filings.py senate
# Or limit downloads: MAX_DOWNLOADS=10 python3 download_filings.py senate

# 6. (Optional) Run local FastAPI microservice
uvicorn app:app --reload --port 8511
```

---

## Configuration Reference

The repository includes dedicated configuration templates in the downloader service:
- **`[.env.house](services/downloader/.env.house.example)`**: House of Representatives settings.
- **`[.env.senate](services/downloader/.env.senate.example)`**: Senate settings.

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CHAMBER` | `House of Representatives` / `Senate` | Chamber name used in logs and display headers. |
| `YEAR` | `2026` | Filing year to target. |
| `OUTPUT_BASE_DIR` | `/data` (in Docker) | Base root directory for storage. |
| `OUTPUT_DIR` | `house_rep` / `senate` | Destination subfolder name for this chamber. |
| `MONTH_FORMAT` | `01_January` | Options: `01_January` (preserves calendar order), `January`, `01`, `Jan`. |
| `REP_NAME_FORMAT` | `last_first` | Options: `last_first` (`Pelosi_Nancy`) or `first_last` (`Nancy_Pelosi`). |
| `FILING_TYPES` | `P,A,O,C,T,Z` | Filing type filter (`P` = Periodic Transaction Reports / stock trades, `ALL` = everything). |
| `START_DATE` | `01/01/{year}` | Senate start date filter (Jan 1 of the filing year). |
| `END_DATE` | `TODAY` | Senate end date filter (current date when script executes). |
| `REQUEST_DELAY` | `0.3` | Delay in seconds between PDF downloads to respect server limits. |
| `MAX_DOWNLOADS` | `0` | Maximum files to download (`0` = no limit / download all). |
| `FORCE_DOWNLOAD` | `false` | Set `true` to overwrite and re-download already existing local files. |
| `USER_AGENT` | Standard Chrome header | Custom HTTP User-Agent header. |

---

## Public Data & Responsible Use

This tool accesses publicly accessible records provided by congressional disclosure portals. Users are responsible for ensuring their use complies with public record guidelines, which state that disclosure data is provided for public transparency and news reporting, and should not be used for commercial solicitation, credit assessments, or unauthorized purposes.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
