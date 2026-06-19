from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
from pathlib import Path
import re
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import sync_playwright

from src.config import PROJECT_ROOT, settings
from src.db import get_session
from src.models import Assignment, Course, Resource
from src.moodle_browser import _resolve_storage_state_path, launch_chromium


logger = logging.getLogger(__name__)


HELPER_NAME_PATTERNS = [
    re.compile(r"\bcourse is starred\b", re.IGNORECASE),
    re.compile(r"\bcourse name\b", re.IGNORECASE),
]

RESOURCE_MODULE_TYPES = {"resource", "url", "page", "folder", "quiz", "forum", "label"}


@dataclass
class DiscoveredCourse:
    name: str
    url: str
    moodle_course_id: str | None = None
    short_name: str | None = None


@dataclass
class CourseScrapeResult:
    found_count: int
    inserted_count: int
    updated_count: int
    courses: list[DiscoveredCourse]
    debug_html_path: Path | None = None


@dataclass
class DiscoveredAssignment:
    title: str
    url: str | None
    description: str | None
    status: str | None
    source_uid: str | None


@dataclass
class DiscoveredResource:
    title: str
    url: str
    resource_type: str | None
    section_title: str | None


@dataclass
class PerCourseContentResult:
    course_name: str
    assignments_found: int
    resources_found: int
    inserted_count: int
    updated_count: int
    error: str | None = None
    debug_html_path: Path | None = None


@dataclass
class CourseContentScrapeResult:
    course_results: list[PerCourseContentResult]


@dataclass
class AssignmentDetailResult:
    assignment_title: str
    due_at_found: bool
    status_found: bool
    updated_count: int
    error: str | None = None
    debug_html_path: Path | None = None


def clean_course_name(raw_name: str) -> str:
    cleaned = " ".join(raw_name.split())

    for pattern in HELPER_NAME_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    cleaned = " ".join(cleaned.split())

    words = cleaned.split()
    if len(words) % 2 == 0:
        half = len(words) // 2
        if words[:half] == words[half:]:
            cleaned = " ".join(words[:half])

    for size in range(len(words) // 2, 1, -1):
        left = " ".join(words[:size])
        right = " ".join(words[size : size * 2])
        if left and left == right:
            cleaned = left
            break

    return " ".join(cleaned.split())


def clean_text(raw_text: str | None) -> str | None:
    if not raw_text:
        return None
    cleaned = " ".join(raw_text.split())
    return cleaned or None


def clean_label_text(raw_text: str | None) -> str | None:
    cleaned = clean_text(raw_text)
    if not cleaned:
        return None
    cleaned = cleaned.rstrip(":").strip()
    return cleaned or None


class MoodleScraper:
    """Scrape Moodle pages using the saved Playwright session."""

    def __init__(self) -> None:
        self.storage_state_path = _resolve_storage_state_path()
        self.debug_html_path = PROJECT_ROOT / "data" / "debug_courses_page.html"
        self.debug_dir = PROJECT_ROOT / "data" / "debug"

    def fetch_courses(self) -> CourseScrapeResult:
        html, final_url = self._load_page_html(settings.moodle_courses_url)
        courses = self._extract_courses_from_html(html, final_url)

        if not courses:
            self._save_debug_html(html, self.debug_html_path)
            logger.warning("No courses found. Saved debug HTML to %s", self.debug_html_path)
            return CourseScrapeResult(
                found_count=0,
                inserted_count=0,
                updated_count=0,
                courses=[],
                debug_html_path=self.debug_html_path,
            )

        inserted_count, updated_count = self._upsert_courses(courses)
        return CourseScrapeResult(
            found_count=len(courses),
            inserted_count=inserted_count,
            updated_count=updated_count,
            courses=courses,
        )

    def fetch_assignments_and_resources(self) -> CourseContentScrapeResult:
        courses = self._load_courses_from_db()
        if not courses:
            raise RuntimeError("No courses found in the database. Run scripts/scrape_courses.py first.")

        results: list[PerCourseContentResult] = []

        with sync_playwright() as playwright:
            browser, context = launch_chromium(playwright, storage_state=self.storage_state_path)
            try:
                page = context.new_page()

                for course in courses:
                    try:
                        result = self._scrape_single_course(page, course)
                    except Exception as exc:
                        logger.exception("Failed scraping course %s", course.name)
                        debug_path = None
                        try:
                            debug_path = self._course_debug_path(course)
                            self._save_debug_html(page.content(), debug_path)
                        except Exception:
                            logger.exception("Failed saving debug HTML for course %s", course.name)
                        result = PerCourseContentResult(
                            course_name=course.name,
                            assignments_found=0,
                            resources_found=0,
                            inserted_count=0,
                            updated_count=0,
                            error=str(exc),
                            debug_html_path=debug_path,
                        )
                    results.append(result)
            finally:
                context.close()
                browser.close()

        return CourseContentScrapeResult(course_results=results)

    def enrich_assignment_details(self) -> list[AssignmentDetailResult]:
        assignments = self._load_assignments_for_enrichment()
        if not assignments:
            raise RuntimeError("No Moodle assignment rows found. Run scripts/scrape_assignments.py first.")

        results: list[AssignmentDetailResult] = []

        with sync_playwright() as playwright:
            browser, context = launch_chromium(playwright, storage_state=self.storage_state_path)
            try:
                page = context.new_page()

                for assignment in assignments:
                    try:
                        result = self._enrich_single_assignment(page, assignment)
                    except Exception as exc:
                        logger.exception("Failed enriching assignment %s", assignment.title)
                        debug_path = None
                        try:
                            debug_path = self._assignment_debug_path(assignment.id)
                            self._save_debug_html(page.content(), debug_path)
                        except Exception:
                            logger.exception("Failed saving debug HTML for assignment %s", assignment.title)
                        result = AssignmentDetailResult(
                            assignment_title=assignment.title,
                            due_at_found=assignment.due_at is not None,
                            status_found=bool(assignment.status),
                            updated_count=0,
                            error=str(exc),
                            debug_html_path=debug_path,
                        )
                    results.append(result)
            finally:
                context.close()
                browser.close()

        return results

    def _load_courses_from_db(self) -> list[Course]:
        session = get_session()
        try:
            return session.query(Course).order_by(Course.name.asc()).all()
        finally:
            session.close()

    def _load_assignments_for_enrichment(self) -> list[Assignment]:
        session = get_session()
        try:
            return (
                session.query(Assignment)
                .filter(Assignment.url.is_not(None))
                .filter(Assignment.url.contains("/mod/assign/"))
                .order_by(Assignment.title.asc())
                .all()
            )
        finally:
            session.close()

    def _load_page_html(self, url: str) -> tuple[str, str]:
        if not self.storage_state_path.exists():
            raise FileNotFoundError(
                f"Saved session file not found at {self.storage_state_path}. "
                "Run scripts/login_moodle.py first."
            )

        with sync_playwright() as playwright:
            browser, context = launch_chromium(playwright, storage_state=self.storage_state_path)
            try:
                page = context.new_page()
                logger.info("Opening page: %s", url)
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=10000)
                return page.content(), page.url
            finally:
                context.close()
                browser.close()

    def _scrape_single_course(self, page, course: Course) -> PerCourseContentResult:
        logger.info("Opening course page: %s", course.url)
        page.goto(course.url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)

        html = page.content()
        assignments, resources = self._extract_course_content_from_html(html, page.url)

        debug_path: Path | None = None
        if not assignments and not resources:
            debug_path = self._course_debug_path(course)
            self._save_debug_html(html, debug_path)

        inserted_count, updated_count = self._upsert_course_content(course, assignments, resources)

        return PerCourseContentResult(
            course_name=course.name,
            assignments_found=len(assignments),
            resources_found=len(resources),
            inserted_count=inserted_count,
            updated_count=updated_count,
            debug_html_path=debug_path,
        )

    def _enrich_single_assignment(self, page, assignment: Assignment) -> AssignmentDetailResult:
        if not assignment.url:
            raise ValueError("Assignment is missing a URL.")

        logger.info("Opening assignment page: %s", assignment.url)
        page.goto(assignment.url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=10000)

        html = page.content()
        details = self._extract_assignment_details_from_html(html)

        useful_details_found = any(
            [
                details["due_at"] is not None,
                details["open_at"] is not None,
                details["close_at"] is not None,
                details["description"] is not None,
                details["status"] is not None,
            ]
        )

        debug_path: Path | None = None
        if not useful_details_found:
            debug_path = self._assignment_debug_path(assignment.id)
            self._save_debug_html(html, debug_path)

        updated_count = self._update_assignment_details(assignment.id, details)
        return AssignmentDetailResult(
            assignment_title=assignment.title,
            due_at_found=details["due_at"] is not None,
            status_found=details["status"] is not None,
            updated_count=updated_count,
            debug_html_path=debug_path,
        )

    def _extract_courses_from_html(self, html: str, base_url: str) -> list[DiscoveredCourse]:
        soup = BeautifulSoup(html, "html.parser")
        seen_urls: set[str] = set()
        courses: list[DiscoveredCourse] = []

        selectors = [
            "a.courseitem .coursename",
            ".coursebox a[href*='/course/view.php']",
            ".card.dashboard-card a[href*='/course/view.php']",
            ".coursename a[href*='/course/view.php']",
            "a.aalink[href*='/course/view.php']",
            "a[href*='/course/view.php']",
        ]

        candidate_anchors: list[Tag] = []
        for selector in selectors:
            matches = soup.select(selector)
            if not matches:
                continue

            for match in matches:
                anchor = match if match.name == "a" else match.find_parent("a")
                if isinstance(anchor, Tag):
                    candidate_anchors.append(anchor)

        if not candidate_anchors:
            for anchor in soup.find_all("a", href=True):
                href = anchor.get("href", "")
                if "/course/view.php" in href or "/course/" in href:
                    candidate_anchors.append(anchor)

        for anchor in candidate_anchors:
            course = self._course_from_anchor(anchor, base_url)
            if course is None or course.url in seen_urls:
                continue

            seen_urls.add(course.url)
            courses.append(course)

        return courses

    def _extract_course_content_from_html(
        self,
        html: str,
        base_url: str,
    ) -> tuple[list[DiscoveredAssignment], list[DiscoveredResource]]:
        soup = BeautifulSoup(html, "html.parser")
        assignments: list[DiscoveredAssignment] = []
        resources: list[DiscoveredResource] = []
        seen_assignment_keys: set[str] = set()
        seen_resource_keys: set[str] = set()

        activity_nodes = soup.select(
            "li.activity, li.activity-item, div.activity, div.activity-item, li[id^='module-'], div[id^='module-']"
        )

        for node in activity_nodes:
            if not isinstance(node, Tag) or self._is_hidden(node):
                continue

            section_title = self._extract_section_title(node)
            module_type = self._detect_module_type(node)

            if module_type == "label":
                resource = self._label_resource_from_node(node, base_url, section_title)
                if resource is not None:
                    key = resource.url
                    if key not in seen_resource_keys:
                        seen_resource_keys.add(key)
                        resources.append(resource)
                continue

            anchor = self._find_primary_anchor(node)
            if anchor is None:
                continue

            href = anchor.get("href")
            if not href:
                continue

            absolute_url = self._normalize_course_url(urljoin(base_url, href))
            title = self._extract_item_title(node, anchor)
            if not title:
                continue

            description = self._extract_item_description(node)
            source_uid = self._extract_source_uid(node, absolute_url)

            if module_type == "assign":
                assignment = DiscoveredAssignment(
                    title=title,
                    url=absolute_url,
                    description=description,
                    status=None,
                    source_uid=source_uid,
                )
                key = assignment.url or assignment.source_uid or f"{title}|assign"
                if key not in seen_assignment_keys:
                    seen_assignment_keys.add(key)
                    assignments.append(assignment)
                continue

            if module_type in RESOURCE_MODULE_TYPES - {"label"}:
                resource = DiscoveredResource(
                    title=title,
                    url=absolute_url,
                    resource_type=module_type,
                    section_title=section_title,
                )
                key = resource.url
                if key not in seen_resource_keys:
                    seen_resource_keys.add(key)
                    resources.append(resource)

        return assignments, resources

    def _extract_assignment_details_from_html(self, html: str) -> dict[str, str | datetime | None]:
        soup = BeautifulSoup(html, "html.parser")

        details: dict[str, str | datetime | None] = {
            "due_at": None,
            "open_at": None,
            "close_at": None,
            "description": None,
            "status": None,
        }

        description = self._extract_assignment_description(soup)
        if description:
            details["description"] = description

        for label, value in self._extract_labeled_values(soup).items():
            normalized = label.lower()
            clean_value = clean_text(value)
            if not clean_value:
                continue

            if normalized in {"due", "due date"}:
                parsed = self._parse_moodle_datetime(clean_value)
                if parsed is None:
                    logger.warning("Could not parse due date text: %s", clean_value)
                details["due_at"] = parsed
                continue

            if normalized in {"opened", "opening date", "allow submissions from", "available from"}:
                parsed = self._parse_moodle_datetime(clean_value)
                if parsed is None:
                    logger.warning("Could not parse open date text: %s", clean_value)
                details["open_at"] = parsed
                continue

            if normalized in {"cut-off date", "cutoff date", "closing date", "close date", "due date (cut-off)"}:
                parsed = self._parse_moodle_datetime(clean_value)
                if parsed is None:
                    logger.warning("Could not parse close date text: %s", clean_value)
                details["close_at"] = parsed
                continue

            if normalized in {"submission status", "status"}:
                details["status"] = clean_value

        if details["status"] is None:
            status = self._extract_submission_status(soup)
            if status:
                details["status"] = status

        return details

    def _course_from_anchor(self, anchor: Tag, base_url: str) -> DiscoveredCourse | None:
        href = anchor.get("href")
        if not href:
            return None

        absolute_url = self._normalize_course_url(urljoin(base_url, href))
        if "/course/view.php" not in absolute_url and "/course/" not in absolute_url:
            return None

        raw_name = " ".join(anchor.stripped_strings)
        if not raw_name:
            heading = anchor.find(["h3", "h4", "span", "div"])
            if heading is not None:
                raw_name = " ".join(heading.stripped_strings)

        name = clean_course_name(raw_name)
        if not name or len(name) < 2:
            return None

        course_id = self._extract_course_id(absolute_url)
        short_name = None

        title_attr = anchor.get("title")
        if title_attr:
            title_attr = " ".join(title_attr.split())
            if title_attr and title_attr != name:
                short_name = title_attr

        return DiscoveredCourse(
            name=name,
            url=absolute_url,
            moodle_course_id=course_id,
            short_name=short_name,
        )

    def _extract_assignment_description(self, soup: BeautifulSoup) -> str | None:
        selectors = [
            "[data-region='activity-description']",
            ".activity-description",
            ".intro",
            "#intro",
            ".box.generalbox.boxaligncenter",
            ".assignintro",
        ]
        for selector in selectors:
            element = soup.select_one(selector)
            if isinstance(element, Tag):
                text = clean_text(element.get_text(" ", strip=True))
                if text:
                    return text
        return None

    def _extract_labeled_values(self, soup: BeautifulSoup) -> dict[str, str]:
        values: dict[str, str] = {}

        for row in soup.select("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) >= 2:
                label = clean_label_text(cells[0].get_text(" ", strip=True))
                value = clean_text(cells[1].get_text(" ", strip=True))
                if label and value:
                    values.setdefault(label, value)

        for item in soup.select("dt"):
            sibling = item.find_next_sibling("dd")
            if sibling is None:
                continue
            label = clean_label_text(item.get_text(" ", strip=True))
            value = clean_text(sibling.get_text(" ", strip=True))
            if label and value:
                values.setdefault(label, value)

        for container in soup.select(".submissionstatustable, .generaltable"):
            for row in container.select("tr"):
                headers = row.select("th")
                cells = row.select("td")
                if headers and cells:
                    label = clean_label_text(headers[0].get_text(" ", strip=True))
                    value = clean_text(cells[0].get_text(" ", strip=True))
                    if label and value:
                        values.setdefault(label, value)

        return values

    def _extract_submission_status(self, soup: BeautifulSoup) -> str | None:
        status_labels = ["submission status", "status"]
        for label, value in self._extract_labeled_values(soup).items():
            if label.lower() in status_labels and value:
                return value

        for selector in [".submissionstatussubmitted", ".submissionstatus", ".badge"]:
            for element in soup.select(selector):
                if isinstance(element, Tag):
                    text = clean_text(element.get_text(" ", strip=True))
                    if text and "status" not in text.lower():
                        return text
        return None

    def _parse_moodle_datetime(self, raw_text: str) -> datetime | None:
        cleaned = clean_text(raw_text)
        if not cleaned:
            return None

        lowered = cleaned.lower()
        if lowered in {"-", "none", "no due date", "not set"}:
            return None

        cleaned = re.sub(r"^[A-Za-z]+,\s*", "", cleaned)
        cleaned = re.sub(r"\s*\([^)]*\)$", "", cleaned).strip()
        cleaned = cleaned.replace(" a.m.", " AM").replace(" p.m.", " PM")
        cleaned = cleaned.replace(" a.m", " AM").replace(" p.m", " PM")
        cleaned = cleaned.replace(" am", " AM").replace(" pm", " PM")
        cleaned = re.sub(r"\bat\b", ",", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
        cleaned = " ".join(cleaned.split())

        formats = [
            "%d %B %Y, %I:%M %p",
            "%d %b %Y, %I:%M %p",
            "%d %B %Y, %H:%M",
            "%d %b %Y, %H:%M",
            "%d %B %Y",
            "%d %b %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue

        return None

    def _find_primary_anchor(self, node: Tag) -> Tag | None:
        selectors = [
            "a[data-region='activity-name']",
            ".activityname a",
            "a.aalink.stretched-link",
            "a.stretched-link",
            "a.aalink",
            "a[href]",
        ]
        for selector in selectors:
            anchor = node.select_one(selector)
            if isinstance(anchor, Tag) and anchor.get("href"):
                return anchor
        return None

    def _extract_item_title(self, node: Tag, anchor: Tag) -> str | None:
        title_candidates = [
            anchor.select_one(".instancename"),
            anchor.select_one(".activityname"),
            node.select_one(".instancename"),
            node.select_one(".activityname"),
            node.select_one("h3"),
            node.select_one("h4"),
            anchor,
        ]
        for candidate in title_candidates:
            if isinstance(candidate, Tag):
                text = clean_text(candidate.get_text(" ", strip=True))
                if text:
                    return clean_course_name(text)
        return None

    def _extract_item_description(self, node: Tag) -> str | None:
        selectors = [
            ".description",
            ".contentafterlink",
            ".activity-description",
            ".availabilityinfo",
            ".contentwithoutlink",
        ]
        parts: list[str] = []
        for selector in selectors:
            for element in node.select(selector):
                if isinstance(element, Tag):
                    text = clean_text(element.get_text(" ", strip=True))
                    if text:
                        parts.append(text)
        if not parts:
            return None
        return " | ".join(dict.fromkeys(parts))

    def _extract_section_title(self, node: Tag) -> str | None:
        section = node.find_parent(["li", "section"], class_=re.compile(r"section", re.IGNORECASE))
        if not isinstance(section, Tag):
            return None

        for selector in [".sectionname", "h3.sectionname", "h4.sectionname", "[data-for='section_title']"]:
            element = section.select_one(selector)
            if isinstance(element, Tag):
                text = clean_text(element.get_text(" ", strip=True))
                if text:
                    return text
        return None

    def _detect_module_type(self, node: Tag) -> str | None:
        classes = node.get("class", [])
        for class_name in classes:
            if class_name.startswith("modtype_"):
                return class_name.removeprefix("modtype_")

        anchor = self._find_primary_anchor(node)
        if isinstance(anchor, Tag):
            href = anchor.get("href", "")
            for module_type in ["assign", "resource", "url", "page", "folder", "quiz", "forum", "label"]:
                if f"/mod/{module_type}/" in href:
                    return module_type

        return None

    def _extract_source_uid(self, node: Tag, url: str | None) -> str | None:
        module_id = node.get("id")
        if module_id:
            return module_id

        if url:
            parsed = urlparse(url)
            query_id = parse_qs(parsed.query).get("id", [None])[0]
            if query_id:
                return f"id={query_id}"

        return None

    def _label_resource_from_node(self, node: Tag, base_url: str, section_title: str | None) -> DiscoveredResource | None:
        text = clean_text(node.get_text(" ", strip=True))
        if not text:
            return None

        digest = hashlib.sha1(f"{section_title}|{text}".encode("utf-8")).hexdigest()[:12]
        synthetic_url = f"{self._normalize_course_url(base_url)}#label-{digest}"
        return DiscoveredResource(
            title=text,
            url=synthetic_url,
            resource_type="label",
            section_title=section_title,
        )

    def _is_hidden(self, node: Tag) -> bool:
        if node.get("hidden") is not None or node.get("aria-hidden") == "true":
            return True

        classes = set(node.get("class", []))
        hidden_classes = {"hidden", "sr-only", "accesshide", "d-none"}
        return bool(classes & hidden_classes)

    def _normalize_course_url(self, url: str) -> str:
        parsed = urlparse(url)
        cleaned = parsed._replace(fragment="")
        return urlunparse(cleaned)

    def _extract_course_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get("id", [None])[0]

    def _course_debug_path(self, course: Course) -> Path:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", course.name).strip("_") or f"course_{course.id}"
        return self.debug_dir / f"course_{course.id}_{slug}.html"

    def _assignment_debug_path(self, assignment_id: int) -> Path:
        return self.debug_dir / f"assignment_{assignment_id}.html"

    def _save_debug_html(self, html: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    def _upsert_courses(self, courses: list[DiscoveredCourse]) -> tuple[int, int]:
        inserted_count = 0
        updated_count = 0
        now = datetime.utcnow()

        session = get_session()
        try:
            existing_courses = {
                course.url: course
                for course in session.query(Course).filter(Course.url.in_([course.url for course in courses])).all()
            }

            for discovered in courses:
                existing = existing_courses.get(discovered.url)
                if existing is None:
                    session.add(
                        Course(
                            moodle_course_id=discovered.moodle_course_id,
                            name=discovered.name,
                            short_name=discovered.short_name,
                            url=discovered.url,
                            visible=True,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    inserted_count += 1
                    continue

                existing.moodle_course_id = discovered.moodle_course_id
                existing.name = discovered.name
                existing.short_name = discovered.short_name
                existing.visible = True
                existing.updated_at = now
                updated_count += 1

            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        logger.info(
            "Course scrape complete: found=%s inserted=%s updated=%s",
            len(courses),
            inserted_count,
            updated_count,
        )
        return inserted_count, updated_count

    def _upsert_course_content(
        self,
        course: Course,
        assignments: list[DiscoveredAssignment],
        resources: list[DiscoveredResource],
    ) -> tuple[int, int]:
        session = get_session()
        inserted_count = 0
        updated_count = 0
        now = datetime.utcnow()

        try:
            assignment_rows = session.query(Assignment).filter(Assignment.course_id == course.id).all()
            resource_rows = session.query(Resource).filter(Resource.course_id == course.id).all()

            assignment_by_url = {row.url: row for row in assignment_rows if row.url}
            assignment_by_uid = {row.source_uid: row for row in assignment_rows if row.source_uid}
            resource_by_url = {row.url: row for row in resource_rows if row.url}

            for item in assignments:
                existing = None
                if item.url:
                    existing = assignment_by_url.get(item.url)
                if existing is None and item.source_uid:
                    existing = assignment_by_uid.get(item.source_uid)

                if existing is None:
                    session.add(
                        Assignment(
                            course_id=course.id,
                            title=item.title,
                            url=item.url,
                            description=item.description,
                            due_at=None,
                            open_at=None,
                            close_at=None,
                            status=item.status,
                            source="moodle_scrape",
                            source_uid=item.source_uid,
                            created_at=now,
                            updated_at=now,
                            last_seen_at=now,
                        )
                    )
                    inserted_count += 1
                    continue

                existing.title = item.title
                existing.url = item.url
                existing.description = item.description
                existing.status = item.status
                existing.source = "moodle_scrape"
                existing.source_uid = item.source_uid
                existing.updated_at = now
                existing.last_seen_at = now
                updated_count += 1

            for item in resources:
                existing = resource_by_url.get(item.url)

                if existing is None:
                    session.add(
                        Resource(
                            course_id=course.id,
                            title=item.title,
                            url=item.url,
                            resource_type=item.resource_type,
                            section_title=item.section_title,
                            created_at=now,
                            updated_at=now,
                            last_seen_at=now,
                        )
                    )
                    inserted_count += 1
                    continue

                existing.title = item.title
                existing.resource_type = item.resource_type
                existing.section_title = item.section_title
                existing.updated_at = now
                existing.last_seen_at = now
                updated_count += 1

            session.commit()
            return inserted_count, updated_count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _update_assignment_details(self, assignment_id: int, details: dict[str, str | datetime | None]) -> int:
        session = get_session()
        try:
            assignment = session.query(Assignment).filter(Assignment.id == assignment_id).one()
            assignment.due_at = details["due_at"]  # type: ignore[assignment]
            assignment.open_at = details["open_at"]  # type: ignore[assignment]
            assignment.close_at = details["close_at"]  # type: ignore[assignment]
            assignment.description = details["description"]  # type: ignore[assignment]
            assignment.status = details["status"]  # type: ignore[assignment]
            assignment.updated_at = datetime.utcnow()
            assignment.last_seen_at = datetime.utcnow()
            session.commit()
            return 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
