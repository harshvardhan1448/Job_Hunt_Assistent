"""JD Analyst agent and task definitions."""

from crewai import Agent, Task, LLM
from utils.config import GEMINI_API_KEY, GEMINI_MODEL


def _get_llm():
    """Build the LLM configuration used by the JD analyst."""
    return LLM(
        model=GEMINI_MODEL,
        api_key=GEMINI_API_KEY,
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
    return Task(
        description=f"""
        Analyze the following USAJobs job posting and extract:
        - A summary of the role
        - Key skills required
        - Any specific qualifications or eligibility
        \n\nJob Description:\n{job_description}
        """,
        expected_output="A structured markdown summary containing sections for Qualifications, Required Skills, and Responsibilities.",
        agent=agent,
        output_file="data/report.md",
    )