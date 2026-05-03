import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('d:/Projects/LEIDOS/Lambda/agent_executor.py', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    if 'Load conversation history' in line or 'load_session_history' in line or 'previous messages' in line:
        print(f"{i}: {line}", end='')
