# Architecture and SQL walkthrough

## Current data flow

```text
Interactive Moodle sign-in → Playwright course traversal
  → verified originals + JSON manifests + readable pages
      → local document reader → source-linked assessments
          → local calendar preview → eligible Google Calendar writes
      → SQLite library audit → coverage and file-size reports
```

The dashboard is a loopback Python HTTP server with a plain JavaScript frontend.
Moodle and Google are external dependencies; a failure should not erase saved
course files. Uncertain extraction is deliberately distinct from confirmed dates.

## Storage boundaries

| Store | Role |
| --- | --- |
| Course manifests and files | Authoritative downloaded library and source metadata |
| Calendar JSON/state and private auth storage | Sync identity, settings, authentication |
| Existing planner SQLite database | Retained user corrections; chat UI is removed |
| SQLAlchemy database (`src/models.py`) | Earlier scraper/summary/calendar CLI workflow |
| Library audit SQLite database | New, disposable relational reporting snapshot |

The audit does not migrate or replace the other stores. This avoids changing
working calendar behavior just to demonstrate SQL. If deleted, its database can
be reconstructed by rerunning the CLI against the saved library.

## Relational model

```text
library_courses 1 ─── many library_files
PK course_id             PK (course_id, source_url)
                         FK course_id → library_courses.course_id
```

A URL identifies a resource within a course, so titles are not used as keys.
Foreign keys are enabled explicitly on writes. Nonnegative sizes and boolean
verification values are constrained. Course coverage uses a LEFT JOIN so courses
with no files remain visible. COALESCE makes empty totals zero.

The importer validates all manifests before beginning snapshot replacement.
DELETE and INSERT operations share a transaction: a write failure rolls back the
replacement. Repeated imports do not append duplicate rows. A file absent from
the latest manifest disappears from the report only; original files are untouched.

Values use SQLite bound parameters. The report connection is read-only. A CTE
and ROW_NUMBER rank files within each course with deterministic tie-breaking.
An index supports filtering by verification status and course. The full aggregate
report still scans the library; no performance benchmark is claimed.

## Tradeoffs you can explain in an interview

- SQLite needs no separate database server for a personal desktop application.
- Manifests preserve collection provenance; SQL makes cross-course aggregation
  easier to inspect and test. This duplicates metadata, so the audit is explicitly
  rebuildable and refreshed on demand rather than treated as a second authority.
- Full snapshot replacement is simple and atomic for a small personal library.
  Larger installations would benefit from incremental updates and schema migrations.
- Verification flags describe the latest downloader run, not guaranteed extraction
  quality. Failed/unsupported documents should never become confident deadlines.
- External-service tests use fakes; real authentication and UI checks are separate.

## Demonstration

1. Run `python3 scripts/audit_library.py --demo`.
2. Open `sql/library_schema.sql` and explain the course/file relationship.
3. Explain why the zero-file course appears in coverage.
4. Open the two report queries and describe aggregation versus window ranking.
5. Run `python3 -m unittest discover -s tests -p 'test_library_audit.py' -v`.

Discuss only work you understand and can demonstrate. Avoid describing the rule
extractor as an LLM, the app as fully autonomous, or the dashboard as fully portable.
