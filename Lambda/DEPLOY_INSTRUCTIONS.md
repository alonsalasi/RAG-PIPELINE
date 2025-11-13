# Deployment Instructions

## Problem
The improved diagram detection code in `image_analysis.py` hasn't been deployed yet. The ingestion logs show the OLD code is still running.

## Solution

### Step 1: Deploy Updated Ingestion Lambda
```powershell
cd d:\Projects\LEIDOS\Lambda
.\ingestion_no_cache_build_push.bat
```

Wait 2-3 minutes for deployment to complete.

### Step 2: Re-upload Your Test Document
Delete the old document and re-upload it so it gets processed with the NEW detection code.

### Step 3: Test
Query: "show me architecture of the cloud landing zone"

Expected: Should return actual architecture diagrams, NOT banners.

## What Changed

### image_analysis.py
1. **Logo/Banner Filtering:**
   - Rejects images < 200px (logos/icons)
   - Rejects aspect ratio > 4:1 (banners)
   - Image #16 (675x115px, aspect 5.87) will be rejected

2. **Better Diagram Detection:**
   - More permissive thresholds
   - Will now detect images #2, #3, #10, #17 that were missed before
   - Line-heavy diagrams: `rectangles > 50 AND lines > 300`

## Expected Results After Deployment

**Before (Current):**
- 9/20 images detected as diagrams
- Agent returns banner (image #16)

**After (New Code):**
- 13-14/20 images detected as diagrams
- Banners filtered out (images #6, #16, #18)
- Agent returns only actual diagrams

## Verification

Check ingestion logs for:
```
[DIAGRAM] Aspect ratio: 5.87 - REJECTED (banner/logo)
[DIAGRAM] DETECTED: architecture diagram (line-heavy)
```

If you still see the OLD logs (no "REJECTED (banner/logo)"), the deployment didn't work.
