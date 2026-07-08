"""Get detailed action failure info - no emoji"""
import json, urllib.request

url = "https://api.github.com/repos/johnjairod1986/pronogol/actions/runs/28946016492/jobs"
req = urllib.request.Request(url, headers={"User-Agent": "Clawbot"})
resp = urllib.request.urlopen(req)
d = json.loads(resp.read())

out_lines = []
for job in d.get("jobs", []):
    out_lines.append(f"Job: {job['name']} | Conclusion: {job['conclusion']}")
    for step in job.get("steps", []):
        conclusion = step.get("conclusion", "")
        if conclusion in ("failure", "cancelled"):
            name = step['name'].replace('\U0001f511', '[lock]').replace('\U0001f4e5', '[download]')
            name = name.replace('\U0001f4e6', '[box]').replace('\U0001f680', '[rocket]').replace('\U0001f4c1', '[folder]')
            name = name.replace('\U0001f9f0', '[puzzle]').replace('\u26a1', '[zap]').replace('\U0001f3f7', '[tag]')
            name = name.replace('\U0001f6a7', '[construction]')
            out_lines.append(f"  * FAILED: {name}")
        if step.get("conclusion") == "failure":
            log_url = f"https://api.github.com/repos/johnjairod1986/pronogol/actions/jobs/{job['id']}/logs"
            out_lines.append(f"  * Log: {log_url}")

with open(r"C:\Users\User\.openclaw\workspace\pronogol\data\_actions_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(out_lines))

print("\n".join(out_lines)[:3000])
