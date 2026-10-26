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
from utils.tracking import log_application, save_cover_letter_file


def load_resume(path="data/sample_resume.txt"):
    """Load resume text from disk for local smoke tests."""
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


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


def _parse_structured_output(text: str) -> dict:
    """Parse resume summary and cover letter from agent output.

    Tries the ``<<MARKER>>`` convention first; if that fails it looks for
    plain-text headings.  Returns a dict with ``resume_summary`` and
    ``cover_letter`` keys — both guaranteed to be strings (possibly empty).

    Args:
        text: Raw string output from the resume/cover-letter agent.

    Returns:
        Dict with ``resume_summary`` and ``cover_letter`` keys.
    """
    if not text:
        return {"resume_summary": "", "cover_letter": ""}

    text = str(text)

    def _between(src, start_marker, end_marker=None):
        try:
            si = src.index(start_marker) + len(start_marker)
            if end_marker:
                try:
                    ei = src.index(end_marker, si)
                except ValueError:
                    ei = len(src)  # end marker missing → read to end of text
            else:
                ei = len(src)
            return src[si:ei].strip()
        except ValueError:
            return None

    # Primary: angle-bracket markers
    resume_summary = _between(text, "<<RESUME_SUMMARY>>", "<<COVER_LETTER>>")
    cover_letter = _between(text, "<<COVER_LETTER>>")

    # Secondary: heading-based fallback
    if resume_summary is None:
        for heading in ["resume summary", "professional summary"]:
            idx = text.lower().find(heading)
            if idx != -1:
                block_start = idx + len(heading)
                # Find next heading or end
                next_heading = re.search(r"\n[A-Z][A-Za-z ]{3,}\n", text[block_start:])
                end = block_start + next_heading.start() if next_heading else len(text)
                resume_summary = text[block_start:end].strip(": \n")
                break

    if cover_letter is None:
        for heading in ["cover letter", "dear hiring manager", "dear "]:
            idx = text.lower().find(heading)
            if idx != -1:
                cover_letter = text[idx:].strip()
                break

    return {
        "resume_summary": resume_summary or "",
        "cover_letter": cover_letter or "",
    }


def run_pipeline(job: dict, resume_text: str, user_bio: str) -> dict:
    """Run the full CrewAI pipeline for one job and return structured outputs.

    Args:
        job: Normalized job dict from the JSearch provider (must have ``description``,
             ``company``, and ``title`` keys).
        resume_text: Candidate's resume text.
        user_bio: Short candidate bio for outreach personalization.

    Returns:
        Dictionary containing generated resume summary, cover letter,
        outreach message, and metadata for display/logging.
    """
    job_summary = (job.get("description") or "")[:6000]
    company = job.get("company", "Unknown Company")
    job_title = job.get("title", "Unknown Position")

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
    message_task = create_messaging_task(message_agent, job_summary, company, user_bio)

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
    if not resume_output.strip():
        try:
            with open("data/resume_agent_output.txt", "r", encoding="utf-8") as f:
                resume_output = f.read()
        except FileNotFoundError:
            pass

    parsed = _parse_structured_output(resume_output)
    resume_summary = parsed["resume_summary"]
    cover_letter = parsed["cover_letter"]

    outreach_message = str(message_task.output or result or "")

    # Log and save
    log_application(job_title, company, resume_summary)
    save_cover_letter_file(job_title, cover_letter)

    return {
        "job_title": job_title,
        "company": company,
        "resume_summary": resume_summary,
        "cover_letter": cover_letter,
        "outreach_message": outreach_message,
        "raw_result": str(result or ""),
    }


if __name__ == "__main__":
    # Quick smoke-test: run the pipeline against a hard-coded mock job
    mock_job = {
        "id": "test-001",
        "title": "Data Analyst",
        "company": "Acme Corp",
        "location": "Mumbai, IN",
        "remote": False,
        "description": "We are looking for a data analyst to join our team.",
        "apply_url": "https://example.com/apply",
        "source": "LinkedIn",
        "posted_at": None,
    }
    resume = load_resume()
    result = run_pipeline(mock_job, resume, "I'm a data professional looking for my next challenge.")
    print(result)
