"""JSearch API client — aggregates LinkedIn, Indeed, Glassdoor, and more.

API documentation: https://openwebninja.s3.us-east-1.amazonaws.com/portal/openapi/jsearch.yaml
Free-tier key:     https://app.openwebninja.com/api/jsearch
"""

import time
import requests
from utils.config import JSEARCH_API_KEY

BASE = "https://api.openwebninja.com/jsearch/search"

# Maximum back-off attempts when the free tier quota is hit
_MAX_RETRIES = 3
_BASE_WAIT = 15  # seconds


def normalize(raw: dict) -> dict:
    """Convert a raw JSearch result into the app's canonical job schema.

    Args:
        raw: A single element from the JSearch ``data`` array.

    Returns:
        A flat dict with consistent field names used throughout the app.
    """
    return {
        "id": raw.get("job_id"),
        "title": raw.get("job_title", ""),
        "company": raw.get("employer_name", ""),
        "location": ", ".join(
            filter(None, [raw.get("job_city"), raw.get("job_state"), raw.get("job_country")])
        ),
        "remote": bool(raw.get("job_is_remote")),
        "description": raw.get("job_description", ""),
        "apply_url": raw.get("job_apply_link"),
        "source": raw.get("job_publisher", ""),
        "posted_at": raw.get("job_posted_at_datetime_utc"),
        "employment_type": raw.get("job_employment_type", ""),
        "required_experience": raw.get("job_required_experience", {}) or {},
        "required_skills": raw.get("job_required_skills") or [],
        "highlights": raw.get("job_highlights", {}) or {},
    }


def fetch_jobs(query: str, country: str = "in", date_posted: str = "week", pages: int = 1) -> list[dict]:
    """Search JSearch and return normalized job listings.

    Args:
        query: Free-text search query (e.g. "data analyst India").
        country: ISO-2 country code for location filtering (default "in").
        date_posted: Freshness filter — "today", "3days", "week", or "month".
        pages: Number of result pages to fetch (10 jobs per page on free tier).

    Returns:
        A list of normalized job dicts that have both an apply URL and description.

    Raises:
        ValueError: If ``JSEARCH_API_KEY`` is not configured.
        requests.HTTPError: For non-transient HTTP errors.
    """
    if not JSEARCH_API_KEY:
        raise ValueError(
            "JSEARCH_API_KEY is not set. "
            "Get a free key at https://app.openwebninja.com/api/jsearch "
            "and add it to your .env file or Streamlit secrets."
        )

    headers = {"x-api-key": JSEARCH_API_KEY}
    params = {
        "query": query,
        "country": country,
        "date_posted": date_posted,
        "num_pages": pages,
    }

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.get(BASE, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json().get("data", [])
            jobs = [normalize(j) for j in data]
            # Only keep listings that have enough info to apply and match against
            return [j for j in jobs if j["apply_url"] and j["description"]]

        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 429 and attempt < _MAX_RETRIES:
                wait = _BASE_WAIT * (2 ** (attempt - 1))
                print(f"⏳ JSearch rate limit (429). Waiting {wait}s before retry {attempt}/{_MAX_RETRIES}…")
                time.sleep(wait)
                continue
            raise

    return []  # unreachable but satisfies linters
