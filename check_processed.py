import json

with open('processed.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Keys: {list(data.keys())}")
print(f"\ntext_preview length: {len(data.get('text_preview', ''))}")
print(f"full_text length: {len(data.get('full_text', ''))}")
print(f"images count: {len(data.get('images', []))}")

if data.get('full_text'):
    print(f"\nFirst 500 chars of full_text:")
    print(data['full_text'][:500])
