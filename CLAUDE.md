# find-jobs (Job Discovery Engine)

## Overview
`find-jobs` is a standalone, ground-truth job discovery engine for senior Individual Contributor (IC) Product Management roles and funded startup leads.

## Execution Rules for AI Assistants (Antigravity, Claude Code, Cursor, etc.)
- **No direct user python calls required**: AI CLI tools execute the python engine script automatically using the repository's virtual environment.
- **Python Interpreter**: Always run scripts using the project's virtual environment: `.venv/bin/python`.
- **Data Location Configuration**: All data file locations (`Profile.md`, `Pipeline.md`, `sources.json`, `job-leads.md`, `logs/`) are resolved dynamically via the root `.env` file (`JOB_DATA_DIR`).

## Key Commands
- Run discovery engine:
  ```bash
  .venv/bin/python find_jobs.py
  ```
- Run debug workflow:
  ```bash
  .venv/bin/python debug_job_finder.py
  ```

## Configuration & Data Separation
- `.env` controls `JOB_DATA_DIR` (default: `personal-files`).
- `.env`, `.venv`, local logs, and personal user data files are strictly gitignored.
- `personal-files/sources.example.json` provides a sanitized reference template for public users.
