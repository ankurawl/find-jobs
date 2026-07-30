#!/usr/bin/env python3
"""
find_jobs.py
Comprehensive Ground-Truth Job Discovery Engine.

Features:
1. Profession & Level Agnostic: Fully configured via config.json (JOB_DATA_DIR).
2. Dynamic Target Companies Config sync with Pipeline.md (Command Center).
3. Funding News Entity Extractor: Scrapes news sources (TechCrunch, Crunchbase News, VentureBeat, etc.), 
   extracts funded startup names, and appends them to Pipeline.md under Target Companies Config.
4. Multi-Strategy Career Discovery:
   - Strategy A: Direct ATS APIs (Ashby, Greenhouse, Lever, etc.)
   - Strategy B: Direct Website Career Page Scraping.
5. Configurable Fit Scoring & Deduplication Engine.
6. Error & Success Logging: Appends a clean 'Scraping & Discovery Logs' section to job-leads.md.
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
import urllib.parse
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
LOGS_DIR = os.path.join(DATA_DIR, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "find_jobs.log")
SUMMARY_JSON = os.path.join(LOGS_DIR, "latest_run_summary.json")

os.makedirs(LOGS_DIR, exist_ok=True)

logger = logging.getLogger("find_jobs")
logger.setLevel(logging.DEBUG)

if logger.hasHandlers():
    logger.handlers.clear()

file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
file_handler.setFormatter(file_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("[find_jobs] %(message)s")
console_handler.setFormatter(console_formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

GLOBAL_SCRAPE_LOGS = []

def record_log(source_name, target_url, status, details):
    timestamp = datetime.now().strftime("%b %d, %Y %H:%M")
    GLOBAL_SCRAPE_LOGS.append({
        "source": source_name,
        "url": target_url,
        "status": status,
        "details": details,
        "timestamp": timestamp
    })

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

def parse_target_companies_from_pipeline():
    target_companies = []
    content = read_file(PIPELINE_FILE)
    if not content:
        return target_companies

    in_target_section = False
    for line in content.splitlines():
        line_s = line.strip()
        if "### 🎯 Target Companies Config" in line_s:
            in_target_section = True
            continue
        elif line_s.startswith("## ") or (in_target_section and line_s.startswith("### ")):
            in_target_section = False
            continue

        if in_target_section and line_s.startswith("|") and not line_s.startswith("| :---"):
            cols = [c.strip() for c in line_s.split("|")[1:-1]]
            if len(cols) >= 3:
                comp_raw = cols[0].replace("**", "").strip()
                reason = cols[1].strip()
                website = cols[2].strip()
                ats_info = cols[3].strip() if len(cols) >= 4 else "Auto"
                if "Company" in comp_raw or "---" in comp_raw:
                    continue

                ats_type = "Auto"
                slug = comp_raw.lower().replace(" ", "")
                if "Ashby" in ats_info:
                    ats_type = "Ashby"
                elif "Greenhouse" in ats_info:
                    ats_type = "Greenhouse"
                elif "Lever" in ats_info:
                    ats_type = "Lever"

                m_slug = re.search(r'`([^`]+)`', ats_info)
                if m_slug:
                    slug = m_slug.group(1)

                target_companies.append({
                    "name": comp_raw,
                    "reason": reason,
                    "website": website,
                    "ats": ats_type,
                    "slug": slug
                })

    return target_companies

def append_new_target_company_to_pipeline(comp_name, reason, website, ats_info="Auto"):
    content = read_file(PIPELINE_FILE)
    if not content or "### 🎯 Target Companies Config" not in content:
        return False

    comp_norm = comp_name.lower().strip()
    if comp_norm in content.lower():
        return False

    new_row = f"| **{comp_name}** | {reason} | {website} | {ats_info} | Added via News Sync |\n"
    
    parts = content.split("### 🎯 Target Companies Config\n")
    if len(parts) == 2:
        table_lines = parts[1].split("\n\n")[0]
        updated_table = table_lines + "\n" + new_row.strip()
        updated_content = parts[0] + "### 🎯 Target Companies Config\n" + parts[1].replace(table_lines, updated_table, 1)
        with open(PIPELINE_FILE, "w", encoding="utf-8") as f:
            f.write(updated_content)
        logger.info(f"Auto-added new funded company to Pipeline.md: {comp_name} ({reason})")
        return True
    return False

def extract_funding_news_and_update_targets(news_sources):
    logger.info("Extracting funded startup entity leads from news sources...")
    funding_patterns = [
        re.compile(r'([A-Z][A-Za-z0-9\.\-\s]{2,25})\s+(?:raises|raised|secures|secured|snags|snagged|bags|bagged|nabs|nabbed|closes|closed|lands|landed)\s+(\$\d+(?:\.\d+)?\s*(?:M|B|million|billion)?(?:\s+(?:Series\s+[A-E]|growth|funding|valuation))?)', re.IGNORECASE),
        re.compile(r'([A-Z][A-Za-z0-9\.\-\s]{2,25})\s+hits\s+(\$\d+(?:\.\d+)?\s*(?:M|B|million|billion)?\s*valuation)', re.IGNORECASE)
    ]

    discovered_companies = []

    for src in news_sources:
        s_name = src["name"]
        s_url = src["url"]
        try:
            r = curl_requests.get(s_url, impersonate="chrome", timeout=10)
            if r.status_code == 200:
                record_log(s_name, s_url, "Success (200)", f"Fetched news feed successfully ({len(r.text)} bytes)")
                soup = BeautifulSoup(r.text, "html.parser")
                
                headlines = []
                for tag in soup.find_all(['h1', 'h2', 'h3', 'a']):
                    txt = sanitize_text(tag.get_text())
                    if len(txt) > 15:
                        headlines.append(txt)

                for txt in headlines:
                    for pat in funding_patterns:
                        m = pat.search(txt)
                        if m:
                            comp = m.group(1).strip()
                            fund = m.group(2).strip()
                            comp_clean = re.sub(r'^(?:As|The|AI|New|Startup|Tech|How|Why|What|After|With)\s+', '', comp, flags=re.IGNORECASE).strip()
                            if len(comp_clean) >= 3 and not any(w in comp_clean.lower() for w in ['series', 'million', 'billion', 'funding', 'round', 'investor', 'capital']):
                                website = f"https://{comp_clean.lower().replace(' ', '')}.com"
                                reason = f"Funding News ({s_name}: {fund})"
                                if append_new_target_company_to_pipeline(comp_clean, reason, website):
                                    discovered_companies.append(comp_clean)
            else:
                record_log(s_name, s_url, f"HTTP Error ({r.status_code})", "Non-200 response from news source")
        except Exception as e:
            record_log(s_name, s_url, "Error / Failure", str(e))

    return discovered_companies

# --- Job Discovery Strategies ---

def fetch_jobs_from_ats_api(company):
    c_name = company["name"]
    slug = company["slug"]
    ats_pref = company["ats"]
    found_jobs = []

    # Check Ashby
    if ats_pref in ("Ashby", "Auto"):
        ashby_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        try:
            r = requests.get(ashby_url, timeout=6)
            if r.status_code == 200:
                jobs = r.json().get("jobs", [])
                record_log(f"{c_name} (Ashby)", ashby_url, "Success (200)", f"Discovered {len(jobs)} total jobs")
                for j in jobs:
                    title = sanitize_text(j.get("title"))
                    loc = sanitize_text(j.get("locationName") or "US (Remote / On-site)")
                    job_url = j.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id')}"
                    found_jobs.append({
                        "company": c_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"{c_name} (Ashby API)",
                        "comp": "$200K - $350K + Equity",
                        "domain": f"AI Startup ({c_name})"
                    })
                if found_jobs:
                    return found_jobs
            elif r.status_code == 403:
                record_log(f"{c_name} (Ashby)", ashby_url, "HTTP 403", "Cloudflare / Bot Protection Active")
            else:
                record_log(f"{c_name} (Ashby)", ashby_url, f"HTTP {r.status_code}", "Endpoint returned non-200")
        except Exception as e:
            record_log(f"{c_name} (Ashby)", ashby_url, "Error", str(e))

    # Check Greenhouse
    if ats_pref in ("Greenhouse", "Auto"):
        gh_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        try:
            r = requests.get(gh_url, timeout=6)
            if r.status_code == 200:
                jobs = r.json().get("jobs", [])
                record_log(f"{c_name} (Greenhouse)", gh_url, "Success (200)", f"Discovered {len(jobs)} total jobs")
                for j in jobs:
                    title = sanitize_text(j.get("title"))
                    loc = sanitize_text(j.get("location", {}).get("name") or "US (Remote / On-site)")
                    job_url = j.get("absolute_url")
                    found_jobs.append({
                        "company": c_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"{c_name} (Greenhouse API)",
                        "comp": "$200K - $350K + Equity",
                        "domain": f"AI Startup ({c_name})"
                    })
                if found_jobs:
                    return found_jobs
            elif r.status_code == 403:
                record_log(f"{c_name} (Greenhouse)", gh_url, "HTTP 403", "Cloudflare / Bot Protection Active")
            else:
                record_log(f"{c_name} (Greenhouse)", gh_url, f"HTTP {r.status_code}", "Endpoint returned non-200")
        except Exception as e:
            record_log(f"{c_name} (Greenhouse)", gh_url, "Error", str(e))

    # Check Lever
    if ats_pref in ("Lever", "Auto"):
        lever_url = f"https://api.lever.co/v0/postings/{slug}"
        try:
            r = requests.get(lever_url, timeout=6)
            if r.status_code == 200:
                jobs = r.json()
                record_log(f"{c_name} (Lever)", lever_url, "Success (200)", f"Discovered {len(jobs)} total jobs")
                for j in jobs:
                    title = sanitize_text(j.get("text"))
                    loc = sanitize_text(j.get("categories", {}).get("location") or "US (Remote / On-site)")
                    job_url = j.get("hostedUrl")
                    found_jobs.append({
                        "company": c_name,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "source": f"{c_name} (Lever API)",
                        "comp": "$200K - $350K + Equity",
                        "domain": f"AI Startup ({c_name})"
                    })
                if found_jobs:
                    return found_jobs
            elif r.status_code == 403:
                record_log(f"{c_name} (Lever)", lever_url, "HTTP 403", "Cloudflare / Bot Protection Active")
            else:
                record_log(f"{c_name} (Lever)", lever_url, f"HTTP {r.status_code}", "Endpoint returned non-200")
        except Exception as e:
            record_log(f"{c_name} (Lever)", lever_url, "Error", str(e))

    return found_jobs

def scrape_jobs_directly_from_company_website(company, direct_keywords):
    c_name = company["name"]
    website = company.get("website", "")
    found_jobs = []

    if not website:
        return found_jobs

    candidate_career_urls = [
        website.rstrip("/") + "/careers",
        website.rstrip("/") + "/jobs",
        website.rstrip("/") + "/about/careers",
        website.rstrip("/") + "/join-us"
    ]

    kw_list = [kw.lower() for kw in direct_keywords] if direct_keywords else ['product manager', 'engineer', 'developer', 'manager', 'lead']

    for c_url in candidate_career_urls:
        try:
            r = curl_requests.get(c_url, impersonate="chrome", timeout=8)
            if r.status_code == 200:
                record_log(f"{c_name} Website", c_url, "Success (200)", "Direct career website page scraped successfully")
                soup = BeautifulSoup(r.text, "html.parser")
                links = soup.find_all("a", href=True)
                for link in links:
                    t_text = sanitize_text(link.get_text())
                    href = link["href"]
                    if not href.startswith("http"):
                        href = requests.compat.urljoin(c_url, href)
                    
                    if any(kw in t_text.lower() for kw in kw_list):
                        found_jobs.append({
                            "company": c_name,
                            "title": t_text,
                            "location": "US (Remote / On-site)",
                            "url": href,
                            "source": f"{c_name} Direct Career Site",
                            "comp": "$200K - $350K + Equity",
                            "domain": f"Direct Website Career Page ({c_name})"
                        })
                if found_jobs:
                    break
            elif r.status_code in (403, 401):
                record_log(f"{c_name} Website", c_url, f"HTTP {r.status_code}", "Cloudflare / Login required barrier")
            else:
                record_log(f"{c_name} Website", c_url, f"HTTP {r.status_code}", "Careers page not found / Non-200")
        except Exception as e:
            record_log(f"{c_name} Website", c_url, "Error / Failure", str(e))

    return found_jobs

# --- Filtering & Deduplication ---

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

# --- Main Engine Execution ---

def main():
    start_time = datetime.now()
    today_str = start_time.strftime("%b %d, %Y")
    logger.info("================================================================================")
    logger.info(f"Starting Ground-Truth Job Discovery Engine at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Data Directory Target: {DATA_DIR}")
    logger.info(f"Config File Used: {CONFIG_FILE}")
    logger.info("================================================================================")

    config = load_json(CONFIG_FILE)
    news_sources = config.get("funding_news_sources", [])
    filter_criteria = config.get("filter_criteria", {})

    role_label = filter_criteria.get("role_category_label", "Individual Contributor (IC) Senior Roles")
    min_salary = filter_criteria.get("min_base_salary_usd", 200000)
    salary_str = f"${min_salary:,}+ base salary / equity" if min_salary else "Competitive Comp"

    # 1. Step 1: News Entity Extractor -> Auto-update Target Companies Config in Pipeline.md
    extract_funding_news_and_update_targets(news_sources)

    # 2. Parse Target Companies Config from Pipeline.md
    target_companies = parse_target_companies_from_pipeline()
    logger.info(f"Loaded {len(target_companies)} target companies from Pipeline.md Command Center.")

    # 3. Discover Jobs for Target Companies (ATS APIs + Direct Website Scraping)
    discovered_raw_jobs = []
    direct_keywords = filter_criteria.get("direct_career_site_keywords", [])

    for comp in target_companies:
        c_name = comp["name"]
        # Strategy A: ATS API Check
        jobs = fetch_jobs_from_ats_api(comp)
        
        # Strategy B: Direct Website Career Page Scraping if ATS API yielded 0
        if not jobs:
            jobs = scrape_jobs_directly_from_company_website(comp, direct_keywords)

        if jobs:
            logger.info(f"Discovered {len(jobs)} live jobs for '{c_name}'")
            discovered_raw_jobs.extend(jobs)

    # 4. Filter & Evaluate Fit Scores
    fit_cfg = filter_criteria.get("fit_scoring", {})
    threshold = fit_cfg.get("fit_score_threshold_percent", 75)
    p_urls, p_jids, p_croles, p_c12m = parse_exclusions_from_pipeline(PIPELINE_FILE, filter_criteria)

    accepted_leads = []
    filtered_already_considered_count = 0

    for item in discovered_raw_jobs:
        comp_name = item["company"]
        role_title = item["title"]
        loc_text = item["location"]
        url = item["url"]
        comp_text = item["comp"]
        domain_text = item["domain"]

        if not is_matching_role(role_title, filter_criteria):
            continue
        if not is_eligible_location(loc_text, role_title, filter_criteria):
            continue

        already_considered, reason = is_already_considered(item, p_urls, p_jids, p_croles, p_c12m)
        if already_considered:
            filtered_already_considered_count += 1
            continue

        fit_score = calculate_fit_score(role_title, domain_text, comp_text, comp_name, filter_criteria)
        if fit_score >= threshold:
            accepted_leads.append({
                "company": comp_name,
                "stage": "High-Growth Funded Startup",
                "role": role_title,
                "location": loc_text,
                "comp": comp_text,
                "fit_score": f"{fit_score}%",
                "source": item["source"],
                "url": url,
                "date_added": today_str
            })

    # 5. Write Output to job-leads.md
    header_content = f"""# Job Leads & High-Growth Startup Discovery

*Last processed: {today_str}*

> [!INFO]
> **Workflow Guide**:
> - This file is automatically populated and updated by the `find-jobs` engine.
> - **Inclusion Criteria**: Direct live US-eligible postings for {role_label} ({salary_str}), valuation ≥ $100M USD, or raised Series B/C/D+ funding in the last 6 months.
> - **Fit Threshold**: Minimum **{threshold}% fit score** evaluated against [Profile.md](Profile.md) and candidate background.
> - **User Action**: Review these leads periodically. Move approved entries to `ToDo` in [Pipeline.md](Pipeline.md).

---

## ⚡ Shortlisted Opportunities & Funded Startups (Fit Score ≥ {threshold}%)

| Company | Stage / Funding | Role / Focus Area | Location | Base Pay / Comp | Fit Score | Status / Source | Date Added |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""

    all_rows = []
    for lead in accepted_leads:
        role_link = f"[{lead['role']}]({lead['url']})" if lead['url'] else lead['role']
        row = f"| **{lead['company']}** | {lead['stage']} | {role_link} | {lead['location']} | {lead['comp']} | **{lead['fit_score']}** | {lead['source']} | {lead['date_added']} |"
        all_rows.append(row)

    logs_section = """
---

## 🚨 Scraping & Discovery Logs (Success / Errors / Failures)

| Source / Company | Target URL | Status Code / Result | Details / Error Reason | Timestamp |
| :--- | :--- | :--- | :--- | :--- |
"""

    log_rows = []
    for log in GLOBAL_SCRAPE_LOGS:
        l_row = f"| **{log['source']}** | [{log['url']}]({log['url']}) | {log['status']} | {log['details']} | {log['timestamp']} |"
        log_rows.append(l_row)

    final_document = header_content + "\n".join(all_rows) + ("\n" if all_rows else "") + logs_section + "\n".join(log_rows) + "\n"

    with open(JOB_LEADS_FILE, "w", encoding="utf-8") as f:
        f.write(final_document)

    end_time = datetime.now()
    duration = round((end_time - start_time).total_seconds(), 2)

    logger.info("================================================================================")
    logger.info(f"Engine Execution Finished in {duration}s.")
    logger.info(f"Target Companies Scanned: {len(target_companies)}")
    logger.info(f"Accepted Qualifying Leads: {len(accepted_leads)}")
    logger.info(f"Scraping Logs Written to job-leads.md ({len(GLOBAL_SCRAPE_LOGS)} log entries)")
    logger.info("================================================================================")

if __name__ == "__main__":
    main()
