# Adding Sources And Extractors

This guide is the standard way to grow Jobful's job coverage without breaking
the pipeline contract.

The core contract is:

```text
career URL
-> AtsRouter
-> BaseExtractor subclass
-> JobListing
-> Phase 3 normalization
-> db.import_phase3
-> Postgres
-> FastAPI filters
```

If a change preserves that contract, the rest of the system should keep working.

## Add More Job Sources

Use this path when the company already uses a supported ATS.

1. Add the career URL to a source file.

   For permanent default coverage, add it to `DEFAULT_CAREER_URLS` in
   `sources.py`. For experiments or one-off batches, create a newline-delimited
   file such as `sources_new_companies.txt`.

2. Dry-run queue classification when using Celery:

   ```powershell
   python -m app.phases.phase2 --input-file sources_new_companies.txt --dry-run
   ```

3. Pull the sources:

   ```powershell
   python main.py --input-file sources_new_companies.txt -o outputs/new_pull.json --workers 12 --timeout 8
   ```

4. Normalize:

   ```powershell
   python -m app.phases.phase3 outputs/new_pull.json -o outputs/new_normalized.json --no-ollama
   ```

5. Import:

   ```powershell
   python -m app.db.import_phase3 outputs/new_normalized.json
   ```

6. Verify through the API:

   ```powershell
   Invoke-RestMethod "http://localhost:8000/jobs?company=SomeCompany&limit=5"
   Invoke-RestMethod http://localhost:8000/stats
   ```

Source URL rules:

- Use the public career-board URL, not a job detail URL.
- Keep one URL per ATS board or company board.
- Do not add LinkedIn, Indeed, or aggregator URLs.
- Expect dead or retired boards over time; extraction artifacts record failures.

## Add A New Extractor

Use this path when a source is valuable but its ATS is not supported yet.

1. Create a provider module:

   ```text
   app/extractors/new_provider.py
   ```

2. Subclass `BaseExtractor`:

   ```python
   from __future__ import annotations

   from app.extractors.base import BaseExtractor
   from app.models import JobListing


   class NewProviderExtractor(BaseExtractor):
       provider = "new_provider"

       def extract(self) -> list[JobListing]:
           payload = self._get_json("https://example.com/api/jobs")
           return [self._map_job(item) for item in payload["jobs"]]
   ```

3. Use `BaseExtractor` helpers wherever possible:

- `_get_json` and `_post_json` for HTTP calls, retry handling, proxy rotation,
  and JSON validation.
- `_build_listing` to create validated `JobListing` records.
- `_parse_datetime` for timestamps.
- `_string_list` and `_required_string` for defensive payload mapping.
- `_content_hash` only when `_build_listing` is not enough.

4. Add the provider name to `AtsProvider` in `app/models.py`.

5. Export the extractor in `app/extractors/__init__.py` if it needs package-level
   access.

6. Register routing in `app/router.py`:

- Import the extractor.
- Add a provider detection branch in `AtsRouter.route`.
- Add helper methods for host/path checks and board-token extraction.
- Return `AtsRoute(provider, board_token, ExtractorClass, career_url)`.

7. Add tests:

- Router detection in `app/tests/test_phase2.py` or a provider-specific test file.
- Payload mapping with a fake `requests.Session`.
- Failure behavior for malformed payloads.
- A CLI or pipeline smoke test only when the provider has unusual behavior.

8. Run tests:

   ```powershell
   python -m unittest discover -v
   ```

## JobListing Mapping Checklist

Every extractor must return `JobListing` records with:

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

Mapping guidance:

- Prefer stable ATS-native job IDs for `ats_job_id`.
- Use the direct application URL for `job_url`.
- Convert HTML descriptions to text for `raw_description`.
- Preserve original HTML in `description_html` when available.
- Use `["Unspecified"]` when no location exists.
- Keep skills, eligibility, visa, and remote classification out of extractors;
  Phase 3 owns normalization.

## Validation Before Import

Before importing a new provider's data, check the generated artifact:

```powershell
python main.py https://new-provider.example/jobs -o outputs/new_provider_pull.json
python -m app.phases.phase3 outputs/new_provider_pull.json -o outputs/new_provider_normalized.json --no-ollama
python -m app.db.import_phase3 outputs/new_provider_normalized.json
```

Then verify:

```powershell
Invoke-RestMethod "http://localhost:8000/jobs?company=Example&limit=10"
Invoke-RestMethod "http://localhost:8000/jobs?skill=python&limit=10"
Invoke-RestMethod http://localhost:8000/skills/popular
```

## When To Use Browser Fallbacks

Prefer direct JSON APIs. Use Playwright/browser flows only when:

- the ATS has no usable public JSON endpoint,
- the endpoint requires client-side token discovery,
- direct HTTP consistently returns HTML, 403, or bot challenges,
- and the source is important enough to justify slower extraction.

Browser-heavy sources should usually route to the slow queue.

## Done Criteria

A source or extractor addition is done when:

- `python -m unittest discover -v` passes.
- The source emits valid `JobListing` records.
- Phase 3 can normalize the records.
- `db.import_phase3` inserts or updates without duplicates.
- `/jobs` can find the imported records by company and at least one useful
  filter.
