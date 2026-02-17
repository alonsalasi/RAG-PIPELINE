import pickle

with open('index.pkl', 'rb') as f:
    index_tuple = pickle.load(f)

# FAISS index structure: (faiss_index, docstore, index_to_docstore_id)
faiss_index, docstore, id_map = index_tuple

# Count documents by source
sources = {}
edge_chunks = []

for doc_id, doc in docstore._dict.items():
    source = doc.metadata.get('source', 'unknown')
    sources[source] = sources.get(source, 0) + 1
    
    if 'Edge-To-Cloud' in source:
        content_preview = doc.page_content[:200]
        doc_type = doc.metadata.get('type', 'text')
        edge_chunks.append((doc_type, len(doc.page_content), content_preview))

print(f"Total documents in index: {len(data['docstore']['_dict'])}")
print(f"\nEdge-To-Cloud chunks: {sources.get('21-428700-Edge-To-Cloud-FactSheet-Print', 0)}")

if edge_chunks:
    print(f"\nEdge-To-Cloud content breakdown:")
    text_chunks = [c for c in edge_chunks if c[0] == 'text']
    image_chunks = [c for c in edge_chunks if c[0] == 'image']
    print(f"  Text chunks: {len(text_chunks)}")
    print(f"  Image chunks: {len(image_chunks)}")
    
    if text_chunks:
        print(f"\n  First text chunk ({text_chunks[0][1]} chars):")
        print(f"    {text_chunks[0][2]}")
