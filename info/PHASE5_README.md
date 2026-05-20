# Phase 5 Plan: Frontend Interface & Frictionless Tracking

Phase 5 comes from `Jobful_Engineering_Design_Doc_v2.docx`, section
`PHASE 5 Frontend Interface & Frictionless Tracking`.

## Strategic Goal

Build the anti-LinkedIn frontend: zero noise, maximum signal, mobile-first, and
designed to move a student from "what's open?" to "I just submitted my
application" in under 90 seconds.

## Current Phase 5 Implementation

Implemented locally:

- Next.js App Router frontend in `frontend/`
- `/discover` discovery feed
- `/dashboard` Kanban dashboard
- Zustand stores for discovery and applications
- dnd-kit Kanban drag-and-drop
- mobile tap-to-move fallback
- optimistic application status updates
- expandable notes textarea saved on blur
- direct ATS application CTA: `Apply on [CompanyName]`
- FastAPI application tracking endpoints
- `user_applications` database table

## Frontend Routes

### `/discover`

The discovery feed is a dense, mobile-first job browser:

- 3-column desktop, 2-column tablet, 1-column mobile
- job cards with company letter avatar fallback
- job title, company, location, program type, visa, remote type, and posted age
- sticky filter bar
- debounced search
- single-click detail drawer
- direct external ATS apply link
- save/apply actions that create application records

Supported filters:

- Program Type
- Graduation Year
- Remote/Hybrid/Onsite
- Visa Status
- Skill
- Search

### `/dashboard`

The dashboard tracks the user's personal pipeline:

```text
SAVED -> APPLIED -> PHONE SCREEN -> TECHNICAL -> FINAL ROUND -> OFFER / REJECTED
```

Behavior:

- drag cards between columns on desktop
- mobile move button fallback
- optimistic UI update before `PATCH /applications/{id}` completes
- rollback and toast on API error
- notes save on blur

## Backend Additions

### `user_applications`

Fields:

```text
id UUID primary key
user_id UUID not null
job_id UUID references jobs(id) on delete set null
status varchar(30) default SAVED
applied_at timestamptz
notes text
kanban_order integer default 0
created_at timestamptz
updated_at timestamptz
```

Local Phase 5 uses a fixed dev user ID by default. Real authentication,
Supabase/JWT, and row-level security belong to Phase 6.

### API Endpoints

```text
GET /applications
POST /applications
PATCH /applications/{id}
```

The frontend also consumes existing Phase 4 endpoints:

```text
GET /jobs
GET /jobs/{id}
GET /skills/popular
```

## Local Development

Start the backend dependencies:

```powershell
docker compose up -d redis postgres
python -m alembic upgrade head
```

Run the API:

```powershell
python -m uvicorn app.api.main:app --reload
```

Run the frontend:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000/discover
http://localhost:3000/dashboard
```

Override the API base URL:

```powershell
$env:NEXT_PUBLIC_JOBFUL_API_BASE = "http://127.0.0.1:8000"
```

## Verification

Backend:

```powershell
python -m unittest discover -v
```

Frontend:

```powershell
cd frontend
npm run lint
npm run build
```

Browser checks performed:

- `/discover` loads real imported Postgres jobs
- detail drawer opens from a job card
- save action creates an application record
- `/dashboard` shows the saved job
- desktop screenshot checked
- mobile discovery screenshot checked
- browser console had no errors

## Remaining Phase 5 Hardening

Not yet complete:

- true cursor pagination on the frontend
- Redis response caching for public feed stats
- full-text PostgreSQL index for search
- richer mobile bottom sheet for Kanban movement
- Lighthouse score verification
- iOS Safari and Android Chrome real-device checks

Those are Phase 5 hardening tasks. Authentication and production deployment
belong to Phase 6.
