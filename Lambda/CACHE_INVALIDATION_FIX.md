# Query Cache Invalidation Fix

## Problem
The query cache stores responses for 24 hours but doesn't invalidate when documents are added or deleted, causing stale responses.

### Example Scenario (Bug):
1. User asks: "What is the pricing?" → No documents → Response: "I have no information"
2. System caches this response for 24 hours
3. User uploads pricing document
4. User asks: "What is the pricing?" again → **Returns cached "I have no information"** ❌

## Root Cause
Cache key is based only on normalized query text (hash of query), not on document index state:
```python
query_hash = str(hash(normalized_query))
cache_key = f"query-cache/{query_hash}.json"
```

When documents change, the cache should be invalidated but wasn't.

## Solution
Clear all query cache entries when documents are added or deleted.

### Changes Made

#### 1. agent_executor.py - Clear cache on document deletion
When a document is deleted, clear the entire query cache before rebuilding the index.

**Location:** `handle_delete_file_api()` function
**Action:** Added cache clearing before index rebuild

#### 2. worker.py - Clear cache on document upload  
When a new document is successfully indexed, clear the entire query cache.

**Location:** After master index upload in `process_message()` function
**Action:** Added cache clearing after index upload

## How It Works Now

### Upload Flow:
1. User uploads document
2. Document is processed and indexed
3. Master index is updated
4. **Query cache is cleared** ✅
5. Next query will get fresh results with new document

### Delete Flow:
1. User deletes document
2. **Query cache is cleared** ✅
3. Master index is rebuilt without deleted document
4. Next query will get fresh results without deleted document

## Performance Impact
- Minimal: Cache clearing is a simple S3 batch delete (max 1000 objects)
- Only happens when documents change (not on every query)
- First query after document change will be slower (cache miss), subsequent queries will be fast (new cache)

## Alternative Approaches Considered

### 1. Include document list in cache key (Rejected)
```python
# Would need to hash all document names
doc_list = get_all_document_names()
cache_key = f"query-cache/{hash(query + str(doc_list))}.json"
```
**Why rejected:** Expensive to list all documents on every query

### 2. Store document version in cache (Rejected)
```python
cache_data = {
    "response": answer,
    "doc_version": get_index_timestamp()
}
```
**Why rejected:** Still requires checking version on every query

### 3. Clear entire cache on change (Chosen) ✅
**Why chosen:** 
- Simple and reliable
- No performance impact on queries
- Only affects cache on document changes (rare)
- Guarantees fresh results after changes

## Testing
To verify the fix works:
1. Ask a question → Get "no information" response
2. Upload relevant document
3. Ask same question → Should get answer from new document (not cached "no information")

## Deployment
Both Lambda functions need to be redeployed:
```bash
cd Lambda
.\agent_cache_build_push.bat
.\ingestion_cache_build_push.bat
```
