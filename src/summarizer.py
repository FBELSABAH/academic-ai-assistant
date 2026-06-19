from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import html
from zoneinfo import ZoneInfo

from src.db import get_session
from src.models import Assignment, CalendarEvent, Course, Resource
from sqlalchemy.orm import selectinload
from src.config import settings


@dataclass
class UpcomingItem:
    title: str
    when: datetime
    kind: str
    course_name: str | None = None
    status: str | None = None


class CourseSummarizer:
    """Generate a rule-based academic status summary from local SQLite data."""

    SUPPORT_COURSE_TERMS = (
        "moodle support",
        "academic integrity",
        "faculty / staff moodle support",
        "student moodle support",
    )

    def __init__(self) -> None:
        self.local_timezone = ZoneInfo(settings.local_timezone)

    def summarize(self) -> str:
        session = get_session()
        try:
            # Renderer methods run after the session is closed, so every relationship
            # they touch must be eager-loaded here instead of relying on lazy loads.
            courses = (
                session.query(Course)
                .options(
                    selectinload(Course.assignments),
                    selectinload(Course.resources),
                )
                .order_by(Course.name.asc())
                .all()
            )
            assignments = (
                session.query(Assignment)
                .options(selectinload(Assignment.course))
                .join(Course)
                .order_by(Course.name.asc(), Assignment.title.asc())
                .all()
            )
            resources = (
                session.query(Resource)
                .options(selectinload(Resource.course))
                .join(Course)
                .order_by(Resource.last_seen_at.desc())
                .all()
            )
            calendar_events = session.query(CalendarEvent).order_by(CalendarEvent.start_at.asc()).all()
        finally:
            session.close()

        now_local = datetime.now(self.local_timezone)
        now = now_local.replace(tzinfo=None)
        in_7_days = now + timedelta(days=7)
        in_30_days = now + timedelta(days=30)
        visible_courses = [course for course in courses if not self._is_support_course(course.name)]
        visible_resources = [resource for resource in resources if not self._is_support_course(resource.course.name)]
        hidden_support_courses = len(courses) - len(visible_courses)
        hidden_support_resources = len(resources) - len(visible_resources)

        upcoming_next_7 = self._collect_upcoming_items(calendar_events, assignments, now, in_7_days)
        upcoming_days_8_to_30 = self._collect_upcoming_items(calendar_events, assignments, in_7_days, in_30_days)

        lines: list[str] = []
        lines.append("Academic Assistant Summary")
        lines.append(f"Generated: {self._format_datetime(now_local)}")
        lines.append("")

        lines.extend(self._render_upcoming_section("Upcoming deadlines/events in the next 7 days", upcoming_next_7))
        lines.append("")
        lines.extend(self._render_upcoming_section("Upcoming deadlines/events in the next 30 days", upcoming_days_8_to_30))
        lines.append("")
        lines.extend(self._render_assignment_statuses(assignments))
        lines.append("")
        lines.extend(self._render_courses_with_most_items(visible_courses, hidden_support_courses))
        lines.append("")
        lines.extend(self._render_recent_resources(visible_resources, hidden_support_resources))
        lines.append("")
        lines.extend(self._render_urgent_tasks(calendar_events, assignments, now))

        return "\n".join(lines).strip() + "\n"

    def _collect_upcoming_items(
        self,
        calendar_events: list[CalendarEvent],
        assignments: list[Assignment],
        start: datetime,
        end: datetime,
    ) -> list[UpcomingItem]:
        items: list[UpcomingItem] = []

        for event in calendar_events:
            if start <= event.start_at <= end:
                items.append(
                    UpcomingItem(
                        title=self._clean_text(event.title),
                        when=event.start_at,
                        kind="calendar",
                    )
                )

        for assignment in assignments:
            if assignment.due_at and start <= assignment.due_at <= end:
                items.append(
                    UpcomingItem(
                        title=self._clean_text(assignment.title),
                        when=assignment.due_at,
                        kind="assignment",
                        course_name=self._clean_text(assignment.course.name),
                        status=self._clean_text(assignment.status),
                    )
                )

        items.sort(key=lambda item: item.when)
        return items

    def _render_upcoming_section(self, title: str, items: list[UpcomingItem]) -> list[str]:
        lines = [title]
        if not items:
            lines.append("- None")
            return lines

        for item in items:
            when_text = self._format_datetime(item.when)
            label = item.title
            if item.course_name:
                label = f"{label} [{item.course_name}]"
            if item.status:
                label = f"{label} ({item.status})"
            lines.append(f"- {when_text} | {label}")
        return lines

    def _render_assignment_statuses(self, assignments: list[Assignment]) -> list[str]:
        lines = ["Assignment statuses"]
        if not assignments:
            lines.append("- None")
            return lines

        for assignment in assignments:
            status = self._clean_text(assignment.status) or "missing"
            course_name = self._clean_text(assignment.course.name)
            lines.append(f"- {self._clean_text(assignment.title)} [{course_name}] | {status}")
        return lines

    def _render_courses_with_most_items(self, courses: list[Course], hidden_support_courses: int) -> list[str]:
        lines = ["Courses with the most resources/items"]
        if not courses:
            lines.append("- None")
            if hidden_support_courses:
                lines.append("Support courses hidden from resource summary.")
            return lines

        ranked = sorted(
            courses,
            key=lambda course: len(course.assignments) + len(course.resources),
            reverse=True,
        )

        for course in ranked[:5]:
            total_items = len(course.assignments) + len(course.resources)
            lines.append(
                f"- {self._clean_text(course.name)} | {total_items} total items "
                f"({len(course.assignments)} assignments, {len(course.resources)} resources)"
            )
        if hidden_support_courses:
            lines.append("Support courses hidden from resource summary.")
        return lines

    def _render_recent_resources(self, resources: list[Resource], hidden_support_resources: int) -> list[str]:
        lines = ["Recently seen resources"]
        if not resources:
            lines.append("- None")
            if hidden_support_resources:
                lines.append("Support courses hidden from resource summary.")
            return lines

        for resource in resources[:10]:
            seen_text = self._format_datetime(resource.last_seen_at)
            course_name = self._clean_text(resource.course.name)
            resource_type = self._clean_text(resource.resource_type) or "resource"
            lines.append(
                f"- {seen_text} | {self._clean_text(resource.title)} [{course_name}] ({resource_type})"
            )
        if hidden_support_resources:
            lines.append("Support courses hidden from resource summary.")
        return lines

    def _render_urgent_tasks(
        self,
        calendar_events: list[CalendarEvent],
        assignments: list[Assignment],
        now: datetime,
    ) -> list[str]:
        lines = ["Possible urgent tasks"]
        urgent_items: list[str] = []
        soon = now + timedelta(hours=48)

        for event in calendar_events:
            title = self._clean_text(event.title).lower()
            if event.start_at <= soon and event.start_at >= now:
                urgent_items.append(
                    f"{self._format_datetime(event.start_at)} | {self._clean_text(event.title)}"
                )
                continue

            if any(keyword in title for keyword in ["due", "closes", "exam", "quiz"]) and now <= event.start_at <= (
                now + timedelta(days=7)
            ):
                urgent_items.append(
                    f"{self._format_datetime(event.start_at)} | {self._clean_text(event.title)}"
                )

        for assignment in assignments:
            status = self._clean_text(assignment.status) or ""
            if "no submissions have been made yet" in status.lower():
                urgent_items.append(
                    f"Assignment needs attention | {self._clean_text(assignment.title)} "
                    f"[{self._clean_text(assignment.course.name)}] | {status}"
                )

        if not urgent_items:
            lines.append("- None")
            return lines

        seen: set[str] = set()
        for item in urgent_items:
            if item in seen:
                continue
            seen.add(item)
            lines.append(f"- {item}")
        return lines

    def _clean_text(self, value: str | None) -> str:
        if not value:
            return ""
        return " ".join(html.unescape(value).split())

    def _format_datetime(self, value: datetime) -> str:
        if value.tzinfo is not None:
            localized = value.astimezone(self.local_timezone)
        else:
            # Datetimes loaded from SQLite are naive. We treat them as already in
            # LOCAL_TIMEZONE and do not shift them again in the summary renderer.
            localized = value.replace(tzinfo=self.local_timezone)
        return localized.strftime("%Y-%m-%d %I:%M %p %Z")

    def _is_support_course(self, course_name: str | None) -> bool:
        name = self._clean_text(course_name).lower()
        return any(term in name for term in self.SUPPORT_COURSE_TERMS)
