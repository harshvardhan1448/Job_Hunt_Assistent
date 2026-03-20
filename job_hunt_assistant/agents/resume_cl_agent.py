"""Resume summary and cover-letter agent/task definitions."""

from crewai import Agent, Task, LLM
from utils.config import GEMINI_API_KEY, GEMINI_MODEL


def _get_llm():
    """Build the LLM configuration used by the resume agent."""
    return LLM(
        model=GEMINI_MODEL,
        api_key=GEMINI_API_KEY,
        temperature=0.3,
    )


def get_resume_cl_agent():
    """Create and return the resume + cover-letter writing agent."""
    return Agent(
        role="Resume & Cover Letter Writer",
        goal="Customize application materials to match job descriptions",
        backstory="You're an expert in professional writing and tailoring resumes for job applications, especially in government and tech roles.",
        llm=_get_llm(),
        verbose=True,
    )


def create_resume_cl_task(agent, job_summary, resume_text):
    """Create a task that generates resume summary and cover letter.

    Args:
        agent: CrewAI agent that writes resume artifacts.
        job_summary: Job context extracted from the posting.
        resume_text: Candidate's current resume text.
    """
    return Task(
        description=f"""
        Based on the job summary below, tailor the candidate's resume summary and generate a personalized cover letter.

        --- Job Summary ---
        {job_summary}

        --- Resume Text ---
        {resume_text}

        Your output should include:
        1. Updated professional summary for resume
        2. A personalized cover letter suitable for a government job
        """,
        agent=agent,
        expected_output="""
        <<RESUME_SUMMARY>>
        [Your tailored 3-5 sentence resume summary here]

        <<COVER_LETTER>>
        [Your personalized cover letter here]
        """,
        output_file="data/resume_agent_output.txt",
    )