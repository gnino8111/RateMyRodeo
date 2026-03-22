"""
RateMyRodeo — FastAPI backend
Endpoints: POST /analyze  POST /chat

Required environment variables (put in backend/.env):
  GEMINI_API_KEY  — picked up automatically by the google-genai client
"""

import os
import sys
import json
import asyncio

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from google.genai import types

# ── Setup ──────────────────────────────────────────────────────────────────────

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.dirname(__file__))

# google-genai client — reads GEMINI_API_KEY from environment automatically
client = genai.Client()

MODEL = "gemini-3-flash-preview"

from rmp_scraper import search_professor, get_ratings  # noqa: E402

app = FastAPI(title="RateMyRodeo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pydantic request models ────────────────────────────────────────────────────
# Field names MUST match exactly what App.jsx sends — this prevents all 422s.

class AnalyzeRequest(BaseModel):
    professor_name: str
    course_code: str = "Unknown Course"
    syllabus_text: str = ""


class ChatMessage(BaseModel):
    role: str   # frontend sends "ai" or "user"
    text: str


class ChatRequest(BaseModel):
    history: list[ChatMessage] = []
    user_text: str


# ── Type-safe helpers ──────────────────────────────────────────────────────────

def _float(value, default: float = 0.0) -> float:
    """Cast to float, treat -1 (RMP sentinel) as default."""
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
    """Remove ```json ... ``` fences that LLMs sometimes add."""
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            cleaned = part.strip().lstrip("json").strip()
            if cleaned.startswith("{"):
                return cleaned
    return text


# ── RMP data fetch ─────────────────────────────────────────────────────────────

def fetch_rmp_data(professor_name: str) -> dict:
    """
    Look up the professor on RateMyProfessors (global search, any school).
    Always returns a dict with the expected keys — never raises.
    """
    fallback = {
        "found": False,
        "name": professor_name,
        "department": "Unknown",
        "rating": 0.0,
        "difficulty": 0.0,
        "would_take_again": -1,
        "num_ratings": 0,
        "raw_ratings": [],
    }
    try:
        # Search globally — no school filter so any university's professors are found
        professor = search_professor(professor_name, school_id=None)
        if not professor:
            print(f"[RMP] No match found for {professor_name!r}")
            return fallback

        raw_ratings = get_ratings(professor["id"], max_ratings=20)

        return {
            "found": True,
            "name": f"{professor['firstName']} {professor['lastName']}",
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


# ── Reddit search ──────────────────────────────────────────────────────────────

def fetch_reddit_posts(professor_name: str, limit: int = 8) -> list[dict]:
    """
    Search all of Reddit for posts mentioning the professor.
    Returns [] on any failure so the rest of the pipeline continues.
    """
    try:
        url = (
            f"https://www.reddit.com/search.json"
            f"?q={requests.utils.quote(professor_name + ' professor')}"
            f"&type=link&sort=relevance&limit={limit}"
        )
        headers = {"User-Agent": "RateMyRodeo/1.0 (academic research project)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
        return [
            {
                "title": c["data"].get("title", ""),
                "selftext": (c["data"].get("selftext") or "")[:600],
                "score": c["data"].get("score", 0),
            }
            for c in children
        ]
    except Exception as exc:
        print(f"[Reddit] Error: {exc}")
        return []


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
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=450,
            ),
        )
        raw = _strip_json_fences(resp.text.strip())
        result = json.loads(raw)

        # Clamp and type-coerce every field so the response is always valid
        return {
            "num_assignments": _int(result.get("num_assignments"), 5),
            "num_exams": _int(result.get("num_exams"), 2),
            "has_group_project": _bool(result.get("has_group_project")),
            "weekly_reading_hours": round(_float(result.get("weekly_reading_hours"), 3.0), 1),
            "late_policy_strict": _bool(result.get("late_policy_strict")),
            "attendance_mandatory": _bool(result.get("attendance_mandatory")),
            "red_flags": [str(f) for f in (result.get("red_flags") or [])[:5]],
            "workload_score": round(max(1.0, min(10.0, _float(result.get("workload_score"), 5.0))), 1),
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
        resp = client.models.generate_content(
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


# ── Grade distribution ─────────────────────────────────────────────────────────

def estimate_grades(raw_ratings: list[dict]) -> dict:
    """
    Build an A/B/C/D/F distribution from RMP review data.
    Returns sensible defaults when there's not enough data.
    """
    counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    total = 0
    for r in raw_ratings:
        grade = (r.get("grade") or "").strip().upper()
        key = grade[0] if grade and grade[0] in counts else None
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
    """
    Weighted workload index (0-10) and per-dimension breakdown.
      Syllabus  35% — from Gemini syllabus parse
      Professor 30% — from RMP difficulty (0-5 -> 0-10)
      Grades    20% — inverse of A% (lower A% = harder)
      Reddit    15% — inverse of RMP rating (proxy for sentiment)
    """
    s = max(0.0, min(10.0, float(syllabus_score)))
    p = max(0.0, min(10.0, float(prof_difficulty) * 2.0))
    a_pct = float(grade_dist.get("A", 40))
    g = max(0.0, min(10.0, 10.0 - (a_pct / 10.0)))
    r = max(0.0, min(10.0, (5.0 - float(prof_rating)) * 2.0))

    index = round(s * 0.35 + p * 0.30 + g * 0.20 + r * 0.15, 1)

    return {
        "workload_index": index,
        "breakdown": {
            "syllabus": round(s, 1),
            "professor": round(p, 1),
            "grades": round(g, 1),
            "reddit": round(r, 1),
        },
    }


# ── POST /analyze ──────────────────────────────────────────────────────────────

@app.post("/analyze")
async def analyze(req: AnalyzeRequest):
    """
    Full pipeline: RMP + Reddit (parallel) -> Gemini syllabus + Reddit summary (parallel)
    -> workload score -> structured JSON matching App.jsx's MOCK_RESULT shape.
    """
    try:
        # Phase 1: network fetches in parallel
        rmp_data, reddit_posts = await asyncio.gather(
            asyncio.to_thread(fetch_rmp_data, req.professor_name),
            asyncio.to_thread(fetch_reddit_posts, req.professor_name),
        )
        raw_ratings = rmp_data.pop("raw_ratings", [])

        # Phase 2: AI calls + grade estimation in parallel
        syllabus, reddit_summary, grade_dist = await asyncio.gather(
            asyncio.to_thread(parse_syllabus, req.syllabus_text, req.course_code),
            asyncio.to_thread(summarize_reddit, reddit_posts, req.professor_name),
            asyncio.to_thread(estimate_grades, raw_ratings),
        )

        scores = compute_workload(
            syllabus_score=syllabus.get("workload_score", 5.0),
            prof_difficulty=rmp_data.get("difficulty", 0.0),
            prof_rating=rmp_data.get("rating", 0.0),
            grade_dist=grade_dist,
        )

        return {
            "workload_index": scores["workload_index"],
            "breakdown": scores["breakdown"],
            "red_flags": syllabus.get("red_flags", []),
            "professor": {
                "name": str(rmp_data["name"]),
                "department": str(rmp_data["department"]),
                "rating": float(rmp_data["rating"]),
                "difficulty": float(rmp_data["difficulty"]),
                "would_take_again": int(rmp_data["would_take_again"]),
                "num_ratings": int(rmp_data["num_ratings"]),
            },
            "grade_distribution": grade_dist,
            "syllabus_summary": {
                "num_assignments": int(syllabus["num_assignments"]),
                "num_exams": int(syllabus["num_exams"]),
                "has_group_project": bool(syllabus["has_group_project"]),
                "weekly_reading_hours": float(syllabus["weekly_reading_hours"]),
                "late_policy_strict": bool(syllabus["late_policy_strict"]),
                "attendance_mandatory": bool(syllabus["attendance_mandatory"]),
            },
            "reddit_summary": str(reddit_summary),
        }

    except Exception as exc:
        print(f"[/analyze] Unhandled error: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}")


# ── POST /chat ─────────────────────────────────────────────────────────────────

# The frontend prefixes context messages with this string so we can detect them.
_CONTEXT_PREFIX = "[CONTEXT FOR ADVISOR"


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Gemini chat endpoint using google-genai.
    Handles:
      - Frontend "ai"/"user" roles -> google-genai "model"/"user"
      - Context messages extracted to system_instruction
      - Consecutive same-role messages merged (Gemini requires alternating turns)
      - Ensures first conversation turn is always "user"
    """
    try:
        system_parts: list[str] = []
        chat_history: list[dict] = []

        for msg in req.history:
            if msg.text.startswith(_CONTEXT_PREFIX):
                system_parts.append(msg.text)
            else:
                # google-genai uses "model" for AI, "user" for human
                role = "model" if msg.role == "ai" else "user"
                chat_history.append({"role": role, "content": msg.text})

        # Merge consecutive same-role messages — Gemini requires strict alternation
        merged: list[dict] = []
        for m in chat_history:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n\n" + m["content"]
            else:
                merged.append({"role": m["role"], "content": m["content"]})

        # Gemini requires the first turn to be "user"
        if merged and merged[0]["role"] == "model":
            merged.insert(0, {"role": "user", "content": "Hello."})

        # Append the new user message
        merged.append({"role": "user", "content": req.user_text})

        # Build Contents list for google-genai
        contents = [
            types.Content(
                role=m["role"],
                parts=[types.Part(text=m["content"])],
            )
            for m in merged
        ]

        # Build config — attach system instruction if context was provided
        config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=600,
        )
        if system_parts:
            config.system_instruction = "\n\n".join(system_parts)

        resp = await client.aio.models.generate_content(
            model=MODEL,
            contents=contents,
            config=config,
        )
        return {"response": resp.text.strip()}

    except Exception as exc:
        print(f"[/chat] Error: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}")
