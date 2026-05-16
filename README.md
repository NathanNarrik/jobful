# Project Jobful: System Architecture & Implementation Plan

## 1. The Ultimate Goal & Philosophy
**Jobful** is a unified, automated computer science application database. The current CS job hunting landscape is broken. Students are forced to rely on LinkedIn "ghost jobs," manual crowdsourced spreadsheets (like the Pitt CSC repo), or influencers who gatekeep newly opened positions for engagement. 

Jobful exists to democratize this data. It is built to cut through the noise for students who are balancing intense technical coursework—like digital logic, stats, and data structures—and don't have time to refresh company career pages 24/7. 

**Core Differentiators:**
1.  **Direct-to-Source:** We do not scrape LinkedIn or Indeed. We pull 24/7 directly from company Applicant Tracking Systems (ATS) to ensure 100% accuracy.
2.  **Academic Eligibility Mapping:** Jobful automatically categorizes roles by academic standing (e.g., Freshman/Sophomore STEP programs, Junior Summer 2026 Internships, New Grad roles). 
3.  **Anti-Auto-Apply (The Closed-Loop Tracker):** We are not an auto-filler. Users discover jobs on Jobful, click a direct link to the verified company portal to apply, and then manage their pipeline via a personalized, Kanban-style dashboard (Applied, Interviewing, Rejected, Accepted).

---

## 2. The Full Technical Architecture

Jobful is a highly automated data pipeline built primarily in Python, leveraging local hardware capabilities to keep running costs at zero. 

*   **Phase 1: ATS API Routing & Extraction (Python).** Bypassing brittle HTML scraping by directly querying the hidden JSON endpoints of major ATS platforms (Greenhouse, Lever, Ashby). 
*   **Phase 2: Orchestration (Celery + Redis).** Distributing the scraping workload asynchronously to run 24/7 without IP bans or server lockups.
*   **Phase 3: The AI Normalization Engine.** The raw JSON strings extracted in Phase 1 will undergo robust text manipulation and string replacement to clean the data. This clean text is then passed to open-source NLP models—fine-tuned and running locally on an AM5 rig—to automatically extract hard-to-parse data points like "Visa Sponsorship" or "Required Graduation Year".
*   **Phase 4: Storage & Dashboard (PostgreSQL + FastAPI/React).** A fast backend serving the structured data to a visual frontend where users drag and drop application cards.

---

## 3. Phase 1 Specifications: The Extraction Layer

Your objective as the coding agent is to build Phase 1. You must build a highly modular Python application that takes a company's career page URL, identifies the underlying ATS, and extracts all active job listings into a standardized Pydantic data model.

### 3.1 Core Constraints
*   **Zero DOM Scraping (Where Possible):** Prioritize intercepting the backend JSON APIs. Do not use BeautifulSoup to parse HTML tags unless absolutely unavoidable. 
*   **Modularity:** Implement a Strategy or Factory pattern. A central router should inspect a URL and delegate to a specific provider class (e.g., `GreenhouseExtractor`).
*   **Strict Typing:** Use `pydantic` to enforce a rigid schema. Our downstream text manipulation scripts and local machine learning models will crash if the input schema is unpredictable.

### 3.2 Expected Data Schema (Pydantic)
Create a `JobListing` Pydantic model containing:
*   `company_name` (str)
*   `job_title` (str)
*   `job_url` (HttpUrl) - *The direct application link.*
*   `ats_provider` (str) - *"greenhouse", "lever", "ashby", or "workday"*
*   `ats_job_id` (str) - *Native ATS job identifier for deduplication.*
*   `location` (list[str])
*   `raw_description` (str) - *The complete, unformatted job description text.*
*   `description_html` (str | None)
*   `employment_type` (str | None)
*   `departments` (list[str])
*   `date_posted` (datetime | None)
*   `content_hash` (str) - *SHA-256 of title + company + ATS job ID.*
*   `extracted_at` (datetime)

### 3.3 The Target ATS Endpoints
Start by implementing extractors for:
1.  **Greenhouse:** API structure -> `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`.
2.  **Lever:** API structure -> `https://api.lever.co/v0/postings/{board_token}?mode=json`.
3.  **Ashby:** API structure -> `https://api.ashbyhq.com/posting-api/job-board/{board_token}`.
4.  **Workday:** API structure -> native CXS endpoints with Playwright browser fallback for blocked pages.

### 3.4 Implementation Steps
1.  **Models:** Define `JobListing` in `models.py`.
2.  **Extractors:** Create a `base_extractor.py` (abstract class), and implement `greenhouse.py`, `lever.py`, `ashby.py`, and `workday.py`. Handle API requests and map JSON to the Pydantic model.
3.  **Router:** Create `router.py` to parse URLs, extract the `board_token`, and trigger the right extractor.
4.  **Resilience:** Implement robust `try/except` blocks for network timeouts and unexpected schemas, utilizing Python's `logging` module.

---

## 4. Running the Phase 1 Puller

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Pull the default seed list and write an analysis artifact:

```bash
python main.py
```

The puller writes `outputs/jobful_pull_<timestamp>.json`, containing run metadata, per-source extraction results, validated `JobListing` records, and source-level failures for dead or changed ATS boards.

Pull custom URLs instead:

```bash
python main.py https://boards.greenhouse.io/airbnb https://jobs.lever.co/Flex -o outputs/custom_pull.json
```

Pull a newline-delimited URL file and merge it with the default seed list:

```bash
python main.py --input-file my_sources.txt --include-defaults --workers 12 --timeout 8
```

For the standard source and extractor growth workflow, see
[`ADDING_SOURCES_AND_EXTRACTORS.md`](ADDING_SOURCES_AND_EXTRACTORS.md).

The root command files are intentionally thin wrappers. The command
implementations live in `cli/`, while shared extraction, normalization, storage,
and API code live in `extractors/`, `normalizers/`, `db/`, and `api/`.

---

## 5. Running Phase 2 Orchestration

Phase 2 wraps the Phase 1 extractors in Redis-backed Celery queues. The manual
`main.py` puller still works; Celery workers call the same extraction path so
the CLI and the autonomous pipeline stay consistent.

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start Redis locally:

```bash
docker compose up -d redis
```

Run workers for each queue:

```bash
python -m celery -A celery_app worker -Q jobful:high,jobful:standard,jobful:slow --loglevel=INFO
```

On Windows, use Celery's solo pool:

```bash
python -m celery -A celery_app worker -P solo -Q jobful:high,jobful:standard,jobful:slow --loglevel=INFO
```

Start the beat scheduler in another terminal:

```bash
python -m celery -A celery_app beat --loglevel=INFO
```

For a quick local Beat smoke test, shorten one cadence temporarily:

```bash
$env:JOBFUL_BEAT_HIGH_SECONDS = "10"
python -m celery -A celery_app beat --loglevel=INFO --max-interval=5
```

Submit work manually:

```bash
python phase2.py --include-defaults --dry-run
python phase2.py --include-defaults
python phase2.py https://boards.greenhouse.io/airbnb --queue jobful:high
python phase2.py --input-file sources_user_requested_companies_expanded.txt
python phase2.py --include-defaults --no-locks
```

Inspect queue status and recent dead letters:

```bash
python phase2_status.py
```

Queue behavior:

* `jobful:high` handles major/high-priority companies on an hourly cadence.
* `jobful:standard` handles normal company boards every four hours.
* `jobful:slow` handles slower or browser-heavy sources every twelve hours.
* `jobful:dead_letter` records sources that still fail after retries.

Redis enqueue locks prevent Celery Beat from double-submitting the same company
inside its queue cadence. Use `--no-locks` only when intentionally replaying a
batch.

Dead letters are persisted to `outputs/dead_letters.jsonl` and mirrored into
Redis at `jobful:dead_letters` for quick status checks.

Use `JOBFUL_REDIS_URL` to point workers at a non-default Redis instance:

```bash
$env:JOBFUL_REDIS_URL = "redis://localhost:6379/0"
```

Optional proxy rotation is enabled through environment configuration. Provide
comma-separated URLs or a newline-delimited file:

```bash
$env:JOBFUL_PROXY_URLS = "http://user:pass@proxy1:8000,http://user:pass@proxy2:8000"
$env:JOBFUL_PROXY_FILE = "proxies.txt"
```

When a request through a proxy returns `403` or `429`, Jobful marks the proxy as
banned in Redis for 24 hours using the key pattern `proxy:{url}:banned`.

---

## 6. Running Phase 3 Normalization

Phase 3 turns raw extracted listings into structured eligibility metadata. It
cleans descriptions, deduplicates by content hash, extracts student-relevant
fields with deterministic heuristics, and can optionally call a local Ollama
model when `JOBFUL_USE_OLLAMA=true`. The practical default is hybrid mode:
heuristics run first, and Ollama is used for low-confidence or needs-review
records.

Normalize a Phase 1 pull artifact with heuristics only:

```bash
python phase3.py outputs/full_default_confirmation.json -o outputs/phase3_full_default_normalized.json --no-ollama
```

Normalize a smaller sample:

```bash
python phase3.py outputs/full_default_confirmation.json -o outputs/phase3_sample_500.json --limit 500 --no-ollama
```

Run hybrid mode with Ollama enabled:

```bash
$env:JOBFUL_USE_OLLAMA = "true"
$env:JOBFUL_OLLAMA_MODEL = "mistral"
python phase3.py outputs/full_default_confirmation.json -o outputs/phase3_hybrid_sample_25.json --limit 25
```

Force Ollama for every record in a tiny sample:

```bash
python phase3.py outputs/full_default_confirmation.json -o outputs/phase3_ollama_sample_1.json --limit 1 --ollama-mode all
```

Create CSV files for manual audit:

```bash
python phase3_audit.py outputs/phase3_full_default_normalized.json -o outputs/phase3_audit_sample_100.csv --sample-size 100
python phase3_audit.py outputs/phase3_full_default_normalized.json -o outputs/phase3_needs_review.csv --needs-review-only --sample-size 200
```

Optional Ollama configuration:

```bash
$env:JOBFUL_USE_OLLAMA = "true"
$env:JOBFUL_OLLAMA_MODEL = "mistral"
$env:JOBFUL_OLLAMA_URL = "http://localhost:11434/api/generate"
$env:JOBFUL_OLLAMA_TIMEOUT = "120"
$env:JOBFUL_OLLAMA_MAX_CHARS = "4000"
```

Check whether the configured local model can return valid normalization JSON:

```bash
python phase3_ollama_check.py
```

The normalized artifact contains each original `JobListing`, a
`cleaned_description`, and normalized fields:

* `program_type`
* `academic_levels`
* `degree_requirements`
* `required_grad_years`
* `visa_sponsorship`
* `visa_status`
* `required_skills`
* `nice_to_have_skills`
* `min_gpa`
* `clearance_required`
* `remote_type`
* `normalization_status`
* `confidence`
* `review_reasons`

---

## 7. Running Phase 4 Storage And API

Phase 4 persists normalized records in Postgres and serves read-only FastAPI
endpoints for the future frontend. The database uses companies and jobs tables,
dedupes jobs by unique `content_hash`, and indexes core filters such as skill,
location, academic level, graduation year, visa status, company, and recency.

Start Redis and Postgres:

```bash
docker compose up -d redis postgres
```

Apply the database schema:

```bash
python -m alembic upgrade head
```

Import the full Phase 3 normalized artifact:

```bash
python -m db.import_phase3 outputs/phase3_full_default_normalized.json
```

Re-running the same import updates existing rows instead of duplicating jobs:

```bash
python -m db.import_phase3 outputs/phase3_full_default_normalized.json
```

Run the API:

```bash
python -m uvicorn api.main:app --reload
```

Verify the core endpoints:

```bash
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod "http://localhost:8000/jobs?limit=5&skill=python"
Invoke-RestMethod http://localhost:8000/companies
Invoke-RestMethod http://localhost:8000/skills/popular
Invoke-RestMethod http://localhost:8000/stats
```

Useful maintenance command:

```bash
python -m db.mark_stale --older-than-hours 48
```

---

## 8. Running Phase 5 Frontend

Phase 5 adds the local Next.js frontend and personal application tracking
foundation. The design-source details are captured in
[`PHASE5_README.md`](PHASE5_README.md).

Run the API:

```bash
python -m uvicorn api.main:app --reload
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000/discover
http://localhost:3000/dashboard
```

Frontend checks:

```bash
cd frontend
npm run lint
npm run build
```
