from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import re
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from src.config import PROJECT_ROOT, settings
from src.db import get_session
from src.models import Course
from src.moodle_browser import _resolve_storage_state_path, launch_chromium


logger = logging.getLogger(__name__)


HELPER_NAME_PATTERNS = [
    re.compile(r"\bcourse is starred\b", re.IGNORECASE),
    re.compile(r"\bcourse name\b", re.IGNORECASE),
]


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


class MoodleScraper:
    """Scrape Moodle pages using the saved Playwright session."""

    def __init__(self) -> None:
        self.storage_state_path = _resolve_storage_state_path()
        self.debug_html_path = PROJECT_ROOT / "data" / "debug_courses_page.html"

    def fetch_courses(self) -> CourseScrapeResult:
        html, final_url = self._load_courses_page_html()
        courses = self._extract_courses_from_html(html, final_url)

        if not courses:
            self._save_debug_html(html)
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

    def _load_courses_page_html(self) -> tuple[str, str]:
        if not self.storage_state_path.exists():
            raise FileNotFoundError(
                f"Saved session file not found at {self.storage_state_path}. "
                "Run scripts/login_moodle.py first."
            )

        with sync_playwright() as playwright:
            browser, context = launch_chromium(playwright, storage_state=self.storage_state_path)
            try:
                page = context.new_page()
                logger.info("Opening Moodle courses page: %s", settings.moodle_courses_url)
                page.goto(settings.moodle_courses_url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle", timeout=10000)
                return page.content(), page.url
            finally:
                context.close()
                browser.close()

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

        candidate_anchors = []
        for selector in selectors:
            matches = soup.select(selector)
            if not matches:
                continue

            for match in matches:
                anchor = match if match.name == "a" else match.find_parent("a")
                if anchor is not None:
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

    def _course_from_anchor(self, anchor, base_url: str) -> DiscoveredCourse | None:
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

    def _normalize_course_url(self, url: str) -> str:
        parsed = urlparse(url)
        cleaned = parsed._replace(fragment="")
        return urlunparse(cleaned)

    def _extract_course_id(self, url: str) -> str | None:
        parsed = urlparse(url)
        course_id = parse_qs(parsed.query).get("id", [None])[0]
        return course_id

    def _save_debug_html(self, html: str) -> None:
        self.debug_html_path.parent.mkdir(parents=True, exist_ok=True)
        self.debug_html_path.write_text(html, encoding="utf-8")

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

    def fetch_assignments(self) -> list[dict]:
        raise NotImplementedError("Assignment scraping has not been implemented yet.")
