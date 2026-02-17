import re

query = "Compare 05.MOF_FinOps - May 7_v1 and 06.MOF_FinOps - June 17_s pricing for me in a table format"

patterns = [
    r'["\"]([^\"\"]+)["\"]',  # Pattern 0: Quoted
    r'(?:the\s+)?file\s+["\"]([^\"]+)["\"]',  # Pattern 1: file "name"
    r'(?:the\s+)?(?:file|document)\s+([A-Za-z0-9][^?]+?)\?',  # Pattern 2: document NAME?
    r'(?:from|in)\s+(?:the\s+)?document[:\s]+["\']?([^"\'?]+?)["\']?\s*(\?|$)',  # Pattern 3: from document
]

print("Testing patterns against query:")
print(f"Query: {query}\n")

for i, pattern in enumerate(patterns):
    matches = re.findall(pattern, query, re.IGNORECASE)
    print(f"Pattern {i}: {pattern}")
    print(f"  Matches: {matches}\n")

# Test what the agent should extract
print("\n=== What we NEED to extract ===")
print("Document 1: 05.MOF_FinOps - May 7_v1")
print("Document 2: 06.MOF_FinOps - June 17_s")
