#!/usr/bin/env python3
"""
Test script for semantic chunking functionality.
Run this to validate that tables and structured content are preserved.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'Lambda'))

from semantic_chunker import create_semantic_chunks

def test_table_preservation():
    """Test that tables are kept intact during chunking."""
    
    # Sample text with table that should NOT be split
    sample_text = """
Vehicle Specifications Report

The following table contains detailed specifications for the 2024 Honda Accord:

Engine Type: 1.5L Turbo 4-Cylinder
Horsepower: 192 hp @ 5,500 rpm
Torque: 192 lb-ft @ 1,500-3,000 rpm
Transmission: CVT Automatic
Fuel Economy City: 32 mpg
Fuel Economy Highway: 42 mpg
Fuel Economy Combined: 36 mpg
Seating Capacity: 5 passengers
Cargo Volume: 16.7 cubic feet
Wheelbase: 111.4 inches
Overall Length: 195.7 inches
Overall Width: 73.3 inches
Overall Height: 57.1 inches
Curb Weight: 3,131 lbs

Additional Features:
- Honda Sensing Safety Suite
- Apple CarPlay/Android Auto
- Dual-zone automatic climate control
- LED headlights and taillights
- 17-inch alloy wheels

This vehicle represents excellent value in the midsize sedan segment.
"""

    print("Testing semantic chunking with table data...")
    print("=" * 60)
    
    chunks = create_semantic_chunks(sample_text, "Honda_Accord_2024", max_chunk_size=800)
    
    print(f"Generated {len(chunks)} chunks:")
    print()
    
    for i, chunk in enumerate(chunks):
        print(f"CHUNK {i+1} (Type: {chunk.metadata.get('content_type', 'unknown')}):")
        print(f"Size: {len(chunk.page_content)} characters")
        print(f"Contains structured data: {chunk.metadata.get('contains_structured_data', False)}")
        print(f"Contains specifications: {chunk.metadata.get('contains_specifications', False)}")
        print("-" * 40)
        print(chunk.page_content[:300] + "..." if len(chunk.page_content) > 300 else chunk.page_content)
        print("=" * 60)
        print()

def test_markdown_table():
    """Test markdown table preservation."""
    
    markdown_text = """
# Vehicle Comparison

| Model | Engine | MPG City | MPG Highway | Price |
|-------|--------|----------|-------------|-------|
| Honda Accord | 1.5L Turbo | 32 | 42 | $27,295 |
| Toyota Camry | 2.5L 4-Cyl | 28 | 39 | $26,320 |
| Nissan Altima | 2.5L 4-Cyl | 28 | 39 | $25,300 |
| Hyundai Sonata | 2.5L 4-Cyl | 27 | 37 | $25,500 |

The above comparison shows fuel efficiency across popular midsize sedans.

## Performance Notes
All vehicles listed provide excellent reliability and comfort for daily commuting.
"""

    print("Testing markdown table preservation...")
    print("=" * 60)
    
    chunks = create_semantic_chunks(markdown_text, "Vehicle_Comparison", max_chunk_size=600)
    
    for i, chunk in enumerate(chunks):
        print(f"CHUNK {i+1} (Type: {chunk.metadata.get('content_type', 'unknown')}):")
        print(f"Table detected: {'|' in chunk.page_content}")
        print("-" * 40)
        print(chunk.page_content)
        print("=" * 60)
        print()

def test_large_table_splitting():
    """Test how large tables are split while preserving structure."""
    
    # Create a large table that exceeds chunk size
    large_table = """
Vehicle Inventory Report

Model: Honda Accord
Year: 2024
VIN: 1HGCV1F30PA123456
Engine: 1.5L Turbo
Color: Midnight Black
Mileage: 15 miles
Price: $27,295
Status: Available

Model: Toyota Camry
Year: 2024  
VIN: 4T1G11AK8PU123457
Engine: 2.5L 4-Cylinder
Color: Super White
Mileage: 8 miles
Price: $26,320
Status: Available

Model: Nissan Altima
Year: 2024
VIN: 1N4BL4BV8PC123458
Engine: 2.5L 4-Cylinder  
Color: Pearl White
Mileage: 22 miles
Price: $25,300
Status: Sold

Model: Hyundai Sonata
Year: 2024
VIN: KMHL14JA8PA123459
Engine: 2.5L 4-Cylinder
Color: Calypso Red
Mileage: 5 miles
Price: $25,500
Status: Available

Model: Subaru Legacy
Year: 2024
VIN: 4S3BWAC60P3123460
Engine: 2.5L Boxer
Color: Crystal Black
Mileage: 12 miles
Price: $24,895
Status: Available
"""

    print("Testing large table splitting...")
    print("=" * 60)
    
    chunks = create_semantic_chunks(large_table, "Vehicle_Inventory", max_chunk_size=400)
    
    for i, chunk in enumerate(chunks):
        print(f"CHUNK {i+1} (Type: {chunk.metadata.get('content_type', 'unknown')}):")
        print(f"Size: {len(chunk.page_content)} chars")
        print(f"Is continuation: {chunk.metadata.get('is_continuation', False)}")
        print("-" * 40)
        print(chunk.page_content)
        print("=" * 60)
        print()

if __name__ == "__main__":
    print("SEMANTIC CHUNKING TEST SUITE")
    print("=" * 60)
    print()
    
    test_table_preservation()
    test_markdown_table()
    test_large_table_splitting()
    
    print("✅ All tests completed!")
    print("\nKey Benefits of Semantic Chunking:")
    print("- Tables and structured data stay together")
    print("- Related content blocks are grouped")
    print("- Headers stay with their content")
    print("- Large tables split intelligently with headers preserved")
    print("- Metadata indicates content type for better retrieval")