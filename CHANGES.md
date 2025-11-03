# Code Changes Summary - Google Vision → ABBYY Cloud

## Modified Files

### 1. Lambda/worker.py
**Lines changed**: ~60 lines

**Removed**:
- `get_google_vision_key()` function
- `detect_handwriting_with_google_vision()` function
- Google Vision API calls

**Added**:
- `get_abbyy_credentials()` function - Loads ABBYY credentials from Secrets Manager
- `detect_handwriting_with_abbyy()` function - Handles ABBYY Cloud OCR processing
  - Submits image to ABBYY Cloud
  - Polls for completion (max 60 seconds)
  - Downloads and returns extracted text
  - Supports English, Hebrew, Turkish

**Key Changes**:
```python
# OLD
google_text = detect_handwriting_with_google_vision(img_byte_arr.getvalue())
if google_text:
    full_text += google_text + "\n"
    logger.info(f"Page {i} Google Vision extracted: {len(google_text)} chars")

# NEW
abbyy_text = detect_handwriting_with_abbyy(img_byte_arr.getvalue())
if abbyy_text:
    full_text += abbyy_text + "\n"
    logger.info(f"Page {i} ABBYY Cloud extracted: {len(abbyy_text)} chars")
```

### 2. Lambda/ingestion_requirements.txt
**Lines changed**: 1 line (comment only)

**Changed**:
```diff
- # Google Vision API
+ # ABBYY Cloud OCR API (for handwriting recognition)
  requests==2.32.3
```

## New Files Created

### Scripts
1. **scripts/setup-abbyy-cloud.ps1** (40 lines)
   - PowerShell script to store ABBYY credentials in Secrets Manager
   - Usage: `.\scripts\setup-abbyy-cloud.ps1 -ApplicationId "id" -Password "pwd"`

2. **scripts/test-abbyy-connection.ps1** (80 lines)
   - Tests ABBYY Cloud API connection
   - Validates credentials from Secrets Manager
   - Usage: `.\scripts\test-abbyy-connection.ps1`

### Documentation
3. **docs/ABBYY_CLOUD_SETUP.md** (180 lines)
   - Complete setup guide
   - API reference
   - Troubleshooting
   - Pricing comparison

4. **MIGRATION_SUMMARY.md** (90 lines)
   - Migration overview
   - Key differences
   - Setup steps

5. **QUICK_START_ABBYY.md** (60 lines)
   - Quick reference card
   - 3-step setup
   - Monitoring tips

6. **CHANGES.md** (This file)
   - Detailed change log

## AWS Resources

### Secrets Manager
**New Secret**: `pdfquery-abbyy-cloud-key`
```json
{
  "application_id": "your_app_id",
  "password": "your_password"
}
```

**Old Secret** (can be deleted): `pdfquery-google-vision-key`

## Dependencies
**No new dependencies added** - Uses existing `requests` library

## Deployment
```bash
cd Lambda
.\ingestion_cache_build_push.bat
```

## Testing
1. Store ABBYY credentials
2. Deploy Lambda
3. Upload handwritten PDF
4. Check CloudWatch logs for "ABBYY extracted X chars"

## Rollback Plan
If needed, revert `worker.py` changes:
```bash
git checkout HEAD -- Lambda/worker.py
.\ingestion_cache_build_push.bat
```

## Free Tier Usage
- **500 pages/month** free
- Monitor at: https://cloud.ocrsdk.com/
- Automatic fallback to local OCR if exceeded

## Support
- ABBYY Support: https://support.abbyy.com/
- API Docs: https://support.abbyy.com/hc/en-us/articles/360017269900
