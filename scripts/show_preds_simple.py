import json, os
path = r"C:\Users\User\.openclaw\workspace\pronogol\data\predictions_cache.json"
d = json.load(open(path, encoding='utf-8'))

lines = [f"Date: {d['date']} | Predictions: {d['count']}"]
for p in d['predictions']:
    t = p.get('match_time', 0)
    from datetime import datetime
    t_str = datetime.utcfromtimestamp(t).strftime('%H:%M') if t > 1000000000 else '?'
    bp = p['best_pick']
    bps = f"best:{bp['market']}->{bp['prediction']}({bp['confidence']})" if bp.get('confidence') else ''
    line = f"[{p['match_id']}] {t_str} | {p['league']} | {p['home_team']} vs {p['away_team']} | xG:{p['total_xg']} | {bps}"
    lines.append(line)

out = '\n'.join(lines)
with open(r"C:\Users\User\.openclaw\workspace\pronogol\data\_output.txt", 'w', encoding='utf-8') as f:
    f.write(out)
print(out[:2000])
