import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('d:/Projects/LEIDOS/Lambda/worker.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

keywords = ['replace', 'base_name', 'source_file', '.pdf', 'rsplit', 'split(']
for i, line in enumerate(lines, 1):
    if any(k in line for k in keywords):
        print(f"{i}: {line}", end='')
