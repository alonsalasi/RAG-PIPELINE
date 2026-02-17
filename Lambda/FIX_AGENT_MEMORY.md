# Fix: Agent "Forgets" Old Files (20-30 minutes after upload)

## Problem
When users ask about files uploaded 20-30 minutes ago, the agent responds as if the file doesn't exist, even though the file was successfully processed and indexed.

## Root Cause
The agent Lambda function caches the FAISS vector index in memory for performance. However, the cache invalidation logic had a bug:

1. When checking if the cached index is stale, it compared `_index_s3_timestamp` with the S3 file's `LastModified` timestamp
2. If `_index_s3_timestamp` was `None` (which can happen after Lambda cold starts or certain error conditions), the comparison would fail
3. The agent would continue using the stale cached index that doesn't include recently uploaded files

## Solution Applied

### Fix 1: Improved Timestamp Comparison (Line ~175)
**File**: `agent_executor.py`

**Change**: Added explicit `None` check before comparing timestamps:

```python
# Before (buggy):
if s3_last_modified > _index_s3_timestamp:

# After (fixed):
if _index_s3_timestamp is not None and s3_last_modified > _index_s3_timestamp:
```

This prevents the comparison from failing when `_index_s3_timestamp` is `None`.

### Fix 2: Force Index Refresh Before Search (Line ~430)
**File**: `agent_executor.py`

**Change**: Added index freshness check at the start of every search operation:

```python
# Check S3 for index updates before searching
s3_obj = s3_client.head_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
s3_last_modified = s3_obj['LastModified'].timestamp()

# If our cached timestamp is older than S3, force reload
if _index_s3_timestamp is None or s3_last_modified > _index_s3_timestamp:
    logger.info(f"Index update detected before search, reloading...")
    if cache_key in _faiss_cache:
        del _faiss_cache[cache_key]
    preload_master_index()
```

This ensures that:
- Every search checks if the S3 index has been updated
- If the index is newer, it's automatically reloaded
- Recently uploaded files are always included in search results

## How It Works

### Before Fix:
1. User uploads file → File processed → Index updated in S3
2. Agent Lambda has stale cached index (from 30 min ago)
3. User asks about file → Agent searches stale cache → File not found
4. Agent responds: "No documents found"

### After Fix:
1. User uploads file → File processed → Index updated in S3
2. Agent Lambda has cached index
3. User asks about file → Agent checks S3 timestamp → Detects update → Reloads index
4. Agent searches fresh index → File found → Returns results

## Performance Impact

- **Minimal**: The timestamp check is a lightweight S3 HEAD request (~10ms)
- **Only reloads when needed**: If index hasn't changed, uses cached version
- **Better UX**: Users can query files immediately after upload without waiting

## Testing

To verify the fix works:

1. **Upload a file** and wait for processing to complete
2. **Wait 20-30 minutes** (or trigger a Lambda cold start)
3. **Ask the agent about the file** - it should find it immediately
4. **Check CloudWatch logs** for:
   - "Index update detected before search, reloading..."
   - "S3 index updated (cached: X, S3: Y), reloading..."

## Deployment

```bash
cd Lambda
.\agent_cache_build_push.bat
```

Then update the Lambda function:
```bash
cd ..\scripts
.\force-agent-update.ps1
```

## Additional Notes

- This fix also improves reliability after Lambda cold starts
- The index reload is automatic and transparent to users
- No changes needed to the ingestion pipeline
- Backward compatible with existing functionality

## Related Issues

This fix also resolves:
- Files appearing "missing" after Lambda restarts
- Inconsistent search results between different Lambda instances
- Stale cache after batch uploads
