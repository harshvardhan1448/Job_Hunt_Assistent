# AI Job Hunt Assistant

An end-to-end, AI-powered assistant that helps job seekers automatically:

* **Analyse** USAJobs postings with a Gemini-based LLM.
* **Tailor** resumes and generate cover letters that match each posting.
* **Draft** concise outreach messages for LinkedIn or email.
* **Track** applications in a CSV log.

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Language | Python 3.11+ |
| Multi-agent orchestration | CrewAI |
| LLM | Google Gemini 1.5 Flash (via LangChain) |
| UI | Streamlit |
| Job data | USAJobs API |

---

## Prerequisites

1. **Python 3.11+** installed
2. **USAJobs API key** - request one at <https://developer.usajobs.gov/APIRequest/Index>
3. **Google Gemini API key** - get one at <https://aistudio.google.com/app/apikey>

---

## Local Setup

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/job-hunt-assistant.git
cd job-hunt-assistant/job_hunt_assistant

# 2. Create a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create your .env file from the template
cp .env.example .env
# Then open .env and paste your real API keys

# 5. Run the app
streamlit run streamlit_app.py
```

---

## Deploy to Streamlit Community Cloud (Free)

1. **Push your code to GitHub** (make sure `.env` is in `.gitignore`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **"New app"** and select your repo, branch, and main file: `job_hunt_assistant/streamlit_app.py`.
4. Under **Advanced settings > Secrets**, add your keys in TOML format:
   ```toml
   USAJOBS_API_KEY = "your_key"
   USAJOBS_EMAIL   = "you@example.com"
   GEMINI_API_KEY  = "your_key"
   OPENAI_API_KEY  = "NA"
   ```
5. Click **Deploy** - your app will be live in ~2 minutes.

---

## Project Structure

```
job_hunt_assistant/
├── streamlit_app.py        # Streamlit UI
├── orchestrator.py         # CrewAI pipeline (agents -> tasks -> kickoff)
├── usajobs_api.py          # USAJobs REST client
├── agents/
│   ├── jd_analyst.py       # Job-description analysis agent
│   ├── resume_cl_agent.py  # Resume & cover-letter agent
│   └── messaging_agent.py  # Outreach-message agent
├── utils/
│   ├── config.py           # Env-var loader
│   └── tracking.py         # CSV logger & cover-letter saver
├── data/                   # Generated outputs (gitignored)
├── .env.example            # Template for local secrets
├── .streamlit/
│   ├── config.toml         # Streamlit theme & server config
│   └── secrets.toml.example
├── requirements.txt
└── README.md
```

---

## License

MIT
