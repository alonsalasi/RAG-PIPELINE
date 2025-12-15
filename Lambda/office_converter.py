"""
Office document converter - converts PPTX, DOCX, XLSX to text and images
Also provides Word document (DOCX) editing capabilities
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


# ============================================================================
# WORD DOCUMENT EDITING FUNCTIONS
# ============================================================================

def create_docx(output_path, content=None):
    """
    Create a new Word document.
    
    Args:
        output_path: Path where the document will be saved
        content: Optional initial content (string or list of paragraphs)
    
    Returns:
        Document object for further editing
    
    Example:
        doc = create_docx("output.docx", "Hello World")
        doc = create_docx("output.docx", ["Paragraph 1", "Paragraph 2"])
    """
    try:
        doc = DocxDocument()
        
        if content:
            if isinstance(content, str):
                doc.add_paragraph(content)
            elif isinstance(content, list):
                for para in content:
                    doc.add_paragraph(str(para))
        
        doc.save(output_path)
        logger.info(f"Created new Word document: {output_path}")
        return doc
        
    except Exception as e:
        logger.error(f"Failed to create Word document: {e}")
        raise


def edit_docx(file_path):
    """
    Open an existing Word document for editing.
    
    Args:
        file_path: Path to the Word document to edit
    
    Returns:
        Document object for editing
    
    Example:
        doc = edit_docx("input.docx")
        doc.add_paragraph("New paragraph")
        save_docx(doc, "output.docx")
    """
    try:
        doc = DocxDocument(file_path)
        logger.info(f"Opened Word document for editing: {file_path}")
        return doc
        
    except Exception as e:
        logger.error(f"Failed to open Word document: {e}")
        raise


def save_docx(doc, output_path):
    """
    Save a Word document to a file.
    
    Args:
        doc: Document object to save
        output_path: Path where the document will be saved
    
    Example:
        doc = edit_docx("input.docx")
        doc.add_paragraph("New content")
        save_docx(doc, "output.docx")
    """
    try:
        doc.save(output_path)
        logger.info(f"Saved Word document: {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to save Word document: {e}")
        raise


def add_paragraph_to_docx(doc, text, style=None):
    """
    Add a paragraph to a Word document.
    
    Args:
        doc: Document object
        text: Text content for the paragraph
        style: Optional paragraph style (e.g., 'Heading 1', 'Normal')
    
    Returns:
        The added paragraph object
    
    Example:
        doc = edit_docx("input.docx")
        add_paragraph_to_docx(doc, "My Title", style='Heading 1')
        add_paragraph_to_docx(doc, "Regular paragraph text")
        save_docx(doc, "output.docx")
    """
    try:
        para = doc.add_paragraph(text)
        if style:
            para.style = style
        return para
        
    except Exception as e:
        logger.error(f"Failed to add paragraph: {e}")
        raise


def add_heading_to_docx(doc, text, level=1):
    """
    Add a heading to a Word document.
    
    Args:
        doc: Document object
        text: Heading text
        level: Heading level (0-9, where 0 is Title, 1 is Heading 1, etc.)
    
    Returns:
        The added heading paragraph
    
    Example:
        doc = edit_docx("input.docx")
        add_heading_to_docx(doc, "Document Title", level=0)
        add_heading_to_docx(doc, "Chapter 1", level=1)
        add_heading_to_docx(doc, "Section 1.1", level=2)
        save_docx(doc, "output.docx")
    """
    try:
        heading = doc.add_heading(text, level=level)
        return heading
        
    except Exception as e:
        logger.error(f"Failed to add heading: {e}")
        raise


def replace_text_in_docx(file_path, output_path, replacements):
    """
    Replace text in a Word document.
    
    Args:
        file_path: Path to the input Word document
        output_path: Path where the modified document will be saved
        replacements: Dictionary mapping old text to new text
    
    Example:
        replace_text_in_docx(
            "input.docx",
            "output.docx",
            {"[NAME]": "John Doe", "[DATE]": "2025-12-15"}
        )
    """
    try:
        doc = DocxDocument(file_path)
        
        # Replace in paragraphs
        for para in doc.paragraphs:
            for old_text, new_text in replacements.items():
                if old_text in para.text:
                    for run in para.runs:
                        if old_text in run.text:
                            run.text = run.text.replace(old_text, new_text)
        
        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for old_text, new_text in replacements.items():
                            if old_text in para.text:
                                for run in para.runs:
                                    if old_text in run.text:
                                        run.text = run.text.replace(old_text, new_text)
        
        doc.save(output_path)
        logger.info(f"Replaced {len(replacements)} text patterns in document: {output_path}")
        
    except Exception as e:
        logger.error(f"Failed to replace text in Word document: {e}")
        raise


def add_table_to_docx(doc, data, style='Light Grid Accent 1'):
    """
    Add a table to a Word document.
    
    Args:
        doc: Document object
        data: List of lists representing table rows (first row is header)
        style: Table style name (optional)
    
    Returns:
        The added table object
    
    Example:
        doc = edit_docx("input.docx")
        data = [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "San Francisco"]
        ]
        add_table_to_docx(doc, data)
        save_docx(doc, "output.docx")
    """
    try:
        if not data:
            raise ValueError("Table data cannot be empty")
        
        rows = len(data)
        cols = len(data[0])
        
        table = doc.add_table(rows=rows, cols=cols)
        table.style = style
        
        # Populate table
        for i, row_data in enumerate(data):
            row_cells = table.rows[i].cells
            for j, cell_value in enumerate(row_data):
                row_cells[j].text = str(cell_value)
        
        return table
        
    except Exception as e:
        logger.error(f"Failed to add table: {e}")
        raise
