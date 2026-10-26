@echo off
cd /d "C:\Users\Rajput Shubham\OneDrive\Desktop\JobHuntAssistent\job_hunt_assistant"
"C:\Users\Rajput Shubham\OneDrive\Desktop\JobHuntAssistent\.venv\Scripts\pip.exe" install pytest --quiet
"C:\Users\Rajput Shubham\OneDrive\Desktop\JobHuntAssistent\.venv\Scripts\python.exe" -m pytest tests/test_migration.py -v --tb=short
