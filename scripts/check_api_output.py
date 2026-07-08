"""Check what the predictions API returns"""
import json
from datetime import datetime, timezone, timedelta

with open(r"C:\Users\User\.openclaw\workspace\pronogol\data\predictions_cache.json", encoding="utf-8") as f:
    d = json.load(f)

print(f"Generated: {d.get('generated_at', '?')}")
print(f"Total predictions: {d.get('count', 0)}")
print(f"Total matches fetched: {d.get('total_matches_fetched', 0)}")
print()

# Show dates
dates = d.get("dates", {})
print(f"Dates ({len(dates)}):")
for dt_str, info in sorted(dates.items()):
    bogota = timezone(timedelta(hours=-5))
    dt = datetime.strptime(dt_str, "%Y-%m-%d")
    weekday = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"][dt.weekday()]
    print(f"  {dt_str} ({weekday}): {info['count']} matches | {', '.join(info['leagues'][:5])}{'...' if len(info['leagues'])>5 else ''}")

print()
# Leagues
leagues = set()
for p in d.get("predictions", []):
    leagues.add(p["league"])
print(f"Leagues ({len(leagues)}):")
for l in sorted(leagues):
    count = sum(1 for p in d["predictions"] if p["league"] == l)
    print(f"  {l}: {count} picks")

print()
# Top picks across all dates
by_confidence = sorted(d["predictions"], key=lambda x: x["best_pick"]["confidence"], reverse=True)
print("Top 10 picks (all dates):")
for p in by_confidence[:10]:
    bp = p["best_pick"]
    if bp.get("confidence", 0) >= 6:
        print(f"  [{p['date']}] {p['home_team']} vs {p['away_team']}")
        print(f"    {bp['market']} -> {bp['prediction']} (conf:{bp['confidence']}) | xG:{p['total_xg']}")
    else:
        print(f"  [{p['date']}] {p['home_team']} vs {p['away_team']} - no best pick")
