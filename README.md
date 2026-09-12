# Academic AI Assistant

> **Active Development** — independently developed since January 2026.

A local-first Python assistant that turns a student's Moodle course information and calendar into a clearer academic workload view. It uses a manually authenticated browser session to collect course content, stores results in SQLite, creates a rule-based status summary, optionally refines that summary with a local Ollama model, and exports deadlines to an Apple Calendar-compatible `.ics` file.

## Why it exists

Academic information is often spread across course pages, activity descriptions, submission status, and calendars. This project explores a privacy-conscious workflow for consolidating those sources locally so a student can review upcoming work without sharing their data with a hosted AI service by default.

## Architecture and workflow

```text
Manual Moodle login (Playwright)
        ↓ saved local browser session
Course / assignment / resource scraper ──┐
Moodle calendar ICS importer ────────────┼──> SQLite database
                                          ├──> Rule-based academic summary
                                          ├──> Optional local Ollama brief
                                          └──> Apple Calendar-compatible ICS export
```

## Implemented features

- Manual Moodle login with Playwright and local session reuse.
- Course discovery with course IDs, names, and links stored locally.
- Assignment and resource discovery across Moodle course pages.
- Assignment-detail enrichment for dates, descriptions, and submission status.
- Moodle calendar import from a user-provided ICS feed URL.
- SQLite persistence through SQLAlchemy.
- Rule-based workload summary; optional local Ollama-generated brief.
- ICS export for Apple Calendar/iCal, with duplicate-event filtering.
- Offline fictional demo data for safe walkthroughs.

## Planned work

- Automated tests using saved, anonymized Moodle HTML fixtures.
- Broader Moodle theme/version compatibility and more activity types.
- A richer local interface for reviewing summaries and scrape history.
- Better scheduling, error reporting, and data-retention controls.

## Quick start: safe demo

Use the demo workflow first. It needs no Moodle account, real calendar feed, or student records.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python scripts/init_db.py
python scripts/load_demo_data.py
python scripts/summarize_courses.py
python scripts/export_ics.py
```

The sample configuration writes only to `data/demo.db`, and the generated calendar is saved under `data/exports/`. Both are ignored by Git.

## Moodle workflow

1. Copy `.env.example` to `.env` and replace the `moodle.example.edu` URLs with your institution's Moodle URLs.
2. Keep `MOODLE_CALENDAR_ICS_URL` blank unless you want calendar import; that URL can provide access to academic events and must remain private.
3. If using real data, set `DATABASE_URL` to a separate ignored SQLite file, such as `sqlite:///data/academic.db`.
4. Run the scripts in this order:

```bash
python scripts/init_db.py
python scripts/login_moodle.py
python scripts/check_moodle_session.py
python scripts/scrape_courses.py
python scripts/scrape_assignments.py
python scripts/enrich_assignments.py
python scripts/import_moodle_calendar.py  # optional
python scripts/summarize_courses.py
python scripts/export_ics.py
```

`login_moodle.py` opens a browser for manual sign-in; do not enter passwords in source code or the terminal. Re-run it whenever the saved session expires.

## Project structure

```text
src/          Application modules: configuration, browser, scrapers, database, summaries, calendar I/O
scripts/      Command-line entry points and safe demo-data loader
data/         Local databases, debug HTML, and calendar exports (ignored except `.gitkeep`)
.env.example  Safe configuration template
```

## Technologies

Python, Playwright, Beautiful Soup, SQLAlchemy, SQLite, Requests, iCalendar, python-dotenv, and optional Ollama.

## Privacy and security

- Real Moodle credentials are entered only in the interactive browser login flow.
- Playwright session state, Moodle cookies, calendar feed URLs, databases, debug HTML, calendar exports, logs, and local `.env*` files are ignored by Git.
- The repository includes only fictional demo data; never commit real courses, assignments, student names, course URLs/IDs, or exported calendars.
- The optional Ollama integration targets a local server. Review its configuration before using a remote endpoint because summary inputs may contain academic data.

## Limitations

- Moodle markup differs by institution and theme; selectors may require adjustment.
- The application is a personal workflow tool, not an official Moodle integration.
- Scrapes rely on a valid user session and may fail after Moodle UI changes or session expiry.
- Summary quality depends on the completeness and accuracy of imported data; it is not academic advice.

## Before publishing

Run `git status --ignored` and verify that only source, documentation, `.env.example`, and intentional project files are staged. Do not publish `data/`, `storage_state.json`, `.env`, browser-session files, or any exported ICS file.
