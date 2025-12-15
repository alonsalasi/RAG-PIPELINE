#!/usr/bin/env python3
"""
Test script for Word document editing functionality.
Demonstrates creating, editing, and modifying DOCX files.
"""
import os
import sys
import tempfile
from pathlib import Path

# Add Lambda directory to path for imports
lambda_dir = Path(__file__).parent.parent / 'Lambda'
sys.path.insert(0, str(lambda_dir))

from office_converter import create_docx, edit_docx, extract_docx

def test_create_docx():
    """Test creating a new Word document from scratch."""
    print("\n=== Test 1: Creating a new Word document ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_new_document.docx")
        
        content = {
            'title': 'Test Document',
            'headings': [
                {'text': 'Introduction', 'level': 1},
                {'text': 'Methods', 'level': 1}
            ],
            'paragraphs': [
                'This is a test paragraph created by the Word editing functionality.',
                'This demonstrates the ability to create Word documents programmatically.',
                {'text': 'This is a styled paragraph.', 'style': 'Intense Quote'}
            ],
            'tables': [
                {
                    'rows': 3,
                    'cols': 3,
                    'data': [
                        ['Header 1', 'Header 2', 'Header 3'],
                        ['Row 1 Col 1', 'Row 1 Col 2', 'Row 1 Col 3'],
                        ['Row 2 Col 1', 'Row 2 Col 2', 'Row 2 Col 3']
                    ]
                }
            ]
        }
        
        success = create_docx(output_path, content)
        
        if success and os.path.exists(output_path):
            print(f"✓ Successfully created Word document: {output_path}")
            print(f"  File size: {os.path.getsize(output_path)} bytes")
            
            # Verify by reading it back
            text, _ = extract_docx(output_path)
            print(f"  Extracted text length: {len(text)} characters")
            print(f"  Preview: {text[:200]}...")
            return output_path
        else:
            print("✗ Failed to create Word document")
            return None

def test_edit_docx_add_content():
    """Test adding content to an existing document."""
    print("\n=== Test 2: Adding content to an existing document ===")
    
    # First create a base document
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base_document.docx")
        
        # Create base document
        create_docx(base_path, {'title': 'Original Document', 'paragraphs': ['Original content.']})
        
        # Now edit it
        output_path = os.path.join(tmpdir, "edited_document.docx")
        modifications = {
            'add_heading': [
                {'text': 'New Section', 'level': 1},
                {'text': 'Subsection', 'level': 2}
            ],
            'add_paragraph': [
                {'text': 'This is a newly added paragraph.'},
                {'text': 'Another new paragraph with more content.'}
            ],
            'add_table': {
                'rows': 2,
                'cols': 2,
                'data': [
                    ['Column A', 'Column B'],
                    ['Data 1', 'Data 2']
                ]
            }
        }
        
        success = edit_docx(base_path, output_path, modifications)
        
        if success and os.path.exists(output_path):
            print(f"✓ Successfully edited Word document: {output_path}")
            print(f"  File size: {os.path.getsize(output_path)} bytes")
            
            # Verify changes
            text, _ = extract_docx(output_path)
            print(f"  Extracted text length: {len(text)} characters")
            
            # Check if new content is present
            if 'New Section' in text and 'newly added paragraph' in text:
                print("  ✓ New content verified in document")
            else:
                print("  ✗ Warning: New content not found")
            
            return output_path
        else:
            print("✗ Failed to edit Word document")
            return None

def test_edit_docx_replace_text():
    """Test replacing text in an existing document."""
    print("\n=== Test 3: Replacing text in a document ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base_document.docx")
        
        # Create base document with text to replace
        create_docx(base_path, {
            'title': 'Test Document',
            'paragraphs': [
                'The quick brown fox jumps over the lazy dog.',
                'PLACEHOLDER text that needs to be replaced.',
                'Another PLACEHOLDER in this sentence.'
            ]
        })
        
        # Replace text
        output_path = os.path.join(tmpdir, "replaced_document.docx")
        modifications = {
            'replace_text': [
                {'old': 'PLACEHOLDER', 'new': 'UPDATED'},
                {'old': 'fox', 'new': 'cat'}
            ]
        }
        
        success = edit_docx(base_path, output_path, modifications)
        
        if success and os.path.exists(output_path):
            print(f"✓ Successfully replaced text in Word document: {output_path}")
            
            # Verify replacements
            text, _ = extract_docx(output_path)
            
            if 'PLACEHOLDER' not in text and 'UPDATED' in text:
                print("  ✓ Text replacement verified: PLACEHOLDER → UPDATED")
            else:
                print("  ✗ Warning: PLACEHOLDER replacement failed")
            
            if 'fox' not in text and 'cat' in text:
                print("  ✓ Text replacement verified: fox → cat")
            else:
                print("  ✗ Warning: fox replacement failed")
            
            print(f"  Modified text preview: {text[:200]}...")
            return output_path
        else:
            print("✗ Failed to replace text in document")
            return None

def test_edit_docx_inplace():
    """Test editing a document in-place (same file)."""
    print("\n=== Test 4: In-place document editing ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_path = os.path.join(tmpdir, "inplace_document.docx")
        
        # Create initial document
        create_docx(doc_path, {'title': 'Original Title', 'paragraphs': ['Original text.']})
        
        # Get original size
        original_size = os.path.getsize(doc_path)
        original_text, _ = extract_docx(doc_path)
        
        # Edit in-place (no output_path specified)
        modifications = {
            'add_paragraph': {'text': 'This was added in-place.'},
            'replace_text': {'old': 'Original', 'new': 'Modified'}
        }
        
        success = edit_docx(doc_path, modifications=modifications)
        
        if success:
            new_size = os.path.getsize(doc_path)
            new_text, _ = extract_docx(doc_path)
            
            print(f"✓ Successfully edited document in-place")
            print(f"  Original size: {original_size} bytes → New size: {new_size} bytes")
            print(f"  Original text length: {len(original_text)} chars → New length: {len(new_text)} chars")
            
            if 'Modified Title' in new_text and 'added in-place' in new_text:
                print("  ✓ In-place modifications verified")
            else:
                print("  ✗ Warning: In-place modifications not fully verified")
            
            return doc_path
        else:
            print("✗ Failed to edit document in-place")
            return None

def main():
    """Run all tests."""
    print("=" * 60)
    print("Word Document Editing Functionality Tests")
    print("=" * 60)
    
    try:
        results = []
        
        # Run all tests
        results.append(("Create new document", test_create_docx()))
        results.append(("Add content to document", test_edit_docx_add_content()))
        results.append(("Replace text in document", test_edit_docx_replace_text()))
        results.append(("In-place editing", test_edit_docx_inplace()))
        
        # Summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        
        passed = sum(1 for _, result in results if result is not None)
        total = len(results)
        
        for test_name, result in results:
            status = "✓ PASS" if result is not None else "✗ FAIL"
            print(f"{status}: {test_name}")
        
        print(f"\nTotal: {passed}/{total} tests passed")
        print("=" * 60)
        
        return passed == total
        
    except Exception as e:
        print(f"\n✗ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
