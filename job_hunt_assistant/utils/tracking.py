"""Utilities for persisting generated application artifacts."""

import csv
import os
import datetime
import re


def save_cover_letter_file(job_title, cover_letter, directory="data/cover_letters"):
    """Save a generated cover letter to a timestamped text file.

    Args:
        job_title: Job title used in the file name.
        cover_letter: Cover letter content to save.
        directory: Target folder for generated cover letters.
    """
    # Replace all unsafe characters with underscore
    job_title = re.sub(r'[\\/*?:"<>|]', "_", job_title)
    os.makedirs(directory, exist_ok=True)
    filename = f"{job_title}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(cover_letter)


def log_application(job_title, agency, resume_summary, filepath="data/applications_log.csv"):
    """Append an application event to the CSV tracking file.

    Args:
        job_title: Applied job title.
        agency: Hiring agency or organization name.
        resume_summary: Generated summary used for the application.
        filepath: CSV path used for application logs.
    """
    # Ensure parent directory exists before opening the CSV file.
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    exists = os.path.exists(filepath)
    with open(filepath, "a", newline='', encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # Write header only when creating a new tracking file.
        if not exists:
            writer.writerow(["Job Title", "Agency", "ResumeSummary", "DateApplied"])
        writer.writerow([
            job_title.strip(),
            agency.strip(),
            # Keep CSV rows compact while still logging useful summary text.
            resume_summary.strip()[:150],
            datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        ])