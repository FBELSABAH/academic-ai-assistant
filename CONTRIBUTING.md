# Development

Use Python 3.11+ and install the root requirements plus
`dashboard/requirements-extraction.txt` in a virtual environment. Read `AGENTS.md`
before changing the frontend. Preserve private data and existing saved corrections.

Run both unittest suites and the SQL demo using the commands in README.md.
Use temporary directories and fictional fixtures in tests. Tests must not sign in,
sync a real calendar, submit coursework, or depend on private course downloads.

Keep pull requests focused. Explain the user-visible result, validation performed,
and limitations. For UI changes, inspect desktop and mobile renderings. Do not
commit screenshots containing real student information. Optional design tooling
is documented in `docs/frontend-workflow.md`.
