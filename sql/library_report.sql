-- A bound parameter filters by course ID without SQL string interpolation.
SELECT * FROM library_coverage
WHERE (:course_id IS NULL OR course_id = :course_id)
ORDER BY needs_verification DESC, name;
