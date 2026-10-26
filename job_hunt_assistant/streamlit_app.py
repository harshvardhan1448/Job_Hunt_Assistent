"""Streamlit UI for the AI Job Hunt Assistant.

Flow
----
1. Upload (or paste) resume  →  profile extracted and shown in editable fields
2. Set location / filters    →  Search Jobs
3. Ranked job cards          →  Apply button (external link) or Tailor button
4. Tailoring pipeline runs   →  Download DOCX or view in-app

All heavy state (jobs, profile, results) is kept in ``st.session_state`` so
that widget interactions don't re-trigger searches.
"""

# Must be set BEFORE importing CrewAI
import os
import signal as signal_module

os.environ['CREWAI_TELEMETRY_OPT_OUT'] = 'true'

# Patch signal.signal to catch main-thread-only errors
_original_signal = signal_module.signal
def _safe_signal(sig, handler):
    try:
        return _original_signal(sig, handler)
    except ValueError as e:
        if "main thread" in str(e):
            return None
        raise
signal_module.signal = _safe_signal

import time
import streamlit as st

from utils.resume_parser import parse_resume, extract_profile_from_resume, Profile
from services.search import search_jobs
from services.matcher import rank_jobs
from orchestrator import run_pipeline
from utils.validator import validate_tailored_resume
from utils.exporter import build_resume_docx

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Job Hunt Assistant",
    page_icon="💼",
    layout="wide",
)

# ── CSS polish ───────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .job-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .score-badge { background: #1a56db; color: white; border-radius: 4px; padding: 2px 8px; font-size: 13px; }
    .skill-match { color: #057a55; font-weight: 600; }
    .skill-missing { color: #c81e1e; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Title ─────────────────────────────────────────────────────────────────────
st.title("💼 AI Job Hunt Assistant")
st.markdown(
    "Upload your resume, set your location, and let AI find, rank, and tailor applications — "
    "all powered by [JSearch](https://app.openwebninja.com/api/jsearch) (LinkedIn, Indeed, Glassdoor & more)."
)

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — configuration
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    location = st.text_input("Location (city, country, or 'remote')", "Bangalore, India")
    country_code = st.text_input("Country code (ISO-2)", "in")
    date_posted = st.selectbox(
        "Date posted",
        options=["week", "today", "3days", "month"],
        index=0,
    )
    max_results_display = st.slider("Max jobs to display", 5, 50, 20)

    st.divider()
    st.subheader("🔧 Scoring weights")
    weight_sim = st.slider("Embedding similarity weight", 0.0, 1.0, 0.6, 0.05)
    weight_skill = st.slider("Skill overlap weight", 0.0, 1.0, 0.4, 0.05)

    st.divider()
    st.markdown("**JSearch API key** — get yours free at [openwebninja.com](https://app.openwebninja.com/api/jsearch)")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Resume upload / paste
# ─────────────────────────────────────────────────────────────────────────────
st.header("Step 1 — Your Resume")

col_upload, col_paste = st.columns([1, 1])
with col_upload:
    uploaded_file = st.file_uploader("Upload PDF or DOCX", type=["pdf", "docx"])
with col_paste:
    pasted_resume = st.text_area("Or paste plain text", height=200, placeholder="Paste your resume here…")

resume_text: str = ""
if uploaded_file is not None:
    try:
        resume_text = parse_resume(uploaded_file=uploaded_file)
        st.success(f"✅ Parsed {uploaded_file.name} ({len(resume_text):,} characters)")
    except Exception as exc:
        st.error(f"Failed to parse resume: {exc}")
elif pasted_resume.strip():
    resume_text = pasted_resume.strip()

# ── User bio for outreach personalization ────────────────────────────────────
user_bio = st.text_area(
    "Short bio (for outreach tone — 1-2 sentences about you)",
    value="I'm a data professional with experience in analytics and software engineering, "
          "looking for my next challenge in a growth-oriented company.",
    height=80,
)

# ── Profile extraction ───────────────────────────────────────────────────────
if resume_text and "profile" not in st.session_state:
    with st.spinner("🤖 Extracting profile from resume…"):
        try:
            st.session_state["profile"] = extract_profile_from_resume(resume_text)
        except Exception as exc:
            st.warning(f"Auto-extraction failed: {exc}. Using blank profile.")
            st.session_state["profile"] = Profile()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Review and edit extracted profile
# ─────────────────────────────────────────────────────────────────────────────
st.header("Step 2 — Review Your Profile")
st.caption("AI extracted these from your resume. Edit before searching.")

profile: Profile = st.session_state.get("profile", Profile())

col1, col2 = st.columns(2)
with col1:
    raw_titles = st.text_area(
        "Target job titles (one per line)",
        value="\n".join(profile.target_titles) if profile.target_titles else "",
        height=120,
    )
    raw_locations = st.text_area(
        "Preferred locations (one per line)",
        value="\n".join(profile.preferred_locations) if profile.preferred_locations else "",
        height=80,
    )
with col2:
    raw_skills = st.text_area(
        "Your skills (one per line)",
        value="\n".join(profile.skills) if profile.skills else "",
        height=140,
    )
    years_exp = st.number_input(
        "Years of experience",
        min_value=0.0,
        max_value=50.0,
        value=float(profile.years_experience),
        step=0.5,
    )

# Rebuild profile from edited fields
edited_profile = Profile(
    target_titles=[t.strip() for t in raw_titles.splitlines() if t.strip()],
    skills=[s.strip() for s in raw_skills.splitlines() if s.strip()],
    years_experience=years_exp,
    preferred_locations=[p.strip() for p in raw_locations.splitlines() if p.strip()],
)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Search
# ─────────────────────────────────────────────────────────────────────────────
st.header("Step 3 — Search & Rank Jobs")

search_col, clear_col = st.columns([3, 1])
with search_col:
    do_search = st.button("🔍 Search Jobs", type="primary", disabled=not resume_text)
with clear_col:
    if st.button("🗑 Clear results"):
        for key in ["jobs", "ranked_jobs", "pipeline_results"]:
            st.session_state.pop(key, None)
        st.rerun()

if not resume_text:
    st.info("Upload or paste your resume first.")

if do_search:
    with st.spinner("Searching across LinkedIn, Indeed, Glassdoor and more…"):
        try:
            raw_jobs = search_jobs(
                profile=edited_profile,
                location=location,
                country=country_code,
                date_posted=date_posted,
            )
            if not raw_jobs:
                st.warning(
                    "No jobs returned. This could mean:\n"
                    "- Your JSEARCH_API_KEY is missing or invalid\n"
                    "- No fresh postings matched your query\n"
                    "- The free-tier quota has been reached\n\n"
                    "Check your .env file and try again."
                )
            else:
                ranked = rank_jobs(
                    jobs=raw_jobs,
                    profile=edited_profile,
                    resume_text=resume_text,
                    location_query=location,
                    weight_sim=weight_sim,
                    weight_skill=weight_skill,
                )
                st.session_state["jobs"] = raw_jobs
                st.session_state["ranked_jobs"] = ranked
                st.session_state.pop("pipeline_results", None)
                st.success(f"Found **{len(raw_jobs)}** jobs → ranked **{len(ranked)}** after filtering.")
        except ValueError as exc:
            # Missing API key
            st.error(f"❌ Configuration error: {exc}")
        except Exception as exc:
            error_text = str(exc)
            if "429" in error_text or "quota" in error_text.lower():
                st.error(
                    "⏳ JSearch quota exceeded (HTTP 429). "
                    "Wait a minute and try again, or upgrade your plan."
                )
            else:
                st.error(f"Search failed: {error_text[:300]}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Job cards
# ─────────────────────────────────────────────────────────────────────────────
if "ranked_jobs" in st.session_state:
    ranked_jobs: list[dict] = st.session_state["ranked_jobs"][:max_results_display]
    pipeline_results: dict = st.session_state.get("pipeline_results", {})

    st.markdown(f"### Showing top {len(ranked_jobs)} results")

    for idx, job in enumerate(ranked_jobs):
        title = job.get("title", "Unknown Title")
        company = job.get("company", "Unknown Company")
        loc = job.get("location", "")
        remote = job.get("remote", False)
        score = job.get("score", 0.0)
        apply_url = job.get("apply_url", "")
        matched = job.get("matched_skills", [])
        missing = job.get("missing_skills", [])
        source = job.get("source", "")
        posted_at = (job.get("posted_at") or "")[:10]  # date only

        with st.container():
            # ── Card header ──────────────────────────────────────────────────
            h_col, score_col = st.columns([5, 1])
            with h_col:
                st.markdown(f"#### {title}")
                loc_display = f"🌐 Remote" if remote else f"📍 {loc}" if loc else ""
                st.markdown(f"**{company}** &nbsp; {loc_display} &nbsp; {f'({source})' if source else ''}")
                if posted_at:
                    st.caption(f"Posted: {posted_at}")
            with score_col:
                pct = int(score * 100)
                color = "#057a55" if pct >= 60 else "#e3a008" if pct >= 40 else "#c81e1e"
                st.markdown(
                    f"<div style='text-align:center; background:{color}; color:white; "
                    f"border-radius:8px; padding:8px; font-size:20px; font-weight:700'>"
                    f"{pct}%</div>",
                    unsafe_allow_html=True,
                )

            # ── Skills ───────────────────────────────────────────────────────
            if matched:
                st.markdown(
                    "✅ **Matched:** " + " &nbsp;·&nbsp; ".join(f"`{s}`" for s in matched[:8])
                )
            if missing:
                st.markdown(
                    "❌ **Missing:** " + " &nbsp;·&nbsp; ".join(f"`{s}`" for s in missing[:8])
                )

            # ── Description preview ──────────────────────────────────────────
            with st.expander("📄 Description preview"):
                st.write((job.get("description") or "")[:800] + "…")

            # ── Buttons ──────────────────────────────────────────────────────
            btn_col1, btn_col2 = st.columns([1, 1])
            with btn_col1:
                if apply_url:
                    st.link_button("🚀 Apply (opens job site)", apply_url, use_container_width=True)
                else:
                    st.button("No apply link", disabled=True, key=f"no_apply_{idx}", use_container_width=True)

            with btn_col2:
                tailor_key = f"tailor_{idx}"
                if st.button("✍️ Tailor my resume", key=tailor_key, use_container_width=True):
                    if not resume_text.strip():
                        st.warning("Please upload or paste your resume first.")
                    else:
                        with st.spinner(f"Running AI pipeline for: {title}…"):
                            try:
                                result = run_pipeline(job, resume_text, user_bio)
                                pipeline_results[idx] = result
                                st.session_state["pipeline_results"] = pipeline_results
                            except Exception as exc:
                                error_text = str(exc)
                                if "429" in error_text or "rate" in error_text.lower():
                                    st.warning(f"⏳ Rate limit hit. Please wait and retry. ({title})")
                                elif "401" in error_text or "unauthorized" in error_text.lower():
                                    st.error("❌ Authentication error — check your HF_API_KEY in .env")
                                else:
                                    st.error(f"❌ Pipeline failed: {error_text[:200]}")

            # ── Tailoring results for this job ───────────────────────────────
            if idx in pipeline_results:
                pr = pipeline_results[idx]
                resume_summary = pr.get("resume_summary", "")
                cover_letter = pr.get("cover_letter", "")
                outreach = pr.get("outreach_message", "")

                # Validation
                if resume_text and resume_summary:
                    vr = validate_tailored_resume(resume_text, resume_summary)
                    if not vr["is_clean"]:
                        items = vr["invented_skills"] + vr["invented_numbers"]
                        st.warning(
                            f"⚠️ Potential invented content detected — please review: "
                            + ", ".join(f"`{i}`" for i in items[:10])
                        )

                result_tab1, result_tab2, result_tab3 = st.tabs(
                    ["📝 Resume Summary", "📨 Cover Letter", "💬 Outreach Message"]
                )
                with result_tab1:
                    if resume_summary:
                        st.markdown(resume_summary)
                    else:
                        st.info("Resume summary could not be generated.")

                with result_tab2:
                    if cover_letter:
                        st.markdown(cover_letter)
                    else:
                        st.info("Cover letter could not be generated.")

                with result_tab3:
                    if outreach:
                        st.markdown(outreach)
                    else:
                        st.info("Outreach message could not be generated.")

                # ── Download DOCX ─────────────────────────────────────────────
                try:
                    docx_bytes = build_resume_docx(
                        job_title=pr.get("job_title", title),
                        company=pr.get("company", company),
                        resume_summary=resume_summary,
                        cover_letter=cover_letter,
                    )
                    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:40]
                    st.download_button(
                        label="⬇️ Download as DOCX",
                        data=docx_bytes,
                        file_name=f"{safe_title}_application.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"download_{idx}",
                    )
                except Exception as exc:
                    st.caption(f"DOCX export unavailable: {exc}")

            st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────────────────────
st.caption(
    "Job data via [JSearch](https://app.openwebninja.com/api/jsearch) · "
    "AI by CrewAI + HuggingFace · Built with Streamlit"
)
