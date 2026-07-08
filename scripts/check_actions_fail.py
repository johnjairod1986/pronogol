"""Check why GitHub Actions is failing"""
import json, urllib.request

# Get the latest failed run details
url = "https://api.github.com/repos/johnjairod1986/pronogol/actions/workflows/deploy.yml/runs?per_page=1&status=completed&conclusion=failure"
req = urllib.request.Request(url, headers={"User-Agent": "Clawbot"})
resp = urllib.request.urlopen(req)
d = json.loads(resp.read())
runs = d.get("workflow_runs", [])
if runs:
    run = runs[0]
    print(f"Run ID: {run['id']}")
    print(f"Branch: {run['head_branch']}")
    print(f"Commit: {run['head_sha']}")
    print(f"URL: {run['html_url']}")
    print(f"Created: {run['created_at']}")
    print(f"Conclusion: {run['conclusion']}")
    print()

    # Get the jobs for this run
    jobs_url = run["jobs_url"]
    req2 = urllib.request.Request(jobs_url, headers={"User-Agent": "Clawbot"})
    resp2 = urllib.request.urlopen(req2)
    jobs = json.loads(resp2.read())
    for job in jobs.get("jobs", []):
        print(f"Job: {job['name']}")
        print(f"  Status: {job['status']}")
        print(f"  Conclusion: {job['conclusion']}")
        for step in job.get("steps", []):
            if step.get("conclusion") == "failure":
                print(f"  Failed step: {step['name']}")
