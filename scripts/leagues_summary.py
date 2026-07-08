import json
from collections import Counter

with open(r'C:\Users\User\.openclaw\workspace\pronogol\data\predictions_cache.json', encoding='utf-8') as f:
    data = json.load(f)

leagues = Counter()
for p in data['predictions']:
    leagues[p['league']] += 1

for league, count in leagues.most_common():
    print(f'{league}: {count}')
print()
print(f'Total predictions: {len(data["predictions"])}')
print(f'Total leagues: {len(leagues)}')

# Show sample prediction structure
p = data['predictions'][0]
print(f'\nSample keys: {list(p.keys())}')
m = p.get('markets', {})
for mk, mv in m.items():
    if isinstance(mv, dict):
        print(f'  market.{mk}: {mv}')
    else:
        print(f'  market.{mk}: {mv}')
