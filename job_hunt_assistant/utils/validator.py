"""Validator: ensure tailored resume content does not invent skills or facts.

This module provides a lightweight post-generation check that:
1. Extracts skills and numeric claims from the *tailored* resume text.
2. Cross-references them against the *original* resume text.
3. Returns a list of potentially invented items so the UI can flag them.

The check is intentionally conservative: it flags rather than silently discards,
so the user can review and decide.
"""

from __future__ import annotations

import re


# Common skill tokens to scan for (expandable)
_SKILL_PATTERNS = [
    r"\b(python|java(?:script)?|typescript|c\+\+|c#|ruby|golang|rust|swift|kotlin)\b",
    r"\b(sql|nosql|mongodb|postgresql|mysql|redis|elasticsearch)\b",
    r"\b(aws|azure|gcp|google cloud|kubernetes|docker|terraform|ansible)\b",
    r"\b(react|angular|vue|node\.?js|django|flask|fastapi|spring boot)\b",
    r"\b(machine learning|deep learning|nlp|computer vision|data science)\b",
    r"\b(tableau|power\s?bi|looker|dbt|airflow|spark|kafka)\b",
    r"\b(agile|scrum|kanban|jira|confluence|devops|ci/cd)\b",
]

_NUMBER_PATTERN = re.compile(r"\b\d+[\+%xX]?\b")


def _extract_skills(text: str) -> set[str]:
    """Return a set of skill tokens found in ``text``."""
    found: set[str] = set()
    text_lower = text.lower()
    for pattern in _SKILL_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            found.add(match.group().strip())
    return found


def _extract_numbers(text: str) -> set[str]:
    """Return a set of numeric tokens (years, percentages, multipliers) from ``text``."""
    return set(_NUMBER_PATTERN.findall(text))


def validate_tailored_resume(original_text: str, tailored_text: str) -> dict:
    """Check the tailored resume for skills or numbers absent in the original.

    Args:
        original_text: The candidate's original, unmodified resume text.
        tailored_text: The agent-generated tailored resume summary or cover letter.

    Returns:
        A dict with:
        - ``invented_skills``: skills in tailored text but not in original.
        - ``invented_numbers``: numeric claims in tailored text but not in original.
        - ``is_clean``: True when both lists are empty.
    """
    orig_skills = _extract_skills(original_text)
    tail_skills = _extract_skills(tailored_text)
    invented_skills = sorted(tail_skills - orig_skills)

    orig_numbers = _extract_numbers(original_text)
    tail_numbers = _extract_numbers(tailored_text)
    # Filter out common innocuous numbers like "1", "2", etc. (< 4 digits)
    invented_numbers = sorted(
        n for n in (tail_numbers - orig_numbers) if len(n.rstrip("+%xX")) >= 2
    )

    return {
        "invented_skills": invented_skills,
        "invented_numbers": invented_numbers,
        "is_clean": not invented_skills and not invented_numbers,
    }
