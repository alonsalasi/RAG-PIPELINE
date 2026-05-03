import boto3, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s3 = boto3.client('s3')
paginator = s3.get_paginator('list_objects_v2')

print("=== source_file values for recent docs ===")
for page in paginator.paginate(Bucket='pdfquery-rag-documents-production', Prefix='processed/1777787219'):
    for obj in page['Contents']:
        resp = s3.get_object(Bucket='pdfquery-rag-documents-production', Key=obj['Key'])
        data = json.loads(resp['Body'].read().decode('utf-8'))
        sf = data.get('source_file', '')
        print("source_file:", repr(sf))
        # Simulate what rebuild_master_index does
        base_name = sf.split('/')[-1].replace('.pdf', '')
        print("base_name (current code):", repr(base_name))
        # What it SHOULD be
        base_name_fixed = sf.split('/')[-1].rsplit('.', 1)[0] if '.' in sf.split('/')[-1] else sf.split('/')[-1]
        print("base_name (fixed):", repr(base_name_fixed))
        print("full_text_len:", len(data.get('full_text', '')))
