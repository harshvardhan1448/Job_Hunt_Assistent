import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

def _get_secret(key, default=None):
    value = os.getenv(key)
    if value:
        return value
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default


USAJOBS_API_KEY = _get_secret("USAJOBS_API_KEY")
USAJOBS_EMAIL = _get_secret("USAJOBS_EMAIL", "your-email@example.com")
GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")
GEMINI_MODEL = _get_secret("GEMINI_MODEL", "gemini/gemini-2.5-flash")

if GEMINI_API_KEY:
    if not os.getenv("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
    if not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

# Set dummy OPENAI_API_KEY to avoid CrewAI errors if not using OpenAI
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY", "NA")
if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY