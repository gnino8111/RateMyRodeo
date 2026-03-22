"""
RateMyRodeo — FastAPI backend
Endpoints: POST /analyze  POST /chat

Required environment variables (put in backend/.env):
  GEMINI_API_KEY  — picked up automatically by the google-genai client
"""

import os
import sys
import re
import json
import time
import asyncio

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from rapidfuzz import fuzz, process as rfprocess
from google import genai
from google.genai import types

# ── Setup ──────────────────────────────────────────────────────────────────────

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))

client = genai.Client()   # reads GEMINI_API_KEY from env automatically
MODEL  = "gemini-3-flash-preview"

from rmp_scraper import search_professor, get_ratings  # noqa: E402

app = FastAPI(title="RateMyRodeo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic request models ────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    professor_name: str
    course_code: str = "Unknown Course"
    syllabus_text: str = ""


class ChatMessage(BaseModel):
    role: str   # "ai" or "user"
    text: str


class ChatRequest(BaseModel):
    history: list[ChatMessage] = []
    user_text: str


# ── Type-safe helpers ──────────────────────────────────────────────────────────

def _float(value, default: float = 0.0) -> float:
    try:
        v = float(value)
        return default if v == -1 else v
    except (TypeError, ValueError):
        return default


def _int(value, default: int = 0) -> int:
    try:
        v = int(value)
        return default if v == -1 else v
    except (TypeError, ValueError):
        return default


def _bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    return bool(value) if value is not None else default


def _strip_json_fences(text: str) -> str:
    if "```" in text:
        for part in text.split("```"):
            cleaned = part.strip().lstrip("json").strip()
            if cleaned.startswith("{"):
                return cleaned
    return text


# ── Gemini retry helpers ───────────────────────────────────────────────────────

_TRANSIENT = ("429", "503", "500", "rate limit", "quota", "timeout", "unavailable", "deadline")


def _is_transient(exc: Exception) -> bool:
    return any(t in str(exc).lower() for t in _TRANSIENT)


def _gemini_call(fn, *args, max_retries: int = 3, base_delay: float = 1.5, **kwargs):
    """Synchronous Gemini call with exponential-backoff retry on transient errors."""
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_transient(exc) or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"[Gemini] transient error (attempt {attempt+1}/{max_retries}), retry in {delay:.1f}s: {exc}")
            time.sleep(delay)


async def _gemini_call_async(coro, max_retries: int = 3, base_delay: float = 1.5):
    """Async Gemini call with exponential-backoff retry on transient errors."""
    for attempt in range(max_retries):
        try:
            return await coro
        except Exception as exc:
            if not _is_transient(exc) or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"[Gemini] transient error (attempt {attempt+1}/{max_retries}), retry in {delay:.1f}s: {exc}")
            await asyncio.sleep(delay)


# ── RMP data fetch ─────────────────────────────────────────────────────────────

def fetch_rmp_data(professor_name: str) -> dict:
    """
    Look up the professor on RateMyProfessors (global search, any school).
    Returns a dict with expected keys plus 'school' — never raises.
    """
    fallback = {
        "found": False,
        "name": professor_name,
        "school": "",
        "department": "Unknown",
        "rating": 0.0,
        "difficulty": 0.0,
        "would_take_again": -1,
        "num_ratings": 0,
        "raw_ratings": [],
    }
    try:
        professor = search_professor(professor_name, school_id=None)
        if not professor:
            print(f"[RMP] No match found for {professor_name!r}")
            return fallback

        raw_ratings = get_ratings(professor["id"], max_ratings=50)

        return {
            "found": True,
            "name": f"{professor['firstName']} {professor['lastName']}",
            "school": professor.get("school", {}).get("name", ""),
            "department": professor.get("department") or "Unknown",
            "rating": round(_float(professor.get("avgRating")), 1),
            "difficulty": round(_float(professor.get("avgDifficulty")), 1),
            "would_take_again": _int(professor.get("wouldTakeAgainPercent"), -1),
            "num_ratings": _int(professor.get("numRatings")),
            "raw_ratings": raw_ratings,
        }
    except Exception as exc:
        print(f"[RMP] Error for {professor_name!r}: {exc}")
        return fallback


# ── School → subreddit mapping ─────────────────────────────────────────────────

_SCHOOL_SUBREDDITS: dict[str, str] = {
    "Boston University":                       "BostonU",
    "East Carolina University":                "ecu",
    "Florida State University":                "fsu",
    "George Mason University":                 "gmu",
    "Georgia Institute of Technology":         "gatech",
    "Georgia Tech":                            "gatech",
    "Grand Valley State University":           "GVSU",
    "Illinois State University":               "IllinoisStateU",
    "Indiana University":                      "IndianaUniversity",
    "James Madison University":                "jmu",
    "North Carolina State University":         "ncstate",
    "Ohio State University":                   "OSU",
    "Pennsylvania State University":           "PennStateUniversity",
    "Penn State":                              "PennStateUniversity",
    "Purdue University":                       "Purdue",
    "Rutgers University":                      "rutgers",
    "Texas Tech University":                   "TexasTech",
    "Towson University":                       "towson",
    "University of California Los Angeles":    "ucla",
    "University of Colorado Boulder":          "cuboulder",
    "University of Florida":                   "ufl",
    "University of Illinois Chicago":          "uic",
    "University of Illinois Urbana Champaign": "UIUC",
    "University of Kentucky":                  "uky",
    "University of Maryland":                  "UMD",
    "University of Maryland Baltimore County": "UMBC",
    "University of Michigan":                  "uofm",
    "University of North Carolina Chapel Hill":"UNC",
    "University of North Carolina Charlotte":  "UNCCharlotte",
    "University of Texas Austin":              "UTAustin",
    "University of Virginia":                  "uva",
    "University of Washington":                "udub",
    "Virginia Tech":                           "VirginiaTech",
    "West Virginia University":                "WVU",
}


def _school_to_subreddit(school_name: str) -> str | None:
    """Fuzzy-match a school name to its Reddit community."""
    if not school_name:
        return None
    normalized = school_name.lower().replace(",", "").replace("-", " ")
    for key, sub in _SCHOOL_SUBREDDITS.items():
        if key.lower() in normalized or normalized in key.lower():
            return sub
    match = rfprocess.extractOne(
        school_name, list(_SCHOOL_SUBREDDITS.keys()), scorer=fuzz.token_sort_ratio
    )
    if match and match[1] >= 70:
        return _SCHOOL_SUBREDDITS[match[0]]
    return None


# ── Reddit search ──────────────────────────────────────────────────────────────

def fetch_reddit_posts(professor_name: str, school_name: str = "", limit: int = 8) -> list[dict]:
    """
    Search Reddit for posts mentioning the professor.
    Tries the school-specific subreddit first; falls back to global search.
    Returns posts with title, selftext, score, url, and subreddit fields.
    """
    headers = {"User-Agent": "RateMyRodeo/1.0 (academic research project)"}
    results: list[dict] = []

    def _parse_children(children: list) -> list[dict]:
        return [
            {
                "title":     c["data"].get("title", ""),
                "selftext":  (c["data"].get("selftext") or "")[:400],
                "score":     c["data"].get("score", 0),
                "url":       f"https://www.reddit.com{c['data'].get('permalink', '')}",
                "subreddit": c["data"].get("subreddit", ""),
            }
            for c in children
        ]

    subreddit = _school_to_subreddit(school_name)

    # Try school subreddit first
    if subreddit:
        try:
            url = (
                f"https://www.reddit.com/r/{subreddit}/search.json"
                f"?q={requests.utils.quote(professor_name)}"
                f"&restrict_sr=1&sort=relevance&limit={limit}"
            )
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            results = _parse_children(resp.json().get("data", {}).get("children", []))
            print(f"[Reddit] r/{subreddit} -> {len(results)} posts for {professor_name!r}")
        except Exception as exc:
            print(f"[Reddit] Subreddit r/{subreddit} failed: {exc}")

    # Global fallback if subreddit gave fewer than 3 results
    if len(results) < 3:
        try:
            url = (
                "https://www.reddit.com/search.json"
                f"?q={requests.utils.quote(professor_name + ' professor')}"
                f"&type=link&sort=relevance&limit={limit}"
            )
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            global_posts = _parse_children(resp.json().get("data", {}).get("children", []))
            existing = {r["url"] for r in results}
            results += [p for p in global_posts if p["url"] not in existing]
            print(f"[Reddit] Global fallback -> {len(global_posts)} posts")
        except Exception as exc:
            print(f"[Reddit] Global search failed: {exc}")

    return results[:limit]


# ── GradeToday grade scraper ───────────────────────────────────────────────────
# GradeToday (http only) has real grade data for these schools.

_GT_SCHOOLS: dict[str, int] = {
    "East Carolina University":                    10,
    "George Mason University":                      9,
    "Grand Valley State University":               20,
    "Illinois State University":                   15,
    "Indiana University":                           4,
    "James Madison University":                    14,
    "Texas Tech University":                       17,
    "Towson University":                            1,
    "University of California Los Angeles":         5,
    "University of Colorado Boulder":              18,
    "University of Illinois Chicago":               7,
    "University of Illinois Urbana Champaign":      8,
    "University of Kentucky":                      13,
    "University of Maryland Baltimore County":      2,
    "University of North Carolina Chapel Hill":     3,
    "University of North Carolina Charlotte":      19,
    "University of Virginia":                      11,
    "University of Washington":                     6,
    "West Virginia University":                    12,
}

_GT_HEADERS = {"User-Agent": "RateMyRodeo/1.0 (academic research project)"}
_GT_BASE    = "http://gradetoday.com"


def _gt_get(path: str) -> BeautifulSoup | None:
    """Fetch a GradeToday page and return a BeautifulSoup object, or None on failure."""
    try:
        resp = requests.get(f"{_GT_BASE}{path}", headers=_GT_HEADERS, timeout=8)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        print(f"[GradeToday] GET {path} failed: {exc}")
        return None


def _gt_dept_page_id(school_dept_id: int, prefix: str) -> str | None:
    """
    From the school's department list, find the /courses/{id} page for
    a given course prefix (e.g. "CS", "STAT").
    """
    soup = _gt_get(f"/departments/{school_dept_id}")
    if not soup:
        return None
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.text.strip()
        if href.startswith("/courses/") and text.upper().startswith(prefix.upper() + " -"):
            return href.split("/")[-1]
    return None


def _gt_instructor_page_id(dept_page_id: str, course_number: str) -> str | None:
    """
    From the department's course list, find the /instructors/{id} page
    for a specific course number (e.g. "450").
    """
    soup = _gt_get(f"/courses/{dept_page_id}")
    if not soup:
        return None
    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = link.text.strip()
        # Link text is like "450 - Database Concepts"
        if href.startswith("/instructors/") and text.startswith(course_number):
            return href.split("/")[-1]
    return None


def _gt_grades_page_id(instructor_page_id: str, professor_name: str) -> str | None:
    """
    From the instructor list for a course, fuzzy-match the professor name
    and return the /grades/{course_id}/{instructor_id} path.
    """
    soup = _gt_get(f"/instructors/{instructor_page_id}")
    if not soup:
        return None

    candidates: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        # href = /grades/{course_id}/{instructor_id}
        if not href.startswith("/grades/"):
            continue
        name = link.text.strip().split("\n")[0].strip()
        if name:
            # Store the full path so we can return it directly
            candidates[name] = href

    if not candidates:
        return None

    match = rfprocess.extractOne(
        professor_name,
        list(candidates.keys()),
        scorer=fuzz.token_sort_ratio,
    )
    if match and match[1] >= 50:
        return candidates[match[0]]   # full path e.g. /grades/26487/23346
    return None


def _gt_parse_grade_page(grades_path: str) -> dict | None:
    """
    Parse the GradeToday grade distribution page.
    The data is embedded as:  let record = [{label:"A", value:"28.57"}, ...];
    Aggregates letter+/- variants into A/B/C/D/F buckets.
    """
    soup = _gt_get(grades_path)
    if not soup:
        return None

    # Find the raw HTML to regex-search the JS variable
    html = str(soup)
    m = re.search(r"let\s+record\s*=\s*(\[.*?\]);", html, re.DOTALL)
    if not m:
        return None

    try:
        records = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    buckets: dict[str, float] = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0, "F": 0.0}
    for r in records:
        label = (r.get("label") or "").strip().upper()
        value = _float(r.get("value"), 0.0)
        key = label[0] if label and label[0] in buckets else None
        if key:
            buckets[key] += value

    total = sum(buckets.values())
    if total < 1:
        return None

    # Normalize to percentages summing to ~100
    return {k: round(v * 100 / total) for k, v in buckets.items()}


def fetch_gradetoday_grades(
    professor_name: str,
    course_code: str,
    school_name: str,
) -> dict | None:
    """
    Try to fetch real grade distribution from GradeToday.
    Works for GMU and UVA. Returns A/B/C/D/F dict or None.
    """
    # Match school — try substring first, fall back to fuzzy match
    school_dept_id: int | None = None
    normalized = school_name.lower().replace(",", "").replace("-", " ")
    for key, did in _GT_SCHOOLS.items():
        if key.lower() in normalized or normalized in key.lower():
            school_dept_id = did
            break
    if school_dept_id is None:
        match = rfprocess.extractOne(
            school_name, list(_GT_SCHOOLS.keys()), scorer=fuzz.token_sort_ratio
        )
        if match and match[1] >= 70:
            school_dept_id = _GT_SCHOOLS[match[0]]
    if school_dept_id is None:
        print(f"[GradeToday] No school mapping for {school_name!r}")
        return None

    # Parse prefix + number from course_code  e.g. "CS 450" → ("CS", "450")
    m = re.match(r"([A-Za-z]+)\s*(\d+)", course_code.strip())
    if not m:
        print(f"[GradeToday] Cannot parse course code {course_code!r}")
        return None
    prefix, number = m.group(1).upper(), m.group(2)

    print(f"[GradeToday] Looking up {prefix} {number} for {professor_name!r} at school_dept={school_dept_id}")

    dept_page_id = _gt_dept_page_id(school_dept_id, prefix)
    if not dept_page_id:
        print(f"[GradeToday] No dept page for prefix {prefix!r}")
        return None

    instr_page_id = _gt_instructor_page_id(dept_page_id, number)
    if not instr_page_id:
        print(f"[GradeToday] No instructor page for course {number}")
        return None

    grades_path = _gt_grades_page_id(instr_page_id, professor_name)
    if not grades_path:
        print(f"[GradeToday] No grade page matched for {professor_name!r}")
        return None

    grades = _gt_parse_grade_page(grades_path)
    if grades:
        print(f"[GradeToday] Found real grade data: {grades}")
    return grades


# ── Gemini: syllabus parsing ───────────────────────────────────────────────────

_SYLLABUS_FALLBACK = {
    "num_assignments": 5,
    "num_exams": 2,
    "has_group_project": False,
    "weekly_reading_hours": 3.0,
    "late_policy_strict": False,
    "attendance_mandatory": False,
    "red_flags": [],
    "workload_score": 5.0,
}

_SYLLABUS_PROMPT = """\
Analyze this course syllabus and return ONLY a JSON object — no markdown fences, no explanation.

Course: {course_code}

Syllabus:
{syllabus_text}

Return exactly this JSON shape:
{{
  "num_assignments": <integer>,
  "num_exams": <integer>,
  "has_group_project": <boolean>,
  "weekly_reading_hours": <float, estimate from workload if not explicit>,
  "late_policy_strict": <boolean, true if no late work or heavy penalty>,
  "attendance_mandatory": <boolean>,
  "red_flags": [<up to 5 short strings of notable student concerns>],
  "workload_score": <float 1.0-10.0, overall difficulty estimate>
}}
"""


def parse_syllabus(syllabus_text: str, course_code: str) -> dict:
    """Use Gemini to extract structured data from the syllabus. Falls back gracefully."""
    if not syllabus_text.strip():
        return dict(_SYLLABUS_FALLBACK)

    prompt = _SYLLABUS_PROMPT.format(
        course_code=course_code,
        syllabus_text=syllabus_text[:3500],
    )
    try:
        resp = _gemini_call(
            client.models.generate_content,
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=450,
            ),
        )
        raw    = _strip_json_fences(resp.text.strip())
        result = json.loads(raw)

        return {
            "num_assignments":    _int(result.get("num_assignments"), 5),
            "num_exams":          _int(result.get("num_exams"), 2),
            "has_group_project":  _bool(result.get("has_group_project")),
            "weekly_reading_hours": round(_float(result.get("weekly_reading_hours"), 3.0), 1),
            "late_policy_strict": _bool(result.get("late_policy_strict")),
            "attendance_mandatory": _bool(result.get("attendance_mandatory")),
            "red_flags":          [str(f) for f in (result.get("red_flags") or [])[:5]],
            "workload_score":     round(max(1.0, min(10.0, _float(result.get("workload_score"), 5.0))), 1),
        }
    except Exception as exc:
        print(f"[Gemini/Syllabus] Error: {exc}")
        return dict(_SYLLABUS_FALLBACK)


# ── Gemini: Reddit summary ─────────────────────────────────────────────────────

def summarize_reddit(posts: list[dict], professor_name: str) -> str:
    """Summarize Reddit posts with Gemini. Returns a plain string, never raises."""
    if not posts:
        return f"No Reddit discussions found for {professor_name}."
    try:
        combined = "\n\n".join(
            f"[{p['score']} upvotes] {p['title']}\n{p['selftext']}"
            for p in posts[:5]
        )
        resp = _gemini_call(
            client.models.generate_content,
            model=MODEL,
            contents=(
                f"Summarize what students say about Professor {professor_name} "
                f"based on these Reddit posts. Write 2-3 sentences. "
                f"Focus on workload, difficulty, and overall experience.\n\n{combined}"
            ),
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=220,
            ),
        )
        return resp.text.strip()
    except Exception as exc:
        print(f"[Gemini/Reddit] Error: {exc}")
        return (
            f"Reddit discussions mention {professor_name} — "
            "search Reddit for detailed student experiences."
        )


# ── Gemini: RMP review red flags ──────────────────────────────────────────────

def extract_rmp_red_flags(raw_ratings: list[dict], professor_name: str) -> list[str]:
    """
    Use Gemini to extract the top recurring student complaints from RMP review
    comments. Returns up to 5 short flag strings, or [] on failure/no data.
    """
    comments = [
        r.get("comment", "")
        for r in raw_ratings[:30]
        if r.get("comment") and len(r.get("comment", "")) > 25
    ]
    if len(comments) < 3:
        return []

    combined = "\n\n".join(f"- {c}" for c in comments[:20])
    try:
        resp = _gemini_call(
            client.models.generate_content,
            model=MODEL,
            contents=(
                f"Based on these student reviews for Professor {professor_name}, "
                f"list up to 5 of the most frequently mentioned concerns or red flags. "
                f"Each item must be a short phrase of 5-10 words max. "
                f"Return ONLY a JSON array of strings — no explanation, no markdown.\n\n"
                f"{combined}"
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=200,
            ),
        )
        raw = _strip_json_fences(resp.text.strip())
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(f).strip() for f in result if str(f).strip()][:5]
        return []
    except Exception as exc:
        print(f"[Gemini/RMP-flags] Error: {exc}")
        return []


# ── Grade distribution ─────────────────────────────────────────────────────────

def estimate_grades_from_rmp(raw_ratings: list[dict]) -> dict:
    """
    Build an A/B/C/D/F distribution from RMP review grade fields.
    Returns sensible defaults when there's not enough data.
    """
    counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    total  = 0
    for r in raw_ratings:
        grade = (r.get("grade") or "").strip().upper()
        key   = grade[0] if grade and grade[0] in counts else None
        if key:
            counts[key] += 1
            total += 1

    if total < 5:
        return {"A": 40, "B": 30, "C": 20, "D": 7, "F": 3}

    return {k: round(v / total * 100) for k, v in counts.items()}


# ── Workload index computation ─────────────────────────────────────────────────

def compute_workload(
    syllabus_score: float,
    prof_difficulty: float,
    prof_rating: float,
    grade_dist: dict,
) -> dict:
    s     = max(0.0, min(10.0, float(syllabus_score)))
    p     = max(0.0, min(10.0, float(prof_difficulty) * 2.0))
    a_pct = float(grade_dist.get("A", 40))
    g     = max(0.0, min(10.0, 10.0 - (a_pct / 10.0)))
    r     = max(0.0, min(10.0, (5.0 - float(prof_rating)) * 2.0))

    index = round(s * 0.35 + p * 0.30 + g * 0.20 + r * 0.15, 1)

    return {
        "workload_index": index,
        "breakdown": {
            "syllabus":   round(s, 1),
            "professor":  round(p, 1),
            "grades":     round(g, 1),
            "reddit":     round(r, 1),
        },
    }


# ── POST /analyze ──────────────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        # Phase 1: RMP only — we need school name before routing Reddit
        rmp_data = await asyncio.to_thread(fetch_rmp_data, req.professor_name)
        raw_ratings = rmp_data.pop("raw_ratings", [])
        school_name = rmp_data.pop("school", "")

        # Phase 2: everything in parallel, Reddit now uses school-specific subreddit
        syllabus, reddit_posts, gt_grades, rmp_grades, rmp_flags = await asyncio.gather(
            asyncio.to_thread(parse_syllabus, req.syllabus_text, req.course_code),
            asyncio.to_thread(fetch_reddit_posts, req.professor_name, school_name),
            asyncio.to_thread(fetch_gradetoday_grades, req.professor_name, req.course_code, school_name),
            asyncio.to_thread(estimate_grades_from_rmp, raw_ratings),
            asyncio.to_thread(extract_rmp_red_flags, raw_ratings, req.professor_name),
        )

        # Phase 3: Reddit summary (needs posts from phase 2)
        reddit_summary = await asyncio.to_thread(summarize_reddit, reddit_posts, req.professor_name)

        grade_dist   = gt_grades if gt_grades else rmp_grades
        grade_source = "GradeToday" if gt_grades else "RateMyProfessors"
        print(f"[grades] source={grade_source}  dist={grade_dist}")

        # Merge syllabus flags + RMP flags (deduplicated, syllabus first)
        syllabus_flags = syllabus.get("red_flags", [])
        merged_flags   = syllabus_flags + [f for f in rmp_flags if f not in syllabus_flags]

        scores = compute_workload(
            syllabus_score  = syllabus.get("workload_score", 5.0),
            prof_difficulty = rmp_data.get("difficulty", 0.0),
            prof_rating     = rmp_data.get("rating", 0.0),
            grade_dist      = grade_dist,
        )

        return {
            "workload_index":    scores["workload_index"],
            "breakdown":         scores["breakdown"],
            "red_flags":         merged_flags[:8],
            "grade_source":      grade_source,
            "rmp_red_flags":     rmp_flags,
            "professor": {
                "name":            str(rmp_data["name"]),
                "department":      str(rmp_data["department"]),
                "rating":          float(rmp_data["rating"]),
                "difficulty":      float(rmp_data["difficulty"]),
                "would_take_again": int(rmp_data["would_take_again"]),
                "num_ratings":     int(rmp_data["num_ratings"]),
            },
            "grade_distribution": grade_dist,
            "syllabus_summary": {
                "num_assignments":    int(syllabus["num_assignments"]),
                "num_exams":          int(syllabus["num_exams"]),
                "has_group_project":  bool(syllabus["has_group_project"]),
                "weekly_reading_hours": float(syllabus["weekly_reading_hours"]),
                "late_policy_strict": bool(syllabus["late_policy_strict"]),
                "attendance_mandatory": bool(syllabus["attendance_mandatory"]),
            },
            "reddit_summary": str(reddit_summary),
            "reddit_posts": [
                {"title": p["title"], "score": p["score"], "url": p["url"], "subreddit": p["subreddit"]}
                for p in reddit_posts[:5]
            ],
        }

    except Exception as exc:
        print(f"[/analyze] Unhandled error: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")


# ── POST /compare ─────────────────────────────────────────────────────────────

class CompareProfessor(BaseModel):
    professor_name: str
    syllabus_text: str = ""


class CompareRequest(BaseModel):
    course_code: str
    prof_a: CompareProfessor
    prof_b: CompareProfessor


async def _analyze_one(professor_name: str, course_code: str, syllabus_text: str) -> dict:
    """Run the full analysis pipeline for one professor."""
    rmp_data = await asyncio.to_thread(fetch_rmp_data, professor_name)
    raw_ratings = rmp_data.pop("raw_ratings", [])
    school_name = rmp_data.pop("school", "")

    syllabus, reddit_posts, gt_grades, rmp_grades, rmp_flags = await asyncio.gather(
        asyncio.to_thread(parse_syllabus, syllabus_text, course_code),
        asyncio.to_thread(fetch_reddit_posts, professor_name, school_name),
        asyncio.to_thread(fetch_gradetoday_grades, professor_name, course_code, school_name),
        asyncio.to_thread(estimate_grades_from_rmp, raw_ratings),
        asyncio.to_thread(extract_rmp_red_flags, raw_ratings, professor_name),
    )

    reddit_summary = await asyncio.to_thread(summarize_reddit, reddit_posts, professor_name)

    grade_dist   = gt_grades if gt_grades else rmp_grades
    grade_source = "GradeToday" if gt_grades else "RateMyProfessors"
    syllabus_flags = syllabus.get("red_flags", [])
    merged_flags   = syllabus_flags + [f for f in rmp_flags if f not in syllabus_flags]

    scores = compute_workload(
        syllabus_score  = syllabus.get("workload_score", 5.0),
        prof_difficulty = rmp_data.get("difficulty", 0.0),
        prof_rating     = rmp_data.get("rating", 0.0),
        grade_dist      = grade_dist,
    )

    return {
        "workload_index":    scores["workload_index"],
        "breakdown":         scores["breakdown"],
        "red_flags":         merged_flags[:8],
        "rmp_red_flags":     rmp_flags,
        "grade_source":      grade_source,
        "professor": {
            "name":            str(rmp_data["name"]),
            "department":      str(rmp_data["department"]),
            "rating":          float(rmp_data["rating"]),
            "difficulty":      float(rmp_data["difficulty"]),
            "would_take_again": int(rmp_data["would_take_again"]),
            "num_ratings":     int(rmp_data["num_ratings"]),
        },
        "grade_distribution": grade_dist,
        "syllabus_summary": {
            "num_assignments":     int(syllabus["num_assignments"]),
            "num_exams":           int(syllabus["num_exams"]),
            "has_group_project":   bool(syllabus["has_group_project"]),
            "weekly_reading_hours": float(syllabus["weekly_reading_hours"]),
            "late_policy_strict":  bool(syllabus["late_policy_strict"]),
            "attendance_mandatory": bool(syllabus["attendance_mandatory"]),
        },
        "reddit_summary": str(reddit_summary),
        "reddit_posts": [
            {"title": p["title"], "score": p["score"], "url": p["url"], "subreddit": p["subreddit"]}
            for p in reddit_posts[:5]
        ],
        "has_syllabus":   bool(syllabus_text.strip()),
    }


@app.post("/compare")
async def compare(req: CompareRequest):
    """
    Run the full analysis pipeline for two professors in parallel and return
    both results side-by-side for the comparison view.
    """
    try:
        result_a, result_b = await asyncio.gather(
            _analyze_one(req.prof_a.professor_name, req.course_code, req.prof_a.syllabus_text),
            _analyze_one(req.prof_b.professor_name, req.course_code, req.prof_b.syllabus_text),
        )
        return {"course_code": req.course_code, "prof_a": result_a, "prof_b": result_b}
    except Exception as exc:
        print(f"[/compare] Unhandled error: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=f"Comparison failed: {exc}")


# ── POST /chat ─────────────────────────────────────────────────────────────────

_CONTEXT_PREFIX = "[CONTEXT FOR ADVISOR"


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        system_parts: list[str] = []
        chat_history: list[dict] = []

        for msg in req.history:
            if msg.text.startswith(_CONTEXT_PREFIX):
                system_parts.append(msg.text)
            else:
                role = "model" if msg.role == "ai" else "user"
                chat_history.append({"role": role, "content": msg.text})

        # Merge consecutive same-role messages — Gemini requires strict alternation
        merged: list[dict] = []
        for m in chat_history:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n\n" + m["content"]
            else:
                merged.append({"role": m["role"], "content": m["content"]})

        # Gemini requires conversation to start with "user"
        if merged and merged[0]["role"] == "model":
            merged.insert(0, {"role": "user", "content": "Hello."})

        merged.append({"role": "user", "content": req.user_text})

        contents = [
            types.Content(role=m["role"], parts=[types.Part(text=m["content"])])
            for m in merged
        ]

        config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=2048,
            system_instruction="\n\n".join(system_parts) if system_parts else None,
        )

        resp = await _gemini_call_async(
            client.aio.models.generate_content(
                model=MODEL,
                contents=contents,
                config=config,
            )
        )
        return {"response": resp.text.strip()}

    except Exception as exc:
        print(f"[/chat] Error: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}")
