"""Test fetching match details for xG data"""
import json, urllib.request

KEY = "1abc780710040e043b218e141869d4b664aac69ed8b97ff98dc96da9ca420f72"
match_ids = [8554440, 8554434, 8554577, 8554417, 8554438, 8554598, 8554627, 8469754]

for mid in match_ids:
    url = f"https://api.football-data-api.com/match?match_id={mid}&include=stats&key={KEY}"
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        d = json.loads(resp.read())
        if d.get("success") == 1:
            data = d.get("data", {})
            home = data.get("home_name", data.get("team_a_name", "?"))
            away = data.get("away_name", data.get("team_b_name", "?"))
            xg_a = data.get("team_a_xg_prematch") or data.get("team_a_xg", 0)
            xg_b = data.get("team_b_xg_prematch") or data.get("team_b_xg", 0)
            total_xg = round(float(xg_a or 0) + float(xg_b or 0), 2)
            print(f"[{mid}] {home} vs {away}: xG: {xg_a} + {xg_b} = {total_xg}")
        else:
            print(f"[{mid}] API returned success=0: {d.get('message', '')}")
    except Exception as e:
        print(f"[{mid}] Error: {e}")
