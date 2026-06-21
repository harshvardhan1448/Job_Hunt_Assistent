"""Streamlit UI for searching jobs and generating application artifacts."""

# Must be set BEFORE importing CrewAI
import os
import signal as signal_module

# Disable CrewAI telemetry
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

import streamlit as st
import time
from orchestrator import run_pipeline
from usajobs_api import fetch_usajobs

st.set_page_config(page_title="AI Job Hunt Assistant", layout="centered")

st.title("AI Job Hunt Assistant")
st.markdown("Use AI agents to analyze jobs, tailor your resume, and write outreach messages — all from one interface.")

# Input fields
keyword = st.text_input("Job Keyword", "business analyst")
location = st.text_input("Location", "New York")
resume_text = st.text_area("Paste Your Resume", height=200)
user_bio = st.text_area("Short Bio (for outreach tone)", "I’m a data professional passionate about public service.")

# Step 1: Search Jobs
if st.button("Search Jobs"):
    try:
        with st.spinner("Searching USAJobs..."):
            job_posts = fetch_usajobs(keyword, location, results_per_page=5)
        if not job_posts:
            st.error("No job postings found for this search.")
        else:
            st.session_state["jobs"] = job_posts
            st.success(f"Found {len(job_posts)} jobs! Select the ones you'd like to apply for.")
    except Exception as e:
        st.error(f"Failed to fetch jobs: {e}")

# Step 2: Show checkbox list for job selection
if "jobs" in st.session_state:
    selected_indexes = []
    st.markdown("### Select Jobs to Apply For:")
    for i, job in enumerate(st.session_state["jobs"]):
        # USAJobs wraps the useful fields inside MatchedObjectDescriptor.
        job_data = job['MatchedObjectDescriptor']
        title = job_data.get('PositionTitle', 'Unknown Title')
        org = job_data.get('OrganizationName', 'Unknown Agency')
        checkbox = st.checkbox(f"{title} — {org}", key=f"job_{i}")
        if checkbox:
            selected_indexes.append(i)

    # Step 3: Apply to selected jobs
    if st.button("Apply to Selected Jobs"):
        if not selected_indexes:
            st.warning("Please select at least one job.")
        elif not resume_text.strip():
            st.warning("Please paste your resume before applying.")
        else:
            if len(selected_indexes) > 1:
                st.info("Multiple jobs selected. Processing one-by-one with cooldown to avoid API rate limits.")
            for i in selected_indexes:
                job_data = st.session_state["jobs"][i]['MatchedObjectDescriptor']
                title = job_data.get('PositionTitle', 'Unknown')
                with st.spinner(f"Processing: {title}..."):
                    try:
                        # Pipeline returns a structured dict with generated artifacts.
                        result = run_pipeline(job_data, resume_text, user_bio)
                        if isinstance(result, dict):
                            resume_summary = result.get("resume_summary", "")
                            cover_letter = result.get("cover_letter", "")
                            outreach_message = result.get("outreach_message") or result.get("raw_result", "")
                        else:
                            resume_summary = ""
                            cover_letter = ""
                            outreach_message = str(result)

                        st.markdown("---")
                        st.markdown(f"### Outputs for: {title}")

                        st.markdown("#### Updated Resume Summary")
                        if resume_summary and resume_summary != "Not found":
                            st.markdown(resume_summary)
                        else:
                            st.info("Resume summary could not be generated. Check that the job description was processed correctly.")

                        st.markdown("#### Cover Letter")
                        if cover_letter and cover_letter != "Not found":
                            st.markdown(cover_letter)
                        else:
                            st.info("Cover letter could not be generated. This may require manual editing.")

                        st.markdown("#### Outreach Message")
                        if outreach_message and outreach_message.strip():
                            st.markdown(outreach_message)
                        else:
                            st.info("Outreach message could not be generated.")
                    except Exception as e:
                        error_text = str(e)
                        # Provide user-friendly error messages
                        if "504" in error_text or "gateway" in error_text.lower():
                            st.warning(f"⏳ HuggingFace API temporarily overloaded. Retrying in the background... Job: {title}")
                        elif "429" in error_text or "rate" in error_text.lower():
                            st.warning(f"⏳ Rate limit hit. Waiting before retry... Job: {title}")
                        elif "401" in error_text or "unauthorized" in error_text.lower():
                            st.error(f"❌ Authentication error. Please check your API keys in .env. Job: {title}")
                        else:
                            # Show brief error without HTML dump
                            brief_error = error_text[:200] if len(error_text) > 200 else error_text
                            st.error(f"❌ Error processing '{title}': {brief_error}")
                if len(selected_indexes) > 1:
                    # Gentle cooldown to reduce burst requests on free-tier quotas.
                    time.sleep(8)