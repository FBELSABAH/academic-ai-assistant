-- Derived reporting database; original files and manifests remain authoritative.
CREATE TABLE IF NOT EXISTS library_courses (
    course_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_url TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS library_files (
    course_id TEXT NOT NULL REFERENCES library_courses(course_id) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    byte_count INTEGER NOT NULL CHECK (byte_count >= 0),
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    PRIMARY KEY (course_id, source_url)
);
CREATE INDEX IF NOT EXISTS library_files_verified ON library_files(verified, course_id);
CREATE VIEW IF NOT EXISTS library_coverage AS
SELECT c.course_id, c.name, COUNT(f.source_url) AS files,
       COALESCE(SUM(f.byte_count), 0) AS bytes,
       COALESCE(SUM(f.verified), 0) AS verified_files,
       COUNT(f.source_url) - COALESCE(SUM(f.verified), 0) AS needs_verification
FROM library_courses c
LEFT JOIN library_files f ON f.course_id = c.course_id
GROUP BY c.course_id, c.name;
