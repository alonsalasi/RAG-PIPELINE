import pypdf

with open('test.pdf', 'rb') as f:
    reader = pypdf.PdfReader(f)
    print(f"Pages: {len(reader.pages)}")
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        print(f"\n=== Page {i+1} ({len(text)} chars) ===")
        print(text[:500])
