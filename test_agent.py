"""
Test script to diagnose Bedrock Agent configuration issues
"""
import boto3
import json
import os

def test_agent():
    """Test if agent is calling the search action"""
    
    # Get configuration from environment
    agent_id = os.getenv("BEDROCK_AGENT_ID")
    alias_id = os.getenv("BEDROCK_AGENT_ALIAS_ID")
    region = os.getenv("AWS_REGION", "us-east-1")
    
    if not agent_id or not alias_id:
        print("❌ ERROR: Set BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID environment variables")
        return
    
    print(f"🔧 Testing Agent Configuration")
    print(f"   Agent ID: {agent_id}")
    print(f"   Alias ID: {alias_id}")
    print(f"   Region: {region}")
    print()
    
    # Create Bedrock client
    bedrock = boto3.client('bedrock-agent-runtime', region_name=region)
    
    # Test query
    test_query = "What documents do you have? Search for any information."
    print(f"📝 Test Query: {test_query}")
    print()
    
    try:
        # Invoke agent with trace enabled
        response = bedrock.invoke_agent(
            agentId=agent_id,
            agentAliasId=alias_id,
            sessionId='diagnostic-test',
            inputText=test_query,
            enableTrace=True
        )
        
        print("✅ Agent invoked successfully")
        print()
        
        # Process response and look for search action calls
        search_called = False
        answer = ""
        
        for event in response['completion']:
            # Check for trace events
            if 'trace' in event:
                trace = event['trace']
                
                # Check orchestration trace
                if 'orchestrationTrace' in trace:
                    orch = trace['orchestrationTrace']
                    
                    # Check if agent is invoking an action
                    if 'invocationInput' in orch:
                        inv_input = orch['invocationInput']
                        if 'actionGroupInvocationInput' in inv_input:
                            action_input = inv_input['actionGroupInvocationInput']
                            api_path = action_input.get('apiPath', '')
                            
                            if api_path == '/search':
                                search_called = True
                                print("🔍 SEARCH ACTION CALLED!")
                                print(f"   Action Group: {action_input.get('actionGroupName', 'N/A')}")
                                
                                # Extract search query
                                request_body = action_input.get('requestBody', {})
                                content = request_body.get('content', {})
                                app_json = content.get('application/json', {})
                                properties = app_json.get('properties', [])
                                
                                for prop in properties:
                                    if prop.get('name') == 'query':
                                        print(f"   Search Query: {prop.get('value', 'N/A')}")
                                print()
                    
                    # Check observation (search results)
                    if 'observation' in orch:
                        obs = orch['observation']
                        if 'actionGroupInvocationOutput' in obs:
                            print("📊 SEARCH RESULTS RECEIVED")
                            output = obs['actionGroupInvocationOutput']
                            response_body = output.get('text', '')
                            print(f"   Result length: {len(response_body)} characters")
                            print()
            
            # Collect answer
            if 'chunk' in event and 'bytes' in event['chunk']:
                answer += event['chunk']['bytes'].decode('utf-8')
        
        print("=" * 60)
        print("DIAGNOSTIC RESULTS:")
        print("=" * 60)
        
        if search_called:
            print("✅ SUCCESS: Agent IS calling the search action")
            print("   Your agent is properly configured!")
        else:
            print("❌ PROBLEM: Agent is NOT calling the search action")
            print()
            print("   This means your agent doesn't know to search PDFs.")
            print()
            print("   FIX: Update your agent instructions to include:")
            print("   'You MUST use the search tool to find information")
            print("   from uploaded PDF documents before answering.'")
            print()
            print("   See check_agent_config.md for detailed instructions.")
        
        print()
        print(f"📝 Agent Response ({len(answer)} chars):")
        print("-" * 60)
        print(answer[:500])
        if len(answer) > 500:
            print("...")
        print("-" * 60)
        
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}")
        print(f"   {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent()
