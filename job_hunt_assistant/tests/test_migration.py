"""Unit tests for the JSearch migration (Phase 9).

Run with:
    cd job_hunt_assistant
    python -m pytest tests/ -v

Covers:
- providers.jsearch_api.normalize and fetch_jobs (network mocked)
- services.search dedupe and query builder
- services.matcher hard filters, skill overlap, ranking
- utils.validator "no invented skills / numbers" check
- utils.resume_parser basics
- orchestrator._parse_structured_output

ADJUST-ME markers: a few names below are guesses (ranking function, resume
text extractor, embedding hook). Change the constants at the top of each
section if yours differ. Tests skip (not fail) when the name does not exist.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests


# ─────────────────────────────────────────────────────────────────────────────
# providers.jsearch_api.normalize
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalize:

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
        assert self.normalize(self._make_raw(job_is_remote=True))["remote"] is True

    def test_remote_false(self):
        assert self.normalize(self._make_raw(job_is_remote=False))["remote"] is False

    def test_missing_fields_return_defaults(self):
        result = self.normalize({})
        assert result["id"] is None
        assert result["title"] == ""
        assert result["description"] == ""
        assert result["apply_url"] is None

    def test_required_skills_preserved(self):
        result = self.normalize(self._make_raw(job_required_skills=["AWS", "Docker"]))
        assert "AWS" in result["required_skills"]

    def test_required_skills_none_does_not_crash(self):
        result = self.normalize(self._make_raw(job_required_skills=None))
        assert not result.get("required_skills")


class TestRealResponseFixture:
    """Catches field-name mismatches against a real saved API response.

    Save one real response to tests/fixtures/jsearch_sample.json
    (the full JSON body, with a top-level "data" list).
    """

    FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "jsearch_sample.json")

    def test_every_real_job_normalizes_with_title_and_apply_url(self):
        if not os.path.exists(self.FIXTURE):
            pytest.skip("Save a real response to tests/fixtures/jsearch_sample.json")
        from providers.jsearch_api import normalize
        with open(self.FIXTURE, encoding="utf-8") as f:
            data = json.load(f).get("data", [])
        assert data, "Fixture has no jobs"
        for raw in data:
            job = normalize(raw)
            assert job["title"], f"Empty title for {raw.get('job_id')}"
            assert job["apply_url"], f"Empty apply_url for {raw.get('job_id')}"
            assert job["description"], f"Empty description for {raw.get('job_id')}"


# ─────────────────────────────────────────────────────────────────────────────
# providers.jsearch_api.fetch_jobs  (requests.get mocked)
# ─────────────────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} error")
            err.response = self
            raise err


def _raw_job(**kw):
    base = {
        "job_id": "j1",
        "job_title": "Dev",
        "employer_name": "Co",
        "job_description": "Build things.",
        "job_apply_link": "https://example.com/apply",
    }
    base.update(kw)
    return base


class TestFetchJobs:

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        import providers.jsearch_api as mod
        self.mod = mod
        self.monkeypatch = monkeypatch
        monkeypatch.setattr(mod, "JSEARCH_API_KEY", "test-key", raising=False)

    def _mock_get(self, response):
        self.monkeypatch.setattr(requests, "get", lambda *a, **k: response)

    def test_returns_normalized_jobs(self):
        self._mock_get(FakeResponse(200, {"data": [_raw_job()]}))
        jobs = self.mod.fetch_jobs("python developer")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Dev"

    def test_empty_data_returns_empty_list(self):
        self._mock_get(FakeResponse(200, {"data": []}))
        assert self.mod.fetch_jobs("python developer") == []

    def test_drops_jobs_without_apply_link(self):
        self._mock_get(FakeResponse(200, {"data": [_raw_job(job_apply_link=None)]}))
        assert self.mod.fetch_jobs("x") == []

    def test_drops_jobs_without_description(self):
        self._mock_get(FakeResponse(200, {"data": [_raw_job(job_description="")]}))
        assert self.mod.fetch_jobs("x") == []

    def test_401_raises_http_error(self):
        self._mock_get(FakeResponse(401, {"message": "Invalid key"}))
        with pytest.raises(requests.HTTPError):
            self.mod.fetch_jobs("x")

    def test_429_raises_http_error(self):
        self._mock_get(FakeResponse(429, {"message": "Quota exceeded"}))
        with pytest.raises(requests.HTTPError):
            self.mod.fetch_jobs("x")

    def test_missing_key_raises(self):
        self.monkeypatch.setattr(self.mod, "JSEARCH_API_KEY", "", raising=False)
        with pytest.raises(Exception):
            self.mod.fetch_jobs("x")


# ─────────────────────────────────────────────────────────────────────────────
# services.search deduplication
# ─────────────────────────────────────────────────────────────────────────────

class TestDedupJobs:

    def setup_method(self):
        from services.search import _dedup_jobs
        self.dedup = _dedup_jobs

    def _job(self, id_, title="Dev", company="Co", location="NY"):
        return {"id": id_, "title": title, "company": company, "location": location}

    def test_no_duplicates_pass_through(self):
        jobs = [self._job("1", company="Co A"), self._job("2", company="Co B")]
        assert len(self.dedup(jobs)) == 2

    def test_duplicate_id_removed(self):
        assert len(self.dedup([self._job("1"), self._job("1")])) == 1

    def test_duplicate_composite_removed(self):
        j1 = {"id": None, "title": "Dev", "company": "Co", "location": "NY"}
        j2 = {"id": None, "title": "Dev", "company": "Co", "location": "NY"}
        assert len(self.dedup([j1, j2])) == 1

    def test_composite_ignores_case_and_whitespace(self):
        j1 = {"id": None, "title": "Data Analyst ", "company": "Acme", "location": "Mumbai"}
        j2 = {"id": None, "title": "data analyst", "company": "ACME", "location": "mumbai "}
        assert len(self.dedup([j1, j2])) == 1

    def test_different_companies_both_kept(self):
        j1 = {"id": None, "title": "Dev", "company": "Co A", "location": "NY"}
        j2 = {"id": None, "title": "Dev", "company": "Co B", "location": "NY"}
        assert len(self.dedup([j1, j2])) == 2

    def test_first_occurrence_preserved(self):
        result = self.dedup([self._job("1", title="Senior Dev"), self._job("1", title="Senior Dev v2")])
        assert result[0]["title"] == "Senior Dev"

    def test_empty_list(self):
        assert self.dedup([]) == []


# ─────────────────────────────────────────────────────────────────────────────
# services.search query builder
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildQueries:

    def setup_method(self):
        import services.search as search_mod
        from utils.resume_parser import Profile
        self.build = search_mod._build_queries
        # Free tier is small: keep the cap low. Set MAX_QUERIES in services.search.
        self.max_queries = getattr(search_mod, "MAX_QUERIES", 2)
        self.Profile = Profile

    def test_returns_list_of_strings(self):
        queries = self.build(self.Profile(target_titles=["Data Analyst"], skills=["SQL"]), "Mumbai")
        assert isinstance(queries, list)
        assert all(isinstance(q, str) for q in queries)

    def test_location_included_in_query(self):
        queries = self.build(self.Profile(target_titles=["Engineer"], skills=[]), "Bangalore")
        assert any("Bangalore" in q for q in queries)

    def test_capped_at_max_queries(self):
        profile = self.Profile(target_titles=["A", "B", "C", "D", "E", "F"], skills=[])
        assert len(self.build(profile, "Delhi")) <= self.max_queries

    def test_empty_titles_uses_fallback(self):
        queries = self.build(self.Profile(target_titles=[], skills=[]), "Pune")
        assert len(queries) >= 1
        assert all(q.strip() for q in queries)

    def test_empty_location_has_no_none_text(self):
        queries = self.build(self.Profile(target_titles=["Engineer"], skills=[]), "")
        assert queries
        assert all("None" not in q for q in queries)
        assert all(not q.rstrip().endswith(" in") for q in queries)


# ─────────────────────────────────────────────────────────────────────────────
# services.matcher: hard filters
# ─────────────────────────────────────────────────────────────────────────────

class TestMatcherFilters:

    def setup_method(self):
        from services.matcher import _passes_date_filter, _passes_location_filter
        from utils.resume_parser import Profile
        self.passes_date = _passes_date_filter
        self.passes_location = _passes_location_filter
        self.Profile = Profile

    def _make_job(self, **kw):
        defaults = {
            "id": "x", "title": "Dev", "company": "Co",
            "location": "Mumbai, IN", "remote": False, "description": "",
            "apply_url": "https://example.com", "posted_at": None,
        }
        defaults.update(kw)
        return defaults

    # date
    def test_missing_date_passes(self):
        assert self.passes_date(self._make_job(posted_at=None)) is True

    def test_fresh_job_passes(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        assert self.passes_date(self._make_job(posted_at=recent)) is True

    def test_old_job_fails(self):
        old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        assert self.passes_date(self._make_job(posted_at=old), max_age_days=30) is False

    def test_z_suffix_date_is_parsed(self):
        """JSearch returns e.g. 2024-10-01T00:00:00.000Z"""
        old = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        assert self.passes_date(self._make_job(posted_at=old), max_age_days=30) is False
        fresh = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        assert self.passes_date(self._make_job(posted_at=fresh), max_age_days=30) is True

    def test_malformed_date_does_not_crash(self):
        assert self.passes_date(self._make_job(posted_at="not-a-date")) in (True, False)

    def test_naive_datetime_does_not_crash(self):
        naive = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        assert self.passes_date(self._make_job(posted_at=naive)) in (True, False)

    # location
    def test_remote_job_always_passes_location(self):
        job = self._make_job(remote=True, location="New York")
        assert self.passes_location(job, self.Profile(), "Mumbai") is True

    def test_matching_location_passes(self):
        job = self._make_job(location="Bangalore, Karnataka, IN")
        assert self.passes_location(job, self.Profile(), "Bangalore") is True

    def test_location_match_is_case_insensitive(self):
        job = self._make_job(location="BANGALORE, KA, IN")
        assert self.passes_location(job, self.Profile(), "bangalore") is True

    def test_non_matching_location_fails(self):
        job = self._make_job(remote=False, location="Paris, FR")
        assert self.passes_location(job, self.Profile(), "Mumbai") is False

    def test_empty_location_passes_everything(self):
        job = self._make_job(location="Paris, FR")
        assert self.passes_location(job, self.Profile(), "") is True

    def test_profile_preferred_locations_are_used(self):
        profile = self.Profile(preferred_locations=["Pune"])
        job = self._make_job(location="Pune, MH, IN")
        assert self.passes_location(job, profile, "Mumbai") is True


# ─────────────────────────────────────────────────────────────────────────────
# services.matcher: skill overlap
# ─────────────────────────────────────────────────────────────────────────────

class TestSkillOverlap:

    def setup_method(self):
        from services.matcher import _extract_skill_overlap
        from utils.resume_parser import Profile
        self.overlap = _extract_skill_overlap
        self.Profile = Profile

    def _job(self, skills=None, description=""):
        return {"required_skills": skills or [], "description": description}

    def test_full_overlap(self):
        frac, matched, missing = self.overlap(self._job(skills=["Python", "SQL"]),
                                              self.Profile(skills=["Python", "SQL"]))
        assert frac == 1.0
        assert set(matched) == {"Python", "SQL"}
        assert missing == []

    def test_no_overlap(self):
        frac, matched, missing = self.overlap(self._job(skills=["Python", "SQL"]),
                                              self.Profile(skills=["Java"]))
        assert frac == 0.0
        assert matched == []
        assert set(missing) == {"Python", "SQL"}

    def test_partial_overlap(self):
        frac, matched, missing = self.overlap(self._job(skills=["Python", "SQL"]),
                                              self.Profile(skills=["Python"]))
        assert frac == 0.5
        assert [m.lower() for m in matched] == ["python"]
        assert [m.lower() for m in missing] == ["sql"]

    def test_no_required_skills_returns_zero(self):
        frac, _, _ = self.overlap(self._job(skills=[]), self.Profile(skills=["Python"]))
        assert frac == 0.0

    def test_description_fallback(self):
        job = self._job(skills=[], description="We need someone who knows python well.")
        frac, matched, _ = self.overlap(job, self.Profile(skills=["python"]))
        assert frac > 0
        assert [m.lower() for m in matched] == ["python"]

    def test_case_insensitive_match(self):
        frac, _, _ = self.overlap(self._job(skills=["python"]), self.Profile(skills=["Python"]))
        assert frac == 1.0

    def test_java_does_not_match_javascript(self):
        job = self._job(skills=[], description="Strong JavaScript and React experience required.")
        _, matched, _ = self.overlap(job, self.Profile(skills=["Java"]))
        assert matched == []

    def test_go_does_not_match_google(self):
        job = self._job(skills=[], description="Experience with Google Cloud is a plus.")
        _, matched, _ = self.overlap(job, self.Profile(skills=["Go"]))
        assert matched == []


# ─────────────────────────────────────────────────────────────────────────────
# services.matcher: ranking
# ─────────────────────────────────────────────────────────────────────────────

RANK_FN_NAME = "rank_jobs"  # ADJUST-ME: your ranking function in services.matcher


class TestRanking:

    @pytest.fixture(autouse=True)
    def _stub_embeddings(self, monkeypatch):
        import numpy as np
        import services.matcher as matcher

        class FakeEmbedder:
            def encode(self, texts, **kwargs):
                is_batch = isinstance(texts, list)
                values = texts if is_batch else [texts]
                vectors = []
                for value in values:
                    vectors.append(
                        [0.0, 1.0] if "forklift" in value.lower() else [1.0, 0.0]
                    )
                result = np.array(vectors)
                return result if is_batch else result[0]

        monkeypatch.setattr(matcher, "_get_embedder", lambda: FakeEmbedder())

    def _rank(self):
        import services.matcher as matcher
        fn = getattr(matcher, RANK_FN_NAME, None)
        if fn is None:
            pytest.skip(f"services.matcher.{RANK_FN_NAME} not found; set RANK_FN_NAME")
        return fn

    def _jobs(self):
        return [
            {"id": "1", "title": "Python Data Analyst", "company": "A", "location": "Mumbai",
             "remote": False, "description": "SQL and Python reporting.",
             "required_skills": ["SQL", "Python"], "apply_url": "https://a", "posted_at": None},
            {"id": "2", "title": "Warehouse Operator", "company": "B", "location": "Mumbai",
             "remote": False, "description": "Forklift and packing.",
             "required_skills": ["Forklift"], "apply_url": "https://b", "posted_at": None},
        ]

    def test_results_sorted_by_score_desc(self):
        from utils.resume_parser import Profile
        ranked = self._rank()(self._jobs(), Profile(skills=["Python", "SQL"]), "Mumbai")
        scores = [j["score"] for j in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_each_result_has_required_keys(self):
        from utils.resume_parser import Profile
        ranked = self._rank()(self._jobs(), Profile(skills=["Python", "SQL"]), "Mumbai")
        for job in ranked:
            assert {"score", "matched_skills", "missing_skills"} <= set(job)

    def test_relevant_job_ranks_first(self):
        from utils.resume_parser import Profile
        ranked = self._rank()(self._jobs(), Profile(skills=["Python", "SQL"]), "Mumbai")
        assert ranked[0]["id"] == "1"

    def test_empty_job_list(self):
        from utils.resume_parser import Profile
        assert self._rank()([], Profile(skills=["Python"]), "Mumbai") == []


# ─────────────────────────────────────────────────────────────────────────────
# utils.validator
# ─────────────────────────────────────────────────────────────────────────────

class TestValidator:

    def setup_method(self):
        from utils.validator import validate_tailored_resume
        self.validate = validate_tailored_resume

    def test_clean_when_no_new_skills(self):
        result = self.validate("I have 5 years of experience with Python and SQL.",
                               "Experienced Python and SQL professional with 5 years.")
        assert result["is_clean"] is True

    def test_flags_invented_skill(self):
        result = self.validate("I know Python and SQL.", "Expert in Python, SQL, and Kubernetes.")
        assert "kubernetes" in [s.lower() for s in result["invented_skills"]]
        assert result["is_clean"] is False

    def test_flags_invented_number(self):
        result = self.validate("I have 3 years of experience.", "I have 10 years of experience.")
        assert "10" in result["invented_numbers"]
        assert result["is_clean"] is False

    def test_number_not_matched_as_substring(self):
        """'10' must not pass just because '100' exists in the original."""
        result = self.validate("Handled 100 users.", "Handled 10 users.")
        assert "10" in result["invented_numbers"]
        assert result["is_clean"] is False

    def test_number_formatting_differences_stay_clean(self):
        result = self.validate("Improved speed by 30% and saved $1,000.",
                               "Improved speed by 30 % and saved $1000.")
        assert result["is_clean"] is True

    def test_skill_case_difference_stays_clean(self):
        result = self.validate("Skills: python, sql", "Skilled in Python and SQL.")
        assert result["is_clean"] is True

    def test_reworded_text_without_new_skills_stays_clean(self):
        result = self.validate("Built dashboards in Python for the sales team.",
                               "Results-driven professional who built Python dashboards for stakeholders.")
        assert result["is_clean"] is True

    def test_empty_tailored_is_clean(self):
        assert self.validate("Some resume text", "")["is_clean"] is True


# ─────────────────────────────────────────────────────────────────────────────
# utils.resume_parser
# ─────────────────────────────────────────────────────────────────────────────

EXTRACT_FN_NAME = "extract_text_from_docx"


class TestResumeParser:

    def test_profile_defaults(self):
        from utils.resume_parser import Profile
        p = Profile()
        assert p.target_titles == []
        assert p.skills == []
        assert p.preferred_locations == []

    def test_docx_text_extraction(self, tmp_path):
        import utils.resume_parser as rp
        fn = getattr(rp, EXTRACT_FN_NAME, None)
        if fn is None:
            pytest.skip(f"utils.resume_parser.{EXTRACT_FN_NAME} not found; set EXTRACT_FN_NAME")
        docx = pytest.importorskip("docx")
        path = tmp_path / "resume.docx"
        doc = docx.Document()
        doc.add_paragraph("Harsh Rajput - Python, SQL")
        doc.save(path)
        text = fn(path.read_bytes())
        assert "Python" in text

    def test_empty_or_corrupt_file_fails_gracefully(self, tmp_path):
        import utils.resume_parser as rp
        fn = getattr(rp, EXTRACT_FN_NAME, None)
        if fn is None:
            pytest.skip(f"utils.resume_parser.{EXTRACT_FN_NAME} not found")
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a real pdf")
        try:
            out = fn(bad.read_bytes())
            assert isinstance(out, str)
        except Exception as e:  # a clean, specific error is also acceptable
            assert str(e)


# ─────────────────────────────────────────────────────────────────────────────
# orchestrator._parse_structured_output
# ─────────────────────────────────────────────────────────────────────────────

class TestParseStructuredOutput:

    def setup_method(self):
        from orchestrator import _parse_structured_output
        self.parse = _parse_structured_output

    def test_parses_both_markers(self):
        text = "<<RESUME_SUMMARY>>\nGreat candidate.\n\n<<COVER_LETTER>>\nDear Hiring Manager,\nI am interested."
        result = self.parse(text)
        assert "Great candidate." in result["resume_summary"]
        assert "Dear Hiring Manager" in result["cover_letter"]

    def test_sections_do_not_leak_into_each_other(self):
        text = "<<RESUME_SUMMARY>>\nSummary here.\n<<COVER_LETTER>>\nLetter here."
        result = self.parse(text)
        assert "Letter here." not in result["resume_summary"]
        assert "Summary here." not in result["cover_letter"]

    def test_whitespace_is_trimmed(self):
        text = "<<RESUME_SUMMARY>>\n\n   Summary.   \n\n<<COVER_LETTER>>\n\n  Letter.  \n"
        result = self.parse(text)
        assert result["resume_summary"] == "Summary."
        assert result["cover_letter"] == "Letter."

    def test_missing_cover_letter_marker_returns_empty(self):
        result = self.parse("<<RESUME_SUMMARY>>\nSome summary.")
        assert "Some summary." in result["resume_summary"]
        assert result["cover_letter"] == ""

    def test_empty_input(self):
        result = self.parse("")
        assert result["resume_summary"] == ""
        assert result["cover_letter"] == ""

    def test_none_input(self):
        result = self.parse(None)
        assert result["resume_summary"] == ""
        assert result["cover_letter"] == ""

    def test_no_markers_returns_empty_strings(self):
        """Proves the old 'split the text in half' fallback is gone."""
        result = self.parse("This is just a plain response without any markers.")
        assert result["resume_summary"] == ""
        assert result["cover_letter"] == ""