"""Resume summary and cover-letter agent/task definitions."""

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
    """Build the LLM configuration used by the resume agent."""
    return LLM(
        model=HF_MODEL,
        api_key=HF_API_KEY,
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
    # Truncate job summary to first 3000 chars to avoid token limits
    truncated_job_summary = job_summary[:3000] if job_summary else "No summary available"
    
    # Truncate resume to first 2000 chars
    truncated_resume = resume_text[:2000] if resume_text else "No resume provided"
    
    return Task(
        description=f"""You MUST generate output in the exact format below with the markers.

Job Summary: {truncated_job_summary}...

Resume: {truncated_resume}...

TASKS:
1. Create a 3-5 sentence tailored professional resume summary based on the job
2. Create a personalized cover letter for this government position

OUTPUT FORMAT (use these exact markers):
<<RESUME_SUMMARY>>
[Your 3-5 sentence tailored resume summary here]

<<COVER_LETTER>>
[Your personalized cover letter here]
""",
        agent=agent,
        expected_output="""Output with markers:
<<RESUME_SUMMARY>>
[3-5 sentence tailored resume summary]

<<COVER_LETTER>>
[Personalized cover letter]""",
        output_file="data/resume_agent_output.txt",
    )