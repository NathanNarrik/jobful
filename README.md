# Project Jobful: System Architecture & Phase 1 Directives

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

## 3. Phase 1 Specifications: The Extraction Layer (Current Task)

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
