"""Open only an existing published course directory, never a caller-supplied path."""
import json
from pathlib import Path
import subprocess


def open_course_folder(course_id, state_root, root):
    if not str(course_id).isdigit():
        raise ValueError('Unknown course.')
    try:
        state = json.loads((state_root / f'{course_id}.json').read_text())
        name = state['folder']
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError('No exported folder yet. Update Moodle first.') from None
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ValueError('Invalid course folder.')
    folder = (root / name).resolve()
    if folder.parent != root.resolve() or not folder.is_dir():
        raise ValueError('Course folder is missing. Update Moodle to restore it.')
    try:
        subprocess.run(['/usr/bin/open', str(folder)], check=True, timeout=10, capture_output=True)
    except (subprocess.SubprocessError, OSError):
        raise ValueError('Finder could not open the folder. Please try again.') from None
