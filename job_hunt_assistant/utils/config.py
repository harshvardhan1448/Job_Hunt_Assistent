"""Centralized configuration loader for local and Streamlit deployments.

This module reads environment variables from a project-level `.env` file and
falls back to Streamlit secrets when running on Streamlit Cloud.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _get_secret(key, default=None):
    """Return a configuration value from env vars or Streamlit secrets.

    Args:
        key: Secret key name to lookup.
        default: Value to return if the key does not exist.

    Returns:
        The resolved secret value, or `default`.
    """
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
HF_API_KEY = _get_secret("HF_API_KEY")
HF_MODEL = _get_secret("HF_MODEL", "huggingface/meta-llama/Llama-3.1-8B-Instruct")

# Set Hugging Face API key for LangChain
if HF_API_KEY:
    if not os.getenv("HUGGINGFACEHUB_API_TOKEN"):
        os.environ["HUGGINGFACEHUB_API_TOKEN"] = HF_API_KEY

# Set dummy OPENAI_API_KEY to avoid CrewAI errors if not using OpenAI
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY", "NA")
if not os.getenv("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY