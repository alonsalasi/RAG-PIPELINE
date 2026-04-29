content = open('Lambda/worker.py', 'rb').read().decode('utf-8')
lines = content.split('\n')
NL = '\n'

# ── Fix 1: invoke_lambda_for_range (lines 272-294, 0-indexed 271-293) ────────
# Replace lines 272-294 (1-indexed) = indices 271-293
new_invoke = [
    'def invoke_lambda_for_range(s3_bucket, s3_key, start_page, end_page, invocation_id, total_invocations):\r',
    '    """Invoke a worker Lambda for a specific page range."""\r',
    '    function_name = os.environ.get(\'INGESTION_LAMBDA_NAME\', os.environ.get(\'AWS_LAMBDA_FUNCTION_NAME\'))\r',
    '    payload = {\r',
    '        "Records": [{"s3": {"bucket": {"name": s3_bucket}, "object": {"key": s3_key}}}],\r',
    '        "page_range": {"start": start_page, "end": end_page},\r',
    '        "invocation_id": invocation_id,\r',
    '        "total_invocations": total_invocations\r',
    '    }\r',
    '    boto3.client(\'lambda\').invoke(\r',
    '        FunctionName=function_name,\r',
    '        InvocationType=\'Event\',\r',
    '        Payload=json.dumps(payload)\r',
    '    )\r',
    '    logger.info(f"Spawned worker {invocation_id}/{total_invocations} for pages {start_page}-{end_page}")\r',
]
# Find end of function (next def or blank line after last line)
# Lines 272-295 (1-indexed), indices 271-294
lines[271:294] = new_invoke
print(f'Fix 1 done, lines now: {len(lines)}')

# Recalculate line numbers after replacement
# Original line 423 = coordinator comment, but lines shifted
# Re-find by content
coord_idx = next(i for i, l in enumerate(lines) if 'Only coordinator' in l)
chunk_end_idx = next(i for i, l in enumerate(lines) if 'Chunked processing complete' in l)
extract_img_idx = next(i for i, l in enumerate(lines) if 'Extract images from full PDF' in l)
too_large_idx = next(i for i, l in enumerate(lines) if 'If PDF is too large' in l)
print(f'coordinator: {coord_idx+1}, too_large: {too_large_idx+1}, chunk_end: {chunk_end_idx+1}, extract_img: {extract_img_idx+1}')

# ── Fix 2: Replace coordinator block (coord_idx to coord_idx+13 approx) ──────
# Find the end of the coordinator block (the "return" line)
coord_end = coord_idx
while coord_end < len(lines) and 'return  # coordinator exits' not in lines[coord_end]:
    coord_end += 1
coord_end += 1  # include the return line

print(f'Coordinator block: lines {coord_idx+1}-{coord_end}')
print('  First:', repr(lines[coord_idx]))
print('  Last:', repr(lines[coord_end-1]))

new_coordinator = [
    '            # Coordinator: split PDFs >10 pages into parallel workers\r',
    '            if invocation_id == 0 and not page_range and file_ext == \'pdf\':\r',
    '                from pypdf import PdfReader as _PR\r',
    '                _page_count = len(_PR(local_path).pages)\r',
    '                if _page_count > 10:\r',
    '                    num_workers = min(5, max(1, _page_count // 10))\r',
    '                    pages_per_worker = (_page_count + num_workers - 1) // num_workers\r',
    '                    ranges = []\r',
    '                    for w in range(num_workers):\r',
    '                        s = w * pages_per_worker + 1\r',
    '                        e = min(s + pages_per_worker - 1, _page_count)\r',
    '                        if s <= _page_count:\r',
    '                            ranges.append((s, e))\r',
    '                    logger.info(f"Splitting {_page_count} pages into {len(ranges)} parallel workers: {ranges}")\r',
    '                    update_progress(base_name, 5, f"Processing {_page_count} pages with {len(ranges)} parallel workers...")\r',
    '                    for idx, (s, e) in enumerate(ranges, 1):\r',
    '                        invoke_lambda_for_range(s3_bucket, s3_key, s, e, idx, len(ranges))\r',
    '                    return  # coordinator exits, workers do the real work\r',
]
lines[coord_idx:coord_end] = new_coordinator
print(f'Fix 2 done, lines now: {len(lines)}')

# ── Fix 3: Remove sequential chunked loop (>60 pages) ────────────────────────
# Re-find markers after Fix 2
too_large_idx = next(i for i, l in enumerate(lines) if 'If PDF is too large' in l)
extract_img_idx = next(i for i, l in enumerate(lines) if 'Extract images from full PDF' in l)
print(f'too_large: {too_large_idx+1}, extract_img: {extract_img_idx+1}')
print('  too_large line:', repr(lines[too_large_idx]))
print('  extract_img line:', repr(lines[extract_img_idx]))

# Remove lines from "If PDF is too large" comment up to (not including) "Extract images from full PDF"
# But we need to keep the else: branch that handles page_range
# Find the else: that comes right before extract_img
else_idx = extract_img_idx - 1
while else_idx > too_large_idx and 'else:' not in lines[else_idx]:
    else_idx -= 1
print(f'else: at line {else_idx+1}: {repr(lines[else_idx])}')

# Delete from too_large_idx up to and including the blank line before else:
del lines[too_large_idx:else_idx]
print(f'Fix 3 done, lines now: {len(lines)}')

open('Lambda/worker.py', 'wb').write('\n'.join(lines).encode('utf-8'))
print('SUCCESS - worker.py written')
