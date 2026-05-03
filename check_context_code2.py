import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('d:/Projects/LEIDOS/Lambda/agent_executor.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Show lines 3166 to 3320
for i, line in enumerate(lines[3165:3320], 3166):
    print(f"{i}: {line}", end='')
