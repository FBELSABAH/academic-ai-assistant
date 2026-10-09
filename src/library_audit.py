"""Rebuildable SQLite reporting for the downloaded Moodle library.

Does not modify downloads, authenticate, or contact Moodle/Google.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3

SQL_ROOT = Path(__file__).resolve().parents[1] / "sql"


def refresh(library: Path, database: Path) -> dict:
    """Atomically replace the report snapshot after validating all manifests.

    A malformed snapshot leaves existing report rows intact. Removed files are
    removed only from this derived index, never from the original library.
    """
    if not library.is_dir():
        raise ValueError(f"Library directory does not exist: {library}")
    courses, files = [], []
    for path in sorted(library.glob("course-*/manifest.json")):
        manifest = json.loads(path.read_text())
        cid = path.parent.name.removeprefix("course-")
        courses.append((cid, manifest["course_name"], manifest.get("course_url", "")))
        for url, item in manifest.get("files", {}).items():
            relative = Path(item["path"])
            if relative.is_absolute() or not (path.parent / relative).resolve().is_relative_to(path.parent.resolve()):
                raise ValueError(f"Unsafe file path in course {cid}")
            size = int(item.get("bytes", 0))
            if size < 0:
                raise ValueError("File size cannot be negative")
            files.append((cid, url, item.get("title", relative.name), str(relative),
                          size, int(bool(item.get("verified_in_last_run", False)))))
    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database, timeout=10) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript((SQL_ROOT / "library_schema.sql").read_text())
        with db:
            db.execute("DELETE FROM library_files")
            db.execute("DELETE FROM library_courses")
            db.executemany("INSERT INTO library_courses VALUES (?, ?, ?)", courses)
            db.executemany("INSERT INTO library_files VALUES (?, ?, ?, ?, ?, ?)", files)
    return {"courses": len(courses), "files": len(files)}


def report(database: Path, course_id: str | None = None) -> list[dict]:
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(
            (SQL_ROOT / "library_report.sql").read_text(), {"course_id": course_id})]


def largest_files(database: Path, limit_per_course: int = 3) -> list[dict]:
    if limit_per_course < 1:
        raise ValueError("Limit must be positive")
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute(
            (SQL_ROOT / "largest_files.sql").read_text(), {"limit_per_course": limit_per_course})]
