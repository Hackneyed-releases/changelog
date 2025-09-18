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
ALT_ORG_NAME = "Realme-SM6375-devs"
AOSP_EXTRA_ORG = "aosp-extra"
TEAMHACKNEYED_ORG = "Teamhackneyed"
MOTO_SM7250_ORG = "moto-sm7250-devs"

TARGET_GITHUB_TOKEN = os.getenv("TARGET_GITHUB_TOKEN")

# Specify the date to filter commits (user-friendly format)
FETCH_DATE = os.getenv("FETCH_DATE")
CURRENT_DATE = os.getenv("CURRENT_DATE")

# Define allowed repository prefixes and exceptions
ALLOWED_REPOS = {
    # Realme sm6375 family
    "android_kernel_realme_sm6375",
    "android_device_realme_sm6375-common",
    "android_device_realme_oscar",
    "android_device_realme_oscarc",
    "android_device_realme_oscarru",
    "android_device_realme_luigi",

    # OnePlus sm6375 family from Teamhackneyed
    "android_kernel_oneplus_sm6375",
    "android_device_oneplus_sm6375-common",
    "android_device_oneplus_oscaro",
    "android_device_oneplus_larry",

    # Motorola sm6375 + denver from Teamhackneyed
    "android_device_motorola_sm6375-common",
    "android_device_motorola_denver",

    # Motorola sm7250 + kiev from moto-sm7250-devs
    "android_device_motorola_sm7250-common",
    "android_device_motorola_kiev",
    "android_kernel_motorola_sm7250",
}
ALLOWED_PREFIXES = ("android_device_lineage_",)

EXCLUDED_KEYWORDS = (
    "samsung", "nvidia", "mediatek", "exynos", "nintendo", "sony",
    "lge", "nothing", "google_pixel", "amlogic", "xiaomi"
)

# These repos should be tracked from aosp-extra, not LineageOS
AOSP_EXTRA_REPOS = {
    "android_packages_apps_Settings",
    "android_frameworks_base",
    "android_system_core",
    "android_bionic",
    "android_packages_services_Telecomm",
    "android_hardware_oplus"
}

def convert_to_iso8601(date_str):
    """Convert a date in DD-MM-YYYY format to ISO 8601 format."""
    return datetime.strptime(date_str, "%d-%m-%Y").isoformat() + "Z"

# Convert to ISO 8601
DATE_FILTER = convert_to_iso8601(FETCH_DATE)
HEADERS = {"Authorization": f"token {TARGET_GITHUB_TOKEN}"}

def fetch_repositories():
    """Fetch all active repositories from all organizations, filtered by rules."""

    def get_repos(org_name):
        url = f"{GITHUB_API_URL}/orgs/{org_name}/repos"
        repos = []
        page = 1

        while True:
            response = requests.get(url, headers=HEADERS, params={"page": page, "per_page": 100})
            if response.status_code == 403:
                logging.error(f"Rate limit exceeded for {org_name}.")
                break
            response.raise_for_status()
            data = response.json()
            if not data:
                break
            repos.extend(repo for repo in data if not repo["archived"])
            page += 1
        return repos

    # Fetch repos from all orgs
    lineage_repos = get_repos(ORG_NAME)
    realme_repos = get_repos(ALT_ORG_NAME)
    aosp_extra_repos = get_repos(AOSP_EXTRA_ORG)
    teamhackneyed_repos = get_repos(TEAMHACKNEYED_ORG)
    moto_sm7250_repos = get_repos(MOTO_SM7250_ORG)

    filtered = []

    # Repos from LineageOS
    for repo in lineage_repos:
        name = repo["name"]
        if name in AOSP_EXTRA_REPOS:
            continue  # Skip: handled under aosp-extra
        if not any(keyword in name for keyword in EXCLUDED_KEYWORDS) and (
            not name.startswith("android_device_") and not name.startswith("android_kernel_")
            or name in ALLOWED_REPOS
            or name.startswith(ALLOWED_PREFIXES)
        ):
            filtered.append((name, ORG_NAME))

    # Repos from Realme-SM6375-devs
    for repo in realme_repos:
        name = repo["name"]
        if name in ALLOWED_REPOS:
            filtered.append((name, ALT_ORG_NAME))

    # Repos from Teamhackneyed
    for repo in teamhackneyed_repos:
        name = repo["name"]
        if name in ALLOWED_REPOS:
            filtered.append((name, TEAMHACKNEYED_ORG))

    # Repos from moto-sm7250-devs
    for repo in moto_sm7250_repos:
        name = repo["name"]
        if name in ALLOWED_REPOS:
            filtered.append((name, MOTO_SM7250_ORG))

    # Repos from aosp-extra
    for repo in aosp_extra_repos:
        name = repo["name"]
        if name in AOSP_EXTRA_REPOS:
            filtered.append((name, AOSP_EXTRA_ORG))

    return filtered

def fetch_commits(args):
    """Fetch all commits from a repo (with org) after a given date."""
    repo_name, org_name = args
    try:
        branch = "lineage-23.0"
        url = f"{GITHUB_API_URL}/repos/{org_name}/{repo_name}/commits"
        params = {"since": DATE_FILTER, "sha": branch, "per_page": 100, "page": 1}
        all_commits = []

        while True:
            response = requests.get(url, headers=HEADERS, params=params)
            if response.status_code == 404:
                return repo_name, []  # Skip silently
            response.raise_for_status()
            commits = response.json()
            if not commits:
                break
            all_commits.extend(commits)
            params["page"] += 1
        return repo_name, all_commits
    except requests.exceptions.RequestException:
        return repo_name, []

def process_repositories(repositories_with_org):
    """Process repositories in parallel to fetch commits and sort them."""
    output = []
    device_kernel_output = []
    other_output = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_commits, repositories_with_org)
        for repo_name, commits in results:
            if commits:
                repo_output = f"* {repo_name}\n"
                for commit in commits:
                    message = commit["commit"]["message"].split("\n")[0]
                    sha = commit["sha"][:7]
                    author = commit["commit"]["author"]["name"]
                    repo_output += f"{sha} {message} [{author}]\n"

                if repo_name.startswith("android_device_") or repo_name.startswith("android_kernel_"):
                    device_kernel_output.append(repo_output.strip())
                else:
                    other_output.append(repo_output.strip())

    other_output.sort()
    return device_kernel_output + other_output

def main():
    try:
        # Fetch repositories
        repositories = fetch_repositories()

        # Process repositories and fetch commits
        output_lines = process_repositories(repositories)

        # Format the final output
        output = f"\n====================\n     {CURRENT_DATE}    \n====================\n\n"
        output += "\n\n".join(output_lines)

        # Save to file
        with open("change.txt", "w") as file:
            file.write(output.strip())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
