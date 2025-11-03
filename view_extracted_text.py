import pickle
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Load the FAISS index pickle file
with open('master_index.pkl', 'rb') as f:
    data = pickle.load(f)

print(f"Data type: {type(data)}")
print(f"Data structure: {data if isinstance(data, (list, tuple)) and len(data) < 5 else 'complex'}")

# Extract documents - handle tuple structure
if isinstance(data, tuple):
    docstore = data[0] if len(data) > 0 else None
    if hasattr(docstore, '_dict'):
        docs = docstore._dict
    else:
        docs = docstore
else:
    docs = data.get('docstore', {}).get('_dict', {})

if not docs:
    print("Could not extract documents from pickle file")
    exit(1)

print(f"Total documents: {len(docs)}\n")
print("="*80)

# Show first 3 chunks from handwrite-test
count = 0
for doc_id, doc in docs.items():
    if 'handwrite-test' in doc.metadata.get('source', ''):
        count += 1
        print(f"\n--- Chunk {count} (ID: {doc_id}) ---")
        print(f"Source: {doc.metadata.get('source')}")
        print(f"Chunk: {doc.metadata.get('chunk_id', 'N/A')} of {doc.metadata.get('total_chunks', 'N/A')}")
        print(f"\nContent:\n{doc.page_content[:800]}")
        print("="*80)
        if count >= 3:
            break

print(f"\n\nTotal handwrite-test chunks: {sum(1 for d in docs.values() if 'handwrite-test' in d.metadata.get('source', ''))}")
