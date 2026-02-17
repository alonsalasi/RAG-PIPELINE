import re

# Read uploads
with open('uploads.txt', 'r', encoding='utf-8') as f:
    uploads = f.readlines()

# Read processed
with open('processed.txt', 'r', encoding='utf-8') as f:
    processed = f.readlines()

# Extract filenames
upload_files = set()
for line in uploads:
    match = re.search(r'\S+\.(pdf|pptx|docx|xlsx|jpg|jpeg|png|tiff)$', line, re.IGNORECASE)
    if match:
        filename = match.group(0)
        # Remove extension for comparison
        base = filename.rsplit('.', 1)[0]
        upload_files.add(base)

processed_files = set()
for line in processed:
    match = re.search(r'\S+\.json$', line)
    if match:
        filename = match.group(0)
        # Remove .json and timestamp prefix
        base = filename.replace('.json', '')
        if '_' in base:
            parts = base.split('_', 1)
            if parts[0].isdigit() and len(parts[0]) == 10:
                base = parts[1]
        processed_files.add(base)

# Find unprocessed
unprocessed = upload_files - processed_files

print(f"Total uploads: {len(upload_files)}")
print(f"Total processed: {len(processed_files)}")
print(f"Unprocessed: {len(unprocessed)}")
print("\nUnprocessed files:")
for f in sorted(unprocessed):
    print(f"  {f}")
