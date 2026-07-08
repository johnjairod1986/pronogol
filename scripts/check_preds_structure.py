import json

with open(r'C:\Users\User\.openclaw\workspace\pronogol\data\predictions_cache.json', encoding='utf-8') as f:
    data = json.load(f)

p = data['predictions'][0]
print('Keys:', list(p.keys()))
print()
for k, v in p.items():
    if isinstance(v, dict):
        print(f'{k}: (dict)')
        for sk, sv in v.items():
            print(f'  {sk}: {sv}')
    else:
        print(f'{k}: {v}')
    print()
print(f'Total predictions: {len(data["predictions"])}')
