from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import html
import json
from zoneinfo import ZoneInfo

import requests
from sqlalchemy.orm import selectinload

from src.config import settings
from src.db import get_session
from src.models import Assignment, CalendarEvent, Course, Resource


@dataclass
class UpcomingItem:
    title: str
    when: datetime
    kind: str
    course_name: str | None = None
    status: str | None = None


@dataclass
class SummaryResult:
    rule_summary: str
    llm_summary: str | None
    llm_warning: str | None


class CourseSummarizer:
    """Generate a rule-based academic status summary and optional Ollama brief."""

    SUPPORT_COURSE_TERMS = (
        "moodle support",
        "academic integrity",
        "faculty / staff moodle support",
        "student moodle support",
    )

    def __init__(self) -> None:
        self.local_timezone = ZoneInfo(settings.local_timezone)

    def summarize(self) -> str:
        return self.build_summary().rule_summary

    def build_summary(self, include_llm: bool = True) -> SummaryResult:
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

        facts = self._build_fact_bundle(courses, assignments, resources, calendar_events)
        rule_summary = self._render_rule_summary(facts)

        llm_summary = None
        llm_warning = None
        if include_llm:
            try:
                llm_summary = self._generate_llm_summary(facts)
            except Exception as exc:
                llm_warning = (
                    f"LLM summary skipped: {exc}. "
                    "The rule-based summary above remains the source of truth."
                )

        return SummaryResult(
            rule_summary=rule_summary,
            llm_summary=llm_summary,
            llm_warning=llm_warning,
        )

    def _build_fact_bundle(
        self,
        courses: list[Course],
        assignments: list[Assignment],
        resources: list[Resource],
        calendar_events: list[CalendarEvent],
    ) -> dict:
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
        urgent_items = self._collect_urgent_tasks(calendar_events, assignments, now)

        assignment_status_rows = [
            {
                "title": self._clean_text(assignment.title),
                "course_name": self._clean_text(assignment.course.name),
                "status": self._clean_text(assignment.status) or "missing",
            }
            for assignment in assignments
        ]

        ranked_courses = sorted(
            visible_courses,
            key=lambda course: len(course.assignments) + len(course.resources),
            reverse=True,
        )
        course_item_rows = [
            {
                "course_name": self._clean_text(course.name),
                "total_items": len(course.assignments) + len(course.resources),
                "assignments": len(course.assignments),
                "resources": len(course.resources),
            }
            for course in ranked_courses[:5]
        ]

        recent_resource_rows = [
            {
                "seen_at": self._format_datetime(resource.last_seen_at),
                "title": self._clean_text(resource.title),
                "course_name": self._clean_text(resource.course.name),
                "resource_type": self._clean_text(resource.resource_type) or "resource",
            }
            for resource in visible_resources[:10]
        ]

        return {
            "generated_at": self._format_datetime(now_local),
            "local_timezone": settings.local_timezone,
            "upcoming_next_7_days": [self._serialize_upcoming_item(item) for item in upcoming_next_7],
            "upcoming_days_8_to_30": [self._serialize_upcoming_item(item) for item in upcoming_days_8_to_30],
            "assignment_statuses": assignment_status_rows,
            "courses_with_most_items": course_item_rows,
            "recent_resources": recent_resource_rows,
            "urgent_tasks": urgent_items,
            "support_courses_hidden": {
                "course_count": hidden_support_courses,
                "resource_count": hidden_support_resources,
            },
        }

    def _render_rule_summary(self, facts: dict) -> str:
        lines: list[str] = []
        lines.append("Academic Assistant Summary")
        lines.append(f"Generated: {facts['generated_at']}")
        lines.append("")

        lines.extend(
            self._render_upcoming_section(
                "Upcoming deadlines/events in the next 7 days",
                facts["upcoming_next_7_days"],
                serialized=True,
            )
        )
        lines.append("")
        lines.extend(
            self._render_upcoming_section(
                "Upcoming deadlines/events in the next 30 days",
                facts["upcoming_days_8_to_30"],
                serialized=True,
            )
        )
        lines.append("")
        lines.extend(self._render_assignment_statuses_from_rows(facts["assignment_statuses"]))
        lines.append("")
        lines.extend(
            self._render_courses_with_most_items_from_rows(
                facts["courses_with_most_items"],
                facts["support_courses_hidden"]["course_count"],
            )
        )
        lines.append("")
        lines.extend(
            self._render_recent_resources_from_rows(
                facts["recent_resources"],
                facts["support_courses_hidden"]["resource_count"],
            )
        )
        lines.append("")
        lines.extend(self._render_urgent_tasks_from_rows(facts["urgent_tasks"]))

        return "\n".join(lines).strip() + "\n"

    def _generate_llm_summary(self, facts: dict) -> str:
        llm_facts = self._build_llm_fact_bundle(facts)
        prompt = (
            "You are rewriting a factual academic status summary.\n"
            "Do not include your reasoning.\n"
            "Do not include a thinking section.\n"
            "Return only the final brief.\n"
            "Keep the response under 200 words.\n"
            "Use only the facts provided.\n"
            "Do not invent dates.\n"
            "Do not invent assignments.\n"
            "Do not invent deadlines.\n"
            "Do not infer missing data.\n"
            "Preserve original event wording like 'opens', 'closes', and 'is due'.\n"
            "Do not rewrite 'closes' as 'due' unless the source says 'due'.\n"
            "If unsure, say the data is missing.\n"
            "Organize the response into four short sections:\n"
            "1. Top priorities\n"
            "2. Deadlines to watch\n"
            "3. Assignment status notes\n"
            "4. Suggested study/work order\n"
            "Keep it concise and human-readable.\n\n"
            "Facts:\n"
            f"{json.dumps(llm_facts, indent=2)}"
        )

        response = requests.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
            },
            timeout=180,
        )
        response.raise_for_status()
        data = response.json()
        text = self._clean_text(data.get("response"))
        if not text:
            raise RuntimeError("Ollama returned an empty summary")
        return text

    def _build_llm_fact_bundle(self, facts: dict) -> dict:
        attention_statuses = [
            item
            for item in facts["assignment_statuses"]
            if "no submissions have been made yet" in item["status"].lower()
            or item["status"].lower() == "missing"
        ]

        return {
            "generated_at": facts["generated_at"],
            "local_timezone": facts["local_timezone"],
            "upcoming_next_7_days": facts["upcoming_next_7_days"][:8],
            "upcoming_days_8_to_30": facts["upcoming_days_8_to_30"][:8],
            "urgent_tasks": facts["urgent_tasks"][:8],
            "assignment_statuses_needing_attention": attention_statuses[:8],
            "courses_with_most_items": facts["courses_with_most_items"][:5],
        }

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

    def _serialize_upcoming_item(self, item: UpcomingItem) -> dict:
        return {
            "title": item.title,
            "when": self._format_datetime(item.when),
            "kind": item.kind,
            "course_name": item.course_name,
            "status": item.status,
        }

    def _render_upcoming_section(self, title: str, items: list, serialized: bool = False) -> list[str]:
        lines = [title]
        if not items:
            lines.append("- None")
            return lines

        for item in items:
            if serialized:
                when_text = item["when"]
                label = item["title"]
                if item.get("course_name"):
                    label = f"{label} [{item['course_name']}]"
                if item.get("status"):
                    label = f"{label} ({item['status']})"
            else:
                when_text = self._format_datetime(item.when)
                label = item.title
                if item.course_name:
                    label = f"{label} [{item.course_name}]"
                if item.status:
                    label = f"{label} ({item.status})"
            lines.append(f"- {when_text} | {label}")
        return lines

    def _render_assignment_statuses_from_rows(self, assignments: list[dict]) -> list[str]:
        lines = ["Assignment statuses"]
        if not assignments:
            lines.append("- None")
            return lines

        for assignment in assignments:
            lines.append(f"- {assignment['title']} [{assignment['course_name']}] | {assignment['status']}")
        return lines

    def _render_courses_with_most_items_from_rows(self, courses: list[dict], hidden_support_courses: int) -> list[str]:
        lines = ["Courses with the most resources/items"]
        if not courses:
            lines.append("- None")
            if hidden_support_courses:
                lines.append("Support courses hidden from resource summary.")
            return lines

        for course in courses:
            lines.append(
                f"- {course['course_name']} | {course['total_items']} total items "
                f"({course['assignments']} assignments, {course['resources']} resources)"
            )
        if hidden_support_courses:
            lines.append("Support courses hidden from resource summary.")
        return lines

    def _render_recent_resources_from_rows(self, resources: list[dict], hidden_support_resources: int) -> list[str]:
        lines = ["Recently seen resources"]
        if not resources:
            lines.append("- None")
            if hidden_support_resources:
                lines.append("Support courses hidden from resource summary.")
            return lines

        for resource in resources:
            lines.append(
                f"- {resource['seen_at']} | {resource['title']} "
                f"[{resource['course_name']}] ({resource['resource_type']})"
            )
        if hidden_support_resources:
            lines.append("Support courses hidden from resource summary.")
        return lines

    def _collect_urgent_tasks(
        self,
        calendar_events: list[CalendarEvent],
        assignments: list[Assignment],
        now: datetime,
    ) -> list[str]:
        urgent_items: list[str] = []
        soon = now + timedelta(hours=48)

        for event in calendar_events:
            title = self._clean_text(event.title).lower()
            if event.start_at <= soon and event.start_at >= now:
                urgent_items.append(f"{self._format_datetime(event.start_at)} | {self._clean_text(event.title)}")
                continue

            if any(keyword in title for keyword in ["due", "closes", "exam", "quiz"]) and now <= event.start_at <= (
                now + timedelta(days=7)
            ):
                urgent_items.append(f"{self._format_datetime(event.start_at)} | {self._clean_text(event.title)}")

        for assignment in assignments:
            status = self._clean_text(assignment.status) or ""
            if "no submissions have been made yet" in status.lower():
                urgent_items.append(
                    f"Assignment needs attention | {self._clean_text(assignment.title)} "
                    f"[{self._clean_text(assignment.course.name)}] | {status}"
                )

        seen: set[str] = set()
        deduped: list[str] = []
        for item in urgent_items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _render_urgent_tasks_from_rows(self, urgent_items: list[str]) -> list[str]:
        lines = ["Possible urgent tasks"]
        if not urgent_items:
            lines.append("- None")
            return lines

        for item in urgent_items:
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
