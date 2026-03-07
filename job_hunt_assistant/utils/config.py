import os
from dotenv import load_dotenv

load_dotenv()

USAJOBS_API_KEY = os.getenv("USAJOBS_API_KEY")
USAJOBS_EMAIL = os.getenv("USAJOBS_EMAIL", "your-email@example.com")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Set dummy OPENAI_API_KEY to avoid CrewAI errors if not using OpenAI
if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "NA"