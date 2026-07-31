# find-jobs (Job Discovery Engine)

## Overview
`find-jobs` is a standalone, profession-agnostic job discovery engine and startup lead finder.

## Execution Rules for AI Assistants (Antigravity, Claude Code, Cursor, etc.)
- **No direct user python calls required**: AI CLI tools execute the python engine script automatically using the repository's virtual environment.
- **Python Interpreter**: Always run scripts using the project's virtual environment: `.venv/bin/python`.
- **Data Location Configuration**: All data file locations (`Profile.md`, `Pipeline.md`, `target-companies.md`, `config.json`, `job-leads.md`, `logs/`) are resolved dynamically via the root `.env` file (`JOB_DATA_DIR`).
- **Git Branching Strategy**: Always make feature/functionality changes in a separate branch (which can later be merged into `main`) to keep `main` clean and functional at all times. Direct commits/edits to `main` are ONLY allowed when explicitly instructed.

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
- `personal-files/config.example.json` provides a sanitized reference template with examples for different professions (Product Management, Software Engineering, etc.).
