# Google Vision → ABBYY Cloud Migration Summary

## What Changed

### Code Changes
- **worker.py**: Replaced Google Vision API functions with ABBYY Cloud API
  - `get_google_vision_key()` → `get_abbyy_credentials()`
  - `detect_handwriting_with_google_vision()` → `detect_handwriting_with_abbyy()`

### Dependencies
- **No changes needed** - `requests` library already present in requirements.txt
- Updated comment to reflect ABBYY Cloud usage

### New Files Created
1. **scripts/setup-abbyy-cloud.ps1** - PowerShell script to store ABBYY credentials
2. **docs/ABBYY_CLOUD_SETUP.md** - Complete setup and usage guide

## Setup Steps

### 1. Get ABBYY Cloud Credentials (Free Tier)
```
1. Sign up at https://cloud.ocrsdk.com/
2. Create application and get credentials:
   - Application ID
   - Password
```

### 2. Store Credentials in AWS Secrets Manager
```powershell
.\scripts\setup-abbyy-cloud.ps1 `
    -ApplicationId "your_app_id" `
    -Password "your_password"
```

### 3. Redeploy Lambda
```bash
cd Lambda
.\ingestion_cache_build_push.bat
```

## Key Differences

| Aspect | Google Vision | ABBYY Cloud |
|--------|---------------|-------------|
| **Free Tier** | 1,000 pages/month | 500 pages/month |
| **Handwriting Quality** | Good | Excellent |
| **Processing Time** | 1-3 seconds | 5-30 seconds |
| **Cost (1K pages)** | $1.50 | $50-75 |
| **Authentication** | API Key | App ID + Password |
| **Secret Name** | `pdfquery-google-vision-key` | `pdfquery-abbyy-cloud-key` |

## Testing the Free Tier

The free tier provides **500 pages/month** which is perfect for:
- Testing handwriting recognition quality
- Processing low-volume documents
- Evaluating before committing to paid tier

## Fallback Behavior

If ABBYY is unavailable (no credentials, quota exceeded, or API error):
- System automatically falls back to enhanced local OCR (Tesseract)
- Processing continues without interruption
- CloudWatch logs show: "ABBYY Cloud unavailable, using enhanced OCR"

## Monitoring

Check CloudWatch logs for:
- ✅ `ABBYY extracted X chars` - Success
- ⚠️ `ABBYY Cloud unavailable` - Fallback triggered
- ⚠️ `NotEnoughCredits` - Free tier exhausted

## Next Steps

1. Sign up for ABBYY Cloud free trial
2. Run setup script with your credentials
3. Redeploy ingestion Lambda
4. Test with handwritten PDF
5. Monitor usage in ABBYY Cloud Console

See **docs/ABBYY_CLOUD_SETUP.md** for detailed instructions.
