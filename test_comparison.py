import re

# Test the current patterns
query = "Compare 05.MOF_FinOps - May 7_v1 and 06.MOF_FinOps - June 17_s pricing for me in a table format"

# NEW PATTERN for comparison queries: "Compare X and Y"
comparison_pattern = r'[Cc]ompare\s+(.+?)\s+and\s+(.+?)(?:\s+(?:pricing|for|in|to)|\s*$)'

match = re.search(comparison_pattern, query)
if match:
    doc1 = match.group(1).strip()
    doc2 = match.group(2).strip()
    print(f"MATCH FOUND!")
    print(f"Document 1: '{doc1}'")
    print(f"Document 2: '{doc2}'")
else:
    print("NO MATCH")
