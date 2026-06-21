"""Outreach message agent and task definitions."""

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
    """Build the LLM configuration used by the outreach agent."""
    return LLM(
        model=HF_MODEL,
        api_key=HF_API_KEY,
        temperature=0.5,
    )


def get_messaging_agent():
    """Create and return the outreach message writing agent."""
    return Agent(
        role="Outreach Message Writer",
        goal="Draft personalized messages for job outreach",
        backstory="You're a professional career coach skilled in writing effective cold emails and outreach messages for job seekers in tech and government.",
        llm=_get_llm(),
        verbose=True,
    )


def create_messaging_task(
    agent,
    job_summary,
    agency_name,
    user_bio="I'm a data professional passionate about public service.",
):
    """Create a task that drafts a short outreach message.

    Args:
        agent: CrewAI agent handling outreach writing.
        job_summary: Summary of the target role.
        agency_name: Hiring agency/organization name.
        user_bio: Candidate bio used to personalize tone.
    """
    # Truncate inputs to avoid token limits
    truncated_summary = job_summary[:1500] if job_summary else "No job summary"
    truncated_bio = user_bio[:300] if user_bio else "Data professional"
    
    return Task(
        description=f"""Draft a personalized outreach message for {agency_name} expressing interest in this position.

Agency: {agency_name}
Job Summary: {truncated_summary}...
Candidate Background: {truncated_bio}

Write a professional, friendly outreach message under 150 words suitable for LinkedIn or email that:
- Expresses genuine interest in the role
- Highlights relevant experience
- Shows knowledge of the agency/position
- Includes a call to action""",
        expected_output="A professional outreach message under 150 words suitable for LinkedIn or email",
        agent=agent,
    )