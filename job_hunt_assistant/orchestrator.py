import os
from crewai import Crew, Process
from agents.jd_analyst import get_jd_analyst_agent, create_jd_analysis_task
from agents.resume_cl_agent import get_resume_cl_agent, create_resume_cl_task
from agents.messaging_agent import get_messaging_agent, create_messaging_task
from usajobs_api import fetch_usajobs
from utils.tracking import log_application, save_cover_letter_file


def load_resume(path="data/sample_resume.txt"):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def extract_between_markers(text, start, end=None):
    """Extract text between two marker strings."""
    try:
        start_idx = text.index(start) + len(start)
        end_idx = text.index(end, start_idx) if end else len(text)
        return text[start_idx:end_idx].strip()
    except ValueError:
        return "Not found"


def run_pipeline(job_data, resume_text, user_bio):
    """Run the full CrewAI pipeline for a single job posting."""
    try:
        job_summary = job_data['UserArea']['Details']['JobSummary']
    except (KeyError, TypeError):
        job_summary = job_data.get('QualificationSummary', 'No summary available.')

    agency_name = job_data.get('OrganizationName', 'Unknown Agency')
    job_title = job_data.get('PositionTitle', 'Unknown Position')

    # Initialize agents
    jd_agent = get_jd_analyst_agent()
    resume_agent = get_resume_cl_agent()
    message_agent = get_messaging_agent()

    # Create tasks
    jd_task = create_jd_analysis_task(jd_agent, job_summary)
    resume_task = create_resume_cl_task(resume_agent, job_summary, resume_text)
    message_task = create_messaging_task(message_agent, job_summary, agency_name, user_bio)

    # Build and run the crew
    crew = Crew(
        agents=[jd_agent, resume_agent, message_agent],
        tasks=[jd_task, resume_task, message_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()  # must run BEFORE reading task outputs

    # Extract key outputs (available only after kickoff)
    resume_output = str(resume_task.output or "")
    resume_summary = extract_between_markers(
        resume_output, "<<RESUME_SUMMARY>>", "<<COVER_LETTER>>"
    )
    cover_letter = extract_between_markers(resume_output, "<<COVER_LETTER>>")

    # Log and save
    log_application(job_title, agency_name, resume_summary)
    save_cover_letter_file(job_title, cover_letter)

    return result


if __name__ == "__main__":
    # Quick smoke-test: search for a job, pick the first result, and run the pipeline
    jobs = fetch_usajobs("business analyst", "New York", results_per_page=1)
    if jobs:
        sample_job = jobs[0]["MatchedObjectDescriptor"]
        resume = load_resume()
        run_pipeline(sample_job, resume, "I'm a data professional passionate about public service.")
    else:
        print("No jobs found for smoke-test.")