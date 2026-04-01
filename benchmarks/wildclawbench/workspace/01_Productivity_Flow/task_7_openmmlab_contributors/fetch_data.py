import requests
import json
import time
import os

ORG = "open-mmlab"
REPOS_FILE = "results/repos.txt"
OUTPUT_FILE = "results/contributors.jsonl"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

headers = {}
if GITHUB_TOKEN:
    headers["Authorization"] = f"token {GITHUB_TOKEN}"

def get_contributors(repo):
    contributors_data = {}
    page = 1
    while True:
        url = f"https://api.github.com/repos/{ORG}/{repo}/contributors?per_page=100&page={page}"
        try:
            response = requests.get(url, headers=headers, timeout=20)
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                for item in data:
                    if item['type'] == 'User':
                        login = item['login']
                        contributions = item['contributions']
                        if contributions >= 30:
                            contributors_data[login] = contributions
                if len(data) < 100:
                    break
                page += 1
            elif response.status_code == 403:
                # Rate limit or other issues, just stop for this repo to save time
                print(f"Rate limit hit for {repo}")
                break
            else:
                print(f"Error {response.status_code} for {repo}")
                break
        except Exception as e:
            print(f"Exception for {repo}: {e}")
            break
        time.sleep(0.1)
    return contributors_data

def main():
    if not os.path.exists(REPOS_FILE):
        return
    with open(REPOS_FILE, 'r') as f:
        repos = [line.strip() for line in f if line.strip()]

    user_projects = {}
    for repo in repos:
        print(f"Fetching {repo}...")
        repo_contributors = get_contributors(repo)
        for user, count in repo_contributors.items():
            if user not in user_projects:
                user_projects[user] = {}
            user_projects[user][repo] = count

    with open(OUTPUT_FILE, 'w') as f:
        for user, projects in user_projects.items():
            if projects:
                f.write(json.dumps({"user": user, "project": projects}) + '\n')

if __name__ == "__main__":
    main()
