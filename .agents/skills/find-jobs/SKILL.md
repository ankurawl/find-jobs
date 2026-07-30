---
name: find-jobs
description: >-
  Search for product management job opportunities and funded startup leads (Series B/C/D+ in last 6 months or >$100M valuation, >$200K base salary, US) from tech news and job sources, evaluate candidate fit (>75% threshold), verify link availability, and populate job-leads.md. Triggered whenever the user says "find jobs", "search for jobs", or "run job finder".
---

# Find Jobs Skill

This skill defines the instructions and automated workflow for discovering high-growth startup leads and senior product management opportunities, scoring candidate fit, deduplicating, and updating `job-leads.md`.

## Data Configuration (.env & config.json)
- The execution engine resolves the target data directory dynamically from `.env` (`JOB_DATA_DIR`).
- Target data directory contains `Profile.md`, `Pipeline.md`, `config.json`, and `job-leads.md`.

## Core Rules & Criteria
1. **Virtual Environment**: ALWAYS use the Python virtual environment located at `/home/agag/Documents/find-jobs/.venv/bin/python` for executing `/home/agag/Documents/find-jobs/find_jobs.py`.
2. **Sources & Config**: Reads job sources, funding feeds, role title patterns, and filtering rules from `config.json` in the configured `JOB_DATA_DIR` (falls back to `personal-files/config.example.json`).
3. **Filtering Rules**:
   - **Funding / Valuation**: Private companies must have raised Series B, C, D+ in the last 6 months, or have a valuation/market cap ≥ $100M USD.
   - **US Market & Location**: US-focused opportunities (On-site, Remote, or Hybrid). Candidate is based in Austin but open to relocation/travel.
   - **Seniority & Compensation**: Target senior IC PM roles (*Principal PM, Staff PM, Lead PM, Senior PM*). Minimum base salary **$200,000 USD + equity**. Excludes People Management roles (Director, VP, Head of Product, GPM).
   - **Fit Score Threshold**: Minimum **75% fit score** calculated against candidate profile (`Profile.md` and resume). Prioritize AI application, AI platforms, LLM evals, and AI agent frameworks.
4. **Date-Aware Deduplication & Link Validation**:
   - Cross-reference against ALL sections in `Pipeline.md` (`Active`, `ToDo`, `Inactive - Applied`, `Inactive - Rejected/Dropped`, `Self Selected Out`) as well as active leads in `job-leads.md`.
   - **3-Month Reconsideration Window**: For `Applied - No Update`, resume-screen rejections, or uninterviewed drops/self-selected-out roles, filter out only if the activity date was within the last **3 months (90 days)**. Roles older than 3 months may be reconsidered if re-posted.
   - **12-Month Interview Exclusion**: If the candidate had active interview discussions with a company and then got rejected/dropped/self-selected-out, filter out **the entire company for 12 months (365 days)**.
   - **Active/ToDo**: Roles in `Active` or `ToDo` are always excluded.
5. **Output**: Append qualifying leads to `job-leads.md` inside `JOB_DATA_DIR`.

---

## How to Trigger
- **Manual Trigger**: Simply say **"find jobs"**, **"search for jobs"**, or **"run find jobs"**.
- **Automated Schedule**: Runs automatically every night at 2:00 AM.

---

## Workflow Steps

### Step 1: Execute Job Discovery Script
Execute the job discovery engine script using the repo's virtual environment:
```bash
/home/agag/Documents/find-jobs/.venv/bin/python /home/agag/Documents/find-jobs/find_jobs.py
```

### Step 2: Review and Format Output
- Verify that `job-leads.md` (in `JOB_DATA_DIR`) contains updated tables sorted by fit score or date added.
- Provide a summary report to the user detailing:
  1. Number of fresh sources scanned (Ashby/Greenhouse/Lever APIs, etc.).
  2. Roles filtered out because they were already considered in `Pipeline.md` or `job-leads.md`.
  3. New qualifying roles added to `job-leads.md` with fit scores, compensation, and location.
  4. Next actions for user review.

### Step 3: Processing User Feedback
When the user indicates which leads they like from `job-leads.md`:
1. Move approved entries to the `ToDo - Need to apply, respond, etc.` table in `Pipeline.md`.
2. Move unapproved/declined entries (roles the user decided not to pursue) to the `Self Selected Out` table in `Pipeline.md`.
3. Clear those processed entries from `job-leads.md`.
