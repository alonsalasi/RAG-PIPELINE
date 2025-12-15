# Word Document Editing Functionality

This document describes the Word document editing capabilities added to the RAG-PIPELINE system.

## Overview

The system can now **edit and create** Word (.docx) files in addition to extracting content from them. This functionality is implemented in `Lambda/office_converter.py`.

## Available Functions

### 1. `create_docx(output_path, content=None)`

Creates a new Word document from scratch.

**Parameters:**
- `output_path` (str): Path where the new document will be saved
- `content` (dict, optional): Dictionary containing content to add:
  - `'title'` (str): Document title (added as Heading level 0)
  - `'headings'` (list): List of headings to add
    - Each item can be a string or dict with `'text'` and `'level'` (1-9)
  - `'paragraphs'` (list): List of paragraphs to add
    - Each item can be a string or dict with `'text'` and optional `'style'`
  - `'tables'` (list): List of tables to add
    - Each dict should contain `'rows'`, `'cols'`, and optional `'data'` (2D list)

**Returns:** `bool` - True if successful, False otherwise

**Example:**
```python
from office_converter import create_docx

content = {
    'title': 'Project Report',
    'headings': [
        {'text': 'Introduction', 'level': 1},
        {'text': 'Background', 'level': 2}
    ],
    'paragraphs': [
        'This is the introduction paragraph.',
        {'text': 'This is a styled paragraph.', 'style': 'Intense Quote'}
    ],
    'tables': [
        {
            'rows': 3,
            'cols': 2,
            'data': [
                ['Name', 'Value'],
                ['Item 1', '100'],
                ['Item 2', '200']
            ]
        }
    ]
}

create_docx('output/report.docx', content)
```

### 2. `edit_docx(file_path, output_path=None, modifications=None)`

Edits an existing Word document with various modifications.

**Parameters:**
- `file_path` (str): Path to the input DOCX file
- `output_path` (str, optional): Path to save the modified document. If None, modifies the file in-place
- `modifications` (dict, optional): Dictionary containing modification instructions:
  - `'add_paragraph'`: Add new paragraph(s)
    - Single dict with `'text'` and optional `'style'`
    - Or list of dicts for multiple paragraphs
  - `'add_heading'`: Add new heading(s)
    - Single dict with `'text'` and `'level'` (1-9)
    - Or list of dicts for multiple headings
  - `'replace_text'`: Replace text throughout the document
    - Single dict with `'old'` and `'new'` text
    - Or list of dicts for multiple replacements
  - `'add_table'`: Add new table(s)
    - Single dict with `'rows'`, `'cols'`, and optional `'data'`
    - Or list of dicts for multiple tables
  - `'modify_styles'`: Change document formatting
    - Dict with `'paragraph_font'` and/or `'paragraph_size'`

**Returns:** `bool` - True if successful, False otherwise

**Examples:**

#### Adding content to an existing document:
```python
from office_converter import edit_docx

modifications = {
    'add_heading': {'text': 'New Section', 'level': 1},
    'add_paragraph': [
        {'text': 'First new paragraph.'},
        {'text': 'Second new paragraph.'}
    ]
}

edit_docx('input.docx', 'output.docx', modifications)
```

#### Replacing text:
```python
modifications = {
    'replace_text': [
        {'old': 'DRAFT', 'new': 'FINAL'},
        {'old': '2024', 'new': '2025'}
    ]
}

edit_docx('document.docx', 'updated_document.docx', modifications)
```

#### In-place editing:
```python
modifications = {
    'add_paragraph': {'text': 'Added at the end.'},
    'replace_text': {'old': 'old_term', 'new': 'new_term'}
}

# No output_path specified - modifies the file in-place
edit_docx('document.docx', modifications=modifications)
```

#### Adding a table:
```python
modifications = {
    'add_table': {
        'rows': 4,
        'cols': 3,
        'data': [
            ['Header 1', 'Header 2', 'Header 3'],
            ['A1', 'B1', 'C1'],
            ['A2', 'B2', 'C2'],
            ['A3', 'B3', 'C3']
        ]
    }
}

edit_docx('document.docx', 'with_table.docx', modifications)
```

### 3. `extract_docx(file_path)`

Extracts text and images from a Word document (existing functionality).

**Parameters:**
- `file_path` (str): Path to the DOCX file

**Returns:** `tuple` - (text_content, images)
- `text_content` (str): Extracted text from the document
- `images` (list): List of extracted images with metadata

## Testing

Run the test suite to verify Word editing functionality:

```bash
python scripts/test_word_editing.py
```

The test suite includes:
1. Creating new documents from scratch
2. Adding content to existing documents
3. Replacing text in documents
4. In-place document editing

## Use Cases

### 1. Document Generation
Create reports, invoices, or form letters programmatically:
```python
create_docx('invoice.docx', {
    'title': 'Invoice #12345',
    'paragraphs': ['Bill to: Customer Name', 'Date: 2025-12-15'],
    'tables': [{
        'rows': 3,
        'cols': 3,
        'data': [['Item', 'Qty', 'Price'], ['Service A', '1', '$100'], ['Service B', '2', '$200']]
    }]
})
```

### 2. Template Modification
Modify existing templates with dynamic content:
```python
edit_docx('template.docx', 'personalized.docx', {
    'replace_text': [
        {'old': '{NAME}', 'new': 'John Doe'},
        {'old': '{DATE}', 'new': '2025-12-15'}
    ]
})
```

### 3. Document Updates
Update existing documents with new sections or corrections:
```python
edit_docx('report.docx', modifications={
    'add_heading': {'text': 'Addendum', 'level': 1},
    'add_paragraph': {'text': 'Additional findings...'},
    'replace_text': {'old': 'preliminary', 'new': 'final'}
})
```

## Requirements

The following Python packages are required (already included in `Lambda/ingestion_requirements.txt`):
- `python-docx==1.1.2` - For reading and writing Word documents
- `Pillow==11.0.0` - For image processing

## Limitations

1. **Supported Format**: Only `.docx` (Office Open XML) format is supported, not older `.doc` format
2. **Complex Formatting**: Some advanced formatting features (e.g., embedded objects, SmartArt) may not be fully preserved
3. **Text Replacement**: Replaces text in runs, which may affect formatting if text spans multiple runs with different styles
4. **Table Styling**: Added tables use basic "Table Grid" style by default

## Security Considerations

- File paths are validated to prevent path traversal attacks
- File size limits are enforced during processing
- Only trusted sources should be allowed to modify documents
- Consider implementing access controls for document editing operations

## Future Enhancements

Potential improvements for future versions:
- Support for more complex formatting (colors, fonts, alignment)
- Ability to delete or modify existing content by position
- Support for headers, footers, and page breaks
- Image insertion capabilities
- Document merging functionality
- Conversion between document formats
