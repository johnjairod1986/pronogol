"""Format predictions for Telegram message"""
import json
from datetime import datetime, timezone, timedelta

path = r"C:\Users\User\.openclaw\workspace\pronogol\data\predictions_cache.json"
d = json.load(open(path, encoding='utf-8'))
bogota_tz = timedelta(hours=-5)

lines = [
    "PRONOGOL — 8 Jul 2026",
    f"{d['count']} partidos analizados",
    "=" * 30
]

for p in d['predictions']:
    t = p.get('match_time', 0)
    if t > 1000000000:
        dt = datetime.fromtimestamp(t, tz=timezone.utc) + bogota_tz
        t_str = dt.strftime('%H:%M')
    else:
        t_str = '?'
    
    home = p['home_team']
    away = p['away_team']
    league = p['league']
    xg = p['total_xg']
    
    bp = p.get('best_pick', {})
    if bp.get('confidence', 0) >= 7:
        star = "MEGA" if bp['confidence'] >= 9 else "TOP"
        bp_str = f"  {star}: {bp['prediction']} (conf:{bp['confidence']})"
    elif bp.get('confidence', 0) >= 6:
        bp_str = f"  Pick: {bp['prediction']} (conf:{bp['confidence']})"
    else:
        bp_str = ""
    
    mw = p['markets']['match_winner']
    dc = p['markets']['double_chance']
    ou = p['markets']['over_under_2.5']
    
    lines.append(f"\n[{t_str}] {league}")
    lines.append(f"{home} vs {away}")
    lines.append(f"xG:{xg}")
    if bp_str:
        lines.append(bp_str)
    lines.append(f"1X2: {mw['home_pct']}/{mw['draw_pct']}/{mw['away_pct']} | DC: {dc['prediction']}")
    lines.append(f"O/U2.5: {ou['prediction']} | BTTS: {p['markets']['btts']['prediction']}")

lines.append("\n=" * 30)
lines.append("pronogol.app (local: puerto 8000)")

result = "\n".join(lines)

# Save for display
with open(r"C:\Users\User\.openclaw\workspace\pronogol\data\_tg_message.txt", "w", encoding='utf-8') as f:
    f.write(result)

print(result)
