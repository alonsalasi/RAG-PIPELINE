# ABBYY Cloud Quick Start (Free Tier)

## 🚀 3-Step Setup

### Step 1: Get Free ABBYY Account
```
https://cloud.ocrsdk.com/
→ Sign up (no credit card needed)
→ Get Application ID + Password
```

### Step 2: Store Credentials
```powershell
.\scripts\setup-abbyy-cloud.ps1 `
    -ApplicationId "your_app_id" `
    -Password "your_password"
```

### Step 3: Test & Deploy
```powershell
# Test connection
.\scripts\test-abbyy-connection.ps1

# Deploy Lambda
cd Lambda
.\ingestion_cache_build_push.bat
```

## ✅ What You Get

- **500 free pages/month** for testing
- **Superior handwriting recognition**
- **Automatic fallback** to local OCR if quota exceeded
- **Multi-language support** (English, Hebrew, Turkish)

## 📊 Free Tier Limits

| Feature | Limit |
|---------|-------|
| Pages/month | 500 |
| Processing time | 5-30 sec/page |
| Retention | 24 hours |
| Languages | 200+ |

## 🔍 How to Monitor

**ABBYY Console**: https://cloud.ocrsdk.com/
- View pages processed
- Check remaining quota
- Download processing history

**CloudWatch Logs**:
```
✓ "ABBYY extracted 1234 chars" → Success
⚠ "ABBYY Cloud unavailable" → Using fallback
⚠ "NotEnoughCredits" → Quota exceeded
```

## 💡 Tips

1. **Start with free tier** - Perfect for testing
2. **Monitor usage** - Check ABBYY console regularly
3. **Fallback works** - System continues if quota exceeded
4. **Upgrade when ready** - Contact ABBYY for volume pricing

## 📚 Full Documentation

- Setup Guide: `docs/ABBYY_CLOUD_SETUP.md`
- Migration Details: `MIGRATION_SUMMARY.md`
- ABBYY Docs: https://support.abbyy.com/hc/en-us/categories/360002562119-Cloud-OCR-SDK
