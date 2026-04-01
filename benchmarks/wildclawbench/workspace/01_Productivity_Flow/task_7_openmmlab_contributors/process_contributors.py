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
    max_retries = 3
    while True:
        url = f"https://api.github.com/repos/{ORG}/{repo}/contributors?per_page=100&page={page}"
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if not data:
                        return contributors_data
                    for item in data:
                        if item['type'] == 'User':
                            login = item['login']
                            contributions = item['contributions']
                            if contributions >= 30:
                                contributors_data[login] = contributions
                    if len(data) < 100:
                        return contributors_data
                    page += 1
                    break
                elif response.status_code == 403:
                    print("Rate limit hit or forbidden. Sleeping...")
                    time.sleep(60)
                else:
                    print(f"Error fetching {repo}: {response.status_code}")
                    return contributors_data
            except Exception as e:
                print(f"Attempt {attempt+1} failed for {repo}: {e}")
                time.sleep(2)
                if attempt == max_retries - 1:
                    return contributors_data
        time.sleep(0.5)
    return contributors_data

def main():
    with open(REPOS_FILE, 'r') as f:
        repos = [line.strip() for line in f if line.strip()]

    user_projects = {}

    for repo in repos:
        print(f"Processing {repo}...")
        repo_contributors = get_contributors(repo)
        for user, count in repo_contributors.items():
            if user not in user_projects:
                user_projects[user] = {}
            user_projects[user][repo] = count

    with open(OUTPUT_FILE, 'w') as f:
        for user, projects in user_projects.items():
            if projects:
                line = json.dumps({"user": user, "project": projects})
                f.write(line + '\n')

if __name__ == "__main__":
    main()
