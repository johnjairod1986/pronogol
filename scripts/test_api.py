"""Test the predictions endpoint"""
import json, urllib.request

# Test predictions
url = "http://localhost:8000/api/v2/predictions/today"
resp = urllib.request.urlopen(url)
d = json.loads(resp.read())

print(f"Predictions count: {d.get('count', 0)}")
print(f"Date: {d.get('date', '?')}")
print()

for p in d.get('predictions', []):
    print(f"{p['league']}")
    print(f"  {p['home_team']} vs {p['away_team']}")
    print(f"  xG: {p['total_xg']}")
    bp = p.get('best_pick', {})
    if bp.get('confidence'):
        print(f"  Best: {bp['market']} -> {bp['prediction']} (conf: {bp['confidence']})")
    mw = p['markets']['match_winner']
    print(f"  1X2: {mw['home_pct']}% / {mw['draw_pct']}% / {mw['away_pct']}%")
    print()
