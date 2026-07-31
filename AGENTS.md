# AGENTS.md

## Repository Instructions & Memory

### Git & Branching Policy
- **Feature & Functionality Changes**: Always create and work in a separate feature branch (e.g. `feature/...` or `fix/...`) when implementing any feature or functionality changes, so that the `main` branch remains clean and functional at all times.
- **Branch Continuity**: Unless explicitly instructed by the user, always continue working in the same active feature/fix branch (as long as it is not the `main` branch), rather than creating multiple separate branches.
- **Merge Process**: Changes in feature branches can later be merged into `main` after verification.
- **Exception**: Direct changes to `main` are ONLY permitted when explicitly instructed by the user.
- **Push to Remote**: Always push all feature/fix branches and commits to GitHub (`origin`) upon completing changes.

### Execution Rules
- **Python Interpreter**: Always run scripts using the project's virtual environment (`.venv/bin/python`).
- **Data Location Configuration**: All data file locations (`Profile.md`, `Pipeline.md`, `target-companies.md`, `config.json`, `job-leads.md`, `logs/`) are resolved dynamically via the root `.env` file (`JOB_DATA_DIR`).
