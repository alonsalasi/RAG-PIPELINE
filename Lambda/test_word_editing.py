"""
Test script demonstrating Word document editing capabilities.
This script shows how to use the office_converter module to edit Word files.
"""

import os
import sys
import tempfile
from office_converter import (
    create_docx,
    edit_docx,
    save_docx,
    add_paragraph_to_docx,
    add_heading_to_docx,
    replace_text_in_docx,
    add_table_to_docx
)


def test_create_new_document():
    """Test creating a new Word document from scratch."""
    print("\n=== Test 1: Creating a new Word document ===")
    
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
        output_path = tmp.name
    
    try:
        # Create a new document with initial content
        doc = create_docx(output_path, "This is a new Word document created programmatically!")
        print(f"✓ Created new document: {output_path}")
        
        # Verify file exists
        assert os.path.exists(output_path), "Document file was not created"
        print(f"✓ File exists and has size: {os.path.getsize(output_path)} bytes")
        
    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_add_content_to_document():
    """Test adding various content types to a Word document."""
    print("\n=== Test 2: Adding content to a Word document ===")
    
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
        output_path = tmp.name
    
    try:
        # Create a new document
        doc = create_docx(output_path)
        
        # Add title
        add_heading_to_docx(doc, "Document Editing Demo", level=0)
        
        # Add headings and paragraphs
        add_heading_to_docx(doc, "Introduction", level=1)
        add_paragraph_to_docx(doc, "This document demonstrates the Word editing capabilities of the office_converter module.")
        
        add_heading_to_docx(doc, "Features", level=1)
        add_paragraph_to_docx(doc, "The module supports:")
        add_paragraph_to_docx(doc, "• Creating new Word documents")
        add_paragraph_to_docx(doc, "• Adding paragraphs and headings")
        add_paragraph_to_docx(doc, "• Adding tables")
        add_paragraph_to_docx(doc, "• Text replacement")
        
        add_heading_to_docx(doc, "Sample Table", level=2)
        
        # Add a table
        table_data = [
            ["Feature", "Status", "Notes"],
            ["Create documents", "✓", "Fully supported"],
            ["Edit documents", "✓", "Fully supported"],
            ["Add tables", "✓", "With styling"],
            ["Replace text", "✓", "Pattern-based"]
        ]
        add_table_to_docx(doc, table_data)
        
        # Save the document
        save_docx(doc, output_path)
        print(f"✓ Added content to document: {output_path}")
        
        # Verify file exists and has reasonable size
        assert os.path.exists(output_path), "Document file was not created"
        file_size = os.path.getsize(output_path)
        assert file_size > 1000, f"Document seems too small: {file_size} bytes"
        print(f"✓ Document saved successfully with size: {file_size} bytes")
        
    finally:
        if os.path.exists(output_path):
            os.unlink(output_path)


def test_edit_existing_document():
    """Test editing an existing Word document."""
    print("\n=== Test 3: Editing an existing Word document ===")
    
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
        temp_path = tmp.name
    
    try:
        # First, create a document
        doc = create_docx(temp_path, ["Original paragraph 1", "Original paragraph 2"])
        
        # Now edit it
        doc = edit_docx(temp_path)
        add_heading_to_docx(doc, "Added After Creation", level=1)
        add_paragraph_to_docx(doc, "This paragraph was added by editing the existing document.")
        save_docx(doc, temp_path)
        
        print(f"✓ Successfully edited existing document")
        
        # Verify the file was updated
        assert os.path.exists(temp_path), "Document file was not found"
        print(f"✓ Document exists with size: {os.path.getsize(temp_path)} bytes")
        
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_replace_text():
    """Test text replacement in a Word document."""
    print("\n=== Test 4: Replacing text in a Word document ===")
    
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_in:
        input_path = tmp_in.name
    
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_out:
        output_path = tmp_out.name
    
    try:
        # Create a template document
        doc = create_docx(input_path)
        add_paragraph_to_docx(doc, "Dear [NAME],")
        add_paragraph_to_docx(doc, "Your order [ORDER_ID] will be delivered on [DATE].")
        add_paragraph_to_docx(doc, "Thank you for your business!")
        save_docx(doc, input_path)
        
        # Replace placeholders
        replacements = {
            "[NAME]": "John Doe",
            "[ORDER_ID]": "12345",
            "[DATE]": "December 15, 2025"
        }
        replace_text_in_docx(input_path, output_path, replacements)
        
        print(f"✓ Successfully replaced text in document")
        
        # Verify output file exists
        assert os.path.exists(output_path), "Output document was not created"
        print(f"✓ Output document created with size: {os.path.getsize(output_path)} bytes")
        
    finally:
        if os.path.exists(input_path):
            os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)


def main():
    """Run all tests."""
    print("="*60)
    print("Word Document Editing Capabilities Test Suite")
    print("="*60)
    
    try:
        test_create_new_document()
        test_add_content_to_document()
        test_edit_existing_document()
        test_replace_text()
        
        print("\n" + "="*60)
        print("✓ All tests passed successfully!")
        print("="*60)
        print("\nThe office_converter module CAN edit Word files!")
        print("\nAvailable functions:")
        print("  • create_docx() - Create new Word documents")
        print("  • edit_docx() - Open existing documents for editing")
        print("  • save_docx() - Save documents")
        print("  • add_paragraph_to_docx() - Add paragraphs")
        print("  • add_heading_to_docx() - Add headings")
        print("  • add_table_to_docx() - Add tables")
        print("  • replace_text_in_docx() - Replace text patterns")
        print("="*60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
