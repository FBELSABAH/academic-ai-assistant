"""Publish readable course folders without overwriting a user's own files."""
import hashlib
import json
import re
import os
import shutil
import tempfile
from pathlib import Path

from src.course_library import atomic_write, safe_name


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.partial-', dir=destination.parent)
    os.close(fd)
    try:
        shutil.copyfile(source, name)
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def folder_name(name):
    match = re.match(r'2026F\s+(.+?)\s*\(([^)]+)\)', name)
    if match:
        title, code = match.groups()
        return safe_name(f'{code} - {title}')
    return safe_name(name)


def free_path(folder, filename, reserved=()):
    candidate = folder / filename
    n = 2
    while candidate.exists() or candidate.name.casefold() in reserved:
        p = Path(filename)
        candidate = folder / f'{p.stem} ({n}){p.suffix}'
        n += 1
    return candidate


def publish(library, destination, semester, state_root):
    """Only replace unchanged managed originals. Locally edited copies stay in place."""
    state_root.mkdir(parents=True, exist_ok=True)
    state_path = state_root / f'{library.course_id}.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'files': {}}
    course_folder = state.get('folder') or folder_name(library.manifest['course_name'])
    folder = destination / semester / course_folder
    folder.mkdir(parents=True, exist_ok=True)
    state['folder'] = course_folder
    archive = destination / 'Archive' / semester / course_folder
    counts = {'added': 0, 'replaced': 0, 'unchanged': 0, 'local_edits_preserved': 0}
    published = {}
    for url, item in library.manifest['files'].items():
        if not item.get('verified_in_last_run'):
            continue
        source = library.root / item['path']
        if digest(source) != item['sha256']:
            raise RuntimeError(f'Original failed hash verification: {source.name}')
        identity = (source.name, item['sha256'])
        if identity in published:
            state['files'][url] = published[identity]
            continue
        old = state['files'].get(url)
        target = folder / old['name'] if old else None
        if target and target.exists() and digest(target) == item['sha256']:
            counts['unchanged'] += 1
        else:
            if target and target.exists():
                if digest(target) == old['sha256']:
                    archive.mkdir(parents=True, exist_ok=True)
                    archived = free_path(archive, f'{target.stem} - {old["sha256"][:8]}{target.suffix}')
                    atomic_copy(target, archived)
                    counts['replaced'] += 1
                else:
                    # Keep a user's edited file exactly where it is; choose a fresh name.
                    target = None
                    counts['local_edits_preserved'] += 1
            if target is None:
                target = free_path(folder, source.name)
                counts['added'] += 1
            elif not target.exists():
                counts['added'] += 1
            atomic_copy(source, target)
        record = {'name': target.name, 'sha256': item['sha256']}
        state['files'][url] = record
        published[identity] = record
        atomic_write(state_path, (json.dumps(state, indent=2) + '\n').encode())
    return folder, counts
