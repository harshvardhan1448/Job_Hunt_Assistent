"""Job matching and ranking service.

Scores each job against the candidate's resume embedding and skill list,
then applies hard filters for location/remote and posting date.

Scoring formula (tunable weights):
    score = WEIGHT_SIM * cosine_sim(resume, jd) + WEIGHT_SKILL * skill_overlap

The model ``all-MiniLM-L6-v2`` is downloaded automatically by
``sentence-transformers`` on first use (~80 MB, cached to disk).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from utils.resume_parser import Profile

# Tunable scoring weights
WEIGHT_SIM = 0.6
WEIGHT_SKILL = 0.4

# Hard-filter: ignore jobs older than this many days (0 = disabled)
MAX_AGE_DAYS = 30

_embedder = None  # lazy-loaded


def _get_embedder():
    """Lazily load the sentence-transformer model (cached after first call)."""
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for matching. "
                "Run: pip install sentence-transformers"
            )
    return _embedder


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------

def _passes_location_filter(job: dict, profile: Profile, location_query: str) -> bool:
    """Return True if the job location is compatible with the candidate's preference.

    A job passes if it is remote OR its location string overlaps with either the
    UI location query or the profile's preferred_locations.

    Args:
        job: Normalized job dict.
        profile: Candidate profile.
        location_query: Free-text location string from the UI.

    Returns:
        True if the job should be included.
    """
    if job.get("remote"):
        return True

    wanted = [
        location.strip().lower()
        for location in ([location_query] + list(profile.preferred_locations))
        if location and location.strip()
    ]
    if not wanted:
        return True
    job_location = (job.get("location") or "").lower()
    return any(location in job_location for location in wanted)


def _passes_date_filter(job: dict, max_age_days: int = MAX_AGE_DAYS) -> bool:
    """Return True if the job was posted within ``max_age_days`` days.

    Args:
        job: Normalized job dict.
        max_age_days: Maximum acceptable age in days; 0 disables the filter.

    Returns:
        True if the job is recent enough.
    """
    if max_age_days <= 0:
        return True

    posted_at = job.get("posted_at")
    if not posted_at:
        return True  # missing date → don't filter out

    try:
        posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_days = (now - posted_dt).days
        return age_days <= max_age_days
    except (ValueError, TypeError):
        return True


# ---------------------------------------------------------------------------
# Skill matching
# ---------------------------------------------------------------------------

def _has_skill(text: str, skill: str) -> bool:
    pattern = r"(?<![A-Za-z0-9+#])" + re.escape(skill.strip()) + r"(?![A-Za-z0-9+#])"
    return re.search(pattern, text or "", re.IGNORECASE) is not None

def _extract_skill_overlap(job: dict, profile: Profile) -> tuple[float, list[str], list[str]]:
    """Compute the fraction of detected job skills that the candidate has.

    Args:
        job: Normalized job dict.
        profile: Candidate profile with skill list.

    Returns:
        Tuple of (overlap_fraction, matched_skills, missing_skills).
    """
    # Prefer explicit skills list from API; fall back to scanning description
    api_skills: list[str] = job.get("required_skills") or []
    description = job.get("description") or ""

    if not api_skills:
        # Heuristic: scan description for candidate skills
        api_skills = [s for s in profile.skills if _has_skill(description, s)]

    if not api_skills:
        return 0.0, [], []

    api_skills_lower = [s.lower() for s in api_skills]
    profile_skills_lower = [s.lower() for s in profile.skills]

    matched = [s for s in api_skills if s.lower() in profile_skills_lower]
    missing = [s for s in api_skills if s.lower() not in profile_skills_lower]

    overlap = len(matched) / len(api_skills_lower) if api_skills_lower else 0.0
    return overlap, matched, missing


# ---------------------------------------------------------------------------
# Embedding similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(vec_a, vec_b) -> float:
    """Compute cosine similarity between two numpy arrays.

    Args:
        vec_a: First embedding vector.
        vec_b: Second embedding vector.

    Returns:
        Cosine similarity in [−1, 1].
    """
    import numpy as np
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


# ---------------------------------------------------------------------------
# Public ranking API
# ---------------------------------------------------------------------------

def rank_jobs(
    jobs: list[dict],
    profile: Profile,
    resume_text: str,
    location_query: str = "",
    weight_sim: float = WEIGHT_SIM,
    weight_skill: float = WEIGHT_SKILL,
    max_age_days: int = MAX_AGE_DAYS,
) -> list[dict]:
    """Filter, score, and rank a list of jobs against the candidate profile.

    Args:
        jobs: Normalized job dicts from the search service.
        profile: Candidate profile extracted from the resume.
        resume_text: Full resume text for embedding-based similarity.
        location_query: UI location string used for hard filtering.
        weight_sim: Weight for cosine similarity in score formula.
        weight_skill: Weight for skill overlap in score formula.
        max_age_days: Maximum job age in days (0 disables filter).

    Returns:
        List of job dicts enriched with ``score``, ``matched_skills``, and
        ``missing_skills``, sorted by ``score`` descending.
    """
    if not jobs:
        return []

    # --- Hard filters ---
    filtered = [
        j for j in jobs
        if _passes_location_filter(j, profile, location_query)
        and _passes_date_filter(j, max_age_days)
    ]

    if not filtered:
        # Relax location filter if nothing passes
        filtered = [j for j in jobs if _passes_date_filter(j, max_age_days)]

    if not filtered:
        filtered = jobs  # last resort: return everything

    # --- Embeddings ---
    try:
        embedder = _get_embedder()
        resume_emb = embedder.encode(resume_text[:4000], normalize_embeddings=True)
        jd_texts = [j.get("description", "")[:2000] for j in filtered]
        jd_embs = embedder.encode(jd_texts, normalize_embeddings=True, show_progress_bar=False)
        use_embeddings = True
    except Exception as exc:
        print(f"⚠️  Embedding model unavailable ({exc}). Falling back to skill-only scoring.")
        use_embeddings = False

    # --- Score each job ---
    ranked = []
    for idx, job in enumerate(filtered):
        skill_overlap, matched, missing = _extract_skill_overlap(job, profile)

        if use_embeddings:
            sim = _cosine_similarity(resume_emb, jd_embs[idx])
            # Normalize cosine from [-1,1] to [0,1]
            sim_norm = (sim + 1) / 2
        else:
            sim_norm = 0.5  # neutral when embeddings are unavailable

        score = weight_sim * sim_norm + weight_skill * skill_overlap

        ranked.append({
            **job,
            "score": round(score, 4),
            "matched_skills": matched,
            "missing_skills": missing,
        })

    ranked.sort(key=lambda j: j["score"], reverse=True)
    return ranked
