import os
import requests
from rapidfuzz import fuzz, process

RMP_GRAPHQL_URL = "https://www.ratemyprofessors.com/graphql"

HEADERS = {
    "Authorization": "Basic dGVzdDp0ZXN0",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.ratemyprofessors.com/",
}

# ── GraphQL Queries ────────────────────────────────────────────────────────────

SEARCH_SCHOOLS_QUERY = """
query NewSearchSchoolsQuery($query: SchoolSearchQuery!) {
  newSearch {
    schools(query: $query) {
      edges {
        node {
          id
          legacyId
          name
          city
          state
        }
      }
    }
  }
}
"""

SEARCH_TEACHERS_QUERY = """
query NewSearchTeachersQuery($text: String!, $schoolID: ID) {
  newSearch {
    teachers(query: {text: $text, schoolID: $schoolID}, first: 8) {
      edges {
        node {
          id
          legacyId
          firstName
          lastName
          department
          avgRating
          avgDifficulty
          numRatings
          wouldTakeAgainPercent
          school {
            id
            name
          }
        }
      }
    }
  }
}
"""

GET_RATINGS_QUERY = """
query RatingsListQuery($id: ID!, $count: Int!, $cursor: String, $courseFilter: String) {
  node(id: $id) {
    ... on Teacher {
      ratings(first: $count, after: $cursor, courseFilter: $courseFilter) {
        pageInfo {
          hasNextPage
          endCursor
        }
        edges {
          node {
            comment
            date
            class
            helpfulRating
            difficultyRating
            attendanceMandatory
            wouldTakeAgain
            grade
            isForOnlineClass
            isForCredit
            ratingTags
            thumbsUpTotal
            thumbsDownTotal
          }
        }
      }
    }
    id
  }
}
"""

# ── HTTP ───────────────────────────────────────────────────────────────────────

def _graphql(query: str, variables: dict) -> dict:
    resp = requests.post(
        RMP_GRAPHQL_URL,
        headers=HEADERS,
        json={"query": query, "variables": variables},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise ValueError(f"GraphQL errors: {data['errors']}")
    return data

# ── Search helpers ─────────────────────────────────────────────────────────────

def search_school(school_name: str, min_score: int = 55) -> dict | None:
    """
    Search RMP for a school. Uses fuzzy matching so partial or misspelled
    names (e.g. "george mason" or "GMU") still resolve correctly.
    Returns the best-matching school node, or None if nothing found.
    """
    data = _graphql(SEARCH_SCHOOLS_QUERY, {"query": {"text": school_name}})
    edges = (
        data.get("data", {})
        .get("newSearch", {})
        .get("schools", {})
        .get("edges", [])
    )
    if not edges:
        return None

    schools = [e["node"] for e in edges]

    # Build display strings that include city/state so "Mason" doesn't
    # accidentally match a school in another state.
    candidates = {
        f"{s['name']}, {s.get('city', '')}, {s.get('state', '')}": s
        for s in schools
    }

    match = process.extractOne(
        school_name, list(candidates.keys()), scorer=fuzz.token_sort_ratio
    )
    if match and match[1] >= min_score:
        return candidates[match[0]]

    # Fallback: return the first result RMP gave us
    return schools[0]


def search_professor(
    professor_name: str, school_id: str | None = None, min_score: int = 45
) -> dict | None:
    """
    Search RMP for a professor. Fuzzy-matches the returned candidates so
    typos like "Masri" vs "Massri" still resolve to the right person.
    Pass school_id (RMP's base64 node ID) to scope the search to one school.
    Returns the best-matching professor node, or None.
    """
    variables: dict = {"text": professor_name}
    if school_id:
        variables["schoolID"] = school_id

    data = _graphql(SEARCH_TEACHERS_QUERY, variables)
    edges = (
        data.get("data", {})
        .get("newSearch", {})
        .get("teachers", {})
        .get("edges", [])
    )
    if not edges:
        return None

    professors = [e["node"] for e in edges]
    candidates = {
        f"{p['firstName']} {p['lastName']}": p for p in professors
    }

    match = process.extractOne(
        professor_name, list(candidates.keys()), scorer=fuzz.token_sort_ratio
    )
    if match and match[1] >= min_score:
        return candidates[match[0]]

    return professors[0]


def get_ratings(
    professor_id: str,
    max_ratings: int = 50,
    course_filter: str | None = None,
) -> list[dict]:
    """
    Fetch up to max_ratings reviews for a professor using cursor-based
    pagination. Stops early if there are no more pages.
    """
    ratings: list[dict] = []
    cursor: str | None = None
    page_size = 20  # RMP's practical max per page

    while len(ratings) < max_ratings:
        remaining = max_ratings - len(ratings)
        variables: dict = {
            "id": professor_id,
            "count": min(page_size, remaining),
            "cursor": cursor,
        }
        if course_filter:
            variables["courseFilter"] = course_filter

        data = _graphql(GET_RATINGS_QUERY, variables)
        ratings_data = (
            data.get("data", {})
            .get("node", {})
            .get("ratings", {})
        )

        for edge in ratings_data.get("edges", []):
            ratings.append(edge["node"])
            if len(ratings) >= max_ratings:
                break

        page_info = ratings_data.get("pageInfo", {})
        if not page_info.get("hasNextPage") or not ratings_data.get("edges"):
            break
        cursor = page_info.get("endCursor")

    return ratings

# ── Markdown formatting ────────────────────────────────────────────────────────

def _fmt_wta_percent(value) -> str:
    """Format wouldTakeAgainPercent: -1 or None means no data."""
    if value is None or value == -1:
        return "N/A"
    return f"{round(float(value))}%"


def _fmt_wta_review(value) -> str:
    """Format per-review wouldTakeAgain: 1=Yes, 0=No, else N/A."""
    if value == 1:
        return "Yes"
    if value == 0:
        return "No"
    return "N/A"


def _fmt_tags(tags) -> str:
    if not tags:
        return "None"
    if isinstance(tags, list):
        return ", ".join(t for t in tags if t)
    return str(tags)


def format_markdown(professor: dict, ratings: list[dict]) -> str:
    prof_name = f"{professor['firstName']} {professor['lastName']}"
    school = professor.get("school", {})

    lines = [
        f"# RateMyProfessors: {prof_name}",
        f"",
        f"**School:** {school.get('name', 'N/A')}",
        f"**Department:** {professor.get('department', 'N/A')}",
        f"**Overall Rating:** {professor.get('avgRating', 'N/A')}/5.0",
        f"**Difficulty:** {professor.get('avgDifficulty', 'N/A')}/5.0",
        f"**Would Take Again:** {_fmt_wta_percent(professor.get('wouldTakeAgainPercent'))}",
        f"**Total Ratings on RMP:** {professor.get('numRatings', 'N/A')}",
        f"",
        f"---",
        f"",
        f"## Student Reviews (up to 50 most recent)",
        f"",
    ]

    if not ratings:
        lines.append("*No reviews found.*")
    else:
        for i, r in enumerate(ratings, 1):
            online = " *(Online)*" if r.get("isForOnlineClass") else ""
            credit = " *(For Credit)*" if r.get("isForCredit") else ""
            lines += [
                f"### Review {i}",
                f"- **Course:** {r.get('class', 'N/A')}{online}{credit}",
                f"- **Date:** {r.get('date', 'N/A')}",
                f"- **Quality Rating:** {r.get('helpfulRating', 'N/A')}/5",
                f"- **Difficulty:** {r.get('difficultyRating', 'N/A')}/5",
                f"- **Grade Received:** {r.get('grade', 'N/A')}",
                f"- **Would Take Again:** {_fmt_wta_review(r.get('wouldTakeAgain'))}",
                f"- **Attendance Mandatory:** {r.get('attendanceMandatory', 'N/A')}",
                f"- **Tags:** {_fmt_tags(r.get('ratingTags'))}",
                f"- **Helpful:** 👍 {r.get('thumbsUpTotal', 0)} / 👎 {r.get('thumbsDownTotal', 0)}",
                f"",
                f"> {r.get('comment') or 'No comment provided.'}",
                f"",
            ]

    return "\n".join(lines)

# ── Main entry point ───────────────────────────────────────────────────────────

def scrape_rmp(
    professor_name: str,
    school_name: str | None = None,
    max_reviews: int = 50,
    course_filter: str | None = None,
    output_dir: str = ".",
) -> str | None:
    """
    Scrape RateMyProfessors for a professor and save results to a markdown file.

    Args:
        professor_name: Professor's name (typos OK — fuzzy matched).
        school_name:    School name (typos OK — fuzzy matched). Optional;
                        if omitted the search is global.
        max_reviews:    Cap on number of reviews to fetch (default 50).
        course_filter:  Optional course code to filter reviews (e.g. "CS101").
        output_dir:     Directory to write the .md file into.

    Returns:
        Path to the generated markdown file, or None if professor not found.
    """
    school_id: str | None = None

    if school_name:
        print(f"[RMP] Searching for school: {school_name!r}")
        school = search_school(school_name)
        if school:
            school_id = school["id"]
            print(f"[RMP] Found school: {school['name']} ({school.get('city')}, {school.get('state')})")
        else:
            print("[RMP] School not found — searching globally")

    print(f"[RMP] Searching for professor: {professor_name!r}")
    professor = search_professor(professor_name, school_id)

    if not professor:
        print(f"[RMP] No professor found for: {professor_name!r}")
        return None

    prof_full_name = f"{professor['firstName']} {professor['lastName']}"
    print(f"[RMP] Found: {prof_full_name} at {professor.get('school', {}).get('name', 'Unknown')}")

    print(f"[RMP] Fetching up to {max_reviews} reviews...")
    ratings = get_ratings(professor["id"], max_reviews, course_filter)
    print(f"[RMP] Got {len(ratings)} reviews")

    markdown = format_markdown(professor, ratings)

    safe_name = prof_full_name.replace(" ", "_").lower()
    filename = os.path.join(output_dir, f"rmp_{safe_name}.md")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(markdown)

    print(f"[RMP] Saved to: {filename}")
    return filename


if __name__ == "__main__":
    scrape_rmp("Wassim Masri", school_name="George Mason University")
