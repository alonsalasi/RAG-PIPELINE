# Claude Vision OCR Integration

## Overview
Integrated Claude 3.5 Sonnet Vision API for advanced image and table analysis, replacing basic color/object detection with AI-powered descriptions.

## Changes Made

### 1. Image Analysis (`image_analysis.py`)
- **REMOVED**: OpenCV color detection, MobileNet-SSD object detection
- **ADDED**: Claude Vision API integration using `anthropic` SDK
- **Functionality**: 
  - Detailed image descriptions (objects, colors, text, context)
  - Table/chart data extraction in structured format
  - Specific details (brands, models, features)

### 2. Document Processing (`worker.py`)
- **Updated**: Image processing pipeline to use Claude Vision for embedded images
- **Kept**: Tesseract OCR for all documents (free, always runs)
- **Flow**: 
  1. Extract embedded images from PDF
  2. Analyze with Claude Vision (detailed descriptions)
  3. Run Tesseract OCR on images (extract text)
  4. Process full pages with Tesseract (text extraction)

### 3. Dependencies (`ingestion_requirements.txt`)
- **REMOVED**: `opencv-python-headless==4.10.0.84`
- **ADDED**: `anthropic==0.39.0` (Claude Vision SDK)
- **KEPT**: `pytesseract`, `Pillow`, `pdf2image` (Tesseract OCR)

### 4. Docker Configuration (`ingestion.Dockerfile`)
- **REMOVED**: 
  - OpenCV system dependencies (`libgl1-mesa-glx`, `libglib2.0-0`)
  - MobileNet model files (`deploy.prototxt`, `mobilenet_iter_73000.caffemodel`)
  - Model directory creation
- **KEPT**: Tesseract OCR and language data

### 5. Search Logic (`agent_executor.py`)
- **REMOVED**: Manual color/object filtering with penalty scores
- **SIMPLIFIED**: Pure image queries now rely on Claude Vision's semantic descriptions
- **Benefit**: Better matching through natural language descriptions vs. keyword matching

## Cost Optimization
- **Claude Vision**: Only runs on embedded images/tables (typically 1-5 per document)
- **Tesseract**: Free, runs on all pages for text extraction
- **Hybrid Approach**: Best of both worlds - AI quality + cost efficiency

## API Requirements
- **Environment Variable**: `ANTHROPIC_API_KEY` must be set in Lambda environment
- **Model**: `claude-3-5-sonnet-20241022` (latest vision model)
- **Token Limit**: 1024 tokens per image analysis

## Benefits
1. **Better Image Understanding**: Claude Vision provides context-aware descriptions
2. **Table Extraction**: Structured data extraction from tables/charts
3. **Color/Object Detection**: Natural language descriptions vs. rigid keywords
4. **Reduced Dependencies**: Removed heavy OpenCV library
5. **Smaller Docker Image**: No model files needed

## Testing Checklist
- [ ] Upload PDF with images
- [ ] Verify Claude Vision descriptions in processed JSON
- [ ] Test image search queries
- [ ] Verify Tesseract still extracts text
- [ ] Check table extraction accuracy
- [ ] Validate cost per document
