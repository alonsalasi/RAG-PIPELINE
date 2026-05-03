import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

for fname in ['d:/Projects/LEIDOS/Lambda/agent_executor.py', 'd:/Projects/LEIDOS/Lambda/worker.py']:
    with open(fname, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    hits = [(i+1, l.rstrip()) for i, l in enumerate(lines) if ".replace('.pdf'" in l or '.replace(".pdf"' in l]
    print(f"\n{fname}:")
    if hits:
        for lineno, line in hits:
            print(f"  Line {lineno}: {line.strip()}")
    else:
        print("  No occurrences found ✓")
