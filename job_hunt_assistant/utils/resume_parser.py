"""Resume parser: extract plain text from PDF or DOCX uploads.

Supported formats
-----------------
- PDF  – via ``pymupdf``
- DOCX – via ``python-docx``

The ``parse_resume`` function also accepts a plain-text string so the Streamlit
"paste your resume" fallback keeps working without any file I/O.
"""

from __future__ import annotations

import io
import json
import re
from typing import Optional

from pydantic import BaseModel, Field

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
_DATE_RANGE = re.compile(
    rf"\b{_MONTH}\s*\d{{4}}\s*[–—-]\s*(?:present|current|{_MONTH}\s*\d{{4}})",
    re.IGNORECASE,
)


def clean_title(raw: str) -> str:
    """Turn an extracted resume line into a short job-board title."""
    title = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw or "")
    title = _DATE_RANGE.sub(" ", title)
    title = re.sub(r"\b(?:19|20)\d{2}\b|\b(?:present|current)\b", " ", title, flags=re.IGNORECASE)
    title = re.split(r"\s[-–—|@,]\s", title)[0]
    title = re.sub(r"\s+", " ", title).strip(" -–—|,")
    return title if 2 <= len(title) <= 40 else ""


def sanitize_titles(titles: list[str], skills: list[str] | None = None) -> list[str]:
    """Deduplicate and constrain profile titles to usable search terms."""
    cleaned = list(dict.fromkeys(title for title in (clean_title(item) for item in titles) if title))
    if not cleaned and skills:
        cleaned = [f"{skills[0]} developer"]
    return cleaned


# ---------------------------------------------------------------------------
# Pydantic profile schema
# ---------------------------------------------------------------------------

class Profile(BaseModel):
    """Structured representation of a candidate's resume extracted by LLM."""

    target_titles: list[str] = Field(
        default_factory=list,
        description="Job titles the candidate is targeting (e.g. 'Data Analyst', 'ML Engineer').",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Technical and soft skills listed in the resume.",
    )
    years_experience: float = Field(
        default=0.0,
        description="Total years of professional experience inferred from the resume.",
    )
    preferred_locations: list[str] = Field(
        default_factory=list,
        description="Cities, regions, or countries where the candidate prefers to work.",
    )


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Return all text from a PDF file given its raw bytes.

    Args:
        file_bytes: Raw PDF bytes (e.g. from ``st.file_uploader``).

    Returns:
        Extracted plain text, pages joined by newlines.
    """
    try:
        import fitz
    except ImportError as exc:
        raise ImportError("PyMuPDF is required for PDF parsing. Run: pip install pymupdf") from exc

    with fitz.open(stream=file_bytes, filetype="pdf") as document:
        text = "\n".join(page.get_text("text") for page in document)
    return re.sub(r"[ \t]+", " ", text).strip()


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Return all text from a DOCX file given its raw bytes.

    Args:
        file_bytes: Raw DOCX bytes (e.g. from ``st.file_uploader``).

    Returns:
        Extracted plain text, paragraphs joined by newlines.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise ImportError(
            "python-docx is required for DOCX parsing. Run: pip install python-docx"
        ) from exc

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs).strip()


def parse_resume(uploaded_file=None, plain_text: Optional[str] = None) -> str:
    """Extract resume text from an uploaded file or a plain-text string.

    Args:
        uploaded_file: A ``streamlit.UploadedFile`` object (PDF or DOCX), or ``None``.
        plain_text: Fallback plain text pasted by the user.

    Returns:
        Extracted resume text as a plain string.

    Raises:
        ValueError: If the uploaded file type is not supported.
    """
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        name = uploaded_file.name.lower()
        if name.endswith(".pdf"):
            return extract_text_from_pdf(file_bytes)
        elif name.endswith(".docx"):
            return extract_text_from_docx(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {uploaded_file.name}. Please upload a PDF or DOCX.")

    if plain_text:
        return plain_text.strip()

    return ""


# ---------------------------------------------------------------------------
# Profile extraction via LLM
# ---------------------------------------------------------------------------

def extract_profile_from_resume(resume_text: str) -> Profile:
    """Use the configured LLM to extract a structured Profile from resume text.

    The function calls the Hugging Face LLM configured in ``utils.config`` and
    asks it to return valid JSON matching the ``Profile`` schema. Falls back to
    a default empty Profile if parsing fails.

    Args:
        resume_text: Plain-text content of the candidate's resume.

    Returns:
        A ``Profile`` instance populated with extracted information.
    """
    from utils.config import HF_API_KEY, HF_MODEL

    truncated = resume_text[:4000]  # Keep within free-tier token budget

    system_prompt = """You are a resume parser. Extract structured information from the resume text and return ONLY a valid JSON object.

Return this exact JSON structure (no extra text, no markdown, just JSON):
{
    "target_titles": ["2-4 standard job-board titles, maximum 4 words each; no dates, companies, or Present"],
  "skills": ["list of technical and soft skills found in the resume"],
    "years_experience": 0.0,
  "preferred_locations": ["list of locations mentioned or inferred from work history"]
}

Rules:
- Choose standard titles such as "AI Engineer" or "Machine Learning Engineer".
- Calculate years_experience from work-history dates; use 0 for freshers.
- Never copy an entire resume line into target_titles."""

    user_prompt = f"Extract profile from this resume:\n\n{truncated}"

    try:
        # Try using the LangChain HuggingFace wrapper that's already installed
        from langchain_huggingface import HuggingFaceEndpoint
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = HuggingFaceEndpoint(
            repo_id=HF_MODEL.replace("huggingface/", ""),
            huggingfacehub_api_token=HF_API_KEY,
            temperature=0.1,
            max_new_tokens=512,
        )

        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        raw_output = llm.invoke(full_prompt)

        # Extract JSON from the response
        json_match = re.search(r"\{.*\}", raw_output, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            profile = Profile(**data)
            profile.target_titles = sanitize_titles(profile.target_titles, profile.skills)
            return profile

    except Exception as e:
        print(f"⚠️  LLM profile extraction failed: {e}. Using heuristic fallback.")
        try:
            import streamlit as st
            st.warning(f"AI extraction failed, using basic parser: {e}")
        except Exception:
            pass

    # Heuristic fallback — simple keyword extraction when LLM is unavailable
    return _heuristic_profile(resume_text)


def _heuristic_profile(resume_text: str) -> Profile:
    """Extract a basic profile using keyword heuristics when LLM is unavailable.

    Args:
        resume_text: Plain resume text.

    Returns:
        A roughly populated ``Profile`` from keyword matching.
    """
    text_lower = resume_text.lower()

    # Common tech skills to detect
    skill_keywords = [
        "python", "sql", "java", "javascript", "typescript", "react", "node.js",
        "machine learning", "deep learning", "data analysis", "excel", "power bi",
        "tableau", "aws", "azure", "gcp", "docker", "kubernetes", "git",
        "project management", "agile", "scrum", "communication", "leadership",
        "c++", "r", "tensorflow", "pytorch", "pandas", "numpy", "spark",
    ]
    found_skills = [s for s in skill_keywords if s in text_lower]

    # Rough experience estimation from year mentions
    years = re.findall(r"(\d+)\+?\s+years?", text_lower)
    max_exp = max((int(y) for y in years), default=0)

    # Infer target titles from section headers / summary
    title_candidates: list[str] = []
    for line in resume_text.splitlines():
        stripped = line.strip()
        if len(stripped) < 60 and any(
            kw in stripped.lower()
            for kw in ["analyst", "engineer", "developer", "manager", "consultant", "scientist", "architect"]
        ):
            title_candidates.append(stripped)

    return Profile(
        target_titles=sanitize_titles(title_candidates, found_skills),
        skills=found_skills,
        years_experience=float(max_exp),
        preferred_locations=[],
    )
