"""Parse documents to extract text content."""
import io

def parse_document(file_bytes, filename):
    """Extract text from document."""
    ext = filename.lower().split('.')[-1]
    
    if ext == 'txt':
        return file_bytes.decode('utf-8')
    elif ext == 'pdf':
        return parse_pdf(file_bytes)
    elif ext == 'docx':
        return parse_docx(file_bytes)
    elif ext == 'xlsx':
        return parse_xlsx(file_bytes)
    else:
        raise ValueError(f"Unsupported format: {ext}")

def parse_pdf(file_bytes):
    """Extract text from PDF."""
    try:
        import PyPDF2
        pdf = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        text = []
        for page in pdf.pages:
            text.append(page.extract_text())
        return '\n'.join(text)
    except:
        return ""

def parse_docx(file_bytes):
    """Extract text from DOCX."""
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    text = []
    for para in doc.paragraphs:
        text.append(para.text)
    return '\n'.join(text)

def parse_xlsx(file_bytes):
    """Extract text from XLSX."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(file_bytes))
    text = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows():
            row_text = []
            for cell in row:
                if cell.value:
                    row_text.append(str(cell.value))
            if row_text:
                text.append(' | '.join(row_text))
    return '\n'.join(text)
