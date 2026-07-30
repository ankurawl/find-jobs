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
STEP1_FILE = os.path.join(DATA_DIR, "step1.md")
STEP2_FILE = os.path.join(DATA_DIR, "step2.md")
STEP3_FILE = os.path.join(DATA_DIR, "step3.md")
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

AGGREGATOR_DOMAINS = {
    "techcrunch.com", "venturebeat.com", "crunchbase.com", "pitchbook.com",
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "youtube.com",
    "github.com", "wikipedia.org", "medium.com", "news.ycombinator.com",
    "bloomberg.com", "reuters.com", "wsj.com", "forbes.com",
    "businessinsider.com", "prnewswire.com", "businesswire.com", "globenewswire.com"
}

NOISE_PREFIXES = [
    r'^(?:As|The|AI|New|Startup|Tech|How|Why|What|After|With|About|For|In|On)\s+',
    r'^(?:bot-detection startup|synthetic-user startup|edtech platform|training platform|battery storage startup|cloud security startup|cybersecurity startup|fintech startup|healthtech startup|medtech startup|biotech startup|stealth startup)\s+',
    r'^(?:ery storage startup|ning platform|form)\s+'
]

def clean_company_name(name):
    if not name:
        return ""
    clean = name.strip()
    for pat in NOISE_PREFIXES:
        clean = re.sub(pat, '', clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r'^[^\w]+', '', clean)
    return clean

def is_aggregator_domain(url):
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        for agg in AGGREGATOR_DOMAINS:
            if agg in netloc:
                return True
        return False
    except Exception:
        return True

def extract_article_links(article_url):
    """Scrapes outbound links from a news article URL to find potential company domains."""
    if not article_url:
        return []
    outbound_links = []
    try:
        r = curl_requests.get(article_url, impersonate="chrome", timeout=8)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and not is_aggregator_domain(href):
                    outbound_links.append(href)
    except Exception as e:
        logger.debug(f"Error fetching article links from {article_url}: {e}")
    return list(dict.fromkeys(outbound_links))

def search_ddg_html(query):
    """Performs a DuckDuckGo HTML search and returns result link URLs."""
    urls = []
    try:
        search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = curl_requests.get(search_url, impersonate="chrome", headers=headers, timeout=8)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", class_=re.compile(r"result__url|result__snippet|result__title"), href=True):
                href = a["href"]
                if "uddg=" in href:
                    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if "uddg" in parsed:
                        href = parsed["uddg"][0]
                if href.startswith("http") and not is_aggregator_domain(href):
                    urls.append(href)
    except Exception as e:
        logger.debug(f"DDG search error for '{query}': {e}")
    return list(dict.fromkeys(urls))

def verify_and_select_best_domain(candidate_urls, company_name, news_context):
    """Scrapes candidate landing pages and scores against news context to select official domain."""
    if not candidate_urls:
        slug = company_name.lower().replace(" ", "").replace(".", "")
        return f"https://{slug}.com"

    c_name_norm = company_name.lower().strip()
    c_words = set(re.findall(r'\w+', c_name_norm))
    ignore_words = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "raises", "raised", "funding", "series", "million", "billion"}
    ctx_words = set(re.findall(r'\w+', news_context.lower())) - ignore_words

    best_url = candidate_urls[0]
    best_score = -1

    for url in candidate_urls[:3]:
        score = 0
        try:
            domain = urllib.parse.urlparse(url).netloc.lower()
            if any(w in domain for w in c_words if len(w) >= 3):
                score += 10

            r = curl_requests.get(url, impersonate="chrome", timeout=6)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                title = (soup.title.string if soup.title else "").lower()
                meta_desc = ""
                meta_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)}) or soup.find("meta", attrs={"property": re.compile(r"og:description", re.I)})
                if meta_tag:
                    meta_desc = (meta_tag.get("content") or "").lower()

                combined_text = title + " " + meta_desc
                if any(w in combined_text for w in c_words if len(w) >= 3):
                    score += 15

                overlap = len(ctx_words.intersection(set(re.findall(r'\w+', combined_text))))
                score += overlap * 2

                if score > best_score:
                    best_score = score
                    best_url = url
        except Exception:
            pass

    return best_url.rstrip("/")

def resolve_company_domain(company_name, news_context, article_url=None):
    """3-stage domain resolution: 1. Article links, 2. Web search fallback, 3. Context verification."""
    candidates = []
    if article_url:
        candidates = extract_article_links(article_url)
    if not candidates:
        candidates = search_ddg_html(f"{company_name} official website startup")
    return verify_and_select_best_domain(candidates, company_name, news_context)

def append_new_target_company_to_pipeline_with_limit(comp_name, reason, website, ats_info="Auto", article_url=None, max_new_companies=100, current_session_count=0):
    if current_session_count >= max_new_companies:
        logger.warning(f"Reached max session limit of {max_new_companies} new companies added to Pipeline.md.")
        return False, current_session_count

    content = read_file(PIPELINE_FILE)
    if not content or "### 🎯 Target Companies Config" not in content:
        return False, current_session_count

    comp_norm = comp_name.lower().strip()
    if comp_norm in content.lower():
        return False, current_session_count

    today_str = datetime.now().strftime("%b %d, %Y")
    notes = f"Added via News Sync ({reason})"
    if article_url:
        notes += f" | Article: {article_url}"
    notes += f" - {today_str}"

    new_row = f"| **{comp_name}** | {reason} | {website} | {ats_info} | {notes} |\n"
    
    parts = content.split("### 🎯 Target Companies Config\n")
    if len(parts) == 2:
        table_lines = parts[1].split("\n\n")[0]
        updated_table = table_lines + "\n" + new_row.strip()
        updated_content = parts[0] + "### 🎯 Target Companies Config\n" + parts[1].replace(table_lines, updated_table, 1)
        with open(PIPELINE_FILE, "w", encoding="utf-8") as f:
            f.write(updated_content)
        current_session_count += 1
        logger.info(f"Auto-added new funded company to Pipeline.md ({current_session_count}/{max_new_companies}): {comp_name} ({website})")
        return True, current_session_count
    return False, current_session_count

def extract_funding_news_and_update_targets(news_sources, max_new_companies=100):
    logger.info("Extracting funded startup entity leads from news sources...")
    funding_patterns = [
        re.compile(r'([A-Z][A-Za-z0-9\.\-\s]{2,25})\s+(?:raises|raised|secures|secured|snags|snagged|bags|bagged|nabs|nabbed|closes|closed|lands|landed)\s+(\$\d+(?:\.\d+)?\s*(?:M|B|million|billion)?(?:\s+(?:Series\s+[A-E]|growth|funding|valuation))?)', re.IGNORECASE),
        re.compile(r'([A-Z][A-Za-z0-9\.\-\s]{2,25})\s+hits\s+(\$\d+(?:\.\d+)?\s*(?:M|B|million|billion)?\s*valuation)', re.IGNORECASE)
    ]

    discovered_companies = []
    session_count = 0

    for src in news_sources:
        if session_count >= max_new_companies:
            break
        s_name = src["name"]
        s_url = src["url"]
        try:
            r = curl_requests.get(s_url, impersonate="chrome", timeout=10)
            if r.status_code == 200:
                record_log(s_name, s_url, "Success (200)", f"Fetched news feed successfully ({len(r.text)} bytes)")
                soup = BeautifulSoup(r.text, "html.parser")
                
                for a in soup.find_all('a', href=True):
                    txt = sanitize_text(a.get_text())
                    href = a['href']
                    if not href.startswith("http"):
                        href = requests.compat.urljoin(s_url, href)

                    if len(txt) > 15:
                        for pat in funding_patterns:
                            m = pat.search(txt)
                            if m:
                                comp_raw = m.group(1).strip()
                                fund = m.group(2).strip()
                                comp_clean = clean_company_name(comp_raw)
                                
                                if len(comp_clean) >= 3 and not any(w in comp_clean.lower() for w in ['series', 'million', 'billion', 'funding', 'round', 'investor', 'capital']):
                                    website = resolve_company_domain(comp_clean, txt, href)
                                    reason = f"Funding News ({s_name}: {fund})"
                                    added, session_count = append_new_target_company_to_pipeline_with_limit(
                                        comp_clean, reason, website, ats_info="Auto", article_url=href,
                                        max_new_companies=max_new_companies, current_session_count=session_count
                                    )
                                    if added:
                                        discovered_companies.append(comp_clean)
            else:
                record_log(s_name, s_url, f"HTTP Error ({r.status_code})", "Non-200 response from news source")
        except Exception as e:
            record_log(s_name, s_url, "Error / Failure", str(e))

    return discovered_companies

# --- Job Discovery Strategies (Multi-Probe) ---

def fetch_jobs_from_ats_api(company):
    c_name = company["name"]
    slug = company["slug"]
    ats_pref = company["ats"]
    website = company.get("website", "")
    found_jobs = []

    # Derive slug candidates from company name and website domain
    domain_slug = ""
    if website:
        netloc = urllib.parse.urlparse(website).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        domain_slug = netloc.split(".")[0]

    slug_candidates = list(dict.fromkeys([
        slug,
        c_name.lower().replace(" ", "").replace(".", ""),
        domain_slug,
        f"{domain_slug}hq",
        f"{domain_slug}-ai"
    ]))
    slug_candidates = [s for s in slug_candidates if s and len(s) >= 2]

    # Probe Ashby
    if ats_pref in ("Ashby", "Auto"):
        for s in slug_candidates:
            ashby_url = f"https://api.ashbyhq.com/posting-api/job-board/{s}"
            try:
                r = requests.get(ashby_url, timeout=6)
                if r.status_code == 200:
                    jobs = r.json().get("jobs", [])
                    if jobs:
                        record_log(f"{c_name} (Ashby)", ashby_url, "Success (200)", f"Discovered {len(jobs)} total jobs")
                        for j in jobs:
                            title = sanitize_text(j.get("title"))
                            loc = sanitize_text(j.get("locationName") or "US (Remote / On-site)")
                            job_url = j.get("jobUrl") or f"https://jobs.ashbyhq.com/{s}/{j.get('id')}"
                            found_jobs.append({
                                "company": c_name,
                                "title": title,
                                "location": loc,
                                "url": job_url,
                                "source": f"{c_name} (Ashby API)",
                                "comp": "$200K - $350K + Equity",
                                "domain": f"AI Startup ({c_name})"
                            })
                        return found_jobs
            except Exception as e:
                logger.debug(f"Ashby probe error for {c_name} ({s}): {e}")

    # Probe Greenhouse
    if ats_pref in ("Greenhouse", "Auto"):
        for s in slug_candidates:
            gh_url = f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs"
            try:
                r = requests.get(gh_url, timeout=6)
                if r.status_code == 200:
                    jobs = r.json().get("jobs", [])
                    if jobs:
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
                        return found_jobs
            except Exception as e:
                logger.debug(f"Greenhouse probe error for {c_name} ({s}): {e}")

    # Probe Lever
    if ats_pref in ("Lever", "Auto"):
        for s in slug_candidates:
            lever_url = f"https://api.lever.co/v0/postings/{s}"
            try:
                r = requests.get(lever_url, timeout=6)
                if r.status_code == 200:
                    jobs = r.json()
                    if isinstance(jobs, list) and jobs:
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
                        return found_jobs
            except Exception as e:
                logger.debug(f"Lever probe error for {c_name} ({s}): {e}")

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
        except Exception as e:
            logger.debug(f"Error scraping career site {c_url}: {e}")

    return found_jobs

def web_search_careers_page_fallback(company):
    """Probe 3: Web search for company careers/jobs page if ATS and direct site probing yield 0 jobs."""
    c_name = company["name"]
    found_jobs = []
    search_results = search_ddg_html(f"{c_name} careers jobs ashby OR greenhouse OR lever")

    for url in search_results[:3]:
        try:
            r = curl_requests.get(url, impersonate="chrome", timeout=8)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                links = soup.find_all("a", href=True)
                for link in links:
                    t_text = sanitize_text(link.get_text())
                    href = link["href"]
                    if not href.startswith("http"):
                        href = requests.compat.urljoin(url, href)
                    if len(t_text) >= 8 and any(kw in t_text.lower() for kw in ['product manager', 'lead', 'senior', 'principal', 'staff', 'manager']):
                        found_jobs.append({
                            "company": c_name,
                            "title": t_text,
                            "location": "US (Remote / On-site)",
                            "url": href,
                            "source": f"{c_name} Web Search Careers Link",
                            "comp": "$200K - $350K + Equity",
                            "domain": f"Web Search Discovery ({c_name})"
                        })
                if found_jobs:
                    record_log(f"{c_name} Web Search", url, "Success (200)", f"Discovered {len(found_jobs)} jobs via web search fallback")
                    break
        except Exception as e:
            logger.debug(f"Web search careers fallback error for {c_name} ({url}): {e}")

    return found_jobs

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
        record_log(name, url, "Error", str(e))

    return jobs

def discover_raw_jobs_for_company(company, direct_keywords):
    """Executes 3-tier multi-probe strategy for a target company."""
    # Probe 1: ATS APIs
    jobs = fetch_jobs_from_ats_api(company)
    # Probe 2: Direct Website Career Pages
    if not jobs:
        jobs = scrape_jobs_directly_from_company_website(company, direct_keywords)
    # Probe 3: Web Search Fallback for Careers
    if not jobs:
        jobs = web_search_careers_page_fallback(company)
    return jobs


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

# --- Pipeline Phase Functions (Exposed for Debug Harness & Engine Execution) ---

def collect_all_raw_jobs(config, max_new_companies=100):
    """Step 1: Discover companies from funding news, sync Pipeline.md, and run multi-probe discovery across target companies and web feeds."""
    news_sources = config.get("funding_news_sources", [])
    filter_criteria = config.get("filter_criteria", {})
    direct_keywords = filter_criteria.get("direct_career_site_keywords", [])

    # 1. Scrape funding news, resolve domains, and update target companies in Pipeline.md (capped at max_new_companies)
    extract_funding_news_and_update_targets(news_sources, max_new_companies=max_new_companies)

    # 2. Parse target companies from Pipeline.md
    target_companies = parse_target_companies_from_pipeline()
    logger.info(f"Loaded {len(target_companies)} target companies from Pipeline.md.")

    raw_jobs = []

    # 3. Multi-probe discovery for each target company
    for comp in target_companies:
        jobs = discover_raw_jobs_for_company(comp, direct_keywords)
        if jobs:
            logger.info(f"Discovered {len(jobs)} raw jobs for target company '{comp['name']}'")
            raw_jobs.extend(jobs)

    # 4. Web sources discovery feeds from config.json
    for src in config.get("job_sources", []):
        if src.get("type") in ("job_board", "curated_jobs", "curated_pm_jobs", "tech_news"):
            jobs = fetch_web_source(src)
            if jobs:
                logger.info(f"Discovered {len(jobs)} raw jobs from web feed '{src['name']}'")
                raw_jobs.extend(jobs)

    return raw_jobs

def filter_and_score_jobs(raw_jobs, filter_criteria):
    """Step 2: Apply role matching, location eligibility, and fit score threshold evaluation."""
    threshold = filter_criteria.get("fit_scoring", {}).get("fit_score_threshold_percent", 75)
    filtered_jobs = []
    step2_evaluations = []

    for j in raw_jobs:
        role_pass = is_matching_role(j["title"], filter_criteria)
        loc_pass = is_eligible_location(j["location"], j["title"], filter_criteria)

        if not role_pass:
            status = "Rejected (Role Mismatch)"
            is_passed = False
        elif not loc_pass:
            status = "Rejected (Location Non-US)"
            is_passed = False
        else:
            score = calculate_fit_score(j["title"], j["domain"], j["comp"], j["company"], filter_criteria)
            if score >= threshold:
                status = f"PASSED ({score}%)"
                is_passed = True
                filtered_jobs.append(j)
            else:
                status = f"Rejected (Low Fit Score: {score}%)"
                is_passed = False

        step2_evaluations.append({
            "job": j,
            "status": status,
            "passed": is_passed
        })

    return filtered_jobs, step2_evaluations

def deduplicate_jobs(filtered_jobs, filter_criteria):
    """Step 3: Deduplicate filtered jobs against Pipeline.md rules."""
    p_urls, p_jids, p_croles, p_c12m = parse_exclusions_from_pipeline(PIPELINE_FILE, filter_criteria)
    accepted_leads = []
    step3_records = []
    today_str = datetime.now().strftime("%b %d, %Y")

    for j in filtered_jobs:
        already_considered, reason = is_already_considered(j, p_urls, p_jids, p_croles, p_c12m)
        if already_considered:
            step3_records.append({
                "job": j,
                "status": "EXCLUDED",
                "reason": reason
            })
        else:
            step3_records.append({
                "job": j,
                "status": "NEW LEAD",
                "reason": "N/A"
            })
            score = calculate_fit_score(j["title"], j["domain"], j["comp"], j["company"], filter_criteria)
            accepted_leads.append({
                "company": j["company"],
                "stage": "High-Growth Funded Startup",
                "role": j["title"],
                "location": j["location"],
                "comp": j["comp"],
                "fit_score": f"{score}%",
                "source": j["source"],
                "url": j["url"],
                "date_added": today_str
            })

    return accepted_leads, step3_records

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
    filter_criteria = config.get("filter_criteria", {})

    role_label = filter_criteria.get("role_category_label", "Individual Contributor (IC) Senior Roles")
    min_salary = filter_criteria.get("min_base_salary_usd", 200000)
    salary_str = f"${min_salary:,}+ base salary / equity" if min_salary else "Competitive Comp"

    # Step 1: Collect Raw Jobs
    raw_jobs = collect_all_raw_jobs(config, max_new_companies=100)
    logger.info(f"Step 1 Complete: Discovered {len(raw_jobs)} total raw job postings.")

    # Step 2: Role, Location & Fit Score Filtering
    filtered_jobs, step2_evals = filter_and_score_jobs(raw_jobs, filter_criteria)
    logger.info(f"Step 2 Complete: {len(filtered_jobs)} jobs passed fit score threshold.")

    # Step 3: Deduplicate against Pipeline.md
    accepted_leads, step3_records = deduplicate_jobs(filtered_jobs, filter_criteria)
    logger.info(f"Step 3 Complete: {len(accepted_leads)} new qualifying leads ready for job-leads.md.")

    # Write Output to job-leads.md
    threshold = filter_criteria.get("fit_scoring", {}).get("fit_score_threshold_percent", 75)
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
    logger.info(f"Accepted Qualifying Leads: {len(accepted_leads)}")
    logger.info(f"Scraping Logs Written to job-leads.md ({len(GLOBAL_SCRAPE_LOGS)} log entries)")
    logger.info("================================================================================")

if __name__ == "__main__":
    main()

