# Academic Assistant dashboard

Double-click **Academic Assistant.app** in this folder to open the app at http://127.0.0.1:8767. This starts the server in your normal Mac environment without a Terminal window. Keep the app bundle alongside its supporting files; a Finder alias can be placed elsewhere.

**Update Moodle** reuses your saved session, checks Fall 2026 courses, and updates the existing library and University Courses folders. Progress, partial failures, and newly added or changed files appear in the dashboard. The app must remain running; no schedule is installed.

**Recent Moodle changes** keeps a persistent history independent of the latest update. Updating twice, finding nothing new, losing connection, or restarting the app does not erase earlier findings. The latest 100 entries are displayed, with the full timeline retained locally. Older summaries already overwritten before this upgrade cannot be recovered automatically. No course history or login data is included in Git checkpoints.

Updates try saved Moodle authentication first. If expired, the assistant opens its persistent browser profile and follows UPEI's Microsoft sign-in link. Complete verification only when Microsoft requires it; the update resumes automatically. Reconnect Moodle also opens this profile without clearing it. Closing the browser or timing out preserves the saved session.

The dedicated browser profile lives under `~/Library/Application Support/Academic Assistant/auth` (owner-only directory), separate from your everyday browser and the Documents folder. Existing saved cookies are migrated without overwriting newer browser cookies. Microsoft controls how long sign-in remains valid; a persistent profile cannot bypass MFA or university policies. No passwords are saved by the app itself. The previous localhost:8766 development server is a separate old instance; use the new app address.

The assessment feed is extracted automatically from verified saved Moodle pages and PDF, DOCX, PPTX, Markdown, and text files. Switch between This week, Next 30 days, Needs checking, and All dates; click an entry for source excerpts and file/Moodle links. Recurring pop quizzes remain visible without inventing a date. Conflicting source dates and tentative schedules are flagged. Extraction is cached by content hash; date changes are compared with the previous extraction.

This is conservative rule-based extraction, not exhaustive understanding of every document. Scans/handwriting need OCR or visual review, and skipped/unreadable sources appear under Extraction coverage. Moodle display times remain verbatim until its account timezone is verified. Missing years use the course year. Submission state is not inferred; practice classification requires explicit syllabus/outline evidence. Calendar integration, announcement/forum ingestion, general AI interpretation, and remote phone access remain future work.

Additional extraction dependency: `pypdf>=6,<7` (already installed in the project virtual environment). Reopen the app after this update to replace its idle older service. The bookmark remains http://127.0.0.1:8767.

### Extraction audit update — October 2, 2026

Install the local reader dependencies with the project Python and `pip install -r dashboard/requirements-extraction.txt`. Tesseract is also required for OCR; it is already installed on this Mac. PDF rendering uses the app's own Python dependencies, not a Codex runtime. Low-text PDF pages and image files receive bounded English OCR. OCR-derived events remain review-only. The reader also handles CSV/TSV, HTML, JSON, XLSX cached values and OpenDocument files. Unsupported, encrypted, oversized, unreadable or partially processed documents are explicitly reported in Extraction coverage. XLSX numeric dates and formulas still need review; there is no guarantee that every assessment has been recognized.

The date parser preserves assignments whose topics include “Sample Spaces”, correctly distinguishes “Quiz 1 October 20” from October 1, and flags ranges, historical dates and conflicting final-exam dates. Source hashes are verified before extraction, local file changes invalidate the cache, and subsequent Moodle downloads include page checksums. Older pages without checksums are held for verification until the next download. Failed OCR is retried on the next extraction rebuild. Limits: 100 MB per file, 500 PDF pages, 100 OCR pages per PDF and 20 image frames. Exceeding these limits is reported rather than silently treated as complete.

This is the local extraction foundation. Account-based AI fallback and standalone Google Calendar synchronization are not connected yet. The agreed workflow is user-triggered Update, followed by extraction and calendar sync; no background schedule is installed.

The service binds to loopback only. Update requests require a same-origin request and a random dashboard token. Do not publish or forward this personal local service to the internet.

## Planner chat

Use **Chat with your planner** for a limited set of local commands: “What do I have this week?”, “Add STAT 2910 quiz this Friday”, “Confirm Concept Deck is due October 8”, or “Update Moodle”. Changes require an explicit preview confirmation; ambiguous requests ask you to resend with the course and exact assessment name. The first version handles dates only, not times, reminders, or general tutoring. “Next Friday” means Friday of next week; the preview always displays the concrete date.

User entries and confirmations persist in ignored `.runtime/chat.sqlite`, survive source refreshes, and are labelled Confirmed by you. If source evidence changes after confirmation, the item is flagged for review without replacing your date. Undo restores the previous user change. Chat text is not sent to an external model; messages in the chat panel reset when the page reloads, while saved edits persist.

The canonical source is now checked into this repository's `dashboard/` directory. The existing Mac launcher uses the deployed copy under Documents/Codex/2026-09-27/can/outputs/dashboard. Deploy source changes with rsync excluding `.runtime`, `__pycache__`, and `.DS_Store`; never copy or commit runtime data.

Implementation reuses the existing project's CourseLibrary, course discovery, and safe exporter. Status is stored locally in `.runtime/sync.json`. Original project tests remain unchanged. Run the dashboard tests using the project's virtual-environment Python with `-m unittest -v test_sync_service` from this folder.


## Google Calendar (version 10)

App-owned Desktop OAuth; no Codex/ChatGPT service dependency. Reopen Academic Assistant.app, connect Google, then enable syncing. Credentials and tokens live in ignored `data/calendar/` with owner-only permissions. OAuth uses PKCE, expiring single-use state, and only calendar.app.created scope. The callback never logs authorization codes.

Clicking Update Moodle runs Google sync after course downloads finish. Sync calendar now retries independently. There is no daily scheduler. Confirmed planner changes also trigger sync. Keep the service running until complete.

Moodle's authenticated calendar export is refreshed using the existing Moodle session; secret export URLs are neither logged nor saved. Only Fall 2026 course assessments are used; attendance and other courses are excluded. Stable Moodle event UIDs distinguish repeated tests and preserve identity on rescheduling. Explicit Moodle calendar dates/times take priority over document matching for the same named assessment, while user confirmations remain authoritative. The syllabus's practice-only assignment policy is retained. Failed exports do not reuse stale dates for new writes. The dashboard and Google preview use the same merged data.

Timezone-aware Moodle times are converted to America/Halifax (including daylight-saving transitions). Zero-duration deadlines use one-minute calendar markers. Document-only dates remain all-day. Popup reminders are 24 hours and one hour before timed events, or 9 a.m. the previous day for all-day events. The user's Google Calendar/device notifications must be enabled for delivery.

Upcoming clear dates only: uncertain, tentative, practice, past, and ambiguous repeated names are held back. Duplicate inserts use deterministic event IDs; retries use bounded backoff. Timestamp/reminder normalization avoids mistaking Google's formatting for manual edits. User edits and deletions are preserved. Explicit Moodle cancellations remove only unchanged app-managed events. Missing/uncertain sources alone never delete an event; the dashboard warns. An uncertain calendar-creation outcome is held for manual recovery to avoid creating duplicate calendars. Definite creation rejections can be retried. Reconnect the original Google account; account switching is not supported.

External OAuth apps in Google's Testing mode receive refresh tokens expiring after seven days. Production publishing must be configured in Google Auth Platform for long-term use, subject to Google's requirements. Disconnect removes local tokens but keeps existing Google events. Revoke the grant in Google account settings if desired.

Validation: run dashboard and project unittest suites. Fake transports cover retries, reschedules, duplicate prevention, timezones, cancellations, manual edits, and OAuth checks. Real Google authorization and live sync require user consent; don't treat passing local tests as proof of that connection.
