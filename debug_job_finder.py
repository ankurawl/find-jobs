#!/usr/bin/env python3
"""
debug_job_finder.py
Debug inspection harness for job discovery workflow.
Imports core discovery and filtering logic directly from find_jobs.py.

Step 1: Collect raw output from all dynamic sources & feeds with NO filtering -> step1.md
Step 2: Apply role matching, location eligibility, and fit score evaluation -> step2.md
Step 3: Compare and deduplicate against Pipeline.md -> step3.md
"""

import os
import sys

# Ensure repo directory is in path
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

from find_jobs import (
    DATA_DIR,
    CONFIG_FILE,
    STEP1_FILE,
    STEP2_FILE,
    STEP3_FILE,
    load_json,
    collect_all_raw_jobs,
    filter_and_score_jobs,
    deduplicate_jobs
)

def main():
    print(f"Executing debug workflow using config: {CONFIG_FILE}")
    config = load_json(CONFIG_FILE)
    filter_criteria = config.get("filter_criteria", {})

    # STEP 1: Collect ALL raw listings dynamically via find_jobs core engine
    print("Step 1: Running dynamic news extraction & multi-probe job discovery...")
    raw_jobs = collect_all_raw_jobs(config, max_new_companies=100)

    step1_lines = ["# Step 1: Raw Unfiltered Job Listings\n\n| Company | Title | Location | Source | URL |\n| :--- | :--- | :--- | :--- | :--- |\n"]
    for j in raw_jobs:
        step1_lines.append(f"| **{j['company']}** | {j['title']} | {j['location']} | {j['source']} | [Link]({j['url']}) |")
    
    with open(STEP1_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(step1_lines) + "\n")
    print(f"Step 1 completed: {len(raw_jobs)} raw jobs written to step1.md")

    # STEP 2: Filtered listings (Role + Location + Fit Score)
    print("Step 2: Applying role matching, location eligibility, and fit score evaluation...")
    filtered_jobs, step2_evals = filter_and_score_jobs(raw_jobs, filter_criteria)
    step2_lines = ["# Step 2: Filtered Job Listings\n\n| Company | Title | Location | Fit Score / Status | Source | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"]

    for ev in step2_evals:
        j = ev["job"]
        status = ev["status"]
        step2_lines.append(f"| **{j['company']}** | {j['title']} | {j['location']} | {status} | {j['source']} | [Link]({j['url']}) |")

    with open(STEP2_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(step2_lines) + "\n")
    print(f"Step 2 completed: {len(filtered_jobs)} filtered jobs written to step2.md")

    # STEP 3: Deduplicated against Pipeline.md
    print("Step 3: Deduplicating filtered jobs against Pipeline.md...")
    accepted_leads, step3_records = deduplicate_jobs(filtered_jobs, filter_criteria)

    step3_lines = ["# Step 3: Pipeline Comparison & Final Deduplication\n\n| Company | Title | Location | Status | Exclusion Reason | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"]
    final_count = len(accepted_leads)

    for rec in step3_records:
        j = rec["job"]
        status = rec["status"]
        reason = rec["reason"]
        step3_lines.append(f"| **{j['company']}** | {j['title']} | {j['location']} | {status} | {reason} | [Link]({j['url']}) |")

    with open(STEP3_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(step3_lines) + "\n")
    print(f"Step 3 completed: {final_count} new leads written to step3.md")

if __name__ == "__main__":
    main()
