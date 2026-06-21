"""JD Analyst agent and task definitions."""

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

from crewai import Agent, Task, LLM
from utils.config import HF_API_KEY, HF_MODEL


def _get_llm():
    """Build the LLM configuration used by the JD analyst."""
    return LLM(
        model=HF_MODEL,
        api_key=HF_API_KEY,
        temperature=0.2,
    )


def get_jd_analyst_agent():
    """Create and return the JD analysis agent."""
    return Agent(
        role="JD Analyst",
        goal="Understand and summarize government job postings",
        backstory="You're an expert in job market analysis with a focus on US federal job listings.",
        llm=_get_llm(),
        verbose=True,
    )


def create_jd_analysis_task(agent, job_description):
    """Create the JD analysis task for a given job description.

    Args:
        agent: CrewAI agent responsible for analysis.
        job_description: Raw job summary text from USAJobs.
    """
    # Truncate job description to avoid token limits (keep first 2500 chars)
    truncated_description = job_description[:2500] if job_description else "No job description provided"
    
    return Task(
        description=f"""Analyze this USAJobs job posting and extract key information in structured format:

Job Description:
{truncated_description}...

Provide a structured analysis with these sections:
- ROLE SUMMARY
- KEY SKILLS REQUIRED
- QUALIFICATIONS AND ELIGIBILITY
- RESPONSIBILITIES""",
        expected_output="Structured analysis with clear sections for Role Summary, Key Skills, Qualifications, and Responsibilities",
        agent=agent,
        output_file="data/report.md",
    )