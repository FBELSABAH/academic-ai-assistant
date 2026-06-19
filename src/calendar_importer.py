from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
import html
import logging
from typing import Any

from icalendar import Calendar
import requests

from src.config import settings
from src.db import get_session
from src.models import CalendarEvent


logger = logging.getLogger(__name__)


@dataclass
class CalendarImportResult:
    events_found: int
    inserted: int
    updated: int
    skipped: int
    errors: int


class MissingCalendarUrlError(RuntimeError):
    pass


class MoodleCalendarImporter:
    """Import Moodle calendar events from a dynamic ICS URL."""

    def import_from_ics(self) -> CalendarImportResult:
        if not settings.moodle_calendar_ics_url:
            raise MissingCalendarUrlError(
                "MOODLE_CALENDAR_ICS_URL is missing.\n"
                "Go to the Moodle calendar export page.\n"
                "Select all events.\n"
                "Choose a useful date range.\n"
                "Click 'Get calendar URL'.\n"
                "Paste that URL into .env as MOODLE_CALENDAR_ICS_URL."
            )

        response = requests.get(settings.moodle_calendar_ics_url, timeout=30)
        response.raise_for_status()

        calendar = Calendar.from_ical(response.content)
        return self._upsert_calendar(calendar)

    def _upsert_calendar(self, calendar: Calendar) -> CalendarImportResult:
        inserted = 0
        updated = 0
        skipped = 0
        errors = 0
        events_found = 0
        now = datetime.utcnow()

        session = get_session()
        try:
            for component in calendar.walk():
                if component.name != "VEVENT":
                    continue

                events_found += 1

                try:
                    raw_uid = component.get("uid")
                    uid = str(raw_uid).strip() if raw_uid else ""
                    title = self._as_clean_text(component.get("summary"))
                    start_at = self._as_datetime(component.get("dtstart"))

                    if not uid or not title or start_at is None:
                        skipped += 1
                        logger.warning("Skipping calendar event with missing uid/title/start.")
                        continue

                    end_at = self._as_datetime(component.get("dtend"))
                    description = self._as_clean_text(component.get("description"))
                    location = self._as_clean_text(component.get("location"))
                    url = self._as_clean_text(component.get("url"))

                    existing = session.query(CalendarEvent).filter(CalendarEvent.uid == uid).one_or_none()

                    if existing is None:
                        session.add(
                            CalendarEvent(
                                uid=uid,
                                title=title,
                                description=description,
                                location=location,
                                start_at=start_at,
                                end_at=end_at,
                                url=url,
                                source="moodle_calendar",
                                export_start_date=None,
                                export_end_date=None,
                                created_at=now,
                                updated_at=now,
                                last_seen_at=now,
                            )
                        )
                        inserted += 1
                        continue

                    changed = False
                    for field, value in {
                        "title": title,
                        "description": description,
                        "location": location,
                        "start_at": start_at,
                        "end_at": end_at,
                        "url": url,
                        "source": "moodle_calendar",
                    }.items():
                        if getattr(existing, field) != value:
                            setattr(existing, field, value)
                            changed = True

                    existing.last_seen_at = now
                    existing.updated_at = now if changed else existing.updated_at
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                except Exception:
                    errors += 1
                    logger.exception("Failed processing a calendar event.")

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        return CalendarImportResult(
            events_found=events_found,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    def _as_clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = html.unescape(str(value)).strip()
        text = " ".join(text.split())
        return text or None

    def _as_datetime(self, field: Any) -> datetime | None:
        if field is None:
            return None

        decoded = field.dt if hasattr(field, "dt") else field

        if isinstance(decoded, datetime):
            return decoded.replace(tzinfo=None) if decoded.tzinfo else decoded

        if isinstance(decoded, date):
            return datetime.combine(decoded, time.min)

        return None
