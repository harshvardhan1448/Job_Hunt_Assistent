import csv
import os
import datetime
import re

def save_cover_letter_file(job_title, cover_letter, directory="data/cover_letters"):
    # Replace all unsafe characters with underscore
    job_title = re.sub(r'[\\/*?:"<>|]', "_", job_title)
    os.makedirs(directory, exist_ok=True)
    filename = f"{job_title}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = os.path.join(directory, filename)
    with open(filepath, "w") as f:
        f.write(cover_letter)

def log_application(job_title, agency, resume_summary, filepath="data/applications_log.csv"):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    exists = os.path.exists(filepath)
    with open(filepath, "a", newline='') as csvfile:
        writer = csv.writer(csvfile)
        if not exists:
            writer.writerow(["Job Title", "Agency", "ResumeSummary", "DateApplied"])
        writer.writerow([
            job_title.strip(),
            agency.strip(),
            resume_summary.strip()[:150],
            datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        ])