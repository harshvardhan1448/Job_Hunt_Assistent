"""Streamlit UI for searching jobs and generating application artifacts."""

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
                        st.markdown(resume_summary if resume_summary else "Not available")

                        st.markdown("#### Cover Letter")
                        st.markdown(cover_letter if cover_letter else "Not available")

                        st.markdown("#### Outreach Message")
                        st.markdown(outreach_message if outreach_message else "Not available")
                    except Exception as e:
                        st.error(f"Error processing '{title}': {e}")
                if len(selected_indexes) > 1:
                    # Gentle cooldown to reduce burst requests on free-tier quotas.
                    time.sleep(8)