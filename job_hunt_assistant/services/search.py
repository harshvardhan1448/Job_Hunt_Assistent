"""Job search service: build queries, call JSearch, deduplicate and cache results.

This module is the single entry-point for the Streamlit UI to discover jobs.
It wraps ``providers.jsearch_api.fetch_jobs`` with:
- Multi-query expansion derived from the candidate's target titles.
- Deduplication by ``id`` (JSearch job_id), falling back to (title, company, location).
- A 1-hour ``st.cache_data`` cache to protect the free-tier quota.
- Automatic retry-with-backoff on HTTP 429 responses.
"""

from __future__ import annotations

import time
import requests

import streamlit as st

from providers.jsearch_api import fetch_jobs
from utils.resume_parser import Profile, clean_title

MAX_QUERIES = 2


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _dedup_jobs(jobs: list[dict]) -> list[dict]:
    """Remove duplicate jobs, preferring dedup by ``id`` then by composite key.

    Args:
        jobs: Flat list of normalized job dicts from one or more queries.

    Returns:
        Deduplicated list preserving first-seen order.
    """
    seen_ids: set[str] = set()
    seen_composites: set[tuple] = set()
    unique: list[dict] = []

    for job in jobs:
        job_id = job.get("id")
        composite = (
            (job.get("title") or "").lower().strip(),
            (job.get("company") or "").lower().strip(),
            (job.get("location") or "").lower().strip(),
        )

        if job_id and job_id in seen_ids:
            continue
        if composite in seen_composites:
            continue

        if job_id:
            seen_ids.add(job_id)
        seen_composites.add(composite)
        unique.append(job)

    return unique


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def _build_queries(profile: Profile, location: str) -> list[str]:
    """Generate 3-5 search queries from the candidate profile and target location.

    Args:
        profile: Extracted ``Profile`` with target titles and skills.
        location: Free-text location supplied by the user in the UI.

    Returns:
        List of query strings to submit to JSearch.
    """
    queries: list[str] = []
    city = (location or "").split(",")[0].strip()
    titles = list(dict.fromkeys(
        title for title in (clean_title(item) for item in profile.target_titles) if title
    ))[:MAX_QUERIES] or ["software engineer"]
    if not city or city.lower() == "remote":
        return titles

    queries: list[str] = []
    for title in titles:
        queries.append(f"{title} in {city}")
    return queries


# ---------------------------------------------------------------------------
# Cached search
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def search_with_fallback(query: str, country: str, date_posted: str) -> tuple[list[dict], str | None]:
    """Search with the requested freshness, then widen to a month if empty."""
    for freshness in dict.fromkeys([date_posted, "month"]):
        jobs = _fetch_with_retry(query, country, freshness)
        if jobs:
            return jobs, freshness
    return [], None


def cached_search(queries_tuple: tuple[str, ...], country: str, date_posted: str) -> list[dict]:
    """Execute a deduplicated multi-query job search with a 1-hour cache.

    The arguments must be hashable so Streamlit can use them as the cache key;
    hence ``queries_tuple`` is a tuple, not a list.

    Args:
        queries_tuple: Immutable sequence of query strings.
        country: ISO-2 country code passed to JSearch.
        date_posted: Freshness filter for JSearch.

    Returns:
        Deduplicated list of normalized job dicts.
    """
    all_jobs: list[dict] = []
    for query in queries_tuple:
        results, _ = search_with_fallback(query, country, date_posted)
        all_jobs.extend(results)
    return _dedup_jobs(all_jobs)


def _fetch_with_retry(query: str, country: str, date_posted: str, max_retries: int = 3) -> list[dict]:
    """Call ``fetch_jobs`` with exponential back-off on HTTP 429.

    Args:
        query: Search query string.
        country: ISO-2 country code.
        date_posted: Freshness filter.
        max_retries: Maximum retry attempts before re-raising.

    Returns:
        List of normalized job dicts.

    Raises:
        Exception: After ``max_retries`` unsuccessful attempts.
    """
    base_wait = 15
    for attempt in range(1, max_retries + 1):
        try:
            return fetch_jobs(query, country=country, date_posted=date_posted, pages=1)
        except Exception as exc:
            error_text = str(exc).lower()
            is_rate_limit = "429" in error_text or "rate" in error_text or "quota" in error_text
            if is_rate_limit and attempt < max_retries:
                wait = base_wait * (2 ** (attempt - 1))
                print(f"⏳ Rate limit hit. Waiting {wait}s (attempt {attempt}/{max_retries})…")
                time.sleep(wait)
                continue
            raise
    return []  # unreachable


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def search_jobs(
    profile: Profile,
    location: str,
    country: str = "in",
    date_posted: str = "week",
) -> list[dict]:
    """High-level search called from Streamlit UI.

    Builds queries from the profile, caches results for 1 hour, and deduplicates.

    Args:
        profile: Candidate profile extracted from the resume.
        location: Free-text location string from the UI.
        country: ISO-2 country code (default "in" for India).
        date_posted: Freshness filter — "today", "3days", "week", or "month".

    Returns:
        Sorted list of job dicts (unsorted here; matcher will re-rank them).
    """
    queries = _build_queries(profile, location)
    return cached_search(tuple(queries), country, date_posted)


def search_jobs_with_details(
    profile: Profile,
    location: str,
    country: str = "in",
    date_posted: str = "week",
) -> tuple[list[dict], list[str], dict[str, str]]:
    """Search while retaining query counts and provider errors for the UI."""
    queries = _build_queries(profile, location)
    all_jobs: list[dict] = []
    errors: list[str] = []
    counts: dict[str, str] = {}
    for query in queries:
        try:
            jobs, used_date = search_with_fallback(query, country, date_posted)
            counts[query] = f"{len(jobs)} jobs (date_posted={used_date})"
            all_jobs.extend(jobs)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = (exc.response.text if exc.response is not None else str(exc))[:150]
            errors.append(f"'{query}' -> HTTP {status}: {body}")
        except Exception as exc:
            errors.append(f"'{query}' -> {type(exc).__name__}: {str(exc)[:200]}")

    jobs = _dedup_jobs(all_jobs)
    if not jobs:
        fallback = f"software engineer in {(location or '').split(',')[0].strip()}".strip()
        if fallback not in queries:
            try:
                fallback_jobs, used_date = search_with_fallback(fallback, country, date_posted)
                counts[fallback] = f"{len(fallback_jobs)} jobs (date_posted={used_date})"
                jobs = _dedup_jobs(fallback_jobs)
            except Exception as exc:
                errors.append(f"'{fallback}' -> {type(exc).__name__}: {str(exc)[:200]}")
    return jobs, errors, counts
