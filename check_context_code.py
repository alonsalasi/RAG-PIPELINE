import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('d:/Projects/LEIDOS/Lambda/agent_executor.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

# Find process_agent_query_background and show the relevant section
in_func = False
for i, line in enumerate(lines, 1):
    if 'def process_agent_query_background' in line:
        in_func = True
    if in_func and i >= 2230:  # start from around where history loading is
        print(f"{i}: {line}", end='')
    if in_func and i > 2340:
        break
