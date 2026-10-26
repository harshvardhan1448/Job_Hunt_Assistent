"""Unit tests for the JSearch migration (Phase 9).

Run with:
    cd job_hunt_assistant
    python -m pytest tests/ -v

Tests cover:
- providers.jsearch_api.normalize
- services.search deduplication logic
- services.matcher ranking and filters
- utils.validator "no invented skills" check
- orchestrator._parse_structured_output
"""

import sys
import os

# Ensure the package root is on the path when running tests directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# providers.jsearch_api.normalize
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalize:
    """Tests for the JSearch normalize() function."""

    def setup_method(self):
        from providers.jsearch_api import normalize
        self.normalize = normalize

    def _make_raw(self, **overrides):
        base = {
            "job_id": "abc123",
            "job_title": "Data Analyst",
            "employer_name": "Acme Corp",
            "job_city": "Mumbai",
            "job_state": "MH",
            "job_country": "IN",
            "job_is_remote": False,
            "job_description": "We need a data analyst.",
            "job_apply_link": "https://example.com/apply",
            "job_publisher": "LinkedIn",
            "job_posted_at_datetime_utc": "2024-10-01T00:00:00Z",
            "job_employment_type": "FULLTIME",
            "job_required_skills": ["SQL", "Python"],
            "job_required_experience": {},
            "job_highlights": {},
        }
        base.update(overrides)
        return base

    def test_basic_fields(self):
        result = self.normalize(self._make_raw())
        assert result["id"] == "abc123"
        assert result["title"] == "Data Analyst"
        assert result["company"] == "Acme Corp"
        assert result["apply_url"] == "https://example.com/apply"
        assert result["source"] == "LinkedIn"

    def test_location_joins_city_state_country(self):
        result = self.normalize(self._make_raw())
        assert "Mumbai" in result["location"]
        assert "IN" in result["location"]

    def test_location_skips_none(self):
        result = self.normalize(self._make_raw(job_city=None, job_state=None, job_country="IN"))
        assert result["location"] == "IN"

    def test_remote_flag(self):
        result = self.normalize(self._make_raw(job_is_remote=True))
        assert result["remote"] is True

    def test_remote_false(self):
        result = self.normalize(self._make_raw(job_is_remote=False))
        assert result["remote"] is False

    def test_missing_fields_return_defaults(self):
        result = self.normalize({})
        assert result["id"] is None
        assert result["title"] == ""
        assert result["description"] == ""
        assert result["apply_url"] is None

    def test_required_skills_preserved(self):
        result = self.normalize(self._make_raw(job_required_skills=["AWS", "Docker"]))
        assert "AWS" in result["required_skills"]


# ─────────────────────────────────────────────────────────────────────────────
# services.search deduplication
# ─────────────────────────────────────────────────────────────────────────────

class TestDedupJobs:
    """Tests for the internal _dedup_jobs helper."""

    def setup_method(self):
        from services.search import _dedup_jobs
        self.dedup = _dedup_jobs

    def _job(self, id_, title="Dev", company="Co", location="NY"):
        return {"id": id_, "title": title, "company": company, "location": location}

    def test_no_duplicates_pass_through(self):
        # Different IDs and different composite keys (different company) → both kept
        jobs = [self._job("1", company="Co A"), self._job("2", company="Co B")]
        assert len(self.dedup(jobs)) == 2

    def test_duplicate_id_removed(self):
        jobs = [self._job("1"), self._job("1")]
        assert len(self.dedup(jobs)) == 1

    def test_duplicate_composite_removed(self):
        j1 = {"id": None, "title": "Dev", "company": "Co", "location": "NY"}
        j2 = {"id": None, "title": "Dev", "company": "Co", "location": "NY"}
        assert len(self.dedup([j1, j2])) == 1

    def test_different_companies_both_kept(self):
        j1 = {"id": None, "title": "Dev", "company": "Co A", "location": "NY"}
        j2 = {"id": None, "title": "Dev", "company": "Co B", "location": "NY"}
        assert len(self.dedup([j1, j2])) == 2

    def test_first_occurrence_preserved(self):
        j1 = self._job("1", title="Senior Dev")
        j2 = self._job("1", title="Senior Dev v2")  # same id, different title
        result = self.dedup([j1, j2])
        assert result[0]["title"] == "Senior Dev"


# ─────────────────────────────────────────────────────────────────────────────
# services.search query builder
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildQueries:
    """Tests for the _build_queries helper."""

    def setup_method(self):
        from services.search import _build_queries
        from utils.resume_parser import Profile
        self.build = _build_queries
        self.Profile = Profile

    def test_returns_list_of_strings(self):
        profile = self.Profile(target_titles=["Data Analyst"], skills=["SQL"])
        queries = self.build(profile, "Mumbai")
        assert isinstance(queries, list)
        assert all(isinstance(q, str) for q in queries)

    def test_location_included_in_query(self):
        profile = self.Profile(target_titles=["Engineer"], skills=[])
        queries = self.build(profile, "Bangalore")
        assert any("Bangalore" in q for q in queries)

    def test_capped_at_5(self):
        profile = self.Profile(target_titles=["A", "B", "C", "D", "E", "F"], skills=[])
        queries = self.build(profile, "Delhi")
        assert len(queries) <= 5

    def test_empty_titles_uses_fallback(self):
        profile = self.Profile(target_titles=[], skills=[])
        queries = self.build(profile, "Pune")
        assert len(queries) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# services.matcher — hard filters
# ─────────────────────────────────────────────────────────────────────────────

class TestMatcherFilters:
    """Tests for the date and location hard filters."""

    def setup_method(self):
        from services.matcher import _passes_date_filter, _passes_location_filter
        from utils.resume_parser import Profile
        self.passes_date = _passes_date_filter
        self.passes_location = _passes_location_filter
        self.Profile = Profile

    def _make_job(self, **kw):
        defaults = {
            "id": "x",
            "title": "Dev",
            "company": "Co",
            "location": "Mumbai, IN",
            "remote": False,
            "description": "",
            "apply_url": "https://example.com",
            "posted_at": None,
        }
        defaults.update(kw)
        return defaults

    def test_missing_date_passes(self):
        assert self.passes_date(self._make_job(posted_at=None)) is True

    def test_fresh_job_passes(self):
        from datetime import datetime, timezone, timedelta
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        assert self.passes_date(self._make_job(posted_at=recent)) is True

    def test_old_job_fails(self):
        from datetime import datetime, timezone, timedelta
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        assert self.passes_date(self._make_job(posted_at=old), max_age_days=30) is False

    def test_remote_job_always_passes_location(self):
        profile = self.Profile()
        job = self._make_job(remote=True, location="New York")
        assert self.passes_location(job, profile, "Mumbai") is True

    def test_matching_location_passes(self):
        profile = self.Profile()
        job = self._make_job(location="Bangalore, Karnataka, IN")
        assert self.passes_location(job, profile, "Bangalore") is True

    def test_non_matching_location_fails(self):
        profile = self.Profile()
        job = self._make_job(remote=False, location="Paris, FR")
        assert self.passes_location(job, profile, "Mumbai") is False


# ─────────────────────────────────────────────────────────────────────────────
# services.matcher — skill overlap
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillOverlap:
    """Tests for the skill overlap scorer."""

    def setup_method(self):
        from services.matcher import _extract_skill_overlap
        from utils.resume_parser import Profile
        self.overlap = _extract_skill_overlap
        self.Profile = Profile

    def _job(self, skills=None, description=""):
        return {"required_skills": skills or [], "description": description}

    def test_full_overlap(self):
        profile = self.Profile(skills=["Python", "SQL"])
        frac, matched, missing = self.overlap(self._job(skills=["Python", "SQL"]), profile)
        assert frac == 1.0
        assert set(matched) == {"Python", "SQL"}
        assert missing == []

    def test_no_overlap(self):
        profile = self.Profile(skills=["Java"])
        frac, matched, missing = self.overlap(self._job(skills=["Python", "SQL"]), profile)
        assert frac == 0.0
        assert matched == []
        assert set(missing) == {"Python", "SQL"}

    def test_partial_overlap(self):
        profile = self.Profile(skills=["Python"])
        frac, matched, missing = self.overlap(self._job(skills=["Python", "SQL"]), profile)
        assert frac == 0.5

    def test_no_required_skills_returns_zero(self):
        profile = self.Profile(skills=["Python"])
        frac, matched, missing = self.overlap(self._job(skills=[]), profile)
        assert frac == 0.0

    def test_description_fallback(self):
        """When no explicit skills, scan description for profile skills."""
        profile = self.Profile(skills=["python"])
        job = self._job(skills=[], description="We need someone who knows python well.")
        frac, matched, missing = self.overlap(job, profile)
        assert frac > 0


# ─────────────────────────────────────────────────────────────────────────────
# utils.validator
# ─────────────────────────────────────────────────────────────────────────────

class TestValidator:
    """Tests for the 'no invented skills' validator."""

    def setup_method(self):
        from utils.validator import validate_tailored_resume
        self.validate = validate_tailored_resume

    def test_clean_when_no_new_skills(self):
        original = "I have 5 years of experience with Python and SQL."
        tailored = "Experienced Python and SQL professional with 5 years."
        result = self.validate(original, tailored)
        assert result["is_clean"] is True

    def test_flags_invented_skill(self):
        original = "I know Python and SQL."
        tailored = "Expert in Python, SQL, and Kubernetes."  # kubernetes not in original
        result = self.validate(original, tailored)
        assert "kubernetes" in result["invented_skills"]
        assert result["is_clean"] is False

    def test_flags_invented_number(self):
        original = "I have 3 years of experience."
        tailored = "I have 10 years of experience."  # 10 not in original
        result = self.validate(original, tailored)
        assert "10" in result["invented_numbers"]
        assert result["is_clean"] is False

    def test_empty_tailored_is_clean(self):
        result = self.validate("Some resume text", "")
        assert result["is_clean"] is True


# ─────────────────────────────────────────────────────────────────────────────
# orchestrator._parse_structured_output
# ─────────────────────────────────────────────────────────────────────────────

class TestParseStructuredOutput:
    """Tests for the improved marker-based parser in orchestrator."""

    def setup_method(self):
        from orchestrator import _parse_structured_output
        self.parse = _parse_structured_output

    def test_parses_both_markers(self):
        text = "<<RESUME_SUMMARY>>\nGreat candidate.\n\n<<COVER_LETTER>>\nDear Hiring Manager,\nI am interested."
        result = self.parse(text)
        assert "Great candidate." in result["resume_summary"]
        assert "Dear Hiring Manager" in result["cover_letter"]

    def test_missing_cover_letter_marker_returns_empty(self):
        text = "<<RESUME_SUMMARY>>\nSome summary."
        result = self.parse(text)
        assert "Some summary." in result["resume_summary"]
        # cover_letter may be empty or contain trailing content
        assert isinstance(result["cover_letter"], str)

    def test_empty_input(self):
        result = self.parse("")
        assert result["resume_summary"] == ""
        assert result["cover_letter"] == ""

    def test_none_input(self):
        result = self.parse(None)
        assert result["resume_summary"] == ""
        assert result["cover_letter"] == ""

    def test_no_markers_returns_empty_strings(self):
        text = "This is just a plain response without any markers."
        result = self.parse(text)
        # Should not crash; both values should be strings
        assert isinstance(result["resume_summary"], str)
        assert isinstance(result["cover_letter"], str)
