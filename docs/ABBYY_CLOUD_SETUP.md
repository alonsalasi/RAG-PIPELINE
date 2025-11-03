# ABBYY Cloud OCR Setup Guide

## Overview
This project uses ABBYY Cloud OCR SDK for handwritten text recognition in PDF documents. ABBYY provides superior handwriting recognition compared to other OCR solutions.

## Free Tier
- **500 pages/month** free
- No credit card required for trial
- Excellent for testing and low-volume use

## Getting Started

### 1. Sign Up for ABBYY Cloud
1. Go to https://cloud.ocrsdk.com/
2. Click "Try for Free" or "Sign Up"
3. Create an account with your email
4. Verify your email address

### 2. Get Your Credentials
1. Log in to ABBYY Cloud Console
2. Navigate to **Applications** section
3. Create a new application or use the default one
4. Copy your credentials:
   - **Application ID** (looks like: `your_app_name`)
   - **Password** (API password/key)

### 3. Store Credentials in AWS Secrets Manager

Run the setup script:

```powershell
.\scripts\setup-abbyy-cloud.ps1 `
    -ApplicationId "your_application_id" `
    -Password "your_password" `
    -Profile "leidos" `
    -ProjectName "pdfquery"
```

Or manually create the secret:

```bash
aws secretsmanager put-secret-value \
    --secret-id pdfquery-abbyy-cloud-key \
    --secret-string '{"application_id":"your_app_id","password":"your_password"}' \
    --profile leidos
```

### 4. Deploy Updated Lambda
After storing credentials, redeploy your ingestion Lambda:

```bash
cd Lambda
.\ingestion_cache_build_push.bat
```

## How It Works

### Processing Flow
1. PDF page is detected as handwritten (low OCR confidence)
2. Page image is sent to ABBYY Cloud API
3. ABBYY processes the image (typically 5-30 seconds)
4. Extracted text is returned and indexed

### Fallback Strategy
If ABBYY is unavailable or fails:
- Falls back to enhanced local OCR (Tesseract with preprocessing)
- Ensures processing continues even without ABBYY

## API Endpoints Used

### Submit Image
```
POST https://cloud-eu.ocrsdk.com/v2/processImage
```

### Check Status
```
GET https://cloud-eu.ocrsdk.com/v2/getTaskStatus?taskId={id}
```

### Download Result
```
GET {resultUrl}
```

## Pricing Tiers

| Tier | Pages/Month | Cost |
|------|-------------|------|
| Free | 500 | $0 |
| Starter | 1,000 | ~$50-75 |
| Professional | 5,000 | ~$200-300 |
| Enterprise | 50,000+ | Custom |

## Monitoring Usage

### Check Current Usage
Log in to ABBYY Cloud Console to view:
- Pages processed this month
- Remaining free tier pages
- Processing history

### Lambda Logs
Monitor CloudWatch logs for:
- `ABBYY extracted X chars` - Successful processing
- `ABBYY Cloud unavailable` - Fallback to local OCR
- `NotEnoughCredits` - Free tier exhausted

## Supported Languages
Current configuration supports:
- English
- Hebrew
- Turkish

To add more languages, modify `worker.py`:
```python
params = {
    'language': 'English,Hebrew,Turkish,Spanish,French',  # Add languages
    'exportFormat': 'txt',
    'profile': 'textExtraction'
}
```

## Troubleshooting

### "ABBYY Cloud unavailable"
- Check credentials are stored correctly in Secrets Manager
- Verify APPLICATION_ID and PASSWORD are valid
- Check ABBYY Cloud service status

### "NotEnoughCredits"
- Free tier exhausted (500 pages/month)
- Upgrade to paid tier or wait for monthly reset
- System will fallback to local OCR automatically

### Slow Processing
- ABBYY typically takes 5-30 seconds per page
- This is normal for cloud OCR services
- Consider batch processing for large documents

## Security Notes
- Credentials stored in AWS Secrets Manager (encrypted)
- Images sent to ABBYY Cloud (EU servers)
- ABBYY retains images for 24 hours then deletes
- For sensitive documents, consider on-premise ABBYY Engine

## Comparison with Google Vision

| Feature | ABBYY Cloud | Google Vision |
|---------|-------------|---------------|
| Handwriting | Excellent | Good |
| Free Tier | 500 pages/month | 1,000 pages/month |
| Cost (1K pages) | $50-75 | $1.50 |
| Processing Time | 5-30 seconds | 1-3 seconds |
| Data Retention | 24 hours | Per Google policy |
| Multi-language | Excellent | Good |

## Support
- ABBYY Documentation: https://support.abbyy.com/hc/en-us/categories/360002562119-Cloud-OCR-SDK
- API Reference: https://support.abbyy.com/hc/en-us/articles/360017269900-HTTP-API-Reference
