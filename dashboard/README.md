# Academic Assistant dashboard

Double-click **Academic Assistant.app** in this folder to open the app at http://127.0.0.1:8767. This starts the server in your normal Mac environment without a Terminal window. Keep the app bundle alongside its supporting files; a Finder alias can be placed elsewhere.

**Update Moodle** reuses your saved session, checks Fall 2026 courses, and updates the existing library and University Courses folders. Progress, partial failures, and newly added or changed files appear in the dashboard. The app must remain running; no schedule is installed.

**Recent Moodle changes** keeps a persistent history independent of the latest update. Updating twice, finding nothing new, losing connection, or restarting the app does not erase earlier findings. The latest 100 entries are displayed, with the full timeline retained locally. Older summaries already overwritten before this upgrade cannot be recovered automatically. No course history or login data is included in Git checkpoints.

Updates try saved Moodle authentication first. If expired, the assistant opens its persistent browser profile and follows UPEI's Microsoft sign-in link. Complete verification only when Microsoft requires it; the update resumes automatically. Reconnect Moodle also opens this profile without clearing it. Closing the browser or timing out preserves the saved session.

The dedicated browser profile lives under `~/Library/Application Support/Academic Assistant/auth` (owner-only directory), separate from your everyday browser and the Documents folder. Existing saved cookies are migrated without overwriting newer browser cookies. Microsoft controls how long sign-in remains valid; a persistent profile cannot bypass MFA or university policies. No passwords are saved by the app itself. The previous localhost:8766 development server is a separate old instance; use the new app address.

The assessment feed is extracted automatically from verified saved Moodle pages and PDF, DOCX, PPTX, Markdown, and text files. Switch between This week, Next 30 days, Needs checking, and All dates; click an entry for source excerpts and file/Moodle links. Recurring pop quizzes remain visible without inventing a date. Conflicting source dates and tentative schedules are flagged. Extraction is cached by content hash; date changes are compared with the previous extraction.

This is conservative rule-based extraction, not exhaustive understanding of every document. Scans/handwriting need OCR or visual review, and skipped/unreadable sources appear under Extraction coverage. Moodle display times remain verbatim until its account timezone is verified. Missing years use the course year. Submission state is not inferred; practice classification requires explicit syllabus/outline evidence. Calendar integration, announcement/forum ingestion, general AI interpretation, and remote phone access remain future work.

Additional extraction dependency: `pypdf>=6,<7` (already installed in the project virtual environment). Reopen the app after this update to replace its idle older service. The bookmark remains http://127.0.0.1:8767.

The service binds to loopback only. Update requests require a same-origin request and a random dashboard token. Do not publish or forward this personal local service to the internet.

## Planner chat

Use **Chat with your planner** for a limited set of local commands: “What do I have this week?”, “Add STAT 2910 quiz this Friday”, “Confirm Concept Deck is due October 8”, or “Update Moodle”. Changes require an explicit preview confirmation; ambiguous requests ask you to resend with the course and exact assessment name. The first version handles dates only, not times, reminders, or general tutoring. “Next Friday” means Friday of next week; the preview always displays the concrete date.

User entries and confirmations persist in ignored `.runtime/chat.sqlite`, survive source refreshes, and are labelled Confirmed by you. If source evidence changes after confirmation, the item is flagged for review without replacing your date. Undo restores the previous user change. Chat text is not sent to an external model; messages in the chat panel reset when the page reloads, while saved edits persist.

The canonical source is now checked into this repository's `dashboard/` directory. The existing Mac launcher uses the deployed copy under Documents/Codex/2026-09-27/can/outputs/dashboard. Deploy source changes with rsync excluding `.runtime`, `__pycache__`, and `.DS_Store`; never copy or commit runtime data.

Implementation reuses the existing project's CourseLibrary, course discovery, and safe exporter. Status is stored locally in `.runtime/sync.json`. Original project tests remain unchanged. Run the dashboard tests using the project's virtual-environment Python with `-m unittest -v test_sync_service` from this folder.
