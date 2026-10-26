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
from typing import Optional

import streamlit as st

from providers.jsearch_api import fetch_jobs
from utils.resume_parser import Profile


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
    loc = location.strip()

    titles = profile.target_titles[:5] if profile.target_titles else ["software engineer"]
    for title in titles:
        base_query = f"{title} {loc}".strip()
        queries.append(base_query)

    # Add a skills-enriched query using the top skills
    if profile.skills:
        top_skills = " ".join(profile.skills[:3])
        skill_query = f"{titles[0]} {top_skills} {loc}".strip()
        if skill_query not in queries:
            queries.append(skill_query)

    return queries[:5]  # cap at 5 to stay within quota


# ---------------------------------------------------------------------------
# Cached search
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
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
        try:
            results = _fetch_with_retry(query, country, date_posted)
            all_jobs.extend(results)
        except Exception as exc:
            # Log but continue — one failed query shouldn't abort the search
            print(f"⚠️  Query '{query}' failed: {exc}")

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
