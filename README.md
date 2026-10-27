AI Job Hunt Assistant
AI Job Hunt Assistant helps you find, rank, and apply to jobs from LinkedIn, Indeed, Glassdoor, and more — all from one Streamlit interface powered by AI agents.

For each job, the app produces:

a tailored resume summary,
a personalized cover letter,
a concise outreach message (LinkedIn/email),
a downloadable DOCX with all materials,
and an application log entry.
What This Project Does
This project combines:

JSearch API (via OpenWebNinja) for live job postings aggregated from LinkedIn, Indeed, Glassdoor, and 20+ sources,
sentence-transformers (all-MiniLM-L6-v2) for semantic resume ↔ job-description matching,
CrewAI for multi-agent orchestration,
Hugging Face (Llama 3.1) for content generation,
Streamlit for a simple web interface.
The pipeline runs three agents in sequence:

JD Analyst – extracts key requirements from the job description.
Resume & Cover Letter Writer – creates a role-specific resume summary + cover letter (using only content from your actual resume).
Outreach Message Writer – drafts a short networking/recruiter message.
Features
Upload PDF or DOCX resume (or paste plain text).
AI-extracted candidate profile (titles, skills, years of experience, locations) — editable before search.
Search across LinkedIn, Indeed, Glassdoor and more by title + location.
Smart deduplication and 1-hour result cache to protect free-tier quota.
Semantic + skill-overlap ranking with tunable weights.
Ranked job cards with score badges, matched and missing skills.
One-click Apply link (opens the real job site — no auto-apply).
Tailor my resume button: runs the full AI pipeline for that one job.
Validation: flags any skills or numbers that appear in the tailored resume but not in the original.
Download tailored materials as a DOCX file.
Save application history to CSV.
Built-in retry/backoff for API rate-limit errors.
Tech Stack
Layer	Tool
Language	Python 3.11
UI	Streamlit
Orchestration	CrewAI
LLM Provider	Hugging Face (Llama 3.1)
Job Source	JSearch API (LinkedIn, Indeed, Glassdoor…)
Matching	sentence-transformers (all-MiniLM-L6-v2)
Resume parsing	pypdf, python-docx
Schema validation	Pydantic
Utilities	python-dotenv, requests, numpy
Prerequisites
Before running the app, you need:

Python 3.11 installed
JSearch API key — free at https://app.openwebninja.com/api/jsearch
Hugging Face API token — from https://huggingface.co/settings/tokens
Installation (Local)
From the project root:

# 1) Clone repo
git clone https://github.com/<your-username>/Job_Hunt_Assistent.git
cd Job_Hunt_Assistent/job_hunt_assistant

# 2) Create & activate virtual environment
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

# 3) Install dependencies
pip install -r requirements.txt
Configuration
Create a local .env file in job_hunt_assistant/.

Copy .env.example and fill in your real keys:

JSEARCH_API_KEY="your_jsearch_api_key_here"
HF_API_KEY="your_hf_api_token_here"
HF_MODEL="huggingface/meta-llama/Llama-3.1-8B-Instruct"
OPENAI_API_KEY="NA"
Notes
HF_MODEL is configurable. Default: huggingface/meta-llama/Llama-3.1-8B-Instruct.
If .env is missing in cloud, the app reads st.secrets.
How to Run
streamlit run streamlit_app.py
Then open the local URL shown in terminal (usually http://localhost:8501).

How to Use
Upload your PDF/DOCX resume (or paste plain text).
Review the extracted profile and adjust titles, skills, and locations.
Set your location and filters in the sidebar.
Click Search Jobs.
Browse the ranked job cards with match scores.
Click Apply to go to the real job site, or Tailor my resume to run the AI pipeline.
Download the generated DOCX with your tailored materials.
Deployment (Streamlit Community Cloud)
Push your code to GitHub.
In Streamlit Cloud, create a new app pointing to:
Repository: your fork/repo
Branch: main
Main file path: job_hunt_assistant/streamlit_app.py
In app Secrets, set:
JSEARCH_API_KEY = "your_jsearch_api_key_here"
HF_API_KEY      = "your_hf_api_token_here"
HF_MODEL        = "huggingface/meta-llama/Llama-3.1-8B-Instruct"
OPENAI_API_KEY  = "NA"
Save secrets and reboot the app.
Project Structure
job_hunt_assistant/
├── streamlit_app.py          ← Streamlit UI (upload → profile → search → rank → tailor)
├── orchestrator.py           ← Multi-agent pipeline runner
├── requirements.txt
├── README.md
├── providers/
│   ├── __init__.py
│   └── jsearch_api.py        ← JSearch client + normalize()
├── services/
│   ├── __init__.py
│   ├── search.py             ← Multi-query search, dedup, cache
│   └── matcher.py            ← Hard filters + semantic + skill ranking
├── agents/
│   ├── jd_analyst.py
│   ├── resume_cl_agent.py
│   └── messaging_agent.py
├── utils/
│   ├── config.py             ← Centralized secrets loader
│   ├── resume_parser.py      ← PDF/DOCX parser + Profile schema
│   ├── validator.py          ← "No invented skills" post-generation check
│   ├── exporter.py           ← DOCX export helper
│   └── tracking.py           ← CSV application log
├── data/
│   ├── applications_log.csv
│   ├── report.md
│   ├── sample_resume.txt
│   └── cover_letters/
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
Output Files
Application log CSV: data/applications_log.csv
Generated cover letters: data/cover_letters/
Analysis reports: data/report.md
Troubleshooting
1) JSEARCH_API_KEY is not set
Get your free key at https://app.openwebninja.com/api/jsearch
Add it to .env or Streamlit secrets.
2) 429 RESOURCE_EXHAUSTED (quota/rate limits)
Wait for retry window and try again.
The app retries automatically with exponential backoff.
Search results are cached for 1 hour to reduce calls.
3) Empty search results
Check your API key is valid.
Try broadening the query (fewer skills, wider location).
Try changing Date posted to "month".
4) 404 model not found (HuggingFace)
Set HF_MODEL to a currently supported model.
5) App works locally but fails in Streamlit Cloud
Re-check Streamlit secrets match .env.example key names.
Reboot app after changing secrets.
Security Best Practices
Never commit real API keys.
Keep .env and .streamlit/secrets.toml out of git (both are in .gitignore).
Rotate keys immediately if accidentally exposed.
License
This project is for educational and portfolio use. Add a formal license file if you plan to open-source it publicly.
