from crewai import Crew, Process
from agents.jd_analyst import get_jd_analyst_agent, create_jd_analysis_task
from agents.resume_cl_agent import get_resume_cl_agent, create_resume_cl_task
from agents.messaging_agent import get_messaging_agent, create_messaging_task
from usajobs_api import fetch_usajobs
from utils.tracking import log_application, save_cover_letter_file

def load_resume(path="data/sample_resume.txt"):
    with open(path, "r") as file:
        return file.read()

def extract_between_markers(text, start, end=None):
    try:
        start_idx = text.index(start) + len(start)
        end_idx = text.index(end, start_idx) if end else len(text)
        return text[start_idx:end_idx].strip()
    except ValueError:
        return "Not found"

def run_pipeline(job_data, resume_text, user_bio):
    job_summary = job_data['UserArea']['Details']['JobSummary']
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

    # Run the crew
    crew = Crew(
        agents=[jd_agent, resume_agent, message_agent],
        tasks=[jd_task, resume_task, message_task],
        process=Process.sequential
    )

    # Extract key outputs
    resume_output = str(resume_task.output)
    resume_summary = extract_between_markers(resume_output, "<<RESUME_SUMMARY>>", "<<COVER_LETTER>>")
    cover_letter = extract_between_markers(resume_output, "<<COVER_LETTER>>")

    # Log and save
    log_application(job_title, agency_name, resume_summary)
    save_cover_letter_file(job_title, cover_letter)

    result = crew.kickoff()

    print("\n=== FINAL OUTPUT ===\n")
    print(result)

    return result

if __name__ == "__main__":
    run_pipeline()