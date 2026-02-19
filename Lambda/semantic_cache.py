"""
Semantic Cache Module - FAISS-based vector store
"""

import json
import time
import os
import tempfile
from typing import Optional, Dict, Any

# Global cache
_cache_index = None
_cache_metadata = []
_cache_loaded = False


class SemanticCache:
    """
    FAISS-based semantic cache for fast similarity search.
    Single vector store file instead of individual JSON files.
    """
    
    def __init__(self, s3_client, bucket: str, threshold: float = 0.85):
        self.s3_client = s3_client
        self.bucket = bucket
        self.threshold = threshold
        self.cache_key = "query-cache/cache_index"
        self.ttl_hours = 12
        self._load_cache()
    
    def _get_embeddings_client(self):
        """Get Bedrock embeddings client."""
        from langchain_aws import BedrockEmbeddings
        region = os.getenv("AWS_REGION")
        model_id = os.getenv("EMBEDDINGS_MODEL_ID", "cohere.embed-multilingual-v3")
        return BedrockEmbeddings(model_id=model_id, region_name=region)
    
    def _load_cache(self):
        """Load FAISS index from S3."""
        global _cache_index, _cache_metadata, _cache_loaded
        
        if _cache_loaded:
            return
        
        try:
            from langchain_community.vectorstores import FAISS
            from langchain.docstore.document import Document
            
            # Download FAISS index files
            with tempfile.TemporaryDirectory() as tmpdir:
                index_file = os.path.join(tmpdir, "index.faiss")
                pkl_file = os.path.join(tmpdir, "index.pkl")
                
                try:
                    self.s3_client.download_file(self.bucket, f"{self.cache_key}.faiss", index_file)
                    self.s3_client.download_file(self.bucket, f"{self.cache_key}.pkl", pkl_file)
                    
                    embeddings = self._get_embeddings_client()
                    _cache_index = FAISS.load_local(tmpdir, embeddings, allow_dangerous_deserialization=True)
                    
                    # Load metadata
                    metadata_obj = self.s3_client.get_object(Bucket=self.bucket, Key=f"{self.cache_key}_metadata.json")
                    _cache_metadata = json.loads(metadata_obj['Body'].read().decode('utf-8'))
                    
                    # Filter expired entries
                    current_time = time.time()
                    _cache_metadata = [m for m in _cache_metadata if (current_time - m['timestamp']) / 3600 <= self.ttl_hours]
                    
                except:
                    # No cache exists yet
                    _cache_index = None
                    _cache_metadata = []
            
            _cache_loaded = True
        except:
            _cache_index = None
            _cache_metadata = []
            _cache_loaded = True
    
    def search_similar(self, query: str, session_id: str) -> Optional[Dict[str, Any]]:
        """Search for similar cached query using FAISS."""
        global _cache_index, _cache_metadata
        
        if not _cache_index or not _cache_metadata:
            return None
        
        try:
            # Search FAISS index
            results = _cache_index.similarity_search_with_score(query, k=1)
            
            if not results:
                return None
            
            doc, distance = results[0]
            
            # Convert distance to similarity (lower distance = higher similarity)
            # FAISS returns L2 distance, convert to cosine similarity approximation
            similarity = 1 / (1 + distance)
            
            if similarity >= self.threshold:
                # Find metadata by matching query
                for meta in _cache_metadata:
                    if meta['query'] == doc.page_content:
                        return {
                            'response': meta['response'],
                            'images': meta.get('images', []),
                            'similarity': similarity,
                            'cached': True,
                            'original_query': meta['query']
                        }
            
            return None
        
        except Exception as e:
            return None
    
    def store(self, query: str, response: str, images: list, session_id: str):
        """Store query in FAISS cache."""
        global _cache_index, _cache_metadata
        
        try:
            from langchain_community.vectorstores import FAISS
            from langchain.docstore.document import Document
            
            embeddings = self._get_embeddings_client()
            
            # Create document for new query
            new_doc = Document(page_content=query)
            
            # Add to metadata
            new_metadata = {
                'query': query,
                'response': response,
                'images': images,
                'timestamp': int(time.time())
            }
            
            if _cache_index is None:
                # Create new index
                _cache_index = FAISS.from_documents([new_doc], embeddings)
                _cache_metadata = [new_metadata]
            else:
                # Add to existing index
                new_index = FAISS.from_documents([new_doc], embeddings)
                _cache_index.merge_from(new_index)
                _cache_metadata.append(new_metadata)
            
            # Save to S3
            with tempfile.TemporaryDirectory() as tmpdir:
                _cache_index.save_local(tmpdir)
                
                self.s3_client.upload_file(
                    os.path.join(tmpdir, "index.faiss"),
                    self.bucket,
                    f"{self.cache_key}.faiss"
                )
                self.s3_client.upload_file(
                    os.path.join(tmpdir, "index.pkl"),
                    self.bucket,
                    f"{self.cache_key}.pkl"
                )
                
                # Save metadata
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=f"{self.cache_key}_metadata.json",
                    Body=json.dumps(_cache_metadata),
                    ContentType='application/json'
                )
        
        except Exception as e:
            pass
