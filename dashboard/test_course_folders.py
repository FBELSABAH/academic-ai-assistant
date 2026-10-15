import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from course_folders import open_course_folder

class CourseFolderTests(unittest.TestCase):
    def test_open_and_reject_unsafe_or_missing_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); root=base/'courses';root.mkdir();state=base/'state';state.mkdir()
            folder=root/'MATH - Combinatorics';folder.mkdir()
            record=state/'27641.json';record.write_text(json.dumps({'folder':folder.name}))
            with patch('course_folders.subprocess.run') as run:
                open_course_folder('27641',state,root)
                self.assertEqual(run.call_args.args[0],['/usr/bin/open',str(folder.resolve())])
            for name in ['../outside','/tmp', 'missing']:
                record.write_text(json.dumps({'folder':name}))
                with self.assertRaises(ValueError):open_course_folder('27641',state,root)
            (root/'escape').symlink_to(base,target_is_directory=True)
            record.write_text(json.dumps({'folder':'escape'}))
            with self.assertRaises(ValueError):open_course_folder('27641',state,root)
            with self.assertRaises(ValueError):open_course_folder('../27641',state,root)
