#!/usr/bin/env python3

"""Seed an empty local database with fictional records for offline demos."""

from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import get_session
from src.models import Assignment, CalendarEvent, Course, Resource


def main() -> None:
    session = get_session()
    try:
        has_existing_data = any(
            session.query(model).first() is not None
            for model in (Course, Assignment, Resource, CalendarEvent)
        )
        if has_existing_data:
            raise SystemExit(
                "The configured database already contains data. "
                "Use an empty demo database (for example, data/demo.db) instead."
            )

        now = datetime.now().replace(second=0, microsecond=0)
        analytics = Course(
            moodle_course_id="101",
            name="Applied Analytics",
            short_name="ANLY 101",
            url="https://moodle.example.edu/course/view.php?id=101",
        )
        programming = Course(
            moodle_course_id="202",
            name="Programming Foundations",
            short_name="COMP 202",
            url="https://moodle.example.edu/course/view.php?id=202",
        )
        session.add_all([analytics, programming])
        session.flush()

        session.add_all(
            [
                Assignment(
                    course_id=analytics.id,
                    title="Exploratory Data Report",
                    url="https://moodle.example.edu/mod/assign/view.php?id=1001",
                    description="Fictional demo assignment.",
                    due_at=now + timedelta(days=3),
                    status="No submission has been made yet",
                    source="demo",
                    source_uid="demo-assignment-1001",
                ),
                Assignment(
                    course_id=programming.id,
                    title="Data Structures Exercise",
                    url="https://moodle.example.edu/mod/assign/view.php?id=2001",
                    description="Fictional demo assignment.",
                    due_at=now + timedelta(days=8),
                    status="Draft saved",
                    source="demo",
                    source_uid="demo-assignment-2001",
                ),
                Resource(
                    course_id=analytics.id,
                    title="Regression Review Notes",
                    url="https://moodle.example.edu/mod/resource/view.php?id=1002",
                    resource_type="resource",
                    section_title="Week 4",
                ),
                CalendarEvent(
                    uid="demo-event-1@academic-ai-assistant",
                    title="Fictional quiz window closes",
                    description="Sample event for local testing.",
                    start_at=now + timedelta(days=2),
                    source="demo",
                ),
            ]
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print("Loaded fictional demo data into the configured database.")


if __name__ == "__main__":
    main()
