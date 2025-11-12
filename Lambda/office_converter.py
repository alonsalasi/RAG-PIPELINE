"""
Office document converter - converts PPTX, DOCX, XLSX to text and images
Zero cost - uses only free Python libraries
"""
import io
import logging
from PIL import Image
from pptx import Presentation
from docx import Document as DocxDocument
from openpyxl import load_workbook

logger = logging.getLogger(__name__)

def extract_pptx(file_path):
    """Extract text and images from PowerPoint"""
    text_content = []
    images = []
    
    try:
        prs = Presentation(file_path)
        
        for slide_num, slide in enumerate(prs.slides, 1):
            slide_text = []
            
            # Extract text from shapes
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_text.append(shape.text.strip())
                
                # Extract images
                if shape.shape_type == 13:  # Picture
                    try:
                        image = shape.image
                        image_bytes = image.blob
                        if len(image_bytes) > 10000:  # Min 10KB
                            img_pil = Image.open(io.BytesIO(image_bytes))
                            img_byte_arr = io.BytesIO()
                            img_pil.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
                            images.append({
                                'page': slide_num,
                                'index': len(images),
                                'data': img_byte_arr.getvalue(),
                                'ext': 'jpg'
                            })
                    except Exception as e:
                        logger.warning(f"Failed to extract image from slide {slide_num}: {e}")
            
            if slide_text:
                text_content.append(f"[SLIDE {slide_num}]:\n" + "\n".join(slide_text))
        
        full_text = "\n\n".join(text_content)
        logger.info(f"PPTX: Extracted {len(prs.slides)} slides, {len(images)} images, {len(full_text)} chars")
        return full_text, images
        
    except Exception as e:
        logger.error(f"PPTX extraction failed: {e}")
        return "", []

def extract_docx(file_path):
    """Extract text and images from Word document in document order"""
    text_content = []
    images = []
    
    try:
        doc = DocxDocument(file_path)
        seen_rIds = set()  # Track relationship IDs instead of blobs to avoid missing images
        
        # Extract text from paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                text_content.append(para.text.strip())
        
        # Extract images in document order by walking through all elements
        import re
        
        # Walk through paragraphs in order
        for para in doc.paragraphs:
            for run in para.runs:
                if 'graphic' in run._element.xml:
                    rId_match = re.search(r'r:embed="(rId\d+)"', run._element.xml)
                    if rId_match:
                        rId = rId_match.group(1)
                        if rId not in seen_rIds:
                            seen_rIds.add(rId)
                            try:
                                rel = run.part.rels[rId]
                                if "image" in rel.target_ref:
                                    image_bytes = rel.target_part.blob
                                    if len(image_bytes) > 10000:
                                        img_pil = Image.open(io.BytesIO(image_bytes))
                                        img_byte_arr = io.BytesIO()
                                        img_pil.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
                                        images.append({
                                            'page': None,
                                            'index': len(images),
                                            'data': img_byte_arr.getvalue(),
                                            'ext': 'jpg'
                                        })
                            except Exception as e:
                                logger.warning(f"Failed to extract image from paragraph: {e}")
        
        # Walk through tables in order
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            if 'graphic' in run._element.xml:
                                rId_match = re.search(r'r:embed="(rId\d+)"', run._element.xml)
                                if rId_match:
                                    rId = rId_match.group(1)
                                    if rId not in seen_rIds:
                                        seen_rIds.add(rId)
                                        try:
                                            rel = run.part.rels[rId]
                                            if "image" in rel.target_ref:
                                                image_bytes = rel.target_part.blob
                                                if len(image_bytes) > 10000:
                                                    img_pil = Image.open(io.BytesIO(image_bytes))
                                                    img_byte_arr = io.BytesIO()
                                                    img_pil.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
                                                    images.append({
                                                        'page': None,
                                                        'index': len(images),
                                                        'data': img_byte_arr.getvalue(),
                                                        'ext': 'jpg'
                                                    })
                                        except Exception as e:
                                            logger.warning(f"Failed to extract image from table: {e}")
        
        # Check headers/footers last
        for section in doc.sections:
            for header in [section.header, section.first_page_header, section.even_page_header]:
                try:
                    for para in header.paragraphs:
                        for run in para.runs:
                            if 'graphic' in run._element.xml:
                                rId_match = re.search(r'r:embed="(rId\d+)"', run._element.xml)
                                if rId_match:
                                    rId = rId_match.group(1)
                                    if rId not in seen_rIds:
                                        seen_rIds.add(rId)
                                        try:
                                            rel = run.part.rels[rId]
                                            if "image" in rel.target_ref:
                                                image_bytes = rel.target_part.blob
                                                if len(image_bytes) > 10000:
                                                    img_pil = Image.open(io.BytesIO(image_bytes))
                                                    img_byte_arr = io.BytesIO()
                                                    img_pil.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
                                                    images.append({
                                                        'page': None,
                                                        'index': len(images),
                                                        'data': img_byte_arr.getvalue(),
                                                        'ext': 'jpg'
                                                    })
                                        except Exception as e:
                                            logger.warning(f"Failed to extract image from header: {e}")
                except:
                    pass
            
            for footer in [section.footer, section.first_page_footer, section.even_page_footer]:
                try:
                    for para in footer.paragraphs:
                        for run in para.runs:
                            if 'graphic' in run._element.xml:
                                rId_match = re.search(r'r:embed="(rId\d+)"', run._element.xml)
                                if rId_match:
                                    rId = rId_match.group(1)
                                    if rId not in seen_rIds:
                                        seen_rIds.add(rId)
                                        try:
                                            rel = run.part.rels[rId]
                                            if "image" in rel.target_ref:
                                                image_bytes = rel.target_part.blob
                                                if len(image_bytes) > 10000:
                                                    img_pil = Image.open(io.BytesIO(image_bytes))
                                                    img_byte_arr = io.BytesIO()
                                                    img_pil.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
                                                    images.append({
                                                        'page': None,
                                                        'index': len(images),
                                                        'data': img_byte_arr.getvalue(),
                                                        'ext': 'jpg'
                                                    })
                                        except Exception as e:
                                            logger.warning(f"Failed to extract image from footer: {e}")
                except:
                    pass
        
        full_text = "\n\n".join(text_content)
        logger.info(f"DOCX: Extracted {len(doc.paragraphs)} paragraphs, {len(images)} images, {len(full_text)} chars")
        return full_text, images
        
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return "", []

def extract_xlsx(file_path):
    """Extract text from Excel spreadsheet"""
    text_content = []
    
    try:
        wb = load_workbook(file_path, data_only=True)
        
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            sheet_text = [f"[SHEET: {sheet_name}]"]
            
            for row in sheet.iter_rows(values_only=True):
                row_text = [str(cell) for cell in row if cell is not None]
                if row_text:
                    sheet_text.append(" | ".join(row_text))
            
            if len(sheet_text) > 1:  # Has content beyond header
                text_content.append("\n".join(sheet_text))
        
        full_text = "\n\n".join(text_content)
        logger.info(f"XLSX: Extracted {len(wb.sheetnames)} sheets, {len(full_text)} chars")
        return full_text, []
        
    except Exception as e:
        logger.error(f"XLSX extraction failed: {e}")
        return "", []
