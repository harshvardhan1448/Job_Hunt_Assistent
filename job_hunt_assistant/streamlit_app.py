import streamlit as st
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
    job_posts = fetch_usajobs(keyword, location, results_per_page=5)
    if not job_posts:
        st.error("No job postings found for this search.")
    else:
        st.session_state["jobs"] = job_posts
        st.success("Jobs fetched! Select the ones you'd like to apply for.")

# Step 2: Show checkbox list for job selection
if "jobs" in st.session_state:
    selected_indexes = []
    st.markdown("### Select Jobs to Apply For:")
    for i, job in enumerate(st.session_state["jobs"]):
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
            for i in selected_indexes:
                job_data = st.session_state["jobs"][i]['MatchedObjectDescriptor']
                with st.spinner(f"Applying to: {job_data.get('PositionTitle')}"):
                    result = run_pipeline(job_data, resume_text, user_bio)
                    st.markdown("---")
                    st.markdown(f"### The reach-out message for: {job_data.get('PositionTitle')}")
                    st.markdown(result)