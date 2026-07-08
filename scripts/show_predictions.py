"""Show predictions"""
import json

d = json.load(open(r"C:\Users\User\.openclaw\workspace\pronogol\data\predictions_cache.json"))
print(f"Date: {d['date']} | Generated: {d['generated_at']} | Total: {d['count']} predictions\n")

for p in d['predictions']:
    from datetime import datetime
    t = p.get('match_time', 0)
    if t:
        t_str = datetime.utcfromtimestamp(t).strftime('%H:%M') if t > 1000000000 else f"unix:{t}"
    else:
        t_str = "?"

    bp = p['best_pick']
    bp_str = f"⭐ {bp['market']}->{bp['prediction']} (conf:{bp['confidence']})" if bp['confidence'] else "—"
    
    print(f"[{p['match_id']}] {t_str} | {p['league']}")
    print(f"  {p['home_team']} vs {p['away_team']}")
    print(f"  xG:{p['total_xg']} | {bp_str}")
    print()
