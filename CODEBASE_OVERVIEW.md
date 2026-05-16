# Jobful Codebase Overview

This document explains the current Jobful codebase as it exists after local
verification of Phase 1 and Phase 2.

Jobful is currently a Python data-ingestion pipeline. It pulls job listings
directly from company career systems, normalizes them into strict Pydantic
models, and can run either as a manual CLI puller or as an autonomous
Redis/Celery queue system.

## Current Status

Phase 1, ATS routing and extraction, is locally verified.

- Full default pull: 119 sources
- Successful sources: 119
- Failed sources: 0
- Validated jobs: 16,668

Phase 2, Redis/Celery orchestration, is locally verified.

- Redis runs through Docker Compose
- Celery workers consume extraction tasks
- Celery Beat schedules queue batches
- Priority queues and enqueue locks work
- Dead-letter recording exists
- Queue status inspection exists
- Tests pass with `python -m unittest discover -s tests`

The system is not production-deployed yet. The intended next move is to keep
building the full local stack in a deployment-shaped way: Redis, Postgres,
workers, API, and frontend.

## High-Level Flow

```text
Career URL
  -> AtsRouter
  -> Provider-specific extractor
  -> JobListing models
  -> PullResult JSON artifact or Celery task result
```

For Phase 2:

```text
Celery Beat or phase2.py
  -> Redis queue
  -> Celery worker
  -> main.extract_single_url(...)
  -> AtsRouter
  -> extractor
  -> serialized jobs / failure record
```

The important design choice is that the manual CLI and Celery workers share the
same extraction path. `main.py` is still the source of truth for extracting a
single URL or a batch of URLs.

## Main Entry Points

### `main.py`

Manual Phase 1 puller.

Responsibilities:

- Reads career URLs from CLI args, input files, or `DEFAULT_CAREER_URLS`
- Deduplicates URLs
- Runs extraction concurrently with `ThreadPoolExecutor`
- Converts each URL into either jobs or a structured failure
- Writes a JSON artifact under `outputs/`

Useful commands:

```powershell
python main.py
python main.py https://boards.greenhouse.io/airbnb -o outputs/custom_pull.json
python main.py --input-file sources_user_requested_companies_expanded.txt --workers 12 --timeout 8
```

Important functions:

- `extract_urls(...)`: batch extraction
- `extract_single_url(...)`: one source URL through router/extractor
- `dedupe_urls(...)`: trims, removes blank/commented/duplicate URLs
- `write_result(...)`: writes a `PullResult` JSON artifact

### `phase2.py`

Manual Phase 2 enqueue CLI.

Responsibilities:

- Submits URLs into Celery instead of extracting them directly
- Supports default sources, input files, and one-off URLs
- Can force a queue with `--queue`
- Can preview queue decisions with `--dry-run`
- Can bypass enqueue locks with `--no-locks`

Useful commands:

```powershell
python phase2.py --include-defaults --dry-run
python phase2.py https://boards.greenhouse.io/airbnb --queue jobful:high
python phase2.py --input-file sources_user_requested_companies_expanded.txt
```

### `phase2_status.py`

Queue and failure monitor.

Responsibilities:

- Reads Redis queue depth for `jobful:high`, `jobful:standard`,
  `jobful:slow`, and `jobful:dead_letter`
- Shows recent dead letters from Redis or `outputs/dead_letters.jsonl`

Useful command:

```powershell
python phase2_status.py
```

## Data Models

### `models.py`

Defines the strict schemas used by the rest of the pipeline.

`JobListing` is the normalized output every extractor must produce. Key fields:

- `company_name`
- `job_title`
- `job_url`
- `ats_provider`
- `ats_job_id`
- `location`
- `raw_description`
- `description_html`
- `employment_type`
- `departments`
- `date_posted`
- `content_hash`
- `extracted_at`

`AtsProvider` currently allows:

- `greenhouse`
- `lever`
- `ashby`
- `workday`
- `amazon`
- `google`
- `apple`
- `oracle`
- `talentbrew`
- `avature`

`PullResult` is the full output artifact for a manual pull. It contains run
metadata, per-source results, all jobs, and failures.

`PullFailure` and `PullSourceResult` make failures explicit instead of letting
bad sources disappear silently.

## Routing

### `router.py`

`AtsRouter` detects which provider owns a career URL and returns an `AtsRoute`.

An `AtsRoute` contains:

- `provider`
- `board_token`
- `extractor_class`
- `source_url`

Examples:

```text
https://boards.greenhouse.io/airbnb -> GreenhouseExtractor, token airbnb
https://jobs.lever.co/Flex -> LeverExtractor, token Flex
https://jobs.ashbyhq.com/ashby -> AshbyExtractor, token ashby
```

`AtsRouter.extract(url)` routes and immediately extracts.

`AtsRouter.detect_only(url)` routes without extracting. This is useful for
future company ingestion workflows where a URL needs provider metadata before
being scheduled.

## Extractors

All extractors live in `extractors/`.

### `extractors/base.py`

Defines `BaseExtractor`, shared request behavior, error types, retry behavior,
user-agent rotation, proxy integration, date parsing, content hash generation,
and `JobListing` construction.

Important behavior:

- HTTP requests use timeouts
- User-Agent rotates per request
- `404` becomes `InvalidBoardError`
- `403` becomes `ForbiddenError`
- `429` becomes `RateLimitedError`
- `5xx` responses retry
- `403` and `429` mark the current proxy as banned when proxy rotation is used
- `content_hash` is SHA-256 of `job_title|company_name|ats_job_id`

Extractor implementations call `_build_listing(...)` so schema creation stays
consistent.

### `extractors/greenhouse.py`

Uses the Greenhouse public board API:

```text
https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
```

Maps Greenhouse jobs into `JobListing`, including:

- title
- absolute job URL
- location
- departments
- HTML description
- text description
- updated timestamp as `date_posted`

### `extractors/lever.py`

Uses Lever postings API:

```text
https://api.lever.co/v0/postings/{board_token}?mode=json&limit=250&offset=...
```

Handles pagination with offsets, dedupes repeated job IDs, and maps Lever
categories into location, employment type, and departments.

### `extractors/ashby.py`

Uses Ashby posting API:

```text
https://api.ashbyhq.com/posting-api/job-board/{board_token}
```

Skips jobs where `isListed` is explicitly `False`, extracts company name from
the payload when available, and maps Ashby fields into the shared schema.

### `extractors/workday.py`

Supports Workday CXS APIs. It first attempts direct Workday CXS calls and falls
back to Playwright response collection if direct access is blocked.

This extractor is heavier than Greenhouse/Lever/Ashby and may need browser
dependencies installed:

```powershell
python -m playwright install chromium
```

### Company and platform-specific extractors

These handle boards that do not fit the common ATS patterns cleanly:

- `extractors/amazon.py`
- `extractors/apple.py`
- `extractors/google.py`
- `extractors/oracle.py`
- `extractors/talentbrew.py`
- `extractors/avature.py`

These are the right place to keep adding custom extractors for companies whose
career sites need special handling.

### `extractors/text.py`

Contains HTML/text cleanup helpers used by extractors when turning HTML job
descriptions into `raw_description`.

## Source Lists

### `sources.py`

Defines `DEFAULT_CAREER_URLS`, the main seed list used by `python main.py` and
Phase 2 default enqueue tasks.

### Additional source text files

The root-level `sources_*.txt` files are curated or discovered URL lists. They
are not automatically loaded unless passed with `--input-file`.

Examples:

- `sources_fortune_tech.txt`
- `sources_fortune_plus_quant.txt`
- `sources_finance_quant_expansion.txt`
- `sources_top_companies_expanded_candidates.txt`
- `sources_user_requested_company_targets.txt`
- `sources_user_requested_companies_expanded.txt`

Use them like:

```powershell
python main.py --input-file sources_user_requested_companies_expanded.txt
python phase2.py --input-file sources_user_requested_companies_expanded.txt
```

## Phase 2 Orchestration

### `celery_app.py`

Creates the Celery app.

Environment variables:

- `JOBFUL_REDIS_URL`: broker URL, defaults to `redis://localhost:6379/0`
- `JOBFUL_CELERY_RESULT_BACKEND`: result backend, defaults to the Redis URL

### `celeryconfig.py`

Celery settings:

- JSON task serialization
- Redis result expiry of one hour
- late task acknowledgements
- worker prefetch of one
- queue definitions
- Beat schedules

Queues:

- `jobful:high`
- `jobful:standard`
- `jobful:slow`
- `jobful:dead_letter`

Beat cadence defaults:

- high priority: hourly
- standard: every four hours
- slow: every twelve hours

Smoke-test overrides:

- `JOBFUL_BEAT_HIGH_SECONDS`
- `JOBFUL_BEAT_STANDARD_SECONDS`
- `JOBFUL_BEAT_SLOW_SECONDS`

### `queueing.py`

Defines queue names, queue selection logic, and exponential backoff.

`choose_queue(...)` uses URL markers to route:

- high-priority companies to `jobful:high`
- Ashby/Workday-heavy sources to `jobful:slow`
- everything else to `jobful:standard`

`get_backoff_delay(...)` implements exponential backoff with jitter.

### `tasks.py`

Defines Celery tasks.

Tasks:

- `jobful.extract_source`
- `jobful.enqueue_urls`
- `jobful.enqueue_default_sources`
- `jobful.record_dead_letter`

`extract_source(...)` calls `main.extract_single_url(...)`, then returns
serialized jobs, source metadata, and optional failure metadata.

Retryable failures are retried up to three times with exponential backoff. If
retries are exhausted, the failure is sent to the dead-letter task.

`enqueue_urls(...)` dedupes URLs, chooses the queue, optionally uses Redis
enqueue locks, and submits extraction tasks.

Enqueue lock TTLs match queue cadence:

- high: 1 hour
- standard: 4 hours
- slow: 12 hours

Dead letters are written to:

- `outputs/dead_letters.jsonl`
- Redis list `jobful:dead_letters`

### `docker-compose.yml`

Runs local Redis:

```powershell
docker compose up -d redis
```

Redis is exposed on localhost port `6379` and persists data in the
`redis-data` Docker volume.

## Proxy Rotation

### `proxy.py`

Loads optional proxy configuration and rotates proxies per request.

Environment variables:

- `JOBFUL_PROXY_URLS`: comma-separated proxy URLs
- `JOBFUL_PROXY_FILE`: newline-delimited proxy file

Example:

```powershell
$env:JOBFUL_PROXY_URLS = "http://user:pass@proxy1:8000,http://user:pass@proxy2:8000"
```

When an extractor sees `403` or `429`, the current proxy is marked banned in
Redis for 24 hours using:

```text
proxy:{proxy_url}:banned
```

If all configured proxies are banned or Redis is unavailable, the extractor
falls back to no proxy rather than crashing before making a request.

## Scripts

The `scripts/` directory contains discovery and maintenance utilities. These
are helper scripts, not the core runtime.

Common categories:

- Source discovery: `discover_ats_sources.py`, `inspect_career_page.py`
- URL probing: `probe_urls.py`, `search_url_terms.py`, `search_js_bundles.py`
- Output merging: `merge_job_outputs.py`, `combine_job_outputs.py`
- Debugging specific boards: `debug_talentbrew_pages.py`

Use these when expanding source coverage or investigating companies that do not
route cleanly through existing extractors.

## Tests

Tests live in `tests/`.

Current coverage focuses on Phase 2 support code:

- queue classification
- backoff behavior
- router `detect_only`
- proxy env parsing
- dry-run CLI behavior
- dead-letter JSONL writing

Run tests:

```powershell
python -m unittest discover -s tests
```

## Running The Local Stack

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start Redis:

```powershell
docker compose up -d redis
```

Run a worker on Windows:

```powershell
python -m celery -A celery_app worker -P solo -Q jobful:high,jobful:standard,jobful:slow,jobful:dead_letter --loglevel=INFO
```

Run Beat:

```powershell
python -m celery -A celery_app beat --loglevel=INFO
```

Enqueue work:

```powershell
python phase2.py https://boards.greenhouse.io/airbnb --queue jobful:high
```

Inspect status:

```powershell
python phase2_status.py
```

Stop Redis:

```powershell
docker compose down
```

## Verified Commands

These commands were used to verify the current local state:

```powershell
python main.py -o outputs/full_default_confirmation.json --workers 12 --timeout 8
python -m unittest discover -s tests
docker compose exec redis redis-cli ping
python phase2_status.py
```

Phase 2 was also verified with:

- a Celery Beat high-priority schedule smoke test
- an explicit 25-source Celery batch
- final queue depth check showing all queues empty
- no real dead letters

## What Comes Next

The next major phase is local Phase 3:

- clean raw descriptions
- normalize eligibility fields
- infer program type
- extract graduation year requirements
- extract visa sponsorship signals
- deduplicate against a persistent store

Before deploying, the project should add local Postgres and write extracted
jobs into database tables instead of relying on JSON artifacts and Celery task
results. The local stack should eventually become:

```text
Redis
Postgres
Celery Beat
Celery Worker
FastAPI backend
Frontend
```

Once that works locally, production deployment becomes a matter of moving the
always-on services to a VPS or managed platform.
