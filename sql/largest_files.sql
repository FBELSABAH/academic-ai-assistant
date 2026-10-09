-- Window functions identify the largest files within each course.
WITH ranked AS (
    SELECT c.name, f.title, f.byte_count, f.relative_path,
           ROW_NUMBER() OVER (
               PARTITION BY f.course_id ORDER BY f.byte_count DESC, f.source_url
           ) AS position
    FROM library_files f JOIN library_courses c USING (course_id)
)
SELECT * FROM ranked WHERE position <= :limit_per_course
ORDER BY name, position;
