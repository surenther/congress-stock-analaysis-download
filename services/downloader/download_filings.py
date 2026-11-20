#!/usr/bin/env python3
"""
Congressional Financial Disclosures Downloader & Microservice Engine

Downloads financial disclosure filings (including stock trades / PTRs)
for the House of Representatives or the Senate without hardcoded URLs.

Storage:
  Supports storing files outside Docker containers via OUTPUT_BASE_DIR and volume mounts.
  Hierarchy: {OUTPUT_BASE_DIR}/{OUTPUT_DIR}/{YEAR}/{Month filed}/{rep_name}/{doc_id}.pdf

CLI Usage:
  python3 download_filings.py house    # Loads .env.house (ZIP + XML pipeline)
  python3 download_filings.py senate   # Loads .env.senate (Agreement gate + Search API)
  python3 download_filings.py          # Defaults to .env.house (or .env)
"""

import os
import re
import sys
import time
import zipfile
import urllib.parse
from datetime import datetime
from pathlib import Path

# defusedxml hardens against XXE / entity-expansion ("billion laughs") when
# parsing the externally-downloaded House XML index. It is a pinned dependency
# (see requirements.txt), so no stdlib fallback is provided.
from defusedxml import ElementTree as ET


# ==============================================================================
# ENVIRONMENT FILE RESOLUTION (.env.house vs .env.senate)
# ==============================================================================

def select_env_file() -> Path:
    """Determine which environment file to load based on CLI args or defaults."""
    for arg in sys.argv[1:]:
        arg_lower = arg.lower().strip("-")
        if arg_lower in ("house", "rep", "house_rep"):
            return Path(".env.house")
        elif arg_lower in ("senate", "sen"):
            return Path(".env.senate")
        elif arg.startswith("--env="):
            return Path(arg.split("=", 1)[1])

    if "--env" in sys.argv:
        idx = sys.argv.index("--env")
        if idx + 1 < len(sys.argv):
            return Path(sys.argv[idx + 1])

    if os.getenv("ENV_FILE"):
        return Path(os.getenv("ENV_FILE"))

    if Path(".env.house").exists():
        return Path(".env.house")
    return Path(".env")


def load_env_variables(env_path: Path):
    """Load configuration variables from a specific .env file."""
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=True)
    except ImportError:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip("'\"")


ENV_FILE_PATH = select_env_file()
load_env_variables(ENV_FILE_PATH)

# HTTP Client (requests with persistent Session or built-in urllib)
try:
    import requests
    USE_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    import http.cookiejar
    USE_REQUESTS = False


# ==============================================================================
# CONFIGURATION
# ==============================================================================

def get_config():
    """Retrieve current runtime configuration from environment variables."""
    return {
        "CHAMBER": os.getenv("CHAMBER", "House of Representatives"),
        "YEAR": os.getenv("YEAR", "2026"),
        "OUTPUT_DIR": os.getenv("OUTPUT_DIR", "house_rep"),
        "OUTPUT_BASE_DIR": os.getenv("OUTPUT_BASE_DIR", ""),
        "BASE_URL": os.getenv("BASE_URL", "").rstrip("/"),
        "PORTAL_URL": os.getenv("PORTAL_URL", ""),
        "AGREEMENT_URL": os.getenv("AGREEMENT_URL", ""),
        "SEARCH_URL": os.getenv("SEARCH_URL", "{base_url}/search/"),
        "SEARCH_DATA_URL": os.getenv("SEARCH_DATA_URL", ""),
        "AUTO_ACCEPT_AGREEMENT": os.getenv("AUTO_ACCEPT_AGREEMENT", "false").strip().lower() in ("true", "1", "yes"),
        "SENATE_REPORT_TYPES": os.getenv("SENATE_REPORT_TYPES", "annual,periodic").strip().lower(),
        "START_DATE_CONF": os.getenv("START_DATE", "01/01/{year}"),
        "END_DATE_CONF": os.getenv("END_DATE", "TODAY"),
        "ZIP_URL_TEMPLATES": os.getenv("ZIP_URL_TEMPLATES", ""),
        "ZIP_FILENAME_TEMPLATE": os.getenv("ZIP_FILENAME_TEMPLATE", "{year}FD.zip"),
        "PTR_PDF_URL_TEMPLATE": os.getenv("PTR_PDF_URL_TEMPLATE", ""),
        "FINANCIAL_PDF_URL_TEMPLATE": os.getenv("FINANCIAL_PDF_URL_TEMPLATE", ""),
        "FILING_TYPES": os.getenv("FILING_TYPES", "ALL").strip().upper(),
        "REP_NAME_FORMAT": os.getenv("REP_NAME_FORMAT", "last_first").strip().lower(),
        "MONTH_FORMAT": os.getenv("MONTH_FORMAT", "01_January").strip(),
        "REQUEST_DELAY": float(os.getenv("REQUEST_DELAY", "0.3")),
        "MAX_DOWNLOADS": int(os.getenv("MAX_DOWNLOADS", "0")),
        "FORCE_DOWNLOAD": os.getenv("FORCE_DOWNLOAD", "false").strip().lower() in ("true", "1", "yes"),
        "USER_AGENT": os.getenv(
            "USER_AGENT",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    }


def get_base_output_dir(override_dir: str = None) -> Path:
    """Return the resolved output directory on the filesystem or external container mount."""
    cfg = get_config()
    target_dir = override_dir or cfg["OUTPUT_DIR"]
    base_dir = cfg["OUTPUT_BASE_DIR"]

    if base_dir and not Path(target_dir).is_absolute():
        return Path(base_dir) / target_dir
    return Path(target_dir)


HEADERS = {
    "User-Agent": get_config()["USER_AGENT"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Global HTTP Session for cookie persistence
if USE_REQUESTS:
    HTTP_SESSION = requests.Session()
    HTTP_SESSION.headers.update(HEADERS)
else:
    cookie_jar = http.cookiejar.CookieJar()
    COOKIE_OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    urllib.request.install_opener(COOKIE_OPENER)


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def resolve_template(template: str, cfg: dict = None, **kwargs) -> str:
    """Format a URL or filename template with variables like {base_url}, {year}, {doc_id}."""
    c = cfg or get_config()
    params = {
        "base_url": c["BASE_URL"],
        "year": c["YEAR"],
        **kwargs
    }
    return template.format(**params)


def _is_allowed_url(url: str, cfg: dict) -> bool:
    """Return True if ``url`` targets the configured chamber host.

    Prevents SSRF: only the official House/Senate host (and its subdomains) may
    be fetched, so a compromised search response cannot redirect the downloader
    at internal services or cloud metadata endpoints.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    base_host = urllib.parse.urlparse(cfg.get("BASE_URL", "")).hostname
    if not base_host:
        return False
    host = (parsed.hostname or "").lower()
    base_host = base_host.lower()
    return host == base_host or host.endswith("." + base_host)


def http_get(url: str, headers: dict = None) -> bytes:
    """Download binary content from a URL using the persistent session."""
    if not _is_allowed_url(url, get_config()):
        raise ValueError(f"Refusing to fetch disallowed URL: {url}")
    req_headers = HEADERS.copy()
    if headers:
        req_headers.update(headers)

    if USE_REQUESTS:
        response = HTTP_SESSION.get(url, headers=req_headers, timeout=30)
        response.raise_for_status()
        return response.content
    else:
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()


def sanitize_name(name: str) -> str:
    """Sanitize names for safe filesystem directories across all operating systems."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = re.sub(r'[\s_]+', '_', clean).strip('_')
    return clean or "Unknown"


def sanitize_doc_id(doc_id: str) -> str:
    """Sanitize a document id for safe use in filenames (no path traversal)."""
    clean = re.sub(r"[^A-Za-z0-9._-]", "", str(doc_id)).strip(".")
    return clean or "unknown"


def format_rep_name(first: str, last: str, name_format: str = "last_first") -> str:
    """Format representative/senator directory name."""
    first_clean = sanitize_name(first)
    last_clean = sanitize_name(last)

    if name_format == "first_last":
        if first_clean and last_clean:
            return f"{first_clean}_{last_clean}"
        return first_clean or last_clean or "Unknown_Rep"
    else:
        if last_clean and first_clean:
            return f"{last_clean}_{first_clean}"
        return last_clean or first_clean or "Unknown_Rep"


def extract_filing_month(filing_date_str: str, month_format: str = "01_January") -> str:
    """Extract and format the month filed from the filing date string."""
    if not filing_date_str:
        return "Unknown_Month"

    date_cleaned = filing_date_str.strip()

    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(date_cleaned, fmt)
            if month_format == "January":
                return dt.strftime("%B")
            elif month_format == "01":
                return dt.strftime("%m")
            elif month_format == "Jan":
                return dt.strftime("%b")
            else:
                return dt.strftime("%m_%B")
        except ValueError:
            continue

    parts = re.split(r'[/.-]', date_cleaned)
    if parts and parts[0].isdigit():
        try:
            m = int(parts[0])
            if 1 <= m <= 12:
                dt = datetime(2000, m, 1)
                if month_format == "January":
                    return dt.strftime("%B")
                elif month_format == "01":
                    return dt.strftime("%m")
                elif month_format == "Jan":
                    return dt.strftime("%b")
                return dt.strftime("%m_%B")
        except ValueError:
            pass

    return "Unknown_Month"


def get_xml_tag_text(node, possible_tags: list, default: str = "") -> str:
    """Case-insensitive helper to find the first matching tag inside an XML element."""
    tag_set = {t.lower() for t in possible_tags}
    for child in node:
        clean_tag = child.tag.split("}")[-1].lower()
        if clean_tag in tag_set and child.text:
            return child.text.strip()
    return default


# ==============================================================================
# SENATE GATEWAY & SEARCH PAGE WORKFLOW
# ==============================================================================

def bypass_senate_agreement_gate(agreement_url: str, cfg: dict) -> bool:
    """Step 1: Automatically submit statutory agreement checkbox on /search/home/."""
    resolved_url = resolve_template(agreement_url, cfg=cfg)
    print(f"[*] Step 1: Accessing Senate portal agreement gate...")
    print(f"    URL: {resolved_url}")

    try:
        if USE_REQUESTS:
            resp = HTTP_SESSION.get(resolved_url, timeout=30)
            resp.raise_for_status()
            html = resp.text
            csrf_token = HTTP_SESSION.cookies.get("csrftoken")
        else:
            req = urllib.request.Request(resolved_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            csrf_token = ""

        if not csrf_token:
            match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html)
            if match:
                csrf_token = match.group(1)

        payload = {
            "csrfmiddlewaretoken": csrf_token or "",
            "prohibition_agreement": "1",
            "prohibitions_agreement": "1",
            "agreement": "1",
        }

        post_headers = {
            "Referer": resolved_url,
            "Origin": cfg["BASE_URL"],
        }
        if csrf_token:
            post_headers["X-CSRFToken"] = csrf_token

        print("    Submitting statutory prohibitions checkbox ('prohibition_agreement=1')...")
        if USE_REQUESTS:
            post_resp = HTTP_SESSION.post(resolved_url, data=payload, headers=post_headers, timeout=30)
            if post_resp.status_code in (200, 302):
                print("    [OK] Successfully accepted agreement! Senate session is authorized.")
                return True
        else:
            post_data = urllib.parse.urlencode(payload).encode("utf-8")
            post_req = urllib.request.Request(resolved_url, data=post_data, headers={**HEADERS, **post_headers})
            with urllib.request.urlopen(post_req, timeout=30) as resp:
                print("    [OK] Accepted agreement via urllib!")
                return True

    except Exception as e:
        print(f"    [!] Error passing agreement gate: {e}")
        return False

    return False


def navigate_to_senate_search_page(search_url: str, cfg: dict) -> dict:
    """Step 2: Navigate to Senate search page and parse checkboxes for Annual & Periodic."""
    resolved_search_url = resolve_template(search_url, cfg=cfg)
    print(f"\n[*] Step 2: Navigating to Senate search page...")
    print(f"    URL: {resolved_search_url}")

    search_meta = {
        "report_type_params": [],
        "date_from_param": "submitted_start_date",
        "date_to_param": "submitted_end_date",
        "search_page_url": resolved_search_url,
    }

    try:
        content = http_get(resolved_search_url)
        html = content.decode("utf-8", errors="ignore")

        checkbox_regex = re.compile(r'<input\s+([^>]*type=["\']checkbox["\'][^>]*)>(.*?)(?=<input|</form|<div class=["\']row)', re.IGNORECASE | re.DOTALL)
        for match in checkbox_regex.finditer(html):
            tag_attrs = match.group(1)
            trailing_text = match.group(2)

            name_m = re.search(r'name=["\']([^"\']+)["\']', tag_attrs)
            val_m = re.search(r'value=["\']([^"\']+)["\']', tag_attrs)
            id_m = re.search(r'id=["\']([^"\']+)["\']', tag_attrs)

            name = name_m.group(1) if name_m else "report_type"
            val = val_m.group(1) if val_m else "1"
            elem_id = id_m.group(1) if id_m else ""

            label_text = trailing_text
            if elem_id:
                label_m = re.search(rf'<label[^>]*for=["\']{re.escape(elem_id)}["\'][^>]*>(.*?)</label>', html, re.IGNORECASE | re.DOTALL)
                if label_m:
                    label_text += " " + label_m.group(1)

            label_clean = re.sub(r'<[^>]+>', ' ', label_text).strip().lower()

            if "annual" in label_clean:
                search_meta["report_type_params"].append((name, val, "Annual"))
            elif "periodic" in label_clean or "ptr" in label_clean:
                search_meta["report_type_params"].append((name, val, "Periodic Transactions"))

        if re.search(r'name=["\'](submitted_start_date|start_date)["\']', html, re.IGNORECASE):
            m = re.search(r'name=["\'](submitted_start_date|start_date)["\']', html, re.IGNORECASE)
            search_meta["date_from_param"] = m.group(1)

        if re.search(r'name=["\'](submitted_end_date|end_date)["\']', html, re.IGNORECASE):
            m = re.search(r'name=["\'](submitted_end_date|end_date)["\']', html, re.IGNORECASE)
            search_meta["date_to_param"] = m.group(1)

        print("    [OK] Search page loaded and CSRF session updated.")
        if search_meta["report_type_params"]:
            types_found = [t[2] for t in search_meta["report_type_params"]]
            print(f"    Selected Report Types in form: {', '.join(types_found)}")
        else:
            print("    Configuring standard report types: Annual, Periodic Transactions")

    except Exception as e:
        print(f"    [!] Warning navigating to search page: {e}")

    return search_meta


def fetch_senate_filings(search_data_url: str, start_date: str, end_date: str, search_meta: dict, cfg: dict) -> list:
    """Step 3: Query DataTables API with Annual & Periodic filters and dynamic date range."""
    resolved_search_url = resolve_template(search_data_url, cfg=cfg)
    search_page_url = search_meta.get("search_page_url", resolve_template(cfg["SEARCH_URL"], cfg=cfg))

    print(f"\n[*] Step 3: Querying Senate filing records...")
    print(f"    Endpoint           : {resolved_search_url}")
    print(f"    Date Filed (Start) : {start_date} (Jan 1, {cfg['YEAR']})")
    print(f"    Date Filed (End)   : {end_date} (Current Run Date)")
    print(f"    Selected Types     : Annual, Periodic Transactions")

    filings = []
    start = 0
    length = 100
    draw = 1

    csrf_token = ""
    if USE_REQUESTS:
        csrf_token = HTTP_SESSION.cookies.get("csrftoken", "")

    post_headers = {
        "User-Agent": cfg["USER_AGENT"],
        "Referer": search_page_url,
        "Origin": cfg["BASE_URL"],
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    if csrf_token:
        post_headers["X-CSRFToken"] = csrf_token

    while True:
        payload_tuples = [
            ("draw", str(draw)),
            ("start", str(start)),
            ("length", str(length)),
            ("search[value]", ""),
            ("search[regex]", "false"),
            ("submitted_start_date", f"{start_date} 00:00:00"),
            ("submitted_end_date", f"{end_date} 23:59:59"),
            ("start_date", start_date),
            ("end_date", end_date),
        ]

        if search_meta.get("report_type_params"):
            for name, val, _ in search_meta["report_type_params"]:
                payload_tuples.append((name, val))
                payload_tuples.append(("report_types[]", val))
                payload_tuples.append(("report_type[]", val))
        else:
            for code in ("7", "11", "annual", "periodic"):
                payload_tuples.append(("report_types[]", code))
                payload_tuples.append(("report_type[]", code))

        try:
            if USE_REQUESTS:
                resp = HTTP_SESSION.post(resolved_search_url, data=payload_tuples, headers=post_headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            else:
                encoded = urllib.parse.urlencode(payload_tuples).encode("utf-8")
                req = urllib.request.Request(resolved_search_url, data=encoded, headers={**HEADERS, **post_headers})
                with urllib.request.urlopen(req, timeout=30) as r:
                    import json
                    data = json.loads(r.read().decode("utf-8"))

            rows = data.get("data", [])
            if not rows:
                break

            total_records = data.get("recordsFiltered", data.get("recordsTotal", len(rows)))

            for row in rows:
                if len(row) < 4:
                    continue

                first = re.sub(r'<[^>]+>', '', str(row[0])).strip()
                last = re.sub(r'<[^>]+>', '', str(row[1])).strip()
                report_html = str(row[3])
                filing_date = re.sub(r'<[^>]+>', '', str(row[4])).strip() if len(row) > 4 else ""

                href_match = re.search(r'href=["\']([^"\']+)["\']', report_html)
                if not href_match:
                    continue
                href = href_match.group(1).strip()
                report_url = urllib.parse.urljoin(cfg["BASE_URL"], href)
                doc_id = sanitize_doc_id(href.rstrip('/').split('/')[-1])

                report_text = re.sub(r'<[^>]+>', '', report_html).strip()
                rep_lower = report_text.lower()
                if "periodic" in rep_lower or "ptr" in rep_lower or "transaction" in rep_lower:
                    filing_type = "P"
                elif "annual" in rep_lower:
                    filing_type = "O"
                elif "amend" in rep_lower:
                    filing_type = "A"
                elif "candidate" in rep_lower:
                    filing_type = "C"
                elif "termination" in rep_lower:
                    filing_type = "T"
                else:
                    filing_type = "Z"

                filings.append({
                    "doc_id": doc_id,
                    "first": first,
                    "last": last,
                    "filing_type": filing_type,
                    "report_title": report_text,
                    "year": cfg["YEAR"],
                    "filing_date": filing_date,
                    "url": report_url,
                })

            print(f"    Fetched {len(filings)} of {total_records} filings...")

            if len(filings) >= total_records:
                break
            if cfg["MAX_DOWNLOADS"] > 0 and len(filings) >= cfg["MAX_DOWNLOADS"]:
                break

            start += length
            draw += 1
            time.sleep(0.2)

        except Exception as e:
            print(f"    [!] Error querying Senate search endpoint: {e}")
            break

    print(f"    Found {len(filings)} matching Senate filings from {start_date} to {end_date}.")
    return filings


# ==============================================================================
# HOUSE PIPELINE: BULK ZIP ARCHIVE & XML INDEX
# ==============================================================================

def download_and_extract_zip(year: str, base_dir: Path, cfg: dict) -> Path:
    """Download bulk ZIP archive and extract the filings XML index (House)."""
    year_dir = base_dir / year
    year_dir.mkdir(parents=True, exist_ok=True)

    zip_filename = resolve_template(cfg["ZIP_FILENAME_TEMPLATE"], cfg=cfg)
    zip_path = year_dir / zip_filename

    if not cfg["FORCE_DOWNLOAD"] and zip_path.exists() and zip_path.stat().st_size > 0:
        print(f"[*] ZIP archive already exists locally: {zip_path.name} (skipping download)")
    else:
        urls_to_try = [
            resolve_template(tpl.strip(), cfg=cfg)
            for tplpl in [cfg["ZIP_URL_TEMPLATES"]]
            for tpl in tplpl.split(",")
            if tpl.strip()
        ]

        if not urls_to_try:
            print("[!] Error: No ZIP_URL_TEMPLATES configured in env.")
            sys.exit(1)

        print(f"[*] Downloading {cfg['CHAMBER']} disclosures ZIP archive for {year}...")
        downloaded = False

        for url in urls_to_try:
            try:
                print(f"    Fetching: {url}")
                data = http_get(url)
                with open(zip_path, "wb") as f:
                    f.write(data)
                print(f"    Saved ZIP to: {zip_path} ({len(data):,} bytes)")
                downloaded = True
                break
            except Exception as e:
                print(f"    Attempt failed ({url}): {e}")

        if not downloaded:
            print(f"\n[!] Error: Unable to download ZIP archive for {cfg['CHAMBER']}.")
            if cfg["PORTAL_URL"]:
                print(f"    Verify archive availability at: {cfg['PORTAL_URL']}")
            sys.exit(1)

    with zipfile.ZipFile(zip_path, "r") as z:
        xml_entries = [name for name in z.namelist() if name.lower().endswith(".xml")]
        if not xml_entries:
            raise FileNotFoundError(f"No XML file found inside archive: {zip_path}")

        xml_name = xml_entries[0]
        extracted_xml_path = year_dir / xml_name

        if not cfg["FORCE_DOWNLOAD"] and extracted_xml_path.exists() and extracted_xml_path.stat().st_size > 0:
            print(f"[*] XML index already exists: {extracted_xml_path.name} (skipping extraction)")
        else:
            print(f"[*] Extracting XML index from {zip_path.name}...")
            z.extract(xml_name, path=year_dir)
            print(f"    Extracted: {extracted_xml_path}")

    return extracted_xml_path


def parse_filings_xml(xml_path: Path, default_year: str) -> list:
    """Parse the XML index file to retrieve filing records (House)."""
    print(f"[*] Parsing XML index: {xml_path.name}...")
    tree = ET.parse(xml_path)
    root = tree.getroot()

    filings = []
    record_tags = {"member", "senator", "filing", "record", "row"}

    for elem in root.iter():
        clean_tag = elem.tag.split("}")[-1].lower()
        if clean_tag not in record_tags:
            continue

        doc_id = get_xml_tag_text(elem, ["DocID", "doc_id", "DocId", "ReportID", "report_id", "Id", "id"])
        if not doc_id:
            continue
        doc_id = sanitize_doc_id(doc_id)

        first = get_xml_tag_text(elem, ["First", "first", "FirstName", "first_name"])
        last = get_xml_tag_text(elem, ["Last", "last", "LastName", "last_name"])
        filing_type = get_xml_tag_text(elem, ["FilingType", "filing_type", "ReportType", "report_type", "Type", "type"], default="P").upper()
        filing_year = get_xml_tag_text(elem, ["Year", "year", "FilingYear", "filing_year"], default=default_year)
        filing_date = get_xml_tag_text(elem, ["FilingDate", "filing_date", "Date", "date", "ReceivedDate"])
        state_dst = get_xml_tag_text(elem, ["StateDst", "state_dst", "State", "state"])

        filings.append({
            "doc_id": doc_id,
            "first": first,
            "last": last,
            "filing_type": filing_type,
            "year": filing_year,
            "filing_date": filing_date,
            "state_dst": state_dst,
        })

    print(f"    Found {len(filings)} total filing records in the XML index.")
    return filings


# ==============================================================================
# DOWNLOAD PDF / REPORT FILING
# ==============================================================================

def download_filing_pdf(filing: dict, base_dir: Path, year: str, cfg: dict) -> str:
    """Download an individual filing report into target external folder."""
    doc_id = sanitize_doc_id(filing["doc_id"])
    filing_type = filing["filing_type"]
    month_filed = extract_filing_month(filing["filing_date"], cfg["MONTH_FORMAT"])
    rep_name = format_rep_name(filing["first"], filing["last"], cfg["REP_NAME_FORMAT"])

    rep_folder = base_dir / year / month_filed / rep_name
    try:
        rep_folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"    [FAIL] Cannot create directory {rep_folder}: {exc}")
        return "FAILED"

    pdf_path = rep_folder / f"{doc_id}.pdf"
    html_path = rep_folder / f"{doc_id}.html"

    if not cfg["FORCE_DOWNLOAD"]:
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            print(f"    [SKIP] Already exists: {month_filed}/{rep_name}/{doc_id}.pdf")
            return "SKIPPED"
        if html_path.exists() and html_path.stat().st_size > 0:
            print(f"    [SKIP] Already exists: {month_filed}/{rep_name}/{doc_id}.html")
            return "SKIPPED"

    urls_to_try = []

    if filing.get("url"):
        urls_to_try.append(filing["url"])

    ptr_url = resolve_template(cfg["PTR_PDF_URL_TEMPLATE"], cfg=cfg, doc_id=doc_id) if cfg["PTR_PDF_URL_TEMPLATE"] else ""
    fin_url = resolve_template(cfg["FINANCIAL_PDF_URL_TEMPLATE"], cfg=cfg, doc_id=doc_id) if cfg["FINANCIAL_PDF_URL_TEMPLATE"] else ""

    if filing_type == "P":
        candidates = [ptr_url, fin_url]
    else:
        candidates = [fin_url, ptr_url]

    for u in candidates:
        if u and u not in urls_to_try:
            urls_to_try.append(u)

    for url in urls_to_try:
        try:
            content = http_get(url)

            if content.startswith(b"%PDF"):
                with open(pdf_path, "wb") as f:
                    f.write(content)
                print(f"    [OK] Downloaded PDF: {month_filed}/{rep_name}/{doc_id}.pdf ({len(content):,} bytes)")
                return "DOWNLOADED"

            elif b"<html" in content[:300].lower() or b"<!doctype html" in content[:300].lower():
                html_str = content.decode("utf-8", errors="ignore")
                embedded_pdf = re.search(r'href=["\']([^"\']+\.pdf)["\']', html_str, re.IGNORECASE)
                if embedded_pdf:
                    nested_pdf_url = urllib.parse.urljoin(url, embedded_pdf.group(1))
                    pdf_data = http_get(nested_pdf_url)
                    if pdf_data.startswith(b"%PDF"):
                        with open(pdf_path, "wb") as f:
                            f.write(pdf_data)
                        print(f"    [OK] Downloaded Embedded PDF: {month_filed}/{rep_name}/{doc_id}.pdf ({len(pdf_data):,} bytes)")
                        return "DOWNLOADED"

                with open(html_path, "wb") as f:
                    f.write(content)
                print(f"    [OK] Downloaded Electronic Report (HTML): {month_filed}/{rep_name}/{doc_id}.html ({len(content):,} bytes)")
                return "DOWNLOADED"

        except Exception:
            continue

    print(f"    [FAIL] Could not retrieve filing for DocID {doc_id} ({month_filed}/{rep_name})")
    return "FAILED"


# ==============================================================================
# PIPELINE EXECUTION (CLI & MICROSERVICE COMPATIBLE)
# ==============================================================================

def _discover_filings(
    chamber: str = None,
    env_file_path: Path = None,
    year: str = None,
    force_download: bool = None,
):
    """Load configuration and discover candidate filings without downloading.

    Returns ``(cfg, base_output_dir, filings)``. ``filings`` is the filtered list
    of candidate records (filing-type filter applied) but is **not** truncated by
    the download limit — callers decide how many *new* downloads to queue.
    """
    if env_file_path:
        load_env_variables(Path(env_file_path))

    cfg = get_config()

    # Apply runtime overrides if passed
    if chamber:
        cfg["CHAMBER"] = "Senate" if chamber.lower() in ("senate", "sen") else "House of Representatives"
        cfg["OUTPUT_DIR"] = "senate" if chamber.lower() in ("senate", "sen") else "house_rep"
    if year:
        cfg["YEAR"] = str(year)
    if force_download is not None:
        cfg["FORCE_DOWNLOAD"] = bool(force_download)

    base_output_dir = get_base_output_dir(cfg["OUTPUT_DIR"])

    filings = []

    # SENATE
    if cfg["CHAMBER"].lower() == "senate" or cfg["AUTO_ACCEPT_AGREEMENT"]:
        if cfg["AGREEMENT_URL"]:
            bypass_senate_agreement_gate(cfg["AGREEMENT_URL"], cfg)

        search_meta = navigate_to_senate_search_page(cfg["SEARCH_URL"], cfg)

        start_date = cfg["START_DATE_CONF"].replace("{year}", cfg["YEAR"])
        if not re.match(r'^\d{2}/\d{2}/\d{4}$', start_date):
            start_date = f"01/01/{cfg['YEAR']}"

        if cfg["END_DATE_CONF"].upper() in ("TODAY", "CURRENT", ""):
            end_date = datetime.now().strftime("%m/%d/%Y")
        else:
            end_date = cfg["END_DATE_CONF"].replace("{year}", cfg["YEAR"])

        if cfg["SEARCH_DATA_URL"]:
            filings = fetch_senate_filings(cfg["SEARCH_DATA_URL"], start_date, end_date, search_meta, cfg)

    # HOUSE
    else:
        xml_path = download_and_extract_zip(cfg["YEAR"], base_output_dir, cfg)
        filings = parse_filings_xml(xml_path, cfg["YEAR"])

    if cfg["FILING_TYPES"] != "ALL":
        allowed_types = {t.strip(" \t'\"{}[]()").upper() for t in cfg["FILING_TYPES"].split(",") if t.strip(" \t'\"{}[]()")}
        filings = [f for f in filings if f["filing_type"] in allowed_types]
        print(f"[*] Filtered down to {len(filings)} records matching types: {allowed_types}")

    return cfg, base_output_dir, filings


def _existing_filing_path(filing: dict, base_dir: Path, year: str, cfg: dict):
    """Return the existing PDF/HTML path for a filing, or ``None`` if absent."""
    doc_id = sanitize_doc_id(filing["doc_id"])
    month_filed = extract_filing_month(filing["filing_date"], cfg["MONTH_FORMAT"])
    rep_name = format_rep_name(filing["first"], filing["last"], cfg["REP_NAME_FORMAT"])
    rep_folder = base_dir / year / month_filed / rep_name
    pdf_path = rep_folder / f"{doc_id}.pdf"
    html_path = rep_folder / f"{doc_id}.html"
    if pdf_path.exists() and pdf_path.stat().st_size > 0:
        return pdf_path
    if html_path.exists() and html_path.stat().st_size > 0:
        return html_path
    return None


def build_download_queue(
    chamber: str = None,
    env_file_path: Path = None,
    year: str = None,
    max_downloads: int = None,
    force_download: bool = None,
) -> dict:
    """Discover candidates and select up to ``max_downloads`` *unprocessed* filings.

    ``max_downloads`` is the maximum number of **new** downloads to queue, not the
    number of candidates inspected. Existing PDF/HTML files are skipped (unless
    ``force_download`` is true) and do not count toward the limit. ``0`` means
    "queue every unprocessed candidate".

    Returns a dict with the resolved ``cfg``, ``base_output_dir``, the ``queue``
    of filing records to download, and scan counters.
    """
    cfg, base_output_dir, filings = _discover_filings(
        chamber=chamber,
        env_file_path=env_file_path,
        year=year,
        force_download=force_download,
    )

    # An explicit ``max_downloads`` (including 0 = "all") overrides the env value.
    if max_downloads is not None:
        cfg["MAX_DOWNLOADS"] = int(max_downloads)
    limit = int(cfg["MAX_DOWNLOADS"] or 0)
    force = bool(cfg["FORCE_DOWNLOAD"])

    total_candidates_scanned = 0
    skipped_already_downloaded = 0
    queue = []

    for filing in filings:
        total_candidates_scanned += 1
        if not force and _existing_filing_path(
            filing, base_output_dir, cfg["YEAR"], cfg
        ):
            skipped_already_downloaded += 1
            continue
        queue.append(filing)
        if limit > 0 and len(queue) >= limit:
            break

    return {
        "cfg": cfg,
        "base_output_dir": base_output_dir,
        "queue": queue,
        "total_candidates_scanned": total_candidates_scanned,
        "skipped_already_downloaded": skipped_already_downloaded,
        "queued_for_download": len(queue),
    }


def process_download_queue(
    queue: list,
    base_output_dir: Path,
    year: str,
    cfg: dict,
) -> dict:
    """Download every filing in ``queue`` and return per-outcome counters.

    The returned dict contains the aggregate counters (``DOWNLOADED``,
    ``SKIPPED``, ``FAILED``) plus an ``items`` list with one entry per filing:
    ``{"doc_id", "file_path", "status", "detail"}``. Callers can persist the
    ``items`` list to expose per-file results in the status API.
    """
    stats = {"DOWNLOADED": 0, "SKIPPED": 0, "FAILED": 0, "items": []}

    # Pre-flight: verify the target year directory is writable so a systemic
    # permission problem fails fast with a clear message instead of logging one
    # error per filing.
    year_dir = base_output_dir / year
    try:
        year_dir.mkdir(parents=True, exist_ok=True)
        probe = year_dir / ".write_probe"
        probe.touch()
        probe.unlink()
    except OSError as exc:
        print(f"[!] Output directory is not writable: {year_dir} ({exc})")
        print(
            "[!] Fix the volume permissions, e.g. "
            "`sudo chown -R 10001:10001 <host folder>` (the container runs as UID 10001)."
        )
        stats["FAILED"] = len(queue)
        for filing in queue:
            stats["items"].append(
                {
                    "doc_id": sanitize_doc_id(filing.get("doc_id", "")),
                    "file_path": None,
                    "status": "FAILED",
                    "detail": f"Output directory not writable: {year_dir} ({exc})",
                }
            )
        return stats

    for i, filing in enumerate(queue, start=1):
        full_name = f"{filing['first']} {filing['last']}".strip()
        month_filed = extract_filing_month(filing["filing_date"], cfg["MONTH_FORMAT"])
        rep_name = format_rep_name(filing["first"], filing["last"], cfg["REP_NAME_FORMAT"])
        print(f"\n[{i}/{len(queue)}] Member: {full_name} | Month: {month_filed} | DocID: {filing['doc_id']} | Type: {filing['filing_type']}")

        detail = None
        try:
            result = download_filing_pdf(filing, base_output_dir, year, cfg)
        except Exception as exc:  # keep going; record the failure
            print(f"    [FAIL] DocID {filing.get('doc_id')}: {exc}")
            result = "FAILED"
            detail = str(exc)
        stats[result] = stats.get(result, 0) + 1

        # Resolve the on-disk path for the per-file record (PDF preferred).
        doc_id = sanitize_doc_id(filing["doc_id"])
        rel_dir = f"{year}/{month_filed}/{rep_name}"
        pdf_path = base_output_dir / year / month_filed / rep_name / f"{doc_id}.pdf"
        html_path = base_output_dir / year / month_filed / rep_name / f"{doc_id}.html"
        if pdf_path.exists():
            file_path = f"{rel_dir}/{doc_id}.pdf"
        elif html_path.exists():
            file_path = f"{rel_dir}/{doc_id}.html"
        else:
            file_path = None
        stats["items"].append(
            {
                "doc_id": doc_id,
                "file_path": file_path,
                "status": result,
                "detail": detail,
            }
        )

        if result == "DOWNLOADED" and cfg["REQUEST_DELAY"] > 0 and i < len(queue):
            time.sleep(cfg["REQUEST_DELAY"])

    return stats


def run_pipeline(
    chamber: str = None,
    env_file_path: Path = None,
    year: str = None,
    max_downloads: int = None,
    force_download: bool = None
) -> dict:
    """Programmatic entrypoint to run House or Senate ingestion.

    ``max_downloads`` caps the number of **new** downloads (existing files are
    skipped and do not count toward the limit). ``0`` means "download all new
    candidates".
    """
    built = build_download_queue(
        chamber=chamber,
        env_file_path=env_file_path,
        year=year,
        max_downloads=max_downloads,
        force_download=force_download,
    )
    cfg = built["cfg"]
    base_output_dir = built["base_output_dir"]
    queue = built["queue"]

    print("=" * 70)
    print(f"   U.S. {cfg['CHAMBER']} Financial Disclosures Pipeline")
    print("=" * 70)
    print(f"Target Year        : {cfg['YEAR']}")
    print(f"Output Directory   : {base_output_dir.resolve()}/{cfg['YEAR']}/<month_filed>/<name>/")
    print(f"Base URL           : {cfg['BASE_URL']}")
    print(f"Month Format       : {cfg['MONTH_FORMAT']}")
    print(f"Filing Types Filter: {cfg['FILING_TYPES']}")
    print(f"Force Redownload   : {cfg['FORCE_DOWNLOAD']}")
    print(f"Max New Downloads  : {cfg['MAX_DOWNLOADS'] if cfg['MAX_DOWNLOADS'] > 0 else 'No limit (ALL)'}")
    print(f"Candidates Scanned : {built['total_candidates_scanned']}")
    print(f"Already Present    : {built['skipped_already_downloaded']} (skipped)")
    print(f"Queued for Download: {built['queued_for_download']}")
    print("=" * 70)

    if not queue:
        print(f"\n[*] No new filing records to process.")
        return {
            "status": "NO_RECORDS" if built["total_candidates_scanned"] == 0 else "SUCCESS",
            "chamber": cfg["CHAMBER"],
            "year": cfg["YEAR"],
            "total_candidates_scanned": built["total_candidates_scanned"],
            "skipped_already_downloaded": built["skipped_already_downloaded"],
            "queued_for_download": 0,
            "stats": {"DOWNLOADED": 0, "SKIPPED": 0, "FAILED": 0},
            "output_directory": str(base_output_dir.resolve()),
        }

    print(f"\n[*] Processing filings into '{base_output_dir.resolve()}/{cfg['YEAR']}/<month_filed>/<rep_name>/'...")
    stats = process_download_queue(queue, base_output_dir, cfg["YEAR"], cfg)

    print("\n" + "=" * 70)
    print("Finished Processing Filings:")
    print(f"  - Newly Downloaded : {stats['DOWNLOADED']}")
    print(f"  - Already Present  : {stats['SKIPPED']} (skipped)")
    print(f"  - Failed/Missing   : {stats['FAILED']}")
    print(f"  - Candidates Scanned: {built['total_candidates_scanned']}")
    print(f"  - Queued for Download: {built['queued_for_download']}")
    print(f"Files saved in       : {base_output_dir.resolve()}/{cfg['YEAR']}/")
    print("=" * 70)

    return {
        "status": "SUCCESS",
        "chamber": cfg["CHAMBER"],
        "year": cfg["YEAR"],
        "total_candidates_scanned": built["total_candidates_scanned"],
        "skipped_already_downloaded": built["skipped_already_downloaded"],
        "queued_for_download": built["queued_for_download"],
        "stats": stats,
        "output_directory": str(base_output_dir.resolve())
    }


def main():
    run_pipeline()


if __name__ == "__main__":
    main()
