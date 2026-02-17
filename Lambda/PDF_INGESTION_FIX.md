# PDF Ingestion Fix

## Problem
PDF text extraction was failing for image-based PDFs (scanned documents), returning empty text and causing the comparison feature to fail with the error:
```
"text extraction failed for both documents - they are only available through images"
```

## Root Cause
The `parse_pdf()` function in `document_parser.py` was using only PyPDF2 for text extraction, which fails on image-based PDFs. When extraction failed, it simply returned an empty string with no fallback mechanism.

## Solution
Updated `document_parser.py` to implement a robust two-stage extraction process:

### Stage 1: Fast Text Extraction (pypdf)
- Attempts to extract text directly from PDF using pypdf library
- If successful and returns meaningful text (>50 chars), returns immediately
- This works for text-based PDFs and is very fast

### Stage 2: OCR Fallback (pdf2image + pytesseract)
- If Stage 1 fails or returns insufficient text, automatically falls back to OCR
- Converts PDF pages to images using pdf2image (requires poppler-utils)
- Performs OCR on each page using pytesseract with multilingual support (eng+heb+ara)
- Returns extracted text with page markers for better organization

## Changes Made

### File: `Lambda/document_parser.py`
- Replaced simple PyPDF2 extraction with robust two-stage process
- Added OCR fallback using pdf2image and pytesseract
- Added multilingual OCR support (English, Hebrew, Arabic)
- Added proper error handling and informative error messages
- Fixed import to use `pypdf` instead of `PyPDF2` (matches requirements.txt)

## Dependencies
All required dependencies are already in place:
- ✅ `pypdf==4.2.0` in ingestion_requirements.txt
- ✅ `pdf2image==1.17.0` in ingestion_requirements.txt
- ✅ `pytesseract==0.3.10` in ingestion_requirements.txt
- ✅ `tesseract-ocr` installed in ingestion.Dockerfile
- ✅ `poppler-utils` installed in ingestion.Dockerfile
- ✅ Language data (eng, heb, ara) downloaded in Dockerfile

## Testing
To test the fix:
1. Rebuild the ingestion Lambda Docker image
2. Upload a scanned PDF (image-based) document
3. Verify text extraction succeeds via OCR
4. Test the comparison feature with two scanned PDFs

## Deployment
```bash
cd Lambda
# Rebuild and push the ingestion Lambda
.\ingestion_no_cache_build_push.bat
```

## Notes
- OCR is slower than direct text extraction but necessary for scanned documents
- The system automatically chooses the fastest method that works
- OCR supports English, Hebrew, and Arabic languages
- Page markers help organize multi-page document text
