import json, urllib.request
url = "https://api.github.com/repos/johnjairod1986/pronogol/actions/workflows/deploy.yml/runs?per_page=3"
req = urllib.request.Request(url, headers={"User-Agent": "Clawbot"})
resp = urllib.request.urlopen(req)
d = json.loads(resp.read())
w = d.get("workflow_runs", [])
for r in w:
    print(f"Status: {r.get('status')} | Conclusion: {r.get('conclusion')} | Created: {r.get('created_at','')[:19]} | Branch: {r.get('head_branch','')}")
if not w:
    print("No workflow runs found")
    print(json.dumps(d, indent=2)[:500])
