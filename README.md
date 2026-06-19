# academic-ai-assistant

Local academic automation assistant for macOS.

This project is planned to:

- use Playwright for manual Moodle login and saved browser session reuse
- collect Moodle courses, assignments, resources, and calendar deadlines
- store data locally in SQLite through SQLAlchemy
- summarize academic tasks with a local Ollama model
- export clean `.ics` calendar files for Apple Calendar/iCal

## Stage 1 status

This repository currently contains the initial project skeleton only.

- login automation is not implemented yet
- scraping is not implemented yet
- summarization is not implemented yet
- calendar export/import logic is not implemented yet

## Setup

1. Create or activate your virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in only non-secret values you want to override later.

## Security

- Do not hardcode Moodle credentials.
- Use Playwright manual login and save the browser session to `storage_state.json`.
- Keep `.env`, session files, and SQLite database files out of version control.

## Current scripts

- `scripts/init_db.py`: initialize the local SQLite database
- `scripts/login_moodle.py`: placeholder for manual Playwright login flow
- `scripts/check_moodle_session.py`: placeholder for session validation
- `scripts/scrape_courses.py`: placeholder for course scraping
- `scripts/scrape_assignments.py`: placeholder for assignment scraping
- `scripts/import_moodle_calendar.py`: placeholder for Moodle calendar import
- `scripts/summarize_courses.py`: placeholder for Ollama summarization
- `scripts/export_ics.py`: placeholder for `.ics` export
