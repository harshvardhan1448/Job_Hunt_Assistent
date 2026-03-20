"""Outreach message agent and task definitions."""

from crewai import Agent, Task, LLM
from utils.config import GEMINI_API_KEY, GEMINI_MODEL


def _get_llm():
    """Build the LLM configuration used by the outreach agent."""
    return LLM(
        model=GEMINI_MODEL,
        api_key=GEMINI_API_KEY,
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
    return Task(
        description=f"""
        Write a concise and compelling outreach message that the candidate could send to someone at {agency_name}, expressing interest in the job described below.

        --- Job Summary ---
        {job_summary}

        --- Candidate Bio ---
        {user_bio}

        The message should be friendly, professional, and under 150 words. Tailor it for a platform like LinkedIn or email.
        """,
        expected_output="A short outreach message under 150 words, tailored for LinkedIn or email, that is professional and expresses interest in the job at the given agency.",
        agent=agent,
    )