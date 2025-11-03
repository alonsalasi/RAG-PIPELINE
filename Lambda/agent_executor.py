import json
import boto3
import logging
import os
import time
import uuid
from urllib.parse import unquote_plus
from decimal import Decimal
from functools import wraps
import contextvars

# -----------------------------------------------------------
# Logging with Correlation ID
# -----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - [%(correlation_id)s] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Context variable for correlation ID
correlation_id_var = contextvars.ContextVar('correlation_id', default='no-correlation-id')

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id_var.get()
        return True

logger.addFilter(CorrelationIdFilter())

# -----------------------------------------------------------
# Security Utils
# -----------------------------------------------------------
def sanitize_for_logging(text, max_length=100):
    """Sanitize text for logging to prevent log injection attacks."""
    if not text:
        return "[EMPTY]"
    # Convert to string and remove control characters
    text_str = str(text)
    # Remove all control characters including newlines, tabs, etc.
    safe = ''.join(c if c.isprintable() and ord(c) >= 32 else '_' for c in text_str)
    # Truncate and add indicator if truncated
    if len(safe) > max_length:
        return safe[:max_length-3] + "..."
    return safe

def validate_filename(filename):
    if not filename or not isinstance(filename, str):
        raise ValueError("Invalid filename")
    filename = filename.strip()
    if not filename or filename.startswith('.') or '/' in filename or '\\' in filename:
        raise ValueError("Invalid filename")
    if len(filename) > 255:
        raise ValueError("Filename too long")
    return filename

def retry_with_backoff(max_retries=3):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(2 ** attempt)
        return wrapper
    return decorator

# -----------------------------------------------------------
# AWS Setup
# -----------------------------------------------------------
from botocore.client import Config

# Thread-safe client initialization
_s3_client = None
_bedrock_client = None
_embeddings_client = None
_faiss_cache = {}

def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", config=Config(signature_version='s3v4', connect_timeout=5, read_timeout=60))
    return _s3_client

def get_bedrock_client():
    """Get Bedrock client with proper error handling."""
    global _bedrock_client
    if _bedrock_client is None:
        region = os.getenv("AWS_REGION")
        if not region:
            raise ValueError("AWS_REGION must be configured")
        _bedrock_client = boto3.client(
            "bedrock-agent-runtime",
            region_name=region,
            config=Config(connect_timeout=5, read_timeout=60)
        )
        logger.info(f"Bedrock client initialized: {region}")
    return _bedrock_client

def get_embeddings_client():
    """Get embeddings client with proper error handling."""
    global _embeddings_client
    if _embeddings_client is None:
        from langchain_aws import BedrockEmbeddings
        region = os.getenv("AWS_REGION")
        if not region:
            raise ValueError("AWS_REGION must be configured")
        model_id = os.getenv("EMBEDDINGS_MODEL_ID", "cohere.embed-multilingual-v3")
        _embeddings_client = BedrockEmbeddings(model_id=model_id, region_name=region)
        logger.info(f"Embeddings client initialized: {model_id}")
    return _embeddings_client

# Get S3 bucket from environment
BUCKET = os.getenv("S3_BUCKET")
if not BUCKET:
    logger.error("S3_BUCKET environment variable not configured")
    raise ValueError("S3_BUCKET environment variable must be set")

@retry_with_backoff(max_retries=2)
def preload_master_index():
    """Preload master FAISS index at Lambda startup."""
    from langchain_community.vectorstores import FAISS
    import shutil
    
    cache_key = "master_index"
    cache_dir = "/tmp/master_index"
    s3_client = get_s3_client()
    
    try:
        s3_client.head_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
    except s3_client.exceptions.ClientError as e:
        if e.response.get('Error', {}).get('Code') == '404':
            logger.info("No master index to preload")
        else:
            logger.warning(f"Error checking master index: {type(e).__name__}")
        return
    except Exception as e:
        logger.error(f"Unexpected error: {type(e).__name__}")
        return
    
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
    
    os.makedirs(cache_dir, exist_ok=True)
    
    index_file = os.path.join(cache_dir, "index.faiss")
    pkl_file = os.path.join(cache_dir, "index.pkl")
    
    s3_client.download_file(BUCKET, "vector_store/master/index.faiss", index_file)
    s3_client.download_file(BUCKET, "vector_store/master/index.pkl", pkl_file)
    
    embeddings = get_embeddings_client()
    master_index = FAISS.load_local(cache_dir, embeddings, allow_dangerous_deserialization=True)
    _faiss_cache[cache_key] = master_index
    
    logger.info(f"Preloaded master index: {master_index.index.ntotal} vectors")

try:
    preload_master_index()
except Exception as e:
    logger.error(f"Startup preload failed: {type(e).__name__}")


def list_all_s3_objects(bucket, prefix, max_keys=1000):
    """List all S3 objects with pagination support and limits."""
    if not bucket or not isinstance(bucket, str):
        raise ValueError("Invalid bucket name")
    if not prefix or not isinstance(prefix, str):
        raise ValueError("Invalid prefix")
    
    s3_client = get_s3_client()
    objects = []
    continuation_token = None
    total_fetched = 0
    
    while total_fetched < max_keys:
        params = {
            'Bucket': bucket,
            'Prefix': prefix,
            'MaxKeys': min(1000, max_keys - total_fetched)
        }
        if continuation_token:
            params['ContinuationToken'] = continuation_token
        
        response = s3_client.list_objects_v2(**params)
        batch = response.get('Contents', [])
        objects.extend(batch)
        total_fetched += len(batch)
        
        if not response.get('IsTruncated', False) or total_fetched >= max_keys:
            break
        continuation_token = response.get('NextContinuationToken')
    
    return objects

def batch_delete_s3_objects(bucket, keys):
    """Delete multiple S3 objects in batches of 1000."""
    if not keys:
        return 0
    if not bucket or not isinstance(bucket, str):
        raise ValueError("Invalid bucket name")
    
    s3_client = get_s3_client()
    deleted_count = 0
    
    for i in range(0, len(keys), 1000):
        batch = keys[i:i+1000]
        delete_dict = {'Objects': [{'Key': k} for k in batch], 'Quiet': True}
        try:
            s3_client.delete_objects(Bucket=bucket, Delete=delete_dict)
            deleted_count += len(batch)
        except Exception as e:
            logger.error(f"Batch delete failed: {type(e).__name__}")
            raise
    
    return deleted_count

# -----------------------------------------------------------
# Utilities
# -----------------------------------------------------------
def cors_response(body=None, status=200):
    """Return a standard CORS-enabled response."""
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        },
        "body": json.dumps(body or {}),
    }


# -----------------------------------------------------------
# /get-upload-url
# -----------------------------------------------------------
def handle_get_upload_url():
    """Generate a presigned S3 URL for direct PDF upload."""
    try:
        timestamp = int(time.time())
        key = f"uploads/upload_{timestamp}.pdf"
        s3_client = get_s3_client()
        url = s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": "application/pdf"},
            ExpiresIn=7200,
        )
        logger.info(f"Upload URL generated | Key: {sanitize_for_logging(key)} | Expires: 7200s")
        return cors_response({"uploadUrl": url, "key": key})
    except Exception as e:
        logger.error(f"Upload URL generation failed | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Failed to generate upload URL"}, 500)


# -----------------------------------------------------------
# /list-files
# -----------------------------------------------------------
def handle_list_files():
    """List processed PDFs available for querying."""
    try:
        logger.info("Listing processed files | Bucket: {BUCKET} | Prefix: processed/")
        s3_client = get_s3_client()
        response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix="processed/", MaxKeys=1000)
        files = []
        if "Contents" in response:
            for obj in response["Contents"]:
                key = obj["Key"]
                if key.endswith(".json"):
                    filename = key.split("/")[-1].replace(".json", "")
                    files.append({
                        "filename": filename,
                        "lastModified": obj["LastModified"].isoformat(),
                        "size": obj["Size"]
                    })
        
        logger.info(f"List files complete | Count: {len(files)} | Truncated: {response.get('IsTruncated', False)}")
        return cors_response({"files": files})
    except Exception as e:
        logger.error(f"List files failed | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Failed to list files"}, 500)


# -----------------------------------------------------------
# /delete-file
# -----------------------------------------------------------
def handle_delete_file(filename):
    """Delete a processed PDF and its associated data."""
    try:
        filename = validate_filename(filename)
        logger.info(f"Delete operation started | File: {sanitize_for_logging(filename)}")
        
        s3_client = get_s3_client()
        
        # Delete processed JSON
        processed_key = f"processed/{filename}.json"
        try:
            s3_client.delete_object(Bucket=BUCKET, Key=processed_key)
            logger.info(f"Deleted processed JSON | Key: {sanitize_for_logging(processed_key)}")
        except Exception as e:
            logger.warning(f"Could not delete processed | Key: {processed_key} | Error: {type(e).__name__}")
        
        # Delete uploads (limit search)
        upload_objects = list_all_s3_objects(BUCKET, f"uploads/{filename}", max_keys=100)
        logger.info(f"Found {len(upload_objects)} upload objects")
        for obj in upload_objects:
            try:
                s3_client.delete_object(Bucket=BUCKET, Key=obj["Key"])
            except Exception as e:
                logger.warning(f"Delete upload failed | Key: {obj['Key']} | Error: {type(e).__name__}")
        
        # Delete images
        image_objects = list_all_s3_objects(BUCKET, f"images/{filename}/", max_keys=500)
        image_keys = [obj["Key"] for obj in image_objects]
        if image_keys:
            deleted_count = batch_delete_s3_objects(BUCKET, image_keys)
            logger.info(f"Deleted images | Count: {deleted_count} | File: {filename}")
        
        # Delete vector store data
        vector_objects = list_all_s3_objects(BUCKET, f"vector_store/{filename}/", max_keys=100)
        vector_keys = [obj["Key"] for obj in vector_objects]
        if vector_keys:
            deleted_count = batch_delete_s3_objects(BUCKET, vector_keys)
            logger.info(f"Deleted vector objects | Count: {deleted_count} | File: {filename}")
        
        # Clear FAISS cache
        if filename in _faiss_cache:
            del _faiss_cache[filename]
            logger.info(f"Cleared FAISS cache | File: {sanitize_for_logging(filename)}")
        
        logger.info(f"Delete operation complete | File: {filename}")
        return cors_response({"message": f"Successfully deleted {filename}"})
    except ValueError as e:
        logger.warning(f"Invalid filename | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": str(e)}, 400)
    except Exception as e:
        logger.error(f"Delete failed | File: {filename} | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Failed to delete file"}, 500)


# -----------------------------------------------------------
# Intelligent Search Function
# -----------------------------------------------------------
def intelligent_search(query, top_k=10):
    """Street-smart search with comprehensive automotive intelligence."""
    try:
        from langchain_community.vectorstores import FAISS
        import re
        
        # Load master index
        cache_key = "master_index"
        if cache_key not in _faiss_cache:
            logger.info("Loading master index")
            cache_dir = "/tmp/master_index"
            
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
                s3_client = get_s3_client()
                s3_client.download_file(BUCKET, "vector_store/master/index.faiss", os.path.join(cache_dir, "index.faiss"))
                s3_client.download_file(BUCKET, "vector_store/master/index.pkl", os.path.join(cache_dir, "index.pkl"))
            
            embeddings = get_embeddings_client()
            master_index = FAISS.load_local(cache_dir, embeddings, allow_dangerous_deserialization=True)
            _faiss_cache[cache_key] = master_index
        
        master_index = _faiss_cache[cache_key]
        query_lower = query.lower()
        
        # STREET-SMART AUTOMOTIVE INTELLIGENCE
        
        # Brands (comprehensive)
        brands = {
            'luxury': ['bmw', 'mercedes', 'audi', 'lexus', 'acura', 'infiniti', 'cadillac', 'lincoln', 'jaguar', 'land rover', 'porsche', 'ferrari', 'lamborghini', 'maserati', 'bentley', 'rolls royce', 'genesis'],
            'mainstream': ['toyota', 'honda', 'ford', 'chevrolet', 'nissan', 'hyundai', 'kia', 'mazda', 'subaru', 'volkswagen', 'mitsubishi', 'volvo'],
            'american': ['ford', 'chevrolet', 'gmc', 'jeep', 'ram', 'dodge', 'chrysler', 'cadillac', 'lincoln', 'buick'],
            'japanese': ['toyota', 'honda', 'nissan', 'mazda', 'subaru', 'mitsubishi', 'lexus', 'acura', 'infiniti'],
            'korean': ['hyundai', 'kia', 'genesis'],
            'german': ['bmw', 'mercedes', 'audi', 'volkswagen', 'porsche'],
            'electric': ['tesla', 'lucid', 'rivian', 'polestar', 'nio']
        }
        all_brands = [brand for category in brands.values() for brand in category]
        detected_brands = [brand for brand in all_brands if brand in query_lower]
        
        # Vehicle types (street-smart)
        vehicle_types = {
            'suv': ['suv', 'crossover', 'cuv', 'utility', 'sport utility'],
            'sedan': ['sedan', '4-door', 'four door', 'saloon'],
            'coupe': ['coupe', '2-door', 'two door', 'sports car'],
            'hatchback': ['hatchback', 'hatch', '5-door'],
            'wagon': ['wagon', 'estate', 'touring'],
            'truck': ['truck', 'pickup', 'f-150', 'silverado', 'ram', 'tacoma', 'frontier'],
            'van': ['van', 'minivan', 'mpv', 'people carrier'],
            'convertible': ['convertible', 'cabriolet', 'roadster', 'drop top'],
            'compact': ['compact', 'small', 'subcompact', 'city car'],
            'midsize': ['midsize', 'mid-size', 'medium', 'family'],
            'fullsize': ['full-size', 'full size', 'large', 'big']
        }
        detected_types = []
        for vtype, keywords in vehicle_types.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_types.append(vtype)
        
        # Colors (comprehensive with synonyms)
        colors = {
            'black': ['black', 'jet black', 'obsidian', 'midnight', 'carbon', 'ebony'],
            'white': ['white', 'pearl white', 'snow white', 'arctic white', 'alpine white'],
            'red': ['red', 'crimson', 'scarlet', 'cherry', 'ruby', 'burgundy', 'maroon'],
            'blue': ['blue', 'navy', 'royal blue', 'sky blue', 'midnight blue', 'sapphire'],
            'silver': ['silver', 'metallic silver', 'platinum', 'chrome'],
            'gray': ['gray', 'grey', 'charcoal', 'slate', 'gunmetal', 'storm'],
            'green': ['green', 'forest green', 'emerald', 'olive', 'lime'],
            'yellow': ['yellow', 'gold', 'amber', 'sunshine'],
            'orange': ['orange', 'copper', 'bronze', 'burnt orange'],
            'brown': ['brown', 'tan', 'beige', 'champagne', 'mocha', 'espresso']
        }
        detected_colors = []
        for color, synonyms in colors.items():
            if any(synonym in query_lower for synonym in synonyms):
                detected_colors.append(color)
        
        # Features & Equipment
        features = {
            'luxury': ['leather', 'sunroof', 'moonroof', 'heated seats', 'premium', 'luxury', 'navigation', 'gps'],
            'performance': ['turbo', 'v6', 'v8', 'awd', '4wd', 'sport', 'performance', 'racing', 'fast'],
            'safety': ['airbags', 'abs', 'stability control', 'backup camera', 'blind spot', 'collision'],
            'tech': ['bluetooth', 'usb', 'android auto', 'apple carplay', 'touchscreen', 'digital'],
            'comfort': ['air conditioning', 'climate control', 'power windows', 'power seats', 'cruise control']
        }
        detected_features = []
        for feature_type, keywords in features.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_features.append(feature_type)
        
        # Condition & Age
        conditions = {
            'new': ['new', 'brand new', '2024', '2023', '2022'],
            'used': ['used', 'pre-owned', 'second hand', 'previously owned'],
            'vintage': ['classic', 'vintage', 'antique', 'collector', 'rare'],
            'damaged': ['damaged', 'accident', 'salvage', 'flood', 'hail']
        }
        detected_conditions = []
        for condition, keywords in conditions.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_conditions.append(condition)
        
        # Price ranges (street-smart understanding)
        price_ranges = {
            'budget': ['cheap', 'affordable', 'budget', 'under 20k', 'under 15k', 'under 10k'],
            'mid_range': ['mid-range', 'moderate', '20k-40k', '25k-35k'],
            'expensive': ['expensive', 'premium', 'luxury', 'high-end', 'over 50k']
        }
        detected_price_ranges = []
        for price_range, keywords in price_ranges.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_price_ranges.append(price_range)
        
        # Content type detection (enhanced)
        content_preferences = {
            'images': ['image', 'picture', 'photo', 'show', 'display', 'visual', 'see', 'look', 'view'],
            'specs': ['specs', 'specifications', 'details', 'features', 'options', 'equipment'],
            'reviews': ['review', 'opinion', 'rating', 'feedback', 'experience'],
            'pricing': ['price', 'cost', 'value', 'msrp', 'invoice', 'deal']
        }
        preferred_content = []
        for content_type, keywords in content_preferences.items():
            if any(keyword in query_lower for keyword in keywords):
                preferred_content.append(content_type)
        
        # Intent detection (what user really wants)
        intents = {
            'comparison': ['vs', 'versus', 'compare', 'difference', 'better', 'best'],
            'recommendation': ['recommend', 'suggest', 'should i', 'which one', 'help me choose'],
            'specific_info': ['what is', 'tell me about', 'explain', 'describe'],
            'availability': ['available', 'in stock', 'for sale', 'buy', 'purchase']
        }
        detected_intents = []
        for intent, keywords in intents.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_intents.append(intent)
        
        logger.info(f"Street-smart analysis - Brands: {detected_brands}, Types: {detected_types}, Colors: {detected_colors}, Features: {detected_features}, Conditions: {detected_conditions}, Content: {preferred_content}, Intents: {detected_intents}")
        
        # Perform semantic search with expanded results for filtering
        results = master_index.similarity_search_with_score(query, k=top_k * 5)
        
        # INTELLIGENT FILTERING WITH SCORING
        scored_results = []
        for doc, base_score in results:
            metadata = doc.metadata
            content = doc.page_content.lower()
            relevance_score = 0
            
            # Brand matching (high weight)
            if detected_brands:
                brand_matches = sum(1 for brand in detected_brands if brand in content)
                if brand_matches > 0:
                    relevance_score += brand_matches * 10
                else:
                    continue  # Skip if brand specified but not found
            
            # Vehicle type matching
            if detected_types:
                type_matches = 0
                for vtype in detected_types:
                    if any(keyword in content for keyword in vehicle_types[vtype]):
                        type_matches += 1
                if type_matches > 0:
                    relevance_score += type_matches * 8
                elif len(detected_types) > 0:
                    relevance_score -= 5  # Penalty for wrong type
            
            # Color matching (high weight for specific requests)
            if detected_colors:
                color_matches = 0
                for color in detected_colors:
                    if any(synonym in content for synonym in colors[color]):
                        color_matches += 1
                if color_matches > 0:
                    relevance_score += color_matches * 12
                else:
                    continue  # Skip if color specified but not found
            
            # Feature matching
            for feature_type in detected_features:
                if any(keyword in content for keyword in features[feature_type]):
                    relevance_score += 5
            
            # Condition matching
            for condition in detected_conditions:
                if any(keyword in content for keyword in conditions[condition]):
                    relevance_score += 6
            
            # Content type preference
            is_image = metadata.get('type') == 'image'
            if 'images' in preferred_content and is_image:
                relevance_score += 15
            elif 'images' in preferred_content and not is_image:
                relevance_score -= 10
            elif preferred_content and not is_image:  # Text content preferred
                relevance_score += 8
            
            # Intent-based scoring
            if 'comparison' in detected_intents and ('vs' in content or 'compare' in content):
                relevance_score += 7
            if 'specific_info' in detected_intents and metadata.get('type') != 'image':
                relevance_score += 5
            
            # Combine with semantic similarity (normalize base_score)
            final_score = relevance_score + (1.0 - float(base_score)) * 20
            
            scored_results.append((doc, final_score, base_score))
        
        # Sort by relevance score and take top results
        scored_results.sort(key=lambda x: x[1], reverse=True)
        top_results = scored_results[:top_k]
        
        # Format results with enhanced metadata
        formatted_results = []
        for doc, relevance_score, semantic_score in top_results:
            metadata = doc.metadata
            result = {
                'content': doc.page_content,
                'metadata': metadata,
                'relevance_score': float(relevance_score),
                'semantic_score': float(semantic_score)
            }
            
            # Add image URL if it's an image
            if metadata.get('type') == 'image' and 'image_key' in metadata:
                try:
                    s3_client = get_s3_client()
                    image_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': BUCKET, 'Key': metadata['image_key']},
                        ExpiresIn=7200
                    )
                    result['image_url'] = image_url
                except Exception as e:
                    logger.warning(f"Failed to generate image URL: {type(e).__name__}")
            
            formatted_results.append(result)
        
        logger.info(f"Search completed: {len(formatted_results)} results")
        return formatted_results
        
    except Exception as e:
        logger.error(f"Search failed: {type(e).__name__}")
        return []


# -----------------------------------------------------------
# /search
# -----------------------------------------------------------
def handle_search(query):
    """Handle search requests with intelligent filtering."""
    try:
        if not query or not query.strip():
            return cors_response({"error": "Query is required"}, 400)
        
        query = query.strip()
        logger.info(f"Search started | Query: {sanitize_for_logging(query)} | Length: {len(query)}")
        
        results = intelligent_search(query, top_k=10)
        
        logger.info(f"Search complete | Results: {len(results)} | Query: {sanitize_for_logging(query)[:50]}")
        return cors_response({
            "results": results,
            "query": query,
            "total": len(results)
        })
        
    except Exception as e:
        logger.error(f"Search failed | Query: {sanitize_for_logging(query)[:50]} | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Search failed"}, 500)


# -----------------------------------------------------------
# Bedrock Agent Integration
# -----------------------------------------------------------
def handle_agent_query(query, session_id=None):
    """Handle queries using Bedrock Agent with search integration."""
    try:
        if not query or not query.strip():
            return cors_response({"error": "Query is required"}, 400)
        
        query = query.strip()
        if not session_id:
            session_id = str(uuid.uuid4())
        
        logger.info(f"Processing agent query: {sanitize_for_logging(query)} (session: {sanitize_for_logging(session_id)})")
        
        # Get agent configuration from environment
        agent_id = os.getenv("BEDROCK_AGENT_ID")
        agent_alias_id = os.getenv("BEDROCK_AGENT_ALIAS_ID")
        
        if not agent_id or not agent_alias_id:
            logger.error("Bedrock agent configuration missing")
            return cors_response({"error": "Agent configuration not found"}, 500)
        
        bedrock_client = get_bedrock_client()
        
        # Invoke the agent
        response = bedrock_client.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=session_id,
            inputText=query
        )
        
        # Process the response stream
        response_text = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    response_text += chunk['bytes'].decode('utf-8')
        
        logger.info(f"Agent response generated (length: {len(response_text)})")
        
        return cors_response({
            "response": response_text,
            "sessionId": session_id,
            "query": query
        })
        
    except Exception as e:
        logger.error(f"Agent query failed: {sanitize_for_logging(str(e))}")
        return cors_response({"error": "Agent query failed"}, 500)


# -----------------------------------------------------------
# Lambda Handler
# -----------------------------------------------------------
def lambda_handler(event, context):
    """Main Lambda handler with comprehensive error handling."""
    try:
        logger.info(f"Received event: {sanitize_for_logging(json.dumps(event, default=str))}")
        
        # Handle CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return cors_response()
        
        # Extract path and method
        path = event.get("path", "")
        method = event.get("httpMethod", "")
        
        # Parse body for POST requests
        body = {}
        if method == "POST" and event.get("body"):
            try:
                body = json.loads(event["body"])
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in request body: {sanitize_for_logging(str(e))}")
                return cors_response({"error": "Invalid JSON"}, 400)
        
        # Route requests
        if path == "/get-upload-url" and method == "GET":
            return handle_get_upload_url()
        
        elif path == "/list-files" and method == "GET":
            return handle_list_files()
        
        elif path.startswith("/delete-file/") and method == "DELETE":
            filename = unquote_plus(path.split("/delete-file/")[1])
            return handle_delete_file(filename)
        
        elif path == "/search" and method == "POST":
            query = body.get("query", "")
            return handle_search(query)
        
        elif path == "/agent" and method == "POST":
            query = body.get("query", "")
            session_id = body.get("sessionId")
            return handle_agent_query(query, session_id)
        
        else:
            logger.warning(f"Unknown endpoint: {sanitize_for_logging(path)} {sanitize_for_logging(method)}")
            return cors_response({"error": "Endpoint not found"}, 404)
    
    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {sanitize_for_logging(str(e))}")
        return cors_response({"error": "Internal server error"}, 500)
        for item in response.get("Contents", []):
            key = item["Key"]
            if key.lower().endswith(".pdf"):
                files.append(os.path.basename(key))
        logger.info(f" Listed {len(files)} processed PDFs.")
        return cors_response({"files": files})
    except Exception as e:
        logger.error(f" Failed to list files: {type(e).__name__}")
        return cors_response({"error": "Failed to list files"}, 500)


# -----------------------------------------------------------
# /agent-query
# -----------------------------------------------------------
def handle_get_upload_url_api(event):
    """API Gateway handler for generating upload URLs."""
    try:
        body_str = event.get("body") or "{}"
        try:
            body = json.loads(body_str) if body_str else {}
        except json.JSONDecodeError:
            return cors_response({"error": "Invalid JSON in request body"}, 400)
        
        file_name = body.get("fileName", f"upload_{int(time.time())}.pdf")
        
        try:
            file_name = validate_filename(file_name)
        except ValueError as e:
            return cors_response({"error": str(e)}, 400)
        
        if not file_name.lower().endswith('.pdf'):
            return cors_response({"error": "Only PDF files are allowed"}, 400)
        
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        
        key = f"uploads/{file_name}"
        signed_url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": BUCKET, "Key": key, "ContentType": "application/pdf"},
            ExpiresIn=3600
        )
        logger.info(f" Generated upload URL for key: {key}")
        return cors_response({"signedUrl": signed_url, "fileName": file_name})
    except Exception as e:
        logger.error(f" Upload URL error: {type(e).__name__}", exc_info=True)
        return cors_response({"error": "Upload URL generation failed"}, 500)

def handle_list_files_api(event):
    """API Gateway handler for listing files."""
    try:
        objects = list_all_s3_objects(BUCKET, "processed/")
        filenames = []
        for obj in objects:
            if obj["Key"].endswith(".json"):
                filenames.append(os.path.basename(obj["Key"]))
        return cors_response({"filenames": filenames})
    except Exception as e:
        logger.error(f" List files error: {type(e).__name__}")
        return cors_response({"error": "Failed to list files"}, 500)

def get_document_context(metadata, base_name):
    """Extract rich document-level context for chunk enrichment."""
    context_parts = [f"Document: {base_name}"]
    
    # Add text preview summary
    text_preview = metadata.get('text_preview', '').strip()
    if text_preview:
        first_line = text_preview.split('\n')[0][:80].strip()
        if first_line:
            context_parts.append(f"Subject: {first_line}")
    
    # Add visual context from first image
    images = metadata.get('images', [])
    if images:
        first_img = images[0].get('description', '')
        if 'BRAND:' in first_img:
            brand = first_img.split('BRAND:')[1].split('\n')[0].strip()
            if brand and brand.lower() != 'none visible':
                context_parts.append(f"Brand: {brand}")
    
    return " | ".join(context_parts)

def rebuild_master_index():
    """Rebuild master index from all remaining processed documents."""
    try:
        from langchain_community.vectorstores import FAISS
        from langchain.docstore.document import Document
        import tempfile
        
        logger.info(" Rebuilding master index...")
        
        # Get all processed documents
        processed_objects = list_all_s3_objects(BUCKET, "processed/")
        if not processed_objects:
            logger.info(" No documents to index, deleting master index")
            try:
                s3.delete_object(Bucket=BUCKET, Key="vector_store/master/index.faiss")
                s3.delete_object(Bucket=BUCKET, Key="vector_store/master/index.pkl")
            except:
                pass
            # Clear cache
            if "master_index" in FAISS_CACHE:
                del FAISS_CACHE["master_index"]
            return
        
        embeddings = get_embeddings_client()
        all_docs = []
        
        # Collect all documents from processed files
        for obj in processed_objects:
            if not obj['Key'].endswith('.json'):
                continue
            
            try:
                # Get processed metadata
                response = s3.get_object(Bucket=BUCKET, Key=obj['Key'])
                metadata = json.loads(response['Body'].read().decode('utf-8'))
                
                source_file = metadata.get('source_file', '')
                base_name = os.path.basename(source_file).replace('.pdf', '')
                
                # Get rich document context
                context_prefix = get_document_context(metadata, base_name)
                
                # Get original PDF and re-extract text (simplified - just get from metadata)
                text_preview = metadata.get('text_preview', '')
                if text_preview:
                    # Create document chunks from preview
                    from langchain.text_splitter import RecursiveCharacterTextSplitter
                    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
                    chunks = splitter.split_text(text_preview)
                    
                    for i, chunk in enumerate(chunks):
                        doc = Document(
                            page_content=f"[{context_prefix}] {chunk}",
                            metadata={
                                "source": base_name,
                                "chunk_id": i,
                                "context_summary": context_prefix
                            }
                        )
                        all_docs.append(doc)
                
                # Add image documents
                images = metadata.get('images', [])
                for img_meta in images:
                    img_desc = img_meta.get('description', 'Image')
                    s3_key = img_meta.get('s3_key', '')
                    
                    # Include IMAGE_URL in content so agent can find and return it
                    page_content = f"[{context_prefix}] Image page {img_meta['page']}: {img_desc}\nIMAGE_URL: {s3_key}|PAGE: {img_meta['page']}|SOURCE: {base_name}"
                    
                    img_doc = Document(
                        page_content=page_content,
                        metadata={
                            "source": base_name,
                            "type": "image",
                            "page": img_meta['page'],
                            "image_url": img_meta.get('url', ''),
                            "s3_key": s3_key,
                            "context_summary": context_prefix
                        }
                    )
                    all_docs.append(img_doc)
                    
            except Exception as e:
                logger.error(f" Failed to process {obj['Key']}: {e}")
        
        if not all_docs:
            logger.warning(" No documents collected for indexing")
            return
        
        logger.info(f" Creating master index with {len(all_docs)} documents")
        
        # Create new master index
        with tempfile.TemporaryDirectory() as tmpdir:
            master_store = FAISS.from_documents(all_docs, embeddings)
            master_store.save_local(tmpdir)
            
            # Upload to S3
            s3.upload_file(os.path.join(tmpdir, "index.faiss"), BUCKET, "vector_store/master/index.faiss")
            s3.upload_file(os.path.join(tmpdir, "index.pkl"), BUCKET, "vector_store/master/index.pkl")
        
        # Clear cache to force reload
        if "master_index" in FAISS_CACHE:
            del FAISS_CACHE["master_index"]
        
        logger.info(" Master index rebuilt successfully")
        
    except Exception as e:
        logger.error(f" Failed to rebuild master index: {e}")
        raise

def handle_delete_file_api(event):
    """API Gateway handler for deleting files."""
    try:
        params = event.get("queryStringParameters") or {}
        display_name = params.get("fileName")
        
        try:
            display_name = validate_filename(display_name)
        except (ValueError, TypeError) as e:
            return cors_response({"error": "Invalid fileName"}, 400)
        
        logger.info(f" Deleting file: {sanitize_for_logging(display_name)}")
        base_name = display_name.replace('.json', '') if display_name.endswith('.json') else display_name
        
        # Collect all keys to delete
        keys_to_delete = []
        
        # Add JSON marker
        keys_to_delete.append(f"processed/{base_name}.json")
        
        # Collect PDFs
        try:
            pdf_objects = list_all_s3_objects(BUCKET, f"uploads/{base_name}")
            for obj in pdf_objects:
                if obj['Key'].startswith(f"uploads/{base_name}."):
                    keys_to_delete.append(obj['Key'])
        except Exception as e:
            logger.error(f" Failed to list PDFs: {e}")
        
        # Collect images
        try:
            image_objects = list_all_s3_objects(BUCKET, f"images/{base_name}/")
            keys_to_delete.extend([obj['Key'] for obj in image_objects])
        except Exception as e:
            logger.error(f" Failed to list images: {e}")
        
        # Batch delete all collected keys
        deleted_count = batch_delete_s3_objects(BUCKET, keys_to_delete)
        logger.info(f" Deleted {deleted_count} objects for {base_name}")
        
        # Rebuild master index without this document
        try:
            rebuild_master_index()
            logger.info(" Master index rebuilt after deletion")
        except Exception as e:
            logger.error(f" Failed to rebuild master index: {e}")
            # Don't fail the delete operation if rebuild fails
        
        return cors_response({"message": f"{base_name} deleted successfully"})
    except Exception as e:
        logger.error(f" Delete file error: {type(e).__name__}")
        return cors_response({"error": "Failed to delete file"}, 500)

def handle_cancel_upload_api(event):
    """API Gateway handler for cancelling uploads and cleaning up partial files."""
    try:
        params = event.get("queryStringParameters") or {}
        file_name = params.get("fileName")
        
        try:
            file_name = validate_filename(file_name)
        except (ValueError, TypeError) as e:
            return cors_response({"error": "Invalid fileName"}, 400)
        
        logger.info(f" Cancelling upload: {sanitize_for_logging(file_name)}")
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        
        # Create cancellation marker FIRST to stop Lambda processing
        try:
            s3.put_object(
                Bucket=BUCKET,
                Key=f"cancelled/{base_name}.txt",
                Body=f"Cancelled at {time.time()}",
                ContentType="text/plain"
            )
            logger.info(f" Created cancellation marker")
        except Exception as e:
            logger.error(f" Failed to create cancellation marker: {e}")
        
        # Collect all keys to delete
        keys_to_delete = []
        
        # Collect uploads
        try:
            upload_objects = list_all_s3_objects(BUCKET, f"uploads/{base_name}")
            keys_to_delete.extend([obj['Key'] for obj in upload_objects])
        except Exception as e:
            logger.error(f" Failed to list uploads: {e}")
        
        # Collect processed
        try:
            processed_objects = list_all_s3_objects(BUCKET, f"processed/{base_name}")
            keys_to_delete.extend([obj['Key'] for obj in processed_objects])
        except Exception as e:
            logger.error(f" Failed to list processed: {e}")
        
        # Collect images
        try:
            image_objects = list_all_s3_objects(BUCKET, f"images/{base_name}/")
            keys_to_delete.extend([obj['Key'] for obj in image_objects])
        except Exception as e:
            logger.error(f" Failed to list images: {e}")
        
        # Note: No need to delete vector store - using master index now
        
        # Add cancellation marker to delete list
        keys_to_delete.append(f"cancelled/{base_name}.txt")
        
        # Batch delete all collected keys
        deleted_count = batch_delete_s3_objects(BUCKET, keys_to_delete)
        logger.info(f" Total files deleted: {deleted_count}")
        
        return cors_response({"message": f"Cancelled and deleted {deleted_count} files for {base_name}"})
    except Exception as e:
        logger.error(f" Cancel upload error: {type(e).__name__}")
        return cors_response({"error": "Failed to cancel upload"}, 500)



def handle_search_action(event):
    """Smart search with exact matching and relevance scoring."""
    try:
        request_body = event.get("requestBody", {})
        content = request_body.get("content", {})
        app_json = content.get("application/json", {})
        properties = app_json.get("properties", [])
        
        query = ""
        for prop in properties:
            if prop.get("name") == "query":
                query = prop.get("value", "")
                break
        
        original_input = event.get("inputText", "").lower()
        logger.info(f"Search query: {sanitize_for_logging(query)} | Original: {sanitize_for_logging(original_input)}")
        
        if not query.strip():
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup", "LambdaTools"),
                    "apiPath": "/search",
                    "httpMethod": "POST",
                    "httpStatusCode": 200,
                    "responseBody": {"application/json": {"body": json.dumps({"result": "Please specify what you're looking for."})}}
                }
            }
        
        from langchain_community.vectorstores import FAISS
        
        # Load master index
        cache_key = "master_index"
        if cache_key not in _faiss_cache:
            cache_dir = "/tmp/master_index"
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir, exist_ok=True)
                s3_client = get_s3_client()
                s3_client.download_file(BUCKET, "vector_store/master/index.faiss", os.path.join(cache_dir, "index.faiss"))
                s3_client.download_file(BUCKET, "vector_store/master/index.pkl", os.path.join(cache_dir, "index.pkl"))
            embeddings = get_embeddings_client()
            master_index = FAISS.load_local(cache_dir, embeddings, allow_dangerous_deserialization=True)
            _faiss_cache[cache_key] = master_index
        
        master_index = _faiss_cache[cache_key]
        
        # Extract key terms
        query_lower = query.lower()
        original_lower = original_input.lower()
        
        # Brand detection
        brands = ['hyundai', 'cherry', 'chery', 'honda', 'toyota', 'ford', 'bmw', 'mercedes']
        found_brand = next((b for b in brands if b in query_lower or b in original_lower), None)
        
        # Color detection  
        colors = ['black', 'red', 'white', 'silver', 'blue', 'gray', 'grey', 'green', 'yellow']
        found_color = next((c for c in colors if c in query_lower or c in original_lower), None)
        
        # Content type detection
        wants_images = any(word in original_lower for word in ['show', 'display', 'image', 'picture', 'see'])
        
        logger.info(f"Detected - Brand: {found_brand}, Color: {found_color}, Images: {wants_images}")
        
        # Get search results
        all_results = master_index.similarity_search_with_score(query, k=50)
        
        # Smart filtering with scoring
        scored_results = []
        for doc, semantic_score in all_results:
            content = doc.page_content.lower()
            metadata = doc.metadata
            is_image = metadata.get('type') == 'image'
            doc_source = metadata.get('source', '').lower()
            
            # Calculate relevance score starting with semantic similarity
            relevance = (1.0 - semantic_score) * 50
            
            # Brand matching - boost if found, don't exclude if not
            if found_brand:
                if found_brand in doc_source:
                    relevance += 100  # Strong match in document name
                elif found_brand in content:
                    relevance += 60   # Good match in content
                else:
                    relevance -= 30   # Penalty but don't exclude
            
            # Color matching - boost if found, don't exclude if not
            if found_color:
                if found_color in content:
                    relevance += 80   # Strong boost for color match
                else:
                    relevance -= 20   # Small penalty but don't exclude
            
            # Content type preference
            if wants_images:
                if is_image:
                    relevance += 40
                else:
                    relevance -= 10
            else:
                if not is_image:
                    relevance += 20
            
            # Only include if relevance is positive (filters out very poor matches)
            if relevance > 0:
                scored_results.append((doc, relevance, semantic_score))
        
        # Sort by relevance score
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        if not scored_results:
            result = f"No {found_brand or ''} {found_color or ''} {'images' if wants_images else 'information'} found.".strip()
        else:
            # Return top results
            top_results = scored_results[:5]
            result_parts = []
            
            if wants_images:
                # Extract IMAGE_URL from content or generate from metadata
                import re
                for doc, relevance, semantic in top_results:
                    content = doc.page_content
                    metadata = doc.metadata
                    
                    # Try to extract from content first
                    image_urls = re.findall(r'IMAGE_URL:\s*([^\n|]+)', content)
                    if image_urls:
                        for url in image_urls:
                            result_parts.append(f"IMAGE_URL: {url.strip()}")
                    # If not in content, check metadata for s3_key
                    elif 's3_key' in metadata:
                        s3_key = metadata['s3_key']
                        page = metadata.get('page', 'unknown')
                        source = metadata.get('source', 'unknown')
                        result_parts.append(f"IMAGE_URL: {s3_key}|PAGE: {page}|SOURCE: {source}")
            else:
                for doc, relevance, semantic in top_results:
                    result_parts.append(doc.page_content)
            
            result = "\n\n".join(result_parts) if result_parts else "No results found."
        
        logger.info(f"Returning {len(scored_results)} results")
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/search",
                "httpMethod": "POST",
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"result": result})
                    }
                }
            }
        }
    except Exception as e:
        logger.error(f"Search failed: {type(e).__name__}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/search",
                "httpMethod": "POST",
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": "Search failed"})
                    }
                }
            }
        }

def handle_send_email_action(event):
    """Send email via SES - called by Bedrock Agent."""
    try:
        request_body = event.get("requestBody", {})
        content = request_body.get("content", {})
        app_json = content.get("application/json", {})
        properties = app_json.get("properties", [])
        
        to_email = ""
        subject = ""
        body = ""
        
        for prop in properties:
            name = prop.get("name", "")
            value = prop.get("value", "")
            if name == "to_email":
                to_email = value
            elif name == "subject":
                subject = value
            elif name == "body":
                body = value
        
        logger.info(f"Sending email to: {sanitize_for_logging(to_email)}")
        
        if not to_email or not subject or not body:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup", "LambdaTools"),
                    "apiPath": "/send-email",
                    "httpMethod": "POST",
                    "httpStatusCode": 400,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps({"error": "Missing required fields: to_email, subject, body"})
                        }
                    }
                }
            }
        
        # Send email via SES
        region = os.getenv("AWS_REGION")
        if not region:
            raise ValueError("AWS_REGION must be configured")
        
        sender_email = os.getenv("SES_SENDER_EMAIL")
        if not sender_email:
            raise ValueError("SES_SENDER_EMAIL must be configured")
        
        ses = boto3.client('ses', region_name=region)
        
        response = ses.send_email(
            Source=sender_email,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Text': {'Data': body, 'Charset': 'UTF-8'}}
            }
        )
        
        logger.info(f" Email sent successfully. MessageId: {response['MessageId']}")
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/send-email",
                "httpMethod": "POST",
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"result": f"Email sent successfully to {to_email}"})
                    }
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Email send failed: {sanitize_for_logging(str(e))}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "LambdaTools"),
                "apiPath": "/send-email",
                "httpMethod": "POST",
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({"error": "Email sending failed"})
                    }
                }
            }
        }





def handle_agent_query(event):
    """Route query to Bedrock Agent for natural language response."""
    total_start = time.time()
    try:
        parse_start = time.time()
        body_str = event.get("body", "{}")
        try:
            body = json.loads(body_str) if body_str else {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON | Error: {type(e).__name__} | Details: {str(e)[:100]}")
            return cors_response({"error": "Invalid JSON in request body"}, 400)
        
        query = body.get("query", "")
        session_id = body.get("sessionId", f"session-{int(time.time())}")
        logger.info(f"Agent query started | Session: {session_id[:20]}... | Query length: {len(query)} | Parse time: {time.time() - parse_start:.2f}s")
        
        # Validate inputs
        if not query or not isinstance(query, str):
            return cors_response({"error": "Query is required and must be a string"}, 400)
        
        if len(query) > 10000:
            return cors_response({"error": "Query too long (max 10000 characters)"}, 400)
        
        logger.info(f"Agent invocation | Query: {sanitize_for_logging(query)[:100]} | Session: {sanitize_for_logging(session_id, 50)}")

        config_start = time.time()
        agent_id = os.getenv("BEDROCK_AGENT_ID")
        alias_id = os.getenv("BEDROCK_AGENT_ALIAS_ID")
        
        if not agent_id or not alias_id:
            logger.error("BEDROCK_AGENT_ID or BEDROCK_AGENT_ALIAS_ID environment variable not set")
            return cors_response({"error": "Agent configuration error"}, 500)
        
        logger.info(f"Agent config | AgentId: {sanitize_for_logging(agent_id, 50)} | AliasId: {sanitize_for_logging(alias_id, 50)}")
        
        try:
            bedrock_agent_runtime = get_bedrock_client()
        except Exception as e:
            logger.error(f" Failed to get Bedrock client: {sanitize_for_logging(str(e))}")
            return cors_response({"error": "Failed to initialize agent client"}, 500)
        
        logger.info(f"Agent setup complete | Time: {time.time() - config_start:.2f}s")
        
        invoke_start = time.time()
        try:
            response = bedrock_agent_runtime.invoke_agent(
                agentId=agent_id,
                agentAliasId=alias_id,
                sessionId=session_id,
                inputText=query,
                enableTrace=False
            )
        except Exception as e:
            logger.error(f" Agent invocation failed: {sanitize_for_logging(str(e))}")
            return cors_response({"error": "Failed to invoke agent"}, 500)
        
        logger.info(f"Agent invoked | Time: {time.time() - invoke_start:.2f}s | Processing response stream")
        
        answer = ""
        stream_start = time.time()
        try:
            event_stream = response.get('completion')
            if not event_stream:
                logger.error(" No completion stream in response")
                return cors_response({"error": "Invalid agent response"}, 500)
            
            for event in event_stream:
                if 'chunk' in event:
                    chunk = event['chunk']
                    if 'bytes' in chunk:
                        answer += chunk['bytes'].decode('utf-8')
        except Exception as e:
            logger.error(f" Failed to process response stream: {sanitize_for_logging(str(e))}")
            return cors_response({"error": "Failed to process agent response"}, 500)
        
        logger.info(f"Stream processed | Time: {time.time() - stream_start:.2f}s | Response length: {len(answer)}")
        
        # Extract IMAGE_URL entries and generate presigned URLs
        images = []
        try:
            import re
            image_pattern = r'IMAGE_URL:\s*([^|\n]+)'
            matches = re.findall(image_pattern, answer)
            
            if matches:
                logger.info(f"Image URLs found | Count: {len(matches)}")
                for s3_key in matches:
                    s3_key = s3_key.strip()
                    if not s3_key or not s3_key.startswith('images/'):
                        continue
                    try:
                        url = s3.generate_presigned_url(
                            'get_object',
                            Params={'Bucket': BUCKET, 'Key': s3_key},
                            ExpiresIn=3600
                        )
                        images.append(url)
                        logger.info(f"Presigned URL generated | Key: {s3_key}")
                    except Exception as e:
                        logger.error(f"URL generation failed | Key: {s3_key} | Error: {type(e).__name__}")
        except Exception as e:
            logger.error(f" Image extraction failed: {e}")
        
        logger.info(f"Agent query complete | Response: {len(answer)} chars | Images: {len(images)} | Total time: {time.time() - total_start:.2f}s")
        return cors_response({"response": answer, "sessionId": session_id, "images": images})
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error | Error: {type(e).__name__} | Details: {str(e)[:100]}")
        return cors_response({"error": "Invalid request format"}, 400)
    except Exception as e:
        logger.error(f"Agent query failed | Error: {type(e).__name__} | Details: {str(e)[:200]} | Time: {time.time() - total_start:.2f}s")
        return cors_response({"error": "Agent query failed"}, 500)



def handle_get_image(event):
    """Generate presigned URL for image retrieval."""
    try:
        params = event.get("queryStringParameters") or {}
        image_key = params.get("key")
        
        logger.info(f"Get image request for key: {sanitize_for_logging(image_key)}")
        
        if not image_key or not isinstance(image_key, str):
            return cors_response({"error": "Missing or invalid image key"}, 400)
        
        # Validate key starts with images/ to prevent unauthorized access
        if not image_key.startswith("images/"):
            logger.warning(f"Attempted access to non-image key: {sanitize_for_logging(image_key)}")
            return cors_response({"error": "Invalid image key"}, 403)
        
        s3_client = get_s3_client()
        try:
            s3_client.head_object(Bucket=BUCKET, Key=image_key)
            logger.info(f"Image exists: {image_key}")
        except s3_client.exceptions.NoSuchKey:
            logger.error(f"Image not found: {image_key}")
            return cors_response({"error": "Image not found"}, 404)
        except Exception as e:
            logger.error(f"Failed to check image: {type(e).__name__}")
            return cors_response({"error": "Failed to verify image"}, 500)
        
        try:
            url = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET, "Key": image_key},
                ExpiresIn=7200
            )
            logger.info(f"Generated presigned URL: {image_key}")
            return cors_response({"url": url})
        except Exception as e:
            logger.error(f"Failed to generate URL: {type(e).__name__}")
            return cors_response({"error": "Failed to generate image URL"}, 500)
            
    except Exception as e:
        logger.error(f"Get image error: {sanitize_for_logging(str(e))}")
        return cors_response({"error": "Failed to get image"}, 500)

def handle_processing_status(event):
    """Check processing status of uploaded file."""
    try:
        params = event.get("queryStringParameters") or {}
        file_name = params.get("fileName")
        
        try:
            file_name = validate_filename(file_name)
        except (ValueError, TypeError) as e:
            return cors_response({"error": "Invalid fileName"}, 400)
        
        base_name = os.path.splitext(file_name)[0] if '.' in file_name else file_name
        logger.info(f" Checking status for file: {sanitize_for_logging(file_name)}")
        
        s3_client = get_s3_client()
        
        # Check if cancelled
        try:
            s3_client.head_object(Bucket=BUCKET, Key=f"cancelled/{base_name}.txt")
            return cors_response({
                "status": "cancelled",
                "progress": 0,
                "message": "Processing was cancelled"
            })
        except s3_client.exceptions.NoSuchKey:
            pass
        except Exception as e:
            logger.error(f"Error checking cancellation: {type(e).__name__}")
        
        # Check if processing is complete
        try:
            logger.info(f"Checking: s3://{BUCKET}/processed/{base_name}.json")
            processed_obj = s3_client.get_object(Bucket=BUCKET, Key=f"processed/{base_name}.json")
            processed_data = json.loads(processed_obj['Body'].read().decode('utf-8'))
            logger.info(f"Found completion marker: {base_name}")
            return cors_response({
                "status": "completed",
                "progress": 100,
                "message": "Processing complete",
                "data": processed_data
            })
        except s3_client.exceptions.NoSuchKey:
            logger.info(f"Processed marker not found")
        except Exception as e:
            logger.error(f"Error checking processed: {type(e).__name__}")
        
        # Check if file exists in uploads
        try:
            s3_client.head_object(Bucket=BUCKET, Key=f"uploads/{file_name}")
            logger.info(f"File in uploads, processing")
            return cors_response({
                "status": "processing",
                "progress": 75,
                "message": "Extracting text and creating vector embeddings..."
            })
        except s3_client.exceptions.NoSuchKey:
            pass
        except Exception as e:
            logger.error(f"Error checking uploads: {type(e).__name__}")
        
        # File not found anywhere
        return cors_response({
            "status": "not_found",
            "progress": 0,
            "message": "File not found or processing not started"
        })
        
    except Exception as e:
        logger.error(f" Processing status error: {type(e).__name__}")
        return cors_response({"error": "Failed to check processing status"}, 500)


# -----------------------------------------------------------
# Lambda Entrypoint
# -----------------------------------------------------------
def lambda_handler(event, context):
    """Main Lambda handler for API Gateway and Bedrock Agent requests."""
    # Set correlation ID for request tracking
    request_id = context.request_id if hasattr(context, 'request_id') else str(uuid.uuid4())
    correlation_id_var.set(request_id)
    
    logger.info(f"Lambda triggered | RequestId: {request_id} | Event: {json.dumps(event)[:500]}")
    
    # Handle warmup ping from EventBridge
    if event.get("source") == "aws.events" and event.get("detail-type") == "Scheduled Event":
        logger.info("Warmup ping received")
        return {"statusCode": 200, "body": json.dumps({"status": "warm"})}
    
    # Check if this is a Bedrock Agent action invocation
    if "messageVersion" in event and "agent" in event:
        api_path = event.get("apiPath", "")
        logger.info(f"Bedrock Agent action | Path: {api_path}")
        if api_path == "/search":
            return handle_search_action(event)
        elif api_path == "/send-email":
            return handle_send_email_action(event)
        else:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": event.get("actionGroup", ""),
                    "apiPath": api_path,
                    "httpMethod": event.get("httpMethod", "POST"),
                    "httpStatusCode": 404,
                    "responseBody": {
                        "application/json": {
                            "body": json.dumps({"error": "Unknown action"})
                        }
                    }
                }
            }
    
    # API Gateway invocations
    path = event.get("path", "")
    method = event.get("httpMethod", "")
    logger.info(f"API Gateway request | Method: {method} | Path: {path}")

    if path.startswith("/production/"):
        path = "/" + path[12:]
    elif path.startswith("/default/"):
        path = "/" + path[8:]
    elif path.startswith("/prod/"):
        path = "/" + path[5:]
    
    if path != event.get("path", ""):
        logger.info(f"Path normalized | Original: {event.get('path')} | Cleaned: {path}")

    if method == "OPTIONS":
        return cors_response()

    try:
        if path == "/upload" and method == "POST":
            return handle_get_upload_url_api(event)
        elif path == "/get-upload-url" and method in ["GET", "POST"]:
            return handle_get_upload_url_api(event)
        elif path == "/list-files" and method == "GET":
            return handle_list_files_api(event)
        elif path == "/delete-file" and method in ["DELETE", "GET"]:
            return handle_delete_file_api(event)
        elif path == "/cancel-upload" and method == "DELETE":
            return handle_cancel_upload_api(event)
        elif path == "/agent-query" and method == "POST":
            return handle_agent_query(event)
        elif path == "/get-image" and method == "GET":
            return handle_get_image(event)
        elif path == "/processing-status" and method == "GET":
            return handle_processing_status(event)
        else:
            logger.error(f"Unhandled route | Path: {path} | Method: {method}")
            return cors_response({"error": f"Unhandled route: {path}"}, 404)

    except Exception as e:
        logger.error(f"Lambda error | Type: {type(e).__name__} | Message: {str(e)[:200]}")
        return cors_response({"error": "Internal server error"}, 500)
