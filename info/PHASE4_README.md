# Phase 4 Plan: Storage, Database, and Core API

Phase 4 should turn the current artifact-based pipeline into a database-backed
local application backend.

Phases 1-3 are already locally verified:

- Phase 1 extracts jobs into `JobListing` records.
- Phase 2 schedules and runs extraction with Redis/Celery.
- Phase 3 normalizes extracted jobs into `NormalizedJobRecord` records with
  student-relevant metadata.

Phase 4 should persist those normalized records in Postgres and expose them
through a FastAPI backend.

## Starting Point

The most important Phase 3 output is:

```powershell
outputs/phase3_full_default_normalized.json
```

That file contains a `NormalizationResult`:

```text
NormalizationResult
  records[]
    job: JobListing
    cleaned_description: str
    normalization: JobNormalization
    normalization_method: heuristic | ollama | fallback
    normalized_at: datetime
```

Current verified full run:

- Source jobs: 16,668
- Normalized jobs: 16,668
- Duplicates: 0
- COMPLETE: 16,607
- NEEDS_REVIEW: 61

Phase 4 should use this artifact as the first import source, then later wire the
Celery pipeline to write directly into Postgres.

## Phase 4 Goal

Build the local storage and API layer:

```text
Phase 1 extractor
  -> Phase 3 normalization
  -> Postgres tables
  -> FastAPI endpoints
  -> future frontend
```

Acceptance target:

- Postgres runs locally through Docker Compose.
- Normalized Phase 3 artifact imports into Postgres.
- Jobs dedupe through a unique `content_hash`.
- API can serve active jobs with filters.
- API can serve company and platform stats.
- Tests cover import and core API query behavior.

## Recommended Build Order

### Step 1: Add Postgres To Docker Compose

Extend `docker-compose.yml` with a `postgres` service:

```yaml
postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: jobful
    POSTGRES_USER: jobful
    POSTGRES_PASSWORD: jobful_dev
  ports:
    - "5432:5432"
  volumes:
    - postgres-data:/var/lib/postgresql/data
```

Add `postgres-data` to the volumes block.

Local connection string:

```powershell
$env:JOBFUL_DATABASE_URL = "postgresql+psycopg://jobful:jobful_dev@localhost:5432/jobful"
```

Use an async URL later for FastAPI if using SQLAlchemy async:

```powershell
$env:JOBFUL_ASYNC_DATABASE_URL = "postgresql+asyncpg://jobful:jobful_dev@localhost:5432/jobful"
```

### Step 2: Add Database Dependencies

Add dependencies:

```text
fastapi
uvicorn
sqlalchemy
alembic
psycopg[binary]
asyncpg
```

For initial import scripts, sync SQLAlchemy or `psycopg` is fine. For the API,
prefer async SQLAlchemy with `asyncpg`.

### Step 3: Create Database Modules

Recommended structure:

```text
app/db/
  __init__.py
  config.py
  engine.py
  models.py
  session.py
  import_phase3.py
alembic/
  env.py
  versions/
```

Responsibilities:

- `app/db/config.py`: read database URLs from environment.
- `app/db/engine.py`: create sync and async engines.
- `app/db/models.py`: SQLAlchemy table models.
- `app/db/session.py`: session factories.
- `app/db/import_phase3.py`: import a `NormalizationResult` JSON artifact.

### Step 4: Define Tables

Use two core tables first: `companies` and `jobs`.

Keep user application tracking for Phase 5.

#### `companies`

Fields:

```text
id UUID primary key
name text not null
career_page_url text
ats_provider text not null
ats_board_token text
is_active boolean default true
created_at timestamptz default now()
last_scraped_at timestamptz
```

Recommended constraints/indexes:

```text
unique(name, ats_provider)
index(ats_provider)
index(is_active)
```

For now, company data can be inferred from `JobListing.company_name` and
`JobListing.ats_provider`. Later we can promote source URLs and board tokens
from `PullSourceResult` into company metadata.

#### `jobs`

Fields mapped from `JobListing`:

```text
id UUID primary key
company_id UUID references companies(id)
company_name text not null
job_title text not null
job_url text not null
ats_provider text not null
ats_job_id text not null
location text[] not null default '{}'
raw_description text
cleaned_description text
description_html text
employment_type text
departments text[] not null default '{}'
date_posted timestamptz
content_hash char(64) not null unique
extracted_at timestamptz not null
first_seen_at timestamptz default now()
last_seen_at timestamptz default now()
```

Fields mapped from `JobNormalization`:

```text
program_type text not null
academic_levels text[] not null default '{}'
degree_requirements text[] not null default '{}'
required_grad_years smallint[] not null default '{}'
visa_sponsorship boolean
visa_status text not null
required_skills text[] not null default '{}'
nice_to_have_skills text[] not null default '{}'
min_gpa numeric(3,2)
clearance_required boolean not null default false
remote_type text not null
normalization_status text not null
normalization_method text not null
normalization_confidence numeric(3,2) not null
normalization_review_reasons text[] not null default '{}'
normalized_at timestamptz not null
```

Recommended constraints/indexes:

```text
unique(content_hash)
index(company_id)
index(ats_provider)
index(program_type)
index(remote_type)
index(visa_status)
index(normalization_status)
GIN index(location)
GIN index(required_skills)
GIN index(required_grad_years)
GIN index(academic_levels)
GIN index(degree_requirements)
partial index on last_seen_at where normalization_status = 'COMPLETE'
```

The unique `content_hash` is the key Phase 3 dedupe handoff into Phase 4.

### Step 5: Import Phase 3 Artifacts

Add a CLI script:

```text
python -m app.db.import_phase3
```

Command shape:

```powershell
python -m app.db.import_phase3 outputs/phase3_full_default_normalized.json
```

Behavior:

1. Load the file as `NormalizationResult`.
2. For each `NormalizedJobRecord`:
   - upsert company
   - upsert job by `content_hash`
   - set `last_seen_at = now()` when a job already exists
   - preserve `first_seen_at` on conflict
3. Print summary:
   - records read
   - companies inserted
   - jobs inserted
   - jobs updated
   - skipped/failed records

Postgres upsert pattern:

```sql
INSERT INTO jobs (...)
VALUES (...)
ON CONFLICT (content_hash)
DO UPDATE SET
  last_seen_at = NOW(),
  job_title = EXCLUDED.job_title,
  job_url = EXCLUDED.job_url,
  raw_description = EXCLUDED.raw_description,
  cleaned_description = EXCLUDED.cleaned_description,
  normalization_status = EXCLUDED.normalization_status,
  normalized_at = EXCLUDED.normalized_at;
```

### Step 6: Add Staleness / Archive Behavior

Do not delete stale jobs immediately.

First local implementation can be simple:

```text
jobs.is_active boolean default true
```

Then add a maintenance command:

```powershell
python -m app.db.mark_stale --older-than-hours 48
```

Behavior:

```sql
UPDATE jobs
SET is_active = false
WHERE last_seen_at < now() - interval '48 hours';
```

Later, add a `jobs_archive` table if historical analysis becomes important.

### Step 7: Build FastAPI Backend

Recommended structure:

```text
app/api/
  __init__.py
  main.py
  deps.py
  schemas.py
  routes/
    jobs.py
    companies.py
    stats.py
```

Start with public read-only endpoints:

```text
GET /health
GET /jobs
GET /jobs/{id}
GET /companies
GET /companies/{id}/jobs
GET /skills/popular
GET /stats
```

Defer auth and user application tracking until Phase 5.

### Step 8: API Response Schemas

Use Pydantic API schemas separate from database models.

Recommended schemas:

```text
JobListItem
JobDetail
CompanySummary
StatsSummary
PaginatedJobsResponse
```

`GET /jobs` should return list-card-friendly fields:

```text
id
company_name
job_title
job_url
location
program_type
academic_levels
required_grad_years
visa_status
remote_type
required_skills
normalization_status
normalization_confidence
date_posted
last_seen_at
```

`GET /jobs/{id}` should include full description fields and review reasons.

### Step 9: Filtering For `GET /jobs`

Support these query params first:

```text
limit
cursor
program_type
remote_type
visa_status
grad_year
academic_level
skill
company_id
normalization_status
search
```

Recommended behavior:

- Default `limit`: 50
- Max `limit`: 100
- Default filter: active jobs only
- Default sort: newest `last_seen_at`, then `id`

Cursor pagination can be added after basic offset pagination if needed. For
local Phase 4, offset pagination is acceptable initially; cursor pagination is
better before frontend scale testing.

### Step 10: Stats Endpoints

`GET /stats` should return:

```text
total_jobs
active_jobs
total_companies
last_updated
jobs_by_program_type
jobs_by_remote_type
jobs_by_visa_status
needs_review_count
```

`GET /skills/popular` should return top skills:

```text
skill
count
```

This is useful for frontend filters.

## Mapping From Phase 3 To Database

Use this mapping when writing the importer.

| Phase 3 source | Database target |
| --- | --- |
| `record.job.company_name` | `companies.name`, `jobs.company_name` |
| `record.job.job_title` | `jobs.job_title` |
| `record.job.job_url` | `jobs.job_url` |
| `record.job.ats_provider` | `companies.ats_provider`, `jobs.ats_provider` |
| `record.job.ats_job_id` | `jobs.ats_job_id` |
| `record.job.location` | `jobs.location` |
| `record.job.raw_description` | `jobs.raw_description` |
| `record.cleaned_description` | `jobs.cleaned_description` |
| `record.job.description_html` | `jobs.description_html` |
| `record.job.employment_type` | `jobs.employment_type` |
| `record.job.departments` | `jobs.departments` |
| `record.job.date_posted` | `jobs.date_posted` |
| `record.job.content_hash` | `jobs.content_hash` |
| `record.job.extracted_at` | `jobs.extracted_at` |
| `record.normalization.program_type` | `jobs.program_type` |
| `record.normalization.academic_levels` | `jobs.academic_levels` |
| `record.normalization.degree_requirements` | `jobs.degree_requirements` |
| `record.normalization.required_grad_years` | `jobs.required_grad_years` |
| `record.normalization.visa_sponsorship` | `jobs.visa_sponsorship` |
| `record.normalization.visa_status` | `jobs.visa_status` |
| `record.normalization.required_skills` | `jobs.required_skills` |
| `record.normalization.nice_to_have_skills` | `jobs.nice_to_have_skills` |
| `record.normalization.min_gpa` | `jobs.min_gpa` |
| `record.normalization.clearance_required` | `jobs.clearance_required` |
| `record.normalization.remote_type` | `jobs.remote_type` |
| `record.normalization.normalization_status` | `jobs.normalization_status` |
| `record.normalization.confidence` | `jobs.normalization_confidence` |
| `record.normalization.review_reasons` | `jobs.normalization_review_reasons` |
| `record.normalization_method` | `jobs.normalization_method` |
| `record.normalized_at` | `jobs.normalized_at` |

## Local Development Commands

Expected final local Phase 4 flow:

```powershell
docker compose up -d redis postgres
python -m alembic upgrade head
python -m app.db.import_phase3 outputs/phase3_full_default_normalized.json
python -m uvicorn app.api.main:app --reload
```

Then verify:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod "http://localhost:8000/jobs?limit=5"
Invoke-RestMethod http://localhost:8000/stats
```

## Tests To Add

Add tests for:

- database model creation
- Phase 3 artifact import
- `content_hash` upsert behavior
- company upsert behavior
- `GET /health`
- `GET /jobs`
- `GET /jobs` filters
- `GET /jobs/{id}`
- `GET /companies`
- `GET /stats`

Use a test database or transactional test setup. Avoid writing API tests against
the same local development database unless the test data is isolated.

## What Not To Build Yet

Do not start with:

- frontend
- auth
- Kanban tracking
- user applications
- cloud deployment
- payment/user accounts

Those belong to later phases. Phase 4 should make the data persistent and
queryable first.

## Phase 4 Completion Criteria

Phase 4 is complete when:

- `docker compose up -d redis postgres` works.
- Alembic creates all tables and indexes.
- `outputs/phase3_full_default_normalized.json` imports successfully.
- Re-running the import updates existing jobs instead of duplicating them.
- `GET /jobs` returns normalized jobs from Postgres.
- `GET /jobs` supports core filters.
- `GET /companies`, `GET /companies/{id}/jobs`, `GET /skills/popular`, and
  `GET /stats` work.
- Tests pass.
- README/CODEBASE docs are updated with the new local stack commands.

At that point, the project will have a real local backend and will be ready for
Phase 5 frontend work.
