# AI Job Hunt Assistant

AI Job Hunt Assistant helps you search USAJobs postings and generate application-ready content using a multi-agent workflow.

For each selected job, the app can produce:
- an updated resume summary,
- a tailored cover letter,
- a concise outreach message (LinkedIn/email),
- and an application log entry.

---

## What This Project Does

This project combines:
- **USAJobs API** for live federal job postings,
- **CrewAI** for agent orchestration,
- **Google Gemini** for content generation,
- **Streamlit** for a simple web interface.

The pipeline runs three agents in sequence:
1. **JD Analyst** – extracts key requirements from the job summary.
2. **Resume & Cover Letter Writer** – creates a role-specific resume summary + cover letter.
3. **Outreach Message Writer** – drafts a short networking/recruiter message.

---

## Features

- Search USAJobs by keyword and location.
- Select one or multiple job postings.
- Generate outputs per job:
  - Updated Resume Summary
  - Cover Letter
  - Outreach Message
- Save application history to CSV.
- Save generated cover letters to files.
- Built-in retry/backoff behavior for API rate-limit errors.

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.11 |
| UI | Streamlit |
| Orchestration | CrewAI |
| LLM Provider | Google Gemini API |
| Job Source | USAJobs API |
| Utilities | python-dotenv, requests |

---

## Prerequisites

Before running the app, make sure you have:

1. **Python 3.11** installed
2. **USAJobs API key** from https://developer.usajobs.gov/APIRequest/Index
3. **USAJobs registered email** (the one tied to your API request)
4. **Gemini API key** from Google AI Studio / Gemini API

---

## Installation (Local)

From the project root:

```bash
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
```

---

## Configuration

Create a local `.env` file in `job_hunt_assistant/`.

You can copy the values from `.env.example` and fill your real keys:

```env
USAJOBS_API_KEY="your_usajobs_api_key_here"
USAJOBS_EMAIL="your-email@example.com"
GEMINI_API_KEY="your_gemini_api_key_here"
GEMINI_MODEL="gemini/gemini-2.5-flash"
OPENAI_API_KEY="NA"
```

### Notes
- `GEMINI_MODEL` is configurable.
- Current default in code: `gemini/gemini-2.5-flash`.
- If `.env` is missing in cloud, the app also reads `st.secrets`.

---

## How to Run

```bash
streamlit run streamlit_app.py
```

Then open the local URL shown in terminal (usually `http://localhost:8501`).

---

## How to Use

1. Enter **Job Keyword** and **Location**.
2. Paste your **Resume**.
3. Add a short **Bio** for outreach tone.
4. Click **Search Jobs**.
5. Select one or more jobs.
6. Click **Apply to Selected Jobs**.

For each selected job, the app displays:
- **Updated Resume Summary**
- **Cover Letter**
- **Outreach Message**

---

## Deployment (Streamlit Community Cloud)

1. Push your code to GitHub.
2. In Streamlit Cloud, create a new app pointing to:
   - Repository: your fork/repo
   - Branch: `main`
   - Main file path: `job_hunt_assistant/streamlit_app.py`
3. In app **Secrets**, set:

```toml
USAJOBS_API_KEY = "your_usajobs_api_key_here"
USAJOBS_EMAIL   = "your-email@example.com"
GEMINI_API_KEY  = "your_gemini_api_key_here"
GEMINI_MODEL    = "gemini/gemini-2.5-flash"
OPENAI_API_KEY  = "NA"
```

4. Save secrets and reboot the app.

---

## Output Files

- Application log CSV: `data/applications_log.csv`
- Generated cover letters: `data/cover_letters/`

---

## Troubleshooting

### 1) `429 RESOURCE_EXHAUSTED` (quota/rate limits)
- Wait for retry window and try again.
- Process fewer jobs at once.
- Ensure billing is enabled on the Google project for your key.

### 2) `404 model not found`
- Your model may be deprecated for new users.
- Set `GEMINI_MODEL` to a currently supported model (default here: `gemini/gemini-2.5-flash`).

### 3) USAJobs request failures
- Confirm `USAJOBS_API_KEY` and `USAJOBS_EMAIL` are correct.
- Verify email matches the one registered with USAJobs.

### 4) App works locally but fails in Streamlit Cloud
- Re-check Streamlit secrets.
- Reboot app after changing secrets.

---

## Project Structure

```
job_hunt_assistant/
├── streamlit_app.py
├── orchestrator.py
├── usajobs_api.py
├── requirements.txt
├── Readme.md
├── agents/
│   ├── jd_analyst.py
│   ├── resume_cl_agent.py
│   └── messaging_agent.py
├── utils/
│   ├── config.py
│   └── tracking.py
├── data/
│   ├── applications_log.csv
│   ├── report.md
│   ├── sample_resume.txt
│   └── cover_letters/
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

---

## Security Best Practices

- Never commit real API keys.
- Keep `.env` and `.streamlit/secrets.toml` out of git.
- Rotate keys immediately if accidentally exposed.

---

## License

This project is for educational and portfolio use. Add a formal license file if you plan to open-source it publicly.
