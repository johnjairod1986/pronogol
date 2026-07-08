"""Test FootyStats API connection"""
import requests, json

KEY = "1abc780710040e043b218e141869d4b664aac69ed8b97ff98dc96da9ca420f72"
URL = "https://api.football-data-api.com"

# Test 1: Today's matches
print("=== Todays Matches ===")
r = requests.get(f"{URL}/todays-matches?include=all&key={KEY}", timeout=15)
data = r.json()
print(f"Success: {data.get('success')}")
print(f"Message: {data.get('message', '')}")
matches = data.get("data", [])
print(f"Matches found: {len(matches)}")

if matches:
    comps = {}
    for m in matches:
        cid = m.get("competition_id", 0)
        name = m.get("name", m.get("league_name", "?"))
        if cid not in comps:
            comps[cid] = name
    
    print(f"\nCompetitions ({len(comps)}):")
    for cid, name in sorted(comps.items()):
        count = sum(1 for m in matches if m.get("competition_id") == cid)
        print(f"  {cid}: {name} ({count} matches)")
    
    print(f"\nAll matches:")
    for m in matches:
        home = m.get("home_name", "?")
        away = m.get("away_name", "?")
        cid = m.get("competition_id", 0)
        mid = m.get("id", 0)
        print(f"  [{mid}] {home} vs {away} (comp:{cid})")
else:
    print("No matches found or API issue")
    print(json.dumps(data, indent=2)[:500])
