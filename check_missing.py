import boto3, json, pickle, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s3 = boto3.client('s3')

# Get all processed docs
print("=== ALL PROCESSED DOCS (recent) ===")
paginator = s3.get_paginator('list_objects_v2')
processed = []
for page in paginator.paginate(Bucket='pdfquery-rag-documents-production', Prefix='processed/'):
    for obj in page['Contents']:
        if '1777787' in obj['Key']:
            processed.append((obj['Key'], obj['LastModified']))
            print(obj['LastModified'], obj['Key'])

# Get FAISS index sources
data = pickle.load(open('d:/Projects/LEIDOS/index.pkl', 'rb'))
item = data[0] if isinstance(data, tuple) else data
store = item._dict if hasattr(item, '_dict') else {}
sources = set(v.metadata.get('source', '') for v in store.values() if hasattr(v, 'metadata'))

print("\n=== MISSING FROM INDEX ===")
for key, ts in processed:
    # Extract base name same way rebuild_master_index does
    base = key.split('/')[-1]  # strip processed/
    if base.endswith('.json'):
        base = base[:-5]  # strip .json
    # Strip timestamp prefix
    if '_' in base:
        parts = base.split('_', 1)
        if parts[0].isdigit():
            base = parts[1]
    print(f"base_name: {base!r}")
    print(f"  in index: {base in sources}")
    # Also check with .docx stripped
    base_no_ext = base.rsplit('.', 1)[0] if '.' in base else base
    print(f"  base_no_ext: {base_no_ext!r} -> in index: {base_no_ext in sources}")
