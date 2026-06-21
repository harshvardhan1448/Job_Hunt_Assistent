"""Pipeline orchestration for multi-agent job application generation."""

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

import re
import time
from crewai import Crew, Process
from agents.jd_analyst import get_jd_analyst_agent, create_jd_analysis_task
from agents.resume_cl_agent import get_resume_cl_agent, create_resume_cl_task
from agents.messaging_agent import get_messaging_agent, create_messaging_task
from usajobs_api import fetch_usajobs
from utils.tracking import log_application, save_cover_letter_file


def load_resume(path="data/sample_resume.txt"):
    """Load resume text from disk for local smoke tests."""
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def extract_between_markers(text, start, end=None):
    """Extract text between two marker strings."""
    if not text:
        return "Not found"
    
    text = str(text)
    try:
        start_idx = text.index(start) + len(start)
        end_idx = text.index(end, start_idx) if end else len(text)
        return text[start_idx:end_idx].strip()
    except ValueError:
        # Try alternative markers without angle brackets
        alt_start = start.replace("<<", "").replace(">>", "").strip()
        try:
            start_idx = text.lower().index(alt_start.lower()) + len(alt_start)
            end_idx = text.index(end.replace("<<", "").replace(">>", "").strip(), start_idx) if end else len(text)
            return text[start_idx:end_idx].strip()
        except ValueError:
            return "Not found"


def _parse_retry_delay(error_text, default_seconds=30):
    """Extract retry delay seconds from provider error text when available."""
    retry_patterns = [
        r"retry in\s+([\d.]+)s",
        r'"retryDelay"\s*:\s*"(\d+)s"',
    ]
    for pattern in retry_patterns:
        match = re.search(pattern, error_text, flags=re.IGNORECASE)
        if match:
            try:
                return max(default_seconds, int(float(match.group(1))))
            except ValueError:
                continue
    return default_seconds


def _kickoff_with_retry(crew, max_retries=3):
    """Run crew kickoff with retry behavior for transient errors (rate limits, 504, etc.)."""
    attempt = 0
    base_wait = 15
    
    while True:
        try:
            return crew.kickoff()
        except Exception as exc:
            error_text = str(exc).lower()
            attempt += 1
            
            # Check for transient errors (rate limit, quota, server errors)
            is_transient = any(
                token in error_text
                for token in ["ratelimit", "resource_exhausted", "quota", "429", "504", "gateway", "timeout", "temporarily"]
            )
            
            if not is_transient or attempt >= max_retries:
                print(f"❌ Non-transient error or max retries reached: {error_text[:200]}")
                raise
            
            # Exponential backoff: 15s, 30s, 60s
            wait_seconds = base_wait * (2 ** (attempt - 1))
            print(f"⏳ Transient error (attempt {attempt}/{max_retries}). Waiting {wait_seconds}s before retry...")
            time.sleep(wait_seconds)


def run_pipeline(job_data, resume_text, user_bio):
    """Run the full CrewAI pipeline for one job and return structured outputs.

    Args:
        job_data: USAJobs `MatchedObjectDescriptor` payload.
        resume_text: Candidate's resume text.
        user_bio: Short candidate bio for outreach personalization.

    Returns:
        Dictionary containing generated resume summary, cover letter,
        outreach message, and metadata for display/logging.
    """
    try:
        job_summary = job_data['UserArea']['Details']['JobSummary']
    except (KeyError, TypeError):
        job_summary = job_data.get('QualificationSummary', 'No summary available.')

    agency_name = job_data.get('OrganizationName', 'Unknown Agency')
    job_title = job_data.get('PositionTitle', 'Unknown Position')

    # Limit input size to reduce free-tier token pressure.
    if resume_text:
        resume_text = resume_text[:6000]
    if user_bio:
        user_bio = user_bio[:500]

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

    try:
        result = _kickoff_with_retry(crew)  # must run BEFORE reading task outputs
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Crew execution failed: {error_msg}\n")
        if "invalid request" in error_msg.lower():
            print("💡 Tip: This might be a request size issue. Job summary or resume may be too long.")
        if "401" in error_msg or "unauthorized" in error_msg.lower():
            print("💡 Tip: Check your HF_API_KEY and HF_MODEL in .env file")
        raise

    # Extract key outputs (available only after kickoff)
    resume_output = str(resume_task.output or "")
    
    # If task output is empty, try reading from output file
    if not resume_output or resume_output.strip() == "" or "Not found" in resume_output:
        try:
            with open("data/resume_agent_output.txt", "r", encoding="utf-8") as f:
                resume_output = f.read()
        except FileNotFoundError:
            pass
    
    resume_summary = extract_between_markers(
        resume_output, "<<RESUME_SUMMARY>>", "<<COVER_LETTER>>"
    )
    cover_letter = extract_between_markers(resume_output, "<<COVER_LETTER>>")
    
    # If still not found, try to use first half as summary, second half as letter
    if resume_summary == "Not found" and resume_output and len(resume_output) > 100:
        mid = len(resume_output) // 2
        resume_summary = resume_output[:mid].strip()[:500]  # First 500 chars
    
    if cover_letter == "Not found" and resume_output and len(resume_output) > 100:
        mid = len(resume_output) // 2
        cover_letter = resume_output[mid:].strip()
    
    outreach_message = str(message_task.output or result or "")

    # Log and save
    log_application(job_title, agency_name, resume_summary)
    save_cover_letter_file(job_title, cover_letter)

    return {
        "job_title": job_title,
        "agency_name": agency_name,
        "resume_summary": resume_summary,
        "cover_letter": cover_letter,
        "outreach_message": outreach_message,
        "raw_result": str(result or ""),
    }


if __name__ == "__main__":
    # Quick smoke-test: search for a job, pick the first result, and run the pipeline
    jobs = fetch_usajobs("business analyst", "New York", results_per_page=1)
    if jobs:
        sample_job = jobs[0]["MatchedObjectDescriptor"]
        resume = load_resume()
        run_pipeline(sample_job, resume, "I'm a data professional passionate about public service.")
    else:
        print("No jobs found for smoke-test.")