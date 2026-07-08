"""Get detailed action failure info"""
import json, urllib.request

url = "https://api.github.com/repos/johnjairod1986/pronogol/actions/runs/28946016492/jobs"
req = urllib.request.Request(url, headers={"User-Agent": "Clawbot"})
resp = urllib.request.urlopen(req)
d = json.loads(resp.read())

for job in d.get("jobs", []):
    print(f"Job: {job['name']} | Conclusion: {job['conclusion']}")
    for step in job.get("steps", []):
        conclusion = step.get("conclusion", "")
        if conclusion in ("failure", "cancelled"):
            print(f"  FAILED: {step['name']}")
    # Print the raw log from the failed step
    for step in job.get("steps", []):
        if step.get("conclusion") == "failure":
            url2 = f"https://api.github.com/repos/johnjairod1986/pronogol/actions/jobs/{job['id']}/logs"
            print(f"\n  Log URL: {url2}")
