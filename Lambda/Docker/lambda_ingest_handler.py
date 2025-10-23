import json
import os
import time

# Import the core logic from worker.py
from worker import process_message

def lambda_handler(event, context):
    """
    Handles SQS events triggered by S3 uploads.
    """
    
    # SQS events arrive with a 'Records' array, even if batch_size=1
    for record in event['Records']:
        try:
            # SQS message body contains the SNS notification JSON
            sns_message_json = record['body']
            
            # Process the message using the core worker logic
            success = process_message(sns_message_json)
            
            if not success:
                # If processing failed, raise an exception so SQS knows to retry the message
                # This ensures message durability until processing succeeds or moves to a DLQ.
                raise Exception(f"Worker logic failed to process message {record['messageId']}")
        
        except Exception as e:
            # CRITICAL: Re-raise the exception. This signals SQS to keep the message 
            # in the queue for a retry (based on visibility timeout).
            print(f"LAMBDA EXECUTION FAILED FOR MESSAGE {record['messageId']}: {e}")
            raise

    return {'statusCode': 200, 'body': json.dumps({'message': 'Processing complete'})}
