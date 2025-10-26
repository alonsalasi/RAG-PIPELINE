import json
import traceback
from worker import process_message


def lambda_handler(event, context):
    """
    Lambda entrypoint for ingestion.
    Triggered by SQS messages that originate from S3 → SNS → SQS.
    Unwraps SNS envelopes to extract the actual S3 event and
    passes it to process_message() in worker.py.
    """

    print("🚀 Ingestion Lambda triggered.")
    print("DEBUG raw event:", json.dumps(event)[:1000])

    # Each record represents one SQS message
    for record in event.get("Records", []):
        try:
            message_id = record.get("messageId", "unknown")
            body_raw = record.get("body", "")
            print(f"\n🟦 Processing SQS message {message_id}")

            # Step 1️⃣: Parse SQS body
            try:
                body = json.loads(body_raw)
            except Exception:
                print("⚠️ Could not JSON-decode body, passing as string.")
                body = {"body": body_raw}

            # Step 2️⃣: Handle possible SNS wrapping
            # If coming from S3 → SNS → SQS, the body looks like:
            # {"Type": "Notification", "Message": "{\"Records\": [...]}"}
            if "Message" in body:
                try:
                    s3_event = json.loads(body["Message"])
                    print("✅ Unwrapped SNS message to S3 event.")
                except Exception as e:
                    print(f"❌ Failed to parse SNS 'Message': {e}")
                    continue
            else:
                # Direct invocation or already S3-like structure
                s3_event = body

            # Step 3️⃣: Validate S3 event
            if not s3_event.get("Records") and "s3_key" not in s3_event:
                print("⚠️ Event does not contain Records or s3_key — skipping.")
                continue

            # Step 4️⃣: Process event
            print("🧩 Passing event to process_message() ...")
            success = process_message(s3_event)

            if not success:
                raise Exception("process_message() returned False")

            print(f"✅ Message {message_id} processed successfully.\n")

        except Exception as e:
            print(f"🚨 LAMBDA EXECUTION FAILED for message {record.get('messageId', 'unknown')}: {e}")
            traceback.print_exc()
            # Re-raise to signal SQS for retry (if configured)
            raise

    print("🎉 All records processed.")
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Processing complete"})
    }
