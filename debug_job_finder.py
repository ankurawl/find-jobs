#!/usr/bin/env python3
"""
debug_job_finder.py
Debug script for job discovery workflow.
Step 1: Collect raw output from all sources with NO filtering and NO deduplication -> step1.md
Step 2: Apply filtering logic -> step2.md
Step 3: Compare and deduplicate against Pipeline.md -> step3.md
"""

import json
import os
import re
import sys
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from dotenv import load_dotenv

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(REPO_DIR, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

job_data_dir_cfg = os.getenv("JOB_DATA_DIR", "personal-files")
if os.path.isabs(job_data_dir_cfg):
    DATA_DIR = job_data_dir_cfg
else:
    DATA_DIR = os.path.abspath(os.path.join(REPO_DIR, job_data_dir_cfg))

os.makedirs(DATA_DIR, exist_ok=True)

# Resolve Config File (prefer config.json, fallback to sources.json or config.example.json)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
if not os.path.exists(CONFIG_FILE):
    legacy_sources = os.path.join(DATA_DIR, "sources.json")
    if os.path.exists(legacy_sources):
        CONFIG_FILE = legacy_sources
    else:
        example_cfg = os.path.join(REPO_DIR, "personal-files", "config.example.json")
        if os.path.exists(example_cfg):
            CONFIG_FILE = example_cfg

PROFILE_FILE = os.path.join(DATA_DIR, "Profile.md")
PIPELINE_FILE = os.path.join(DATA_DIR, "Pipeline.md")
JOB_LEADS_FILE = os.path.join(DATA_DIR, "job-leads.md")

STEP1_FILE = os.path.join(DATA_DIR, "step1.md")
STEP2_FILE = os.path.join(DATA_DIR, "step2.md")
STEP3_FILE = os.path.join(DATA_DIR, "step3.md")

# Target Startup Companies with ATS slugs
TARGET_COMPANIES = [
    {"name": "Decagon", "slug": "decagon", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/decagon"},
    {"name": "Scale AI", "slug": "scaleai", "ats": "Greenhouse", "url": "https://boards-api.greenhouse.io/v1/boards/scaleai/jobs"},
    {"name": "Harvey", "slug": "harvey", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/harvey"},
    {"name": "Anthropic", "slug": "anthropic", "ats": "Greenhouse", "url": "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs"},
    {"name": "OpenAI", "slug": "openai", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/openai"},
    {"name": "Cognition", "slug": "cognition", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/cognition"},
    {"name": "Braintrust", "slug": "braintrust", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/braintrust"},
    {"name": "Poolside", "slug": "poolside", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/poolside"},
    {"name": "Anysphere (Cursor)", "slug": "cursor", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/cursor"},
    {"name": "Glean", "slug": "gleanwork", "ats": "Greenhouse", "url": "https://boards-api.greenhouse.io/v1/boards/gleanwork/jobs"},
    {"name": "Cohere", "slug": "cohere", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/cohere"},
    {"name": "Mistral", "slug": "mistral", "ats": "Lever", "url": "https://api.lever.co/v0/postings/mistral"},
    {"name": "ElevenLabs", "slug": "elevenlabs", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/elevenlabs"},
    {"name": "Replit", "slug": "replit", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/replit"},
    {"name": "Pinecone", "slug": "pinecone", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/pinecone"},
    {"name": "Weaviate", "slug": "weaviate", "ats": "Ashby", "url": "https://api.ashbyhq.com/posting-api/job-board/weaviate"}
]

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def read_file(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def sanitize_text(text):
    if not text:
        return ""
    clean = str(text).replace("|", " / ").replace("\n", " ").replace("\r", "")
    return re.sub(r'\s+', ' ', clean).strip()

def fetch_ats_jobs(company_info):
    name = company_info["name"]
    slug = company_info["slug"]
    ats = company_info["ats"]
    endpoint = company_info["url"]
    jobs = []

    try:
        if ats == "Ashby":
            r = requests.get(endpoint, timeout=8)
            if r.status_code == 200:
                for j in r.json().get("jobs", []):
                    jobs.append({
                        "company": name,
                        "title": sanitize_text(j.get("title")),
                        "location": sanitize_text(j.get("locationName") or "US (Remote / On-site)"),
                        "url": j.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id')}",
                        "source": f"{name} ({ats} API)",
                        "comp": "$200K - $350K + Equity",
                        "domain": f"AI Startup ({name})"
                    })
        elif ats == "Greenhouse":
            r = requests.get(endpoint, timeout=8)
            if r.status_code == 200:
                for j in r.json().get("jobs", []):
                    jobs.append({
                        "company": name,
                        "title": sanitize_text(j.get("title")),
                        "location": sanitize_text(j.get("location", {}).get("name") or "US (Remote / On-site)"),
                        "url": j.get("absolute_url"),
                        "source": f"{name} ({ats} API)",
                        "comp": "$200K - $350K + Equity",
                        "domain": f"AI Startup ({name})"
                    })
        elif ats == "Lever":
            r = requests.get(endpoint, timeout=8)
            if r.status_code == 200:
                for j in r.json():
                    jobs.append({
                        "company": name,
                        "title": sanitize_text(j.get("text")),
                        "location": sanitize_text(j.get("categories", {}).get("location") or "US (Remote / On-site)"),
                        "url": j.get("hostedUrl"),
                        "source": f"{name} ({ats} API)",
                        "comp": "$200K - $350K + Equity",
                        "domain": f"AI Startup ({name})"
                    })
    except Exception as e:
        print(f"Error fetching {name} ATS: {e}")

    return jobs

def fetch_web_source(source_info):
    name = source_info["name"]
    url = source_info["url"]
    stype = source_info["type"]
    jobs = []

    try:
        r = curl_requests.get(url, impersonate="chrome", timeout=10)
        if r.status_code in (200, 301, 302):
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a", href=True)
            seen_titles = set()
            for link in links:
                t_text = sanitize_text(link.get_text())
                href = link["href"]
                if not href.startswith("http"):
                    href = requests.compat.urljoin(url, href)
                
                if len(t_text) >= 8 and t_text.lower() not in ("home", "about", "careers", "privacy", "terms", "jobs", "login", "sign up", "learn more"):
                    if t_text not in seen_titles:
                        seen_titles.add(t_text)
                        jobs.append({
                            "company": name,
                            "title": t_text,
                            "location": "US / Unspecified",
                            "url": href,
                            "source": f"{name} ({stype})",
                            "comp": "Unspecified",
                            "domain": f"{stype} Feed"
                        })
    except Exception as e:
        print(f"Error fetching web source {name}: {e}")

    return jobs

# --- Dynamic Filtering Functions for Step 2 ---

def is_matching_role(title, filter_criteria):
    t = title.lower()

    exclude_mgmt = filter_criteria.get("exclude_management_keywords", [])
    if any(rej in t for rej in exclude_mgmt if rej):
        return False

    exclude_roles = filter_criteria.get("exclude_role_keywords", [])
    if any(rej in t for rej in exclude_roles if rej):
        return False

    include_patterns = filter_criteria.get("include_role_patterns", [])
    if include_patterns:
        matches_pattern = any(re.search(pat, t, re.IGNORECASE) for pat in include_patterns)
        if not matches_pattern:
            return False

    return True

def is_eligible_location(loc_str, title_str, filter_criteria):
    title_lower = str(title_str).lower()
    loc_lower = str(loc_str).lower()

    excluded_locs = filter_criteria.get("excluded_location_keywords", [])
    allowed_locs = filter_criteria.get("allowed_location_keywords", [])

    if any(term in title_lower for term in excluded_locs if len(term) > 3):
        return False

    has_allowed = any(re.search(r'\b' + re.escape(term) + r'\b', loc_lower) for term in allowed_locs if term)
    
    if loc_str in ('US (Remote / On-site)', 'US / Unspecified') or has_allowed:
        return True

    has_excluded = any(re.search(r'\b' + re.escape(term) + r'\b', loc_lower) for term in excluded_locs if term)
    if has_excluded and not has_allowed:
        return False

    return True

def calculate_fit_score(title, domain_text, comp_text, company_name, filter_criteria):
    fit_cfg = filter_criteria.get("fit_scoring", {})
    base_score = fit_cfg.get("base_score", 50)
    score = base_score
    combined = (title + " " + domain_text).lower()

    excluded_comps = filter_criteria.get("excluded_company_names", [])
    if any(ex.lower() in company_name.lower() for ex in excluded_comps if ex):
        return 0

    keyword_boosts = fit_cfg.get("keyword_boosts", [])
    for boost in keyword_boosts:
        weight = boost.get("weight", 10)
        patterns = boost.get("patterns", [])
        if any(re.search(r'\b' + re.escape(p.lower()) + r'\b', combined) for p in patterns):
            score += weight

    comp_boost_cfg = fit_cfg.get("compensation_boost", {})
    min_sal = comp_boost_cfg.get("min_salary", 200000)
    weight = comp_boost_cfg.get("weight", 10)

    if str(min_sal) in comp_text or "$200k" in comp_text.lower() or "$2" in comp_text:
        score += weight

    return min(100, max(0, score))

def extract_job_id_from_url(url):
    if not url:
        return None
    m = re.search(r'/(?:jobs/|postings/|job-board/|careers/)?([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}|\d{8,12})', url)
    if m:
        return m.group(1)
    return None

def normalize_text(text):
    if not text:
        return ""
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'[*_`]', '', text)
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()

def parse_date(date_str):
    if not date_str:
        return None
    d_clean = str(date_str).strip()
    d_clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', d_clean)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d_clean, fmt)
        except ValueError:
            pass
    m = re.search(r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', d_clean)
    if m:
        try:
            month_str, day_str, year_str = m.groups()
            for fmt in ("%b %d %Y", "%B %d %Y"):
                try:
                    return datetime.strptime(f"{month_str} {day_str} {year_str}", fmt)
                except ValueError:
                    pass
        except Exception:
            pass
    return None

def parse_exclusions_from_pipeline(file_path, filter_criteria):
    excluded_urls = set()
    excluded_job_ids = set()
    excluded_company_roles = set()
    excluded_companies_12m = set()

    if not os.path.exists(file_path):
        return excluded_urls, excluded_job_ids, excluded_company_roles, excluded_companies_12m

    dedup_cfg = filter_criteria.get("deduplication_policy", {})
    reapp_cooldown = dedup_cfg.get("reapplication_cooldown_days", 90)
    interview_cooldown = dedup_cfg.get("interview_company_exclusion_days", 365)
    interview_kws = dedup_cfg.get("interview_stage_keywords", ['interview', 'hm round', 'panel', 'screen', 'working session'])

    content = read_file(file_path)
    current_section = ""
    now = datetime.now()

    for line in content.splitlines():
        line_s = line.strip()
        if line_s.startswith("## "):
            current_section = line_s.replace("## ", "").strip()
            continue

        if line_s.startswith("|") and not line_s.startswith("| :---"):
            cols = [c.strip() for c in line_s.split("|")[1:-1]]
            if len(cols) >= 2:
                comp_raw = cols[0]
                role_raw = cols[1]
                if "Company" in comp_raw or "---" in comp_raw or ":---" in comp_raw:
                    continue

                comp_norm = normalize_text(comp_raw)
                role_norm = normalize_text(role_raw)
                urls = re.findall(r'https?://[^\s\)"\'>]+', line_s)

                date_obj = None
                status_text = ""
                for col in cols[2:]:
                    d_parsed = parse_date(col)
                    if d_parsed and not date_obj:
                        date_obj = d_parsed
                    else:
                        status_text += " " + col

                days_ago = (now - date_obj).days if date_obj else 0

                if "Active" in current_section or "ToDo" in current_section:
                    if comp_norm and role_norm:
                        excluded_company_roles.add((comp_norm, role_norm))
                    for u in urls:
                        excluded_urls.add(u.strip())
                        jid = extract_job_id_from_url(u)
                        if jid:
                            excluded_job_ids.add(jid)

                elif "Applied, No Update" in current_section:
                    if days_ago < reapp_cooldown:
                        if comp_norm and role_norm:
                            excluded_company_roles.add((comp_norm, role_norm))
                        for u in urls:
                            excluded_urls.add(u.strip())
                            jid = extract_job_id_from_url(u)
                            if jid:
                                excluded_job_ids.add(jid)

                elif "Rejected" in current_section or "Self Selected Out" in current_section:
                    interviewed = any(kw in status_text.lower() for kw in interview_kws)
                    cutoff_days = interview_cooldown if interviewed else reapp_cooldown

                    if days_ago < cutoff_days:
                        if interviewed and comp_norm:
                            excluded_companies_12m.add(comp_norm)
                        if comp_norm and role_norm:
                            excluded_company_roles.add((comp_norm, role_norm))
                        for u in urls:
                            excluded_urls.add(u.strip())
                            jid = extract_job_id_from_url(u)
                            if jid:
                                excluded_job_ids.add(jid)

    return excluded_urls, excluded_job_ids, excluded_company_roles, excluded_companies_12m

def is_already_considered(job, excluded_urls, excluded_job_ids, excluded_company_roles, excluded_companies_12m):
    url = job.get("url", "")
    comp_name = job.get("company", "")
    role_title = job.get("title", "")
    comp_norm = normalize_text(comp_name)
    role_norm = normalize_text(role_title)

    for ex_comp in excluded_companies_12m:
        if comp_norm == ex_comp or (len(comp_norm) >= 4 and comp_norm in ex_comp) or (len(ex_comp) >= 4 and ex_comp in comp_norm):
            return True, f"Company 12-month interview exclusion: {comp_name}"

    if url and url in excluded_urls:
        return True, f"Exact URL match: {url}"

    jid = extract_job_id_from_url(url)
    if jid and jid in excluded_job_ids:
        return True, f"Job ID match: {jid}"

    if (comp_norm, role_norm) in excluded_company_roles:
        return True, f"Company+Role match: {comp_name} - {role_title}"

    for ex_comp, ex_role in excluded_company_roles:
        if comp_norm == ex_comp or (len(comp_norm) >= 4 and comp_norm in ex_comp) or (len(ex_comp) >= 4 and ex_comp in comp_norm):
            if role_norm == ex_role or role_norm in ex_role or ex_role in role_norm:
                return True, f"Fuzzy Company+Role match: {comp_name} - {role_title} vs ({ex_comp}, {ex_role})"

    return False, ""

def main():
    print(f"Executing debug workflow using config: {CONFIG_FILE}")
    config = load_json(CONFIG_FILE)
    filter_criteria = config.get("filter_criteria", {})
    threshold = filter_criteria.get("fit_scoring", {}).get("fit_score_threshold_percent", 75)

    # STEP 1: Collect ALL raw listings
    print("Step 1: Collecting raw job postings from target companies & news feeds...")
    raw_jobs = []

    for comp in TARGET_COMPANIES:
        jobs = fetch_ats_jobs(comp)
        raw_jobs.extend(jobs)

    for src in config.get("job_sources", []):
        if src.get("type") in ("job_board", "curated_jobs", "curated_pm_jobs", "tech_news"):
            jobs = fetch_web_source(src)
            raw_jobs.extend(jobs)

    step1_lines = ["# Step 1: Raw Unfiltered Job Listings\n\n| Company | Title | Location | Source | URL |\n| :--- | :--- | :--- | :--- | :--- |\n"]
    for j in raw_jobs:
        step1_lines.append(f"| **{j['company']}** | {j['title']} | {j['location']} | {j['source']} | [Link]({j['url']}) |")
    
    with open(STEP1_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(step1_lines) + "\n")
    print(f"Step 1 completed: {len(raw_jobs)} raw jobs written to step1.md")

    # STEP 2: Filtered listings (Role + Location + Fit Score)
    print("Step 2: Applying role matching, location eligibility, and fit score evaluation...")
    step2_jobs = []
    step2_lines = ["# Step 2: Filtered Job Listings\n\n| Company | Title | Location | Fit Score | Status | Source | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"]

    for j in raw_jobs:
        role_pass = is_matching_role(j["title"], filter_criteria)
        loc_pass = is_eligible_location(j["location"], j["title"], filter_criteria)

        if not role_pass:
            status = "Rejected (Role Mismatch)"
        elif not loc_pass:
            status = "Rejected (Location Non-US)"
        else:
            score = calculate_fit_score(j["title"], j["domain"], j["comp"], j["company"], filter_criteria)
            if score >= threshold:
                status = f"PASSED ({score}%)"
                step2_jobs.append(j)
            else:
                status = f"Rejected (Low Fit Score: {score}%)"

        step2_lines.append(f"| **{j['company']}** | {j['title']} | {j['location']} | {status} | {j['source']} | [Link]({j['url']}) |")

    with open(STEP2_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(step2_lines) + "\n")
    print(f"Step 2 completed: {len(step2_jobs)} filtered jobs written to step2.md")

    # STEP 3: Deduplicated against Pipeline.md
    print("Step 3: Deduplicating filtered jobs against Pipeline.md...")
    p_urls, p_jids, p_croles, p_c12m = parse_exclusions_from_pipeline(PIPELINE_FILE, filter_criteria)

    step3_lines = ["# Step 3: Pipeline Comparison & Final Deduplication\n\n| Company | Title | Location | Status | Exclusion Reason | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"]
    final_count = 0

    for j in step2_jobs:
        already_considered, reason = is_already_considered(j, p_urls, p_jids, p_croles, p_c12m)
        if already_considered:
            step3_lines.append(f"| **{j['company']}** | {j['title']} | {j['location']} | EXCLUDED | {reason} | [Link]({j['url']}) |")
        else:
            final_count += 1
            step3_lines.append(f"| **{j['company']}** | {j['title']} | {j['location']} | NEW LEAD | N/A | [Link]({j['url']}) |")

    with open(STEP3_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(step3_lines) + "\n")
    print(f"Step 3 completed: {final_count} new leads written to step3.md")

if __name__ == "__main__":
    main()
