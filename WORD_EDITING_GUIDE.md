# Word File Editing Capabilities

**Yes, this system can edit Word files!**

The `office_converter.py` module provides comprehensive Word document (DOCX) editing capabilities using the `python-docx` library.

## Available Functions

### 1. Creating New Documents

```python
from office_converter import create_docx

# Create a blank document
doc = create_docx("output.docx")

# Create with initial content (single paragraph)
doc = create_docx("output.docx", "Hello World")

# Create with multiple paragraphs
doc = create_docx("output.docx", ["Paragraph 1", "Paragraph 2", "Paragraph 3"])
```

### 2. Editing Existing Documents

```python
from office_converter import edit_docx, save_docx

# Open an existing document
doc = edit_docx("input.docx")

# Add more content
doc.add_paragraph("New paragraph")

# Save the changes
save_docx(doc, "output.docx")
```

### 3. Adding Paragraphs

```python
from office_converter import edit_docx, add_paragraph_to_docx, save_docx

doc = edit_docx("input.docx")

# Add normal paragraph
add_paragraph_to_docx(doc, "This is a regular paragraph.")

# Add paragraph with specific style
add_paragraph_to_docx(doc, "This is a quote.", style='Intense Quote')

save_docx(doc, "output.docx")
```

### 4. Adding Headings

```python
from office_converter import edit_docx, add_heading_to_docx, save_docx

doc = edit_docx("input.docx")

# Add title (level 0)
add_heading_to_docx(doc, "Document Title", level=0)

# Add main heading (level 1)
add_heading_to_docx(doc, "Chapter 1", level=1)

# Add subheading (level 2)
add_heading_to_docx(doc, "Section 1.1", level=2)

save_docx(doc, "output.docx")
```

### 5. Adding Tables

```python
from office_converter import edit_docx, add_table_to_docx, save_docx

doc = edit_docx("input.docx")

# Define table data (first row is header)
data = [
    ["Name", "Age", "City"],
    ["Alice", "30", "New York"],
    ["Bob", "25", "San Francisco"],
    ["Charlie", "35", "Seattle"]
]

# Add table with styling
add_table_to_docx(doc, data, style='Light Grid Accent 1')

save_docx(doc, "output.docx")
```

### 6. Replacing Text (Template Fill)

```python
from office_converter import replace_text_in_docx

# Define replacements
replacements = {
    "[NAME]": "John Doe",
    "[ORDER_ID]": "12345",
    "[DATE]": "December 15, 2025",
    "[AMOUNT]": "$99.99"
}

# Replace text in document
replace_text_in_docx("template.docx", "output.docx", replacements)
```

## Complete Example

```python
from office_converter import (
    create_docx,
    add_heading_to_docx,
    add_paragraph_to_docx,
    add_table_to_docx,
    save_docx
)

# Create a new report
doc = create_docx("report.docx")

# Add title
add_heading_to_docx(doc, "Monthly Sales Report", level=0)

# Add introduction
add_heading_to_docx(doc, "Executive Summary", level=1)
add_paragraph_to_docx(doc, "This report provides an overview of sales performance for December 2025.")

# Add data section
add_heading_to_docx(doc, "Sales Data", level=1)

# Add sales table
sales_data = [
    ["Region", "Sales", "Growth"],
    ["North", "$1.2M", "+15%"],
    ["South", "$980K", "+8%"],
    ["East", "$1.5M", "+22%"],
    ["West", "$1.1M", "+12%"]
]
add_table_to_docx(doc, sales_data)

# Add conclusion
add_heading_to_docx(doc, "Conclusion", level=1)
add_paragraph_to_docx(doc, "Overall sales show positive growth across all regions.")

# Save the document
save_docx(doc, "report.docx")
```

## Testing

Run the test suite to verify functionality:

```bash
cd Lambda
python test_word_editing.py
```

## Use Cases

1. **Document Generation**: Create reports, invoices, letters automatically
2. **Template Processing**: Fill in templates with dynamic data
3. **Batch Processing**: Modify multiple documents programmatically
4. **Content Automation**: Add standardized content to documents
5. **Data Export**: Export data to formatted Word documents

## Technical Details

- Uses `python-docx` library (version 1.1.2)
- Supports all standard Word document features
- Works with .docx format (Office Open XML)
- Zero-cost solution using only open-source libraries

## Limitations

- Only supports .docx format (not legacy .doc format)
- Complex formatting may require direct access to python-docx Document object
- Images can be extracted but adding images requires additional python-docx knowledge

## See Also

- [python-docx documentation](https://python-docx.readthedocs.io/)
- `office_converter.py` - Source code with all functions
- `test_word_editing.py` - Test suite and usage examples
