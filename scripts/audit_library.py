#!/usr/bin/env python3
"""Inspect saved library coverage using SQLite; --demo needs no accounts."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.library_audit import refresh, report, largest_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=ROOT/'data/library')
    parser.add_argument('--database', type=Path, default=ROOT/'data/library-audit.sqlite')
    parser.add_argument('--course', help='Filter coverage by Moodle course ID')
    parser.add_argument('--demo', action='store_true', help='Use temporary fictional data and database')
    args = parser.parse_args()
    def run(library, database):
        counts = refresh(library, database)
        print(json.dumps({'indexed': counts, 'coverage': report(database, args.course),
                          'largest_files': largest_files(database)}, indent=2))
    try:
        if args.demo:
            with tempfile.TemporaryDirectory(prefix='academic-audit-demo-') as tmp:
                root = Path(tmp)
                for cid, name, files in [
                    ('101', 'Demo Discrete Mathematics', {
                        'https://moodle.example.edu/resource/1': {'path': 'files/lecture.pdf', 'title': 'Graph theory', 'bytes': 4096, 'verified_in_last_run': True},
                        'https://moodle.example.edu/resource/2': {'path': 'files/practice.pdf', 'title': 'Practice', 'bytes': 2048, 'verified_in_last_run': False}}),
                    ('102', 'Demo Statistics', {})]:
                    folder = root/'library'/('course-'+cid)
                    folder.mkdir(parents=True)
                    (folder/'manifest.json').write_text(json.dumps({'course_name': name, 'files': files}))
                run(root/'library', root/'audit.sqlite')
        else:
            run(args.library, args.database)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'Library audit failed: {exc}\n')


if __name__ == '__main__':
    main()
