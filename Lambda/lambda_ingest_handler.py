import json
import traceback
import logging
import boto3
import os
from worker import process_message
from document_parser import parse_document

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Lambda entrypoint for document ingestion.
    Triggered by SQS (which receives S3 ObjectCreated events) or direct invocation.
    """
    # Handle direct invocation for autofill parsing
    if event.get("action") == "parse_autofill_document":
        return handle_parse_autofill(event)
    
    logger.info("🚀 INGESTION Lambda triggered (not API Lambda).")
    records_count = len(event.get('Records', []))
    logger.info(f"Event type: {type(event).__name__}, Records count: {records_count}")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"DEBUG raw event: {json.dumps(event)[:1000]}")

    # FIX: Use this list to track failed messages
    batch_item_failures = []

    # Loop through SQS messages
    for record in event.get("Records", []):
        msg_id = record.get("messageId", "unknown")
        logger.info(f"🟦 Processing record {msg_id}")

        try:
            # process_message will now raise an error on failure
            process_message(record)
            
        except Exception as inner_e:
            # Log error type without exposing sensitive details
            logger.error(f"⚠️ Failed processing record {msg_id}: {type(inner_e).__name__}. Adding to batch failures.")
            
            # Add the failed messageId to the list for SQS
            batch_item_failures.append({"itemIdentifier": msg_id})

    logger.info(f"🎉 INGESTION batch processing complete. {len(batch_item_failures)} failures.")
    
    # FIX: Return the SQS partial batch response
    return {"batchItemFailures": batch_item_failures}


def handle_parse_autofill(event):
    """Parse document for autofill feature."""
    session_id = event.get("sessionId")
    s3_key = event.get("s3Key")
    filename = event.get("filename")
    output_key = event.get("outputKey", f"document-autofill/sessions/{session_id}/source_text.txt")
    bucket = os.getenv('S3_BUCKET')
    
    try:
        s3_client = boto3.client('s3')
        
        # Download file
        obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
        file_bytes = obj['Body'].read()
        
        # Parse
        text = parse_document(file_bytes, filename)
        
        # Save
        s3_client.put_object(Bucket=bucket, Key=output_key, Body=text.encode('utf-8'))
        
        logger.info(f"Parsed {filename}: {len(text)} chars")
        return {"statusCode": 200, "body": json.dumps({"status": "success"})}
        
    except Exception as e:
        logger.error(f"Parse failed: {e}", exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
