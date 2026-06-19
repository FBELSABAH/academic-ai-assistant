from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import html
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event
from sqlalchemy.orm import selectinload

from src.config import PROJECT_ROOT, settings
from src.db import get_session
from src.models import Assignment, CalendarEvent


@dataclass
class CalendarExportResult:
    events_exported: int
    skipped_events: int
    output_path: Path


class CalendarExporter:
    """Export local academic deadlines/events to an Apple Calendar-compatible ICS file."""

    def __init__(self) -> None:
        self.local_timezone = ZoneInfo(settings.local_timezone)
        self.output_path = PROJECT_ROOT / "data" / "exports" / "academic_deadlines.ics"

    def export(self) -> CalendarExportResult:
        session = get_session()
        try:
            calendar_events = session.query(CalendarEvent).order_by(CalendarEvent.start_at.asc()).all()
            assignments = (
                session.query(Assignment)
                .options(selectinload(Assignment.course))
                .filter(Assignment.due_at.is_not(None))
                .order_by(Assignment.due_at.asc(), Assignment.title.asc())
                .all()
            )
        finally:
            session.close()

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        calendar = Calendar()
        calendar.add("prodid", "-//academic-ai-assistant//Apple Calendar Export//EN")
        calendar.add("version", "2.0")
        calendar.add("calscale", "GREGORIAN")
        calendar.add("method", "PUBLISH")
        calendar.add("x-wr-calname", "Academic Deadlines")
        calendar.add("x-wr-timezone", settings.local_timezone)

        exported = 0
        skipped = 0
        seen_keys: set[tuple[str, datetime]] = set()

        for item in calendar_events:
            key = (self._clean_text(item.title).lower(), item.start_at)
            if key in seen_keys:
                skipped += 1
                continue
            seen_keys.add(key)
            calendar.add_component(self._build_calendar_event(item))
            exported += 1

        for assignment in assignments:
            if assignment.due_at is None:
                skipped += 1
                continue

            key = (self._clean_text(assignment.title).lower(), assignment.due_at)
            if key in seen_keys:
                skipped += 1
                continue

            seen_keys.add(key)
            calendar.add_component(self._build_assignment_event(assignment))
            exported += 1

        self.output_path.write_bytes(calendar.to_ical())
        return CalendarExportResult(
            events_exported=exported,
            skipped_events=skipped,
            output_path=self.output_path,
        )

    def _build_calendar_event(self, item: CalendarEvent) -> Event:
        event = Event()
        event.add("uid", item.uid)
        event.add("summary", self._clean_text(item.title))
        event.add("dtstamp", datetime.now(self.local_timezone))
        event.add("dtstart", self._localize(item.start_at))
        if item.end_at:
            event.add("dtend", self._localize(item.end_at))
        if item.description:
            event.add("description", self._build_description(item.description, item.url, item.source))
        else:
            event.add("description", self._build_description(None, item.url, item.source))
        if item.location:
            event.add("location", self._clean_text(item.location))
        if item.url:
            event.add("url", item.url)
        return event

    def _build_assignment_event(self, item: Assignment) -> Event:
        event = Event()
        event.add("uid", f"assignment-{item.id}@academic-ai-assistant")
        event.add("summary", self._clean_text(item.title))
        event.add("dtstamp", datetime.now(self.local_timezone))
        event.add("dtstart", self._localize(item.due_at))
        event.add("dtend", self._localize(item.due_at + timedelta(hours=1)))

        description_parts = []
        if item.description:
            description_parts.append(self._clean_text(item.description))
        if item.status:
            description_parts.append(f"Status: {self._clean_text(item.status)}")
        event.add("description", self._build_description(" | ".join(description_parts) or None, item.url, item.source))
        if item.url:
            event.add("url", item.url)
        return event

    def _build_description(self, description: str | None, url: str | None, source: str) -> str:
        parts = []
        if description:
            parts.append(self._clean_text(description))
        if url:
            parts.append(f"URL: {url}")
        parts.append(f"Source: {source}")
        return "\n".join(parts)

    def _clean_text(self, value: str | None) -> str:
        if not value:
            return ""
        return " ".join(html.unescape(value).split())

    def _localize(self, value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone(self.local_timezone)
        return value.replace(tzinfo=self.local_timezone)
