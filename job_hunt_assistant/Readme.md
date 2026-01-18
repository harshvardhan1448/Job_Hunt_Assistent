# AI Job Hunt Assistant

An end‑to‑end, AI‑powered assistant that helps job seekers automatically:

* **Analyse** USAJobs postings with a Gemini‑based LLM.
* **Tailor** resumes and generate cover letters that match each posting.
* **Draft** concise outreach messages for LinkedIn or email.
* **Track** applications in a CSV log.

### Tech Stack
- **Python** (3.13)  
- **CrewAI** – multi‑agent orchestration  
- **LangChain** + **Google Gemini 1.5‑flash‑001** (LLM)  
- **Streamlit** – interactive UI  
- **USAJobs API** – live job search  

### Quick start
```powershell
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py