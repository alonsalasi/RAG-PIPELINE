# PDF OCR Troubleshooting Guide

## Problem: "Only images and no extractable text" error

This error occurs when PDFs contain scanned images instead of embedded text. The system needs to use OCR (Optical Character Recognition) to extract text from these images.

## Solution Applied

The following fixes have been implemented in `worker.py`:

### 1. Better handling of image-only PDFs
- When text extraction returns less than 50 characters, the system now creates meaningful content from image descriptions
- Images are still processed and made searchable even when OCR fails

### 2. Improved error logging
- Added detailed logging to track OCR failures on specific pages
- Better visibility into which pages fail and why

### 3. Fallback content generation
- If OCR fails but images are extracted, the system creates searchable content from image metadata
- Each image's description becomes part of the searchable document

## Testing Your PDF

Use the provided test script to diagnose OCR issues:

```bash
cd Lambda
python test_ocr.py path/to/your/problem.pdf
```

This will show you:
- How many pages were converted
- OCR confidence for each page
- Amount of text extracted
- Any errors during processing

## Common Issues and Solutions

### Issue 1: Tesseract not installed
**Symptom:** Error about pytesseract or tesseract command not found

**Solution:**
- Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
- Linux: `sudo apt-get install tesseract-ocr tesseract-ocr-heb tesseract-ocr-ara`
- Mac: `brew install tesseract tesseract-lang`

### Issue 2: Missing language packs
**Symptom:** OCR works but returns gibberish for Hebrew/Arabic text

**Solution:**
Install additional language packs:
- Windows: Select languages during Tesseract installation
- Linux: `sudo apt-get install tesseract-ocr-heb tesseract-ocr-ara`
- Mac: Language packs included with brew installation

### Issue 3: Low OCR confidence
**Symptom:** Text is extracted but quality is poor

**Solution:**
- Increase DPI in convert_from_path (currently 150, try 200-300)
- Check if PDF is very low resolution
- Try preprocessing the image (already implemented for tables)

### Issue 4: PDF is too large
**Symptom:** Lambda timeout or memory errors

**Solution:**
- The system automatically chunks PDFs over 60 pages
- Each chunk is processed separately to avoid timeouts
- Consider increasing Lambda timeout in `Lambda_ingest.tf`

## Deployment

After making changes, redeploy the Lambda function:

```bash
cd Lambda
# Build and push the Docker image
.\ingestion_cache_build_push.bat

# Or force update the Lambda
cd ..\scripts
.\force-reprocess.ps1
```

## Monitoring

Check CloudWatch logs for detailed OCR processing:
- Look for "OCR confidence" messages
- Check for "No text extracted" warnings
- Monitor "Page X OCR failed" errors

## Next Steps

If issues persist:
1. Run the test_ocr.py script on your problematic PDF
2. Check the CloudWatch logs for the specific file
3. Verify Tesseract is installed in the Lambda container
4. Check the ingestion_requirements.txt includes: pytesseract, pdf2image, Pillow

## Configuration

Key settings in worker.py:
- DPI for PDF conversion: Line ~450 (dpi=150)
- OCR language: 'eng+heb+ara' (English, Hebrew, Arabic)
- OCR config: '--psm 6 --oem 1' (standard mode)
- Table detection threshold: 500 pixels for horizontal/vertical lines
