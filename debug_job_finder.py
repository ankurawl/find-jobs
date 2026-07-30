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

SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")
if not os.path.exists(SOURCES_FILE):
    example_sources = os.path.join(REPO_DIR, "personal-files", "sources.example.json")
    if os.path.exists(example_sources):
        SOURCES_FILE = example_sources

PROFILE_FILE = os.path.join(DATA_DIR, "Profile.md")
PIPELINE_FILE = os.path.join(DATA_DIR, "Pipeline.md")
JOB_LEADS_FILE = os.path.join(DATA_DIR, "job-leads.md")

STEP1_FILE = os.path.join(DATA_DIR, "step1.md")
STEP2_FILE = os.path.join(DATA_DIR, "step2.md")
STEP3_FILE = os.path.join(DATA_DIR, "step3.md")

# 16 Target Startup Companies with corrected ATS slugs and endpoints
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
            
            # Scrape links that look like job postings or articles
            links = soup.find_all("a", href=True)
            seen_titles = set()
            for link in links:
                t_text = sanitize_text(link.get_text())
                href = link["href"]
                if not href.startswith("http"):
                    href = requests.compat.urljoin(url, href)
                
                # Filter out generic short nav links
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

# --- Filtering Functions for Step 2 ---

def is_ic_pm_role(title):
    t = title.lower()
    
    # Rejections for People Management / Executive roles
    people_mgmt_rejections = [
        'director', 'vp of', 'vp,', 'head of', 'group product manager', 'gpm',
        'people manager', 'manager, sales', 'manager, engineering', 'engineering manager',
        'talent development manager', 'sales manager', 'manager of product'
    ]
    if any(rej in t for rej in people_mgmt_rejections):
        return False
        
    # IC PM Positive Patterns
    pm_patterns = [
        r'\b(principal|staff|senior|sr\.?|lead)?\s*(product\s*manager|product\s*lead|pm)\b',
        r'\bresearch\s+product\s+manager\b',
        r'\bdeployed\s+product\s+manager\b',
        r'\bai\s+product\s+manager\b'
    ]
    
    matches_pm = any(re.search(pat, t) for pat in pm_patterns)
    if not matches_pm:
        return False
        
    # Rejections for non-PM roles
    non_pm_rejections = [
        'sales development', 'business development', 'development representative', 
        'account executive', 'product marketing', 'product designer', 'product security',
        'program manager', 'project manager', 'development manager', 'enablement manager',
        'software engineer', 'sales engineer', 'recruiter', 'analyst', 'legal', 'finance'
    ]
    if any(rej in t for rej in non_pm_rejections):
        return False

    return True

def is_us_eligible_location(loc_str, title_str=""):
    title_lower = str(title_str).lower()
    loc_lower = str(loc_str).lower()
    
    explicit_title_non_us = ['sydney', 'australia', 'german speaking', 'emea only', 'apac only', 'london only', 'japan only']
    if any(term in title_lower for term in explicit_title_non_us):
        return False
        
    us_indicators = [
        r'\bus\b', r'\bunited states\b', r'\bamerica\b', r'\bamericas\b', r'\bnorth america\b',
        r'\bca\b', r'\bny\b', r'\bwa\b', r'\btx\b', r'\bma\b', r'\bco\b', r'\bdc\b', r'\bil\b', r'\bva\b', r'\bga\b', r'\bfl\b',
        r'san francisco', r'new york', r'austin', r'seattle', r'boston', r'chicago', r'los angeles', r'denver', r'washington',
        r'remote - us', r'us \(remote', r'remote \(us\)', r'us /', r'/ us', r'united states'
    ]
    
    non_us_indicators = [
        'london', 'uk', 'united kingdom', 'germany', 'berlin', 'munich', 
        'france', 'paris', 'sydney', 'australia', 'melbourne', 'canada', 'toronto', 
        'vancouver', 'singapore', 'japan', 'tokyo', 'india', 'bangalore', 'mumbai', 
        'saudi arabia', 'riyadh', 'dubai', 'uae', 'qatar', 'doha', 'emea', 'apac', 
        'latam', 'europe', 'asia', 'south korea', 'seoul', 'brazil', 'mexico', 
        'amsterdam', 'netherlands', 'switzerland', 'zurich', 'stockholm', 'sweden', 
        'dublin', 'ireland', 'mena'
    ]
    
    has_us_indicator = any(re.search(pat, loc_lower) for pat in us_indicators)
    
    if loc_str == 'US (Remote / On-site)' or has_us_indicator or loc_str == 'US / Unspecified':
        return True
        
    has_non_us = any(re.search(r'\b' + re.escape(term) + r'\b', loc_lower) for term in non_us_indicators)
    if has_non_us and not has_us_indicator:
        return False

    return True

def calculate_fit_score(title, domain_text, comp_text, company_name):
    score = 50
    combined = (title + " " + domain_text).lower()
    
    if any(ex in company_name.lower() for ex in ["meta", "facebook", "amazon"]):
        return 0
        
    if re.search(r'\b(agentic|agent|agents|ai agent|ai agents|evals|evaluation|eval)\b', combined):
        score += 25
    elif re.search(r'\b(ai|llm|machine learning|genai|generative ai)\b', combined):
        score += 18
        
    if re.search(r'\b(principal|staff|lead|senior|sr)\b', combined):
        score += 15

    if re.search(r'\b(fintech|platform|developer|subscriptions|marketplace|saas|b2b)\b', combined):
        score += 10

    if "$200k" in comp_text.lower() or "$2" in comp_text or "200,000" in comp_text or "300" in comp_text:
        score += 10

    return min(100, max(0, score))

# --- Pipeline Exclusions for Step 3 ---

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

def parse_exclusions_from_pipeline(file_path):
    excluded_urls = set()
    excluded_job_ids = set()
    excluded_company_roles = set()
    excluded_companies_12m = set()

    if not os.path.exists(file_path):
        return excluded_urls, excluded_job_ids, excluded_company_roles, excluded_companies_12m

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
                    if days_ago < 90:
                        if comp_norm and role_norm:
                            excluded_company_roles.add((comp_norm, role_norm))
                        for u in urls:
                            excluded_urls.add(u.strip())
                            jid = extract_job_id_from_url(u)
                            if jid:
                                excluded_job_ids.add(jid)

                elif "Rejected" in current_section or "Self Selected Out" in current_section:
                    interviewed = any(kw in status_text.lower() for kw in ['interview', 'hm round', 'panel', 'screen', 'working session'])
                    cutoff_days = 365 if interviewed else 90

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

# --- Main Debug Execution ---

def main():
    print("=== STARTING JOB FINDER DEBUG WORKFLOW ===")
    print(f"Data Directory Target: {DATA_DIR}")
    config = load_json(SOURCES_FILE)
    job_sources = config.get("job_sources", [])
    news_sources = config.get("funding_news_sources", [])

    all_raw_jobs = []
    source_counts = {}
    company_names = set()

    # Step 1: Collect ALL raw jobs from ALL sources
    print("\n--- STEP 1: Collecting Raw Listings ---")
    
    # A. 16 Target Company ATS Boards
    for comp in TARGET_COMPANIES:
        c_name = comp["name"]
        company_names.add(c_name)
        jobs = fetch_ats_jobs(comp)
        src_label = f"{c_name} ({comp['ats']} API)"
        source_counts[src_label] = len(jobs)
        all_raw_jobs.extend(jobs)
        print(f"Collected {len(jobs)} raw jobs from {c_name} via {comp['ats']}")

    # B. Web / Curated Sources
    for src in job_sources + news_sources:
        s_name = src["name"]
        jobs = fetch_web_source(src)
        source_counts[s_name] = len(jobs)
        all_raw_jobs.extend(jobs)
        print(f"Collected {len(jobs)} raw listings from {s_name}")

    # Write Step 1 Output
    step1_md = f"# Step 1: Raw Collected Job Listings (No Filtering, No Deduplication)\n\n"
    step1_md += f"**Total Raw Listings Discovered**: {len(all_raw_jobs)}\n"
    step1_md += f"**Total Sources Checked**: {len(source_counts)}\n\n"
    step1_md += "## Source Summary\n"
    step1_md += "| Source | Raw Count |\n| :--- | :--- |\n"
    for src, count in source_counts.items():
        step1_md += f"| {src} | {count} |\n"
    step1_md += "\n## Raw Listings Details\n\n"
    step1_md += "| # | Company | Title | Location | Source | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"
    for idx, j in enumerate(all_raw_jobs, 1):
        step1_md += f"| {idx} | **{j['company']}** | {j['title']} | {j['location']} | {j['source']} | [{j['url']}]({j['url']}) |\n"

    with open(STEP1_FILE, "w", encoding="utf-8") as f:
        f.write(step1_md)
    print(f"Saved Step 1 output to {STEP1_FILE}")

    # Step 2: Apply Filtering Logic
    print("\n--- STEP 2: Applying Filtering Logic ---")
    filtered_jobs = []
    threshold = config.get("filter_criteria", {}).get("fit_score_threshold_percent", 75)

    for j in all_raw_jobs:
        title = j["title"]
        loc = j["location"]
        comp = j["company"]
        
        # Rule 1: IC PM Title
        if not is_ic_pm_role(title):
            continue
            
        # Rule 2: US Location
        if not is_us_eligible_location(loc, title):
            continue
            
        # Rule 3: Fit Score Threshold
        fit_score = calculate_fit_score(title, j.get("domain", ""), j.get("comp", ""), comp)
        if fit_score < threshold:
            continue

        j["fit_score"] = fit_score
        filtered_jobs.append(j)

    step2_md = f"# Step 2: Filtered Job Listings (IC PM Rules, US Location, Fit Score ≥ {threshold}%)\n\n"
    step2_md += f"**Remaining Jobs After Filtering**: {len(filtered_jobs)}\n\n"
    step2_md += "| # | Company | Title | Location | Fit Score | Source | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    for idx, j in enumerate(filtered_jobs, 1):
        step2_md += f"| {idx} | **{j['company']}** | {j['title']} | {j['location']} | **{j['fit_score']}%** | {j['source']} | [{j['url']}]({j['url']}) |\n"

    with open(STEP2_FILE, "w", encoding="utf-8") as f:
        f.write(step2_md)
    print(f"Saved Step 2 output to {STEP2_FILE} ({len(filtered_jobs)} remaining)")

    # Step 3: Deduplicate Against Pipeline.md
    print("\n--- STEP 3: Deduplicating Against Pipeline.md ---")
    p_urls, p_jids, p_croles, p_c12m = parse_exclusions_from_pipeline(PIPELINE_FILE)
    
    deduped_jobs = []
    excluded_reasons = []

    for j in filtered_jobs:
        already_considered, reason = is_already_considered(j, p_urls, p_jids, p_croles, p_c12m)
        if already_considered:
            excluded_reasons.append((j, reason))
        else:
            deduped_jobs.append(j)

    step3_md = f"# Step 3: Final Deduplicated Job Opportunities (Compared against Pipeline.md)\n\n"
    step3_md += f"**Final Opportunities Available**: {len(deduped_jobs)}\n"
    step3_md += f"**Excluded Past Roles / Active Applications**: {len(excluded_reasons)}\n\n"
    step3_md += "## Final Qualifying Opportunities\n\n"
    step3_md += "| # | Company | Role | Location | Fit Score | Source | URL |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    for idx, j in enumerate(deduped_jobs, 1):
        step3_md += f"| {idx} | **{j['company']}** | {j['title']} | {j['location']} | **{j['fit_score']}%** | {j['source']} | [{j['url']}]({j['url']}) |\n"

    step3_md += "\n## Excluded Roles (Matched Pipeline.md)\n\n"
    step3_md += "| Company | Role | Exclusion Reason |\n| :--- | :--- | :--- |\n"
    for j, reason in excluded_reasons:
        step3_md += f"| **{j['company']}** | {j['title']} | {reason} |\n"

    with open(STEP3_FILE, "w", encoding="utf-8") as f:
        f.write(step3_md)
    print(f"Saved Step 3 output to {STEP3_FILE} ({len(deduped_jobs)} remaining)")

    # Print summary statistics
    print("\n=== SUMMARY METRICS FOR REPORT ===")
    print(f"Total Sources Checked: {len(source_counts)}")
    print(f"Target Companies Checked ({len(TARGET_COMPANIES)}): {', '.join([c['name'] for c in TARGET_COMPANIES])}")
    print(f"Total Raw Jobs Found: {len(all_raw_jobs)}")
    print(f"Jobs After Filtering (Step 2): {len(filtered_jobs)}")
    print(f"Jobs After Deduplication (Step 3): {len(deduped_jobs)}")

if __name__ == "__main__":
    main()
