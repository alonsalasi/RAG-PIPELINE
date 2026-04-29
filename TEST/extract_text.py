import PyPDF2
from docx import Document

# Extract text from PDF
with open('שאלות.pdf', 'rb') as f:
    pdf = PyPDF2.PdfReader(f)
    questions = '\n'.join(page.extract_text() for page in pdf.pages)

with open('questions.txt', 'w', encoding='utf-8') as f:
    f.write(questions)

# Extract text from DOCX
doc = Document('תשובות-.docx')
answers = '\n'.join(para.text for para in doc.paragraphs)

with open('answers.txt', 'w', encoding='utf-8') as f:
    f.write(answers)

print("Extraction complete")
