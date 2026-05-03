import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('d:/Projects/LEIDOS/Lambda/agent_executor.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

for lineno in [1511, 1615]:
    print(f"\n--- Line {lineno} context ---")
    for i in range(max(0, lineno-3), min(len(lines), lineno+3)):
        print(f"{i+1}: {lines[i].rstrip()}")
