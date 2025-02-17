#!/usr/bin/env python3

import os
import requests
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    level=logging.ERROR,  # Only show errors in the console
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# GitHub API settings
GITHUB_API_URL = "https://api.github.com"
ORG_NAME = "LineageOS"
TARGET_GITHUB_TOKEN = os.getenv("TARGET_GITHUB_TOKEN")

# Specify the date to filter commits (user-friendly format)
FETCH_DATE = os.getenv("FETCH_DATE")
CURRENT_DATE = os.getenv("CURRENT_DATE") 

# Define allowed repository prefixes and exceptions
ALLOWED_REPOS = {
    "android_kernel_realme_sm6375",
    "android_device_realme_sm6375-common",
    "android_device_realme_oscar",
    "android_device_realme_luigi",
    "android_kernel_oneplus_sm6375",
    "android_device_oneplus_sm6375-common",
    "android_device_oneplus_oscao",
    "android_device_oneplus_larry",
    "android_device_motorola_sm7250-common",
    "android_device_motorola_kiev",
    "android_kernel_motorola_sm7250",
}
ALLOWED_PREFIXES = ("android_device_lineage_",)

def convert_to_iso8601(date_str):
    """Convert a date in DD-MM-YYYY format to ISO 8601 format."""
    return datetime.strptime(date_str, "%d-%m-%Y").isoformat() + "Z"

# Convert to ISO 8601
DATE_FILTER = convert_to_iso8601(FETCH_DATE)
HEADERS = {"Authorization": f"token {TARGET_GITHUB_TOKEN}"}

EXCLUDED_KEYWORDS = ("samsung", "nvidia", "mediatek", "exynos", "nintendo", "sony", "lge", "nothing", "google_pixel", "amlogic", "xiaomi")  # Add more if needed

def fetch_repositories(org_name):
    """Fetch all active repositories for an organization, filtered by rules."""
    url = f"{GITHUB_API_URL}/orgs/{org_name}/repos"
    repos = []
    page = 1

    while True:
        response = requests.get(url, headers=HEADERS, params={"page": page, "per_page": 100})
        
        if response.status_code == 403:
            logging.error("Rate limit exceeded. Check API usage or token permissions.")
            break
        
        response.raise_for_status()
        data = response.json()
        
        if not data:
            break
        
        repos.extend(repo["name"] for repo in data if not repo["archived"])
        page += 1

    # Filter repositories
    filtered_repos = [
        repo for repo in repos
        if not any(keyword in repo for keyword in EXCLUDED_KEYWORDS)  # Exclude unwanted keywords
        and (
            not repo.startswith("android_device_") and not repo.startswith("android_kernel_")
            or repo in ALLOWED_REPOS
            or repo.startswith(ALLOWED_PREFIXES)
        )
    ]
    return filtered_repos

def fetch_commits(repo_name):
    """Fetch all commits from the 'lineage-22.1' branch of a repository after a given date with pagination."""
    try:
        branch = "lineage-22.1"
        url = f"{GITHUB_API_URL}/repos/{ORG_NAME}/{repo_name}/commits"
        params = {"since": DATE_FILTER, "sha": branch, "per_page": 100, "page": 1}
        all_commits = []

        while True:
            response = requests.get(url, headers=HEADERS, params=params)
            
            if response.status_code == 404:  # Branch not found
                return repo_name, []  # Skip silently
            
            response.raise_for_status()
            commits = response.json()
            
            if not commits:
                break  # Exit the loop if no more commits are returned
            
            all_commits.extend(commits)
            params["page"] += 1  # Move to the next page
        
        return repo_name, all_commits

    except requests.exceptions.RequestException:
        return repo_name, []  # Skip repositories with errors silently

def process_repositories(repositories):
    """Process repositories in parallel to fetch commits and sort them."""
    output = []
    device_kernel_output = []
    other_output = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_commits, repositories)
        for repo_name, commits in results:
            if commits:
                repo_output = f"* {repo_name}\n"
                for commit in commits:
                    message = commit["commit"]["message"].split("\n")[0]
                    sha = commit["sha"][:7]
                    author = commit["commit"]["author"]["name"]
                    repo_output += f"{sha} {message} [{author}]\n"

                # Prioritize device and kernel repositories
                if repo_name.startswith("android_device_") or repo_name.startswith("android_kernel_"):
                    device_kernel_output.append(repo_output.strip())
                else:
                    other_output.append(repo_output.strip())

    # Sort other repositories alphabetically
    other_output.sort()

    # Combine outputs with prioritized device and kernel repos on top
    return device_kernel_output + other_output

def main():
    try:
        # Fetch repositories
        repositories = fetch_repositories(ORG_NAME)
        
        # Process repositories and fetch commits
        output_lines = process_repositories(repositories)
        
        # Format the final output
        output = f"\n====================\n     {CURRENT_DATE}    \n====================\n\n"
        output += "\n\n".join(output_lines)
        
        # Save to file
        with open("change.txt", "w") as file:
            file.write(output.strip())
    except Exception as e:
        # Print only errors
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
