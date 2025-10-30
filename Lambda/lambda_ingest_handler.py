import json
import traceback
import logging
from worker import process_message

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Lambda entrypoint for document ingestion.
    Triggered by SQS (which receives S3 ObjectCreated events).
    """
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
