"""Test OCR functionality on a sample PDF to verify text extraction."""
import sys
import os
from pdf2image import convert_from_path
import pytesseract
from PIL import Image

def test_ocr_on_pdf(pdf_path):
    """Test OCR on a PDF file."""
    print(f"Testing OCR on: {pdf_path}")
    
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        return
    
    try:
        # Convert PDF to images
        print("Converting PDF to images...")
        images = convert_from_path(pdf_path, dpi=150)
        print(f"Converted {len(images)} pages")
        
        # Test OCR on each page
        for page_num, page_image in enumerate(images, 1):
            print(f"\n--- Page {page_num} ---")
            print(f"Image size: {page_image.size}")
            
            # Try basic OCR
            try:
                text = pytesseract.image_to_string(
                    page_image, 
                    lang='eng+heb+ara',
                    config='--psm 6 --oem 1'
                )
                
                # Get confidence
                data = pytesseract.image_to_data(
                    page_image,
                    lang='eng+heb+ara',
                    config='--psm 6 --oem 1',
                    output_type=pytesseract.Output.DICT
                )
                
                confidences = [int(conf) for conf in data['conf'] if conf != '-1' and str(conf).isdigit()]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0
                
                print(f"OCR Confidence: {avg_confidence:.1f}%")
                print(f"Text length: {len(text)} characters")
                
                if text.strip():
                    print(f"First 200 chars: {text[:200]}")
                else:
                    print("WARNING: No text extracted!")
                    print("This might be an image-only page.")
                    
            except Exception as e:
                print(f"ERROR during OCR: {e}")
                
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_ocr.py <path_to_pdf>")
        print("Example: python test_ocr.py sample.pdf")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    test_ocr_on_pdf(pdf_path)
