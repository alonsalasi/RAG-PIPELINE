# Cache Invalidation Race Condition Fix

## Issue
The LLM agent was returning "I don't have information" for documents that were successfully uploaded and indexed. This was caused by a **race condition** in the query cache invalidation logic.

## Root Cause
The query cache was being cleared **AFTER** the new index was uploaded to S3:

```python
# OLD CODE (BUGGY)
s3_client.upload_file(master_index_path, BUCKET, "vector_store/master/index.faiss")  # 1. Upload new index
s3_client.upload_file(master_pkl_path, BUCKET, "vector_store/master/index.pkl")

# 2. Clear cache (TOO LATE!)
cache_response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix="query-cache/")
s3_client.delete_objects(...)
```

### The Race Condition Window
1. Document is uploaded and processed
2. New index is uploaded to S3 ✅
3. **User queries immediately** ⚠️
4. Agent finds no cached response
5. Agent searches the OLD index (not yet reloaded)
6. Returns "I don't have information"
7. **This stale response gets cached** ❌
8. Cache is cleared (but the stale response was just re-cached!)

## The Fix
Move cache clearing to happen **BEFORE** index upload:

```python
# NEW CODE (FIXED)
# 1. Clear cache FIRST
logger.info("Clearing query cache before index upload...")
cache_response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix="query-cache/")
s3_client.delete_objects(...)

# 2. Upload new index
s3_client.upload_file(master_index_path, BUCKET, "vector_store/master/index.faiss")
s3_client.upload_file(master_pkl_path, BUCKET, "vector_store/master/index.pkl")
```

### Why This Works
- Cache is cleared before any new queries can happen
- Even if a user queries during index upload, they won't get a cached stale response
- The worst case is a cache miss (which triggers a fresh search)
- Once the new index is uploaded, all queries will use the updated index

## Files Changed
1. **worker.py** (line ~1095): Moved cache clearing before index upload
2. **CACHE_INVALIDATION_FIX.md**: Updated documentation with race condition details

## Testing
To verify the fix:
1. Ask a question about a document that doesn't exist → Get "no information"
2. Upload that document
3. Wait for processing to complete
4. Ask the same question immediately → Should get answer from new document (not cached "no information")

## Deployment
Redeploy the ingestion Lambda:
```bash
cd Lambda
.\ingestion_cache_build_push.bat
```

## Additional Notes
- This fix also applies to document deletion (cache cleared before index rebuild)
- The agent executor already had proper cache clearing on delete
- This was a timing issue, not a logic issue
