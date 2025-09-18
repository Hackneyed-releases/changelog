#!/usr/bin/env python3

import os
import requests
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# --- GitHub / org settings ---
GITHUB_API_URL = "https://api.github.com"
ORG_NAME = "LineageOS"
ALT_ORG_NAME = "Realme-SM6375-devs"
AOSP_EXTRA_ORG = "aosp-extra"
TEAMHACKNEYED_ORG = "Teamhackneyed"
MOTO_SM7250_ORG = "moto-sm7250-devs"

TARGET_GITHUB_TOKEN = os.getenv("TARGET_GITHUB_TOKEN")

# Workflow inputs
FETCH_DATE = os.getenv("FETCH_DATE")
CURRENT_DATE = os.getenv("CURRENT_DATE")
CODENAME = os.getenv("GITHUB_INPUT_CODENAME")

# Allowed prefixes and exclusions
ALLOWED_PREFIXES = ("android_device_lineage_",)
EXCLUDED_KEYWORDS = (
    "samsung", "nvidia", "mediatek", "exynos", "nintendo", "sony",
    "lge", "nothing", "google_pixel", "amlogic", "xiaomi"
)

# AOSP extra repos
AOSP_EXTRA_REPOS = {
    "android_packages_apps_Settings",
    "android_frameworks_base",
    "android_system_core",
    "android_bionic",
    "android_packages_services_Telecomm",
    "android_hardware_oplus"
}

# Exact mapping: codename -> org -> repos
CODENAME_TO_ORG_REPOS = {
    "larry.txt": {
        TEAMHACKNEYED_ORG: [
            "android_device_oneplus_larry",
            "android_device_oneplus_sm6375-common",
            "android_kernel_oneplus_sm6375"
        ]
    },
    "oscaro.txt": {
        TEAMHACKNEYED_ORG: [
            "android_device_oneplus_oscaro",
            "android_device_oneplus_sm6375-common",
            "android_kernel_oneplus_sm6375"
        ]
    },
    "denver.txt": {
        TEAMHACKNEYED_ORG: [
            "android_device_motorola_denver",
            "android_device_motorola_sm6375-common"
        ]
    },
    "kiev.txt": {
        MOTO_SM7250_ORG: [
            "android_device_motorola_kiev",
            "android_device_motorola_sm7250-common",
            "android_kernel_motorola_sm7250"
        ]
    },
    "oscar.txt": {
        ALT_ORG_NAME: [
            "android_device_realme_oscar",
            "android_device_realme_sm6375-common",
            "android_kernel_realme_sm6375"
        ]
    },
    "luigi.txt": {
        ALT_ORG_NAME: [
            "android_device_realme_luigi",
            "android_device_realme_sm6375-common",
            "android_kernel_realme_sm6375"
        ]
    },
    "oscarc.txt": {
        ALT_ORG_NAME: [
            "android_device_realme_oscarc",
            "android_device_realme_sm6375-common",
            "android_kernel_realme_sm6375"
        ]
    },
    "oscarru.txt": {
        ALT_ORG_NAME: [
            "android_device_realme_oscarru",
            "android_device_realme_sm6375-common",
            "android_kernel_realme_sm6375"
        ]
    },
}

HEADERS = {"Authorization": f"token {TARGET_GITHUB_TOKEN}"} if TARGET_GITHUB_TOKEN else {}

def convert_to_iso8601(date_str):
    if not date_str:
        raise ValueError("FETCH_DATE is not set.")
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").isoformat() + "Z"
    except ValueError:
        raise ValueError("FETCH_DATE must be in DD-MM-YYYY format (e.g., 01-09-2025)")

DATE_FILTER = convert_to_iso8601(FETCH_DATE)

def get_repos(org_name):
    """Fetch all non-archived repos from a GitHub org."""
    url = f"{GITHUB_API_URL}/orgs/{org_name}/repos"
    repos = []
    page = 1
    while True:
        resp = requests.get(url, headers=HEADERS, params={"page": page, "per_page": 100})
        if resp.status_code == 403:
            logging.error(f"Rate limit exceeded or access denied for {org_name}")
            break
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        repos.extend(r for r in data if not r.get("archived", False))
        page += 1
    return repos

def fetch_repositories():
    """Return list of (repo_name, org_name) to fetch commits from."""
    filtered = []

    # LineageOS repos
    lineage_repos = get_repos(ORG_NAME)
    for repo in lineage_repos:
        name = repo["name"]
        if name in AOSP_EXTRA_REPOS:
            continue
        if any(kw in name for kw in EXCLUDED_KEYWORDS):
            continue
        if not name.startswith("android_device_") and not name.startswith("android_kernel_"):
            filtered.append((name, ORG_NAME))
        elif name.startswith(ALLOWED_PREFIXES):
            filtered.append((name, ORG_NAME))

    # AOSP extra
    aosp_extra_repos = get_repos(AOSP_EXTRA_ORG)
    for repo in aosp_extra_repos:
        if repo["name"] in AOSP_EXTRA_REPOS:
            filtered.append((repo["name"], AOSP_EXTRA_ORG))

    # Device-specific repos: only exact mapping
    org_repo_map = CODENAME_TO_ORG_REPOS.get(CODENAME, {})
    for org, repos in org_repo_map.items():
        for repo_name in repos:
            filtered.append((repo_name, org))

    return filtered

def fetch_commits(args):
    repo_name, org_name = args
    try:
        branch = "lineage-23.0"
        url = f"{GITHUB_API_URL}/repos/{org_name}/{repo_name}/commits"
        params = {"since": DATE_FILTER, "sha": branch, "per_page": 100, "page": 1}
        all_commits = []
        while True:
            resp = requests.get(url, headers=HEADERS, params=params)
            if resp.status_code == 404:
                return repo_name, []
            resp.raise_for_status()
            commits = resp.json()
            if not commits:
                break
            all_commits.extend(commits)
            params["page"] += 1
        return repo_name, all_commits
    except requests.exceptions.RequestException as exc:
        logging.error(f"Failed to fetch commits for {org_name}/{repo_name}: {exc}")
        return repo_name, []

def process_repositories(repositories_with_org):
    device_kernel_output = []
    other_output = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_commits, repositories_with_org)
        for repo_name, commits in results:
            if not commits:
                continue
            repo_output = f"* {repo_name}\n"
            for commit in commits:
                msg = commit["commit"]["message"].split("\n")[0]
                sha = commit.get("sha", "")[:7]
                author = commit["commit"]["author"].get("name", "unknown")
                repo_output += f"{sha} {msg} [{author}]\n"
            if repo_name.startswith("android_device_") or repo_name.startswith("android_kernel_"):
                device_kernel_output.append(repo_output.strip())
            else:
                other_output.append(repo_output.strip())

    other_output.sort()
    return device_kernel_output + other_output

def main():
    try:
        repositories = fetch_repositories()
        output_lines = process_repositories(repositories)

        header = f"\n====================\n     {CURRENT_DATE}    \n====================\n\n"
        output = header + "\n\n".join(output_lines)

        with open("change.txt", "w") as f:
            f.write(output.strip())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
