from langchain_community.vectorstores import FAISS
from langchain_aws import BedrockEmbeddings
import os

os.environ['AWS_REGION'] = 'us-east-1'

embeddings = BedrockEmbeddings(model_id="cohere.embed-multilingual-v3", region_name="us-east-1")
index = FAISS.load_local('.', embeddings, allow_dangerous_deserialization=True)

print(f"Total vectors: {index.index.ntotal}")

# Search for Edge-To-Cloud
results = index.similarity_search("Edge-To-Cloud", k=10)

edge_docs = [r for r in results if 'Edge-To-Cloud' in r.metadata.get('source', '')]
print(f"\nEdge-To-Cloud documents found: {len(edge_docs)}")

for i, doc in enumerate(edge_docs[:3]):
    doc_type = doc.metadata.get('type', 'text')
    print(f"\n{i+1}. Type: {doc_type}, Length: {len(doc.page_content)}")
    print(f"   Preview: {doc.page_content[:150]}")
