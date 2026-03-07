import requests
from utils.config import USAJOBS_API_KEY, USAJOBS_EMAIL


def fetch_usajobs(keyword, location="remote", results_per_page=5):
    """Search USAJobs and return a list of SearchResultItems."""
    if not USAJOBS_API_KEY:
        raise ValueError(
            "USAJOBS_API_KEY is not set. "
            "Add it to your .env file or Streamlit secrets."
        )

    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": USAJOBS_EMAIL,
        "Authorization-Key": USAJOBS_API_KEY,
    }

    params = {
        "Keyword": keyword,
        "LocationName": location,
        "ResultsPerPage": results_per_page,
    }

    url = "https://data.usajobs.gov/api/search"
    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()

    return response.json().get("SearchResult", {}).get("SearchResultItems", [])


if __name__ == "__main__":
    jobs = fetch_usajobs("business analyst", location="New York", results_per_page=10)
    for job in jobs:
        title = job["MatchedObjectDescriptor"]["PositionTitle"]
        agency = job["MatchedObjectDescriptor"]["OrganizationName"]
        print(f"{title} at {agency}")