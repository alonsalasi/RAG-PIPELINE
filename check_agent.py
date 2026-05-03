import boto3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

client = boto3.client('bedrock-agent')
agent = client.get_agent(agentId='8YWB06TOFD')['agent']

print("Model:", agent.get('foundationModel'))
instruction = agent.get('instruction', '')
print("Instruction length (chars):", len(instruction))
print("Instruction length (approx tokens):", len(instruction) // 4)
print("\nInstruction preview (first 500 chars):")
print(instruction[:500])
