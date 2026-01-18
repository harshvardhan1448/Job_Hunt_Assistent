from crewai import Agent, Task
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.config import GEMINI_API_KEY

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash-001",
    temperature=0.5,
    google_api_key=GEMINI_API_KEY
)

def get_messaging_agent():
    return Agent(
        role="Outreach Message Writer",
        goal="Draft personalized messages for job outreach",
        backstory="You're a professional career coach skilled in writing effective cold emails and outreach messages for job seekers in tech and government.",
        llm=llm,
        verbose=True
    )

def create_messaging_task(agent, job_summary, agency_name, user_bio="I'm a data professional passionate about public service."):
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
        agent=agent
    )