import boto3
import html
from urllib.parse import unquote

# Configuration
BUCKET = "leidos-rag-bucket"
PROFILE = "leidos"

session = boto3.Session(profile_name=PROFILE)
s3 = session.client('s3')

def fix_filenames(prefix):
    """Fix HTML-encoded filenames in S3."""
    print(f"\nScanning {prefix}...")
    
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=BUCKET, Prefix=prefix)
    
    fixed_count = 0
    for page in pages:
        if 'Contents' not in page:
            continue
            
        for obj in page['Contents']:
            old_key = obj['Key']
            
            # Extract filename from key
            parts = old_key.split('/')
            old_filename = parts[-1]
            
            # Decode HTML entities
            new_filename = html.unescape(old_filename)
            
            # Skip if no change needed
            if old_filename == new_filename:
                continue
            
            # Build new key
            new_key = '/'.join(parts[:-1] + [new_filename])
            
            print(f"Renaming:")
            print(f"  Old: {old_key}")
            print(f"  New: {new_key}")
            
            # Copy to new key
            s3.copy_object(
                Bucket=BUCKET,
                CopySource={'Bucket': BUCKET, 'Key': old_key},
                Key=new_key
            )
            
            # Delete old key
            s3.delete_object(Bucket=BUCKET, Key=old_key)
            
            fixed_count += 1
            print(f"  ✓ Fixed")
    
    print(f"\n{prefix}: Fixed {fixed_count} files")
    return fixed_count

# Fix all prefixes
total = 0
total += fix_filenames('processed/')
total += fix_filenames('uploads/')
total += fix_filenames('images/')

print(f"\n✓ Total files fixed: {total}")
