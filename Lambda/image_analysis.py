import base64
import json
import logging
import os
import boto3
from botocore.client import Config

logger = logging.getLogger(__name__)

_bedrock_client = None

def get_bedrock_client():
    """Get or create Bedrock Runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        region = os.environ.get('AWS_REGION', 'us-east-1')
        _bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=region,
            config=Config(connect_timeout=5, read_timeout=60)
        )
    return _bedrock_client

def analyze_image_with_claude(image_bytes, page_num, doc_name):
    """Use Bedrock Claude Vision to analyze images and tables."""
    try:
        client = get_bedrock_client()
        
        # Encode image to base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # Determine media type
        media_type = "image/jpeg"
        if image_bytes[:4] == b'\x89PNG':
            media_type = "image/png"
        
        # Claude Vision prompt - emphasize text extraction including Hebrew handwriting
        prompt = f"""Extract and transcribe ALL text from this image from document '{doc_name}'.

If the image contains:
- HANDWRITTEN TEXT (including Hebrew): Carefully read and transcribe it character by character. Hebrew handwriting can be challenging - focus on each letter.
- PRINTED TEXT: Extract all visible text including logos, labels, captions
- TABLES: State "TABLE DETECTED" and extract:
  Row 1: [col1] | [col2] | [col3]
  Row 2: [col1] | [col2] | [col3]
  NOTE: Hebrew ו (vav) looks like | but is NOT a delimiter

Also describe:
- BRAND/MANUFACTURER if identifiable (e.g., "Hyundai Tucson")
- Item type and colors
- Key visual features

For handwritten Hebrew: Take extra care with similar letters like ד/ר, ה/ח, ו/ז, כ/ב, ס/ם, ע/צ.

If text is truly illegible, state "TEXT ILLEGIBLE" but try your best first."""
        
        # Bedrock API call
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }]
        }
        
        response = client.invoke_model(
            modelId="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            body=json.dumps(body)
        )
        
        response_body = json.loads(response['body'].read())
        description = response_body['content'][0]['text']
        
        logger.info(f"Claude Vision analysis (page {page_num}): {description[:100]}...")
        
        return {
            'description': f"Page {page_num} from {doc_name}: {description}",
            'raw_description': description
        }
        
    except Exception as e:
        logger.error(f"Claude Vision failed: {e}")
        return {
            'description': f"Image from {doc_name}, page {page_num}",
            'raw_description': ''
        }
