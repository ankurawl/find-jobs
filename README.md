# Job Discovery Engine (`find-jobs`)

A modular, ground-truth Individual Contributor (IC) US-eligible Job Discovery Engine and Startup Lead Finder.

## Features
- **Multi-Strategy Career Discovery**: Scrapes ATS job boards (Ashby, Greenhouse, Lever APIs) and direct company website career pages.
- **Funding News Entity Extractor**: Scrapes funding news sources (TechCrunch, VentureBeat, Crunchbase News, PR Newswire) to extract freshly funded startup entities.
- **Filtering & Fit Scoring**: Evaluates roles against IC PM target criteria ($200K+ base salary, US-eligible location, 75%+ candidate fit threshold). Excludes People Management roles (Director, VP, Head of Product, GPM).
- **Date-Aware Deduplication**: Excludes active pipeline roles, 90-day re-applications, and 12-month interview exclusions.
- **Configurable Data Separation**: Personal candidate profile (`Profile.md`), tracking pipeline (`Pipeline.md`), and search target lists (`sources.json`) remain in a separate folder defined in `.env`.

---

## Quick Setup

### 1. Virtual Environment & Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` to specify your personal data folder:
```ini
# Path to your personal files folder (relative or absolute)
JOB_DATA_DIR=personal-files
```

If `JOB_DATA_DIR` is set to `personal-files`, place your `Profile.md`, `Pipeline.md`, and `sources.json` inside `personal-files/`. You can use `personal-files/sources.example.json` as a starting template.

---

## Running the Engine

### Via AI CLI Assistants (Recommended)
Simply ask your AI assistant (AGY, Claude Code, etc.):
> *"Find jobs"* or *"Run job finder"*

### Via Command Line
```bash
.venv/bin/python find_jobs.py
```

### Debug Mode
```bash
.venv/bin/python debug_job_finder.py
```

---

## Repository Structure

```
find-jobs/
├── .env.example               # Environment config template
├── README.md                  # Documentation
├── CLAUDE.md                  # Guidelines for AI CLI tools
├── requirements.txt           # Python dependencies
├── find_jobs.py               # Main job discovery script
├── debug_job_finder.py        # Debug script for raw feed/ATS inspection
├── personal-files/
│   └── sources.example.json   # Sanitized reference config template
└── .agents/
    └── skills/
        └── find-jobs/
            └── SKILL.md       # Skill definition for AI assistants
```

---

## Data Privacy & Security
Personal data files (`Profile.md`, `Pipeline.md`, `sources.json`, `job-leads.md`), local environment config (`.env`), virtual environment (`.venv/`), and execution logs (`logs/`) are strictly listed in `.gitignore` to prevent any accidental leakage.
