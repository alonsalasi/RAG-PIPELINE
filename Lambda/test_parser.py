"""Test document parser locally."""
import base64

# Test with a simple text file
test_text = "Test document content"
file_bytes = test_text.encode('utf-8')

from document_parser import parse_document

try:
    result = parse_document(file_bytes, "test.txt")
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
