import boto3, json, pickle, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s3 = boto3.client('s3')

# 1. Check the processed JSON for the FINOPS document
print("=== PROCESSED JSON ===")
paginator = s3.get_paginator('list_objects_v2')
for page in paginator.paginate(Bucket='pdfquery-rag-documents-production', Prefix='processed/1777787219'):
    for obj in page['Contents']:
        key = obj['Key']
        print("Key:", key)
        resp = s3.get_object(Bucket='pdfquery-rag-documents-production', Key=key)
        data = json.loads(resp['Body'].read().decode('utf-8'))
        print("source_file:", repr(data.get('source_file', '')))
        print("full_text_len:", len(data.get('full_text', data.get('text_preview', ''))))
        print("keys:", list(data.keys())[:10])

# 2. Check what Hebrew sources are in the FAISS index
print("\n=== FAISS INDEX SOURCES (Hebrew) ===")
data = pickle.load(open('d:/Projects/LEIDOS/index.pkl', 'rb'))
item = data[0] if isinstance(data, tuple) else data
store = item._dict if hasattr(item, '_dict') else {}
sources = sorted(set(v.metadata.get('source', '') for v in store.values() if hasattr(v, 'metadata')))
hebrew_sources = [s for s in sources if any(ord(c) > 127 for c in s)]
print("Total sources:", len(sources))
print("Hebrew sources:")
for s in hebrew_sources:
    print(" -", s)
