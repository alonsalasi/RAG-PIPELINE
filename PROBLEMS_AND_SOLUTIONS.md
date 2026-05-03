# Problems & Solutions Log — Leidos RAG Pipeline

## Project Overview
AWS-based RAG document assistant. Stack: Bedrock Agent, FAISS vector search, S3, Lambda (agent + ingestion), API Gateway, Cognito, CloudFront, Terraform IaC.

---

## 1. Stale Upload Bug — Re-upload Blocked After Failed Ingestion

**Problem:**
`handle_get_upload_url_api` checked if a file existed in `uploads/` and blocked re-upload with "already exists" error — even if the previous ingestion had failed and the file was never processed.

**Root Cause:**
The duplicate check only looked at `uploads/` but didn't verify whether the file had actually been successfully processed (i.e., existed in `processed/`).

**Solution:**
Modified the duplicate check to:
1. If file is in `uploads/` AND in `processed/` → block as true duplicate.
2. If file is in `uploads/` but NOT in `processed/` → stale/failed upload. Clean it up and allow re-upload.

**File:** `Lambda/agent_executor.py` → `handle_get_upload_url_api`

---

## 2. Agent Timeout — Silent Failure on Async Query

**Problem:**
`handle_agent_query_async` invoked itself asynchronously to process queries in the background, but the invocation was silently failing. Queries would hang forever.

**Root Cause:**
The `AGENT_LAMBDA_NAME` environment variable was missing from the Lambda configuration. The code fell back to `AWS_LAMBDA_FUNCTION_NAME` which was also unreliable in this context.

**Solution:**
Added `AGENT_LAMBDA_NAME = "${var.project_name}-agent-executor"` to the environment variables block in `Lambda_agent.tf`.

**File:** `Lambda_agent.tf`

---

## 3. Ingestion Lambda — Broken Container (CodeArtifactUserFailedException)

**Problem:**
The ingestion Lambda container was failing to initialize with `CodeArtifactUserFailedException`, causing all document processing to fail silently.

**Root Cause:**
The Docker image was stale/corrupted and failed during dependency resolution at container startup.

**Solution:**
Rebuilt the Docker image from scratch. The rebuild resolved the initialization error.

**Files:** `Lambda/ingestion.Dockerfile`, ECR push via Terraform `null_resource`

---

## 4. OCR Performance — Double Tesseract Pass Per Page

**Problem:**
Each PDF page was being OCR'd twice — once with `image_to_string` (for text) and once with `image_to_data` (for confidence/word data). This doubled processing time on large scanned PDFs.

**Root Cause:**
Two separate Tesseract calls were made per page in the ingestion worker.

**Solution:**
Replaced both calls with a single `ocr_page()` function using only `image_to_data`, extracting both the text and confidence data from one pass.

**File:** `Lambda/worker.py`

---

## 5. Progress Jumping — Page Counter Restarting Each Chunk

**Problem:**
On chunked PDF processing, the progress percentage would jump backwards or restart mid-document. Users saw progress go from 45% back to 10%.

**Root Cause:**
The `start_page` variable was being overwritten at the start of each chunk iteration in the loop, causing page numbers to restart from 0 for each chunk.

**Solution:**
Replaced `start_page` with a monotonic `pages_done` counter that only increments and never resets across chunk iterations.

**File:** `Lambda/worker.py`

---

## 6. Parallel OCR — Single-threaded Processing Too Slow

**Problem:**
Large PDFs (100+ pages) took 10–20+ minutes to process because OCR was single-threaded.

**Solution:**
Rewrote ingestion to split PDFs >10 pages into up to 5 parallel Lambda worker invocations. Each worker processes its assigned page range independently. Progress is aggregated from per-worker S3 files (`progress/{base_name}_worker_{n}.json`).

Added:
- `write_worker_progress()` — writes per-worker S3 progress files
- `invoke_lambda_for_range()` — invokes ingestion Lambda for a page range using `INGESTION_LAMBDA_NAME` env var
- `handle_processing_status` aggregates worker progress files for the frontend

**Files:** `Lambda/worker.py`, `Lambda_ingest.tf` (added `INGESTION_LAMBDA_NAME` env var)

---

## 7. Syntax Error — Orphaned `else:` Block After Parallel OCR Rewrite

**Problem:**
After the parallel OCR rewrite, the ingestion Lambda crashed on startup with a `SyntaxError` due to an orphaned `else:` block that no longer had a matching `if`.

**Root Cause:**
During the refactor, an `else:` clause was left behind after its corresponding `if` block was removed.

**Solution:**
Removed the orphaned `else:` block.

**File:** `Lambda/worker.py`

---

## 8. Agent Code Quality — Multiple Issues Found in Full Review

**Problems found and fixed in `agent_executor.py`:**

| Issue | Fix |
|---|---|
| Inline imports inside functions (`from langchain...`) | Moved all to top-level imports |
| Dead code after `return` statements | Removed unreachable code |
| `NameError` on `failed_images` variable | Initialized `failed_images = []` before use |
| `s3_client` used before assignment in `handle_get_chat` | Replaced with `get_s3_client()` call |
| Bare `except: pass` blocks swallowing errors | Replaced with `except Exception as e: logger.warning(...)` |
| `time.sleep(0.5)` with no purpose | Removed |
| Duplicate `load_session_history` call | Removed second call |
| `enableTrace=True` on Bedrock agent (slow) | Set to `enableTrace=False` |
| Index timestamp checked on every query (S3 call per query) | Throttled to once per 60 seconds using `_index_last_checked` |
| Image size filtering called `head_object` per image (50–200 S3 calls/query) | Switched to `file_size` metadata stored in FAISS index |

**File:** `Lambda/agent_executor.py`

---

## 9. Delete Bug — Wrong S3 Key for Processed File

**Problem:**
`handle_delete_file_api` was trying to delete `processed/{display_name}.json` where `display_name` was the upload-timestamp-prefixed name sent by the frontend. But the actual processed key used the *ingestion* timestamp, which is always different.

**Root Cause:**
`handle_list_files_api` returns `{upload_ts}_{base_name}` (using the upload object's `LastModified`), but the ingestion worker stores the processed file as `processed/{ingest_ts}_{base_name}.json`. These two timestamps are never the same.

**Solution:**
Changed `handle_delete_file_api` to list `processed/` and match by `base_name` (after stripping any timestamp prefix) to find the actual key, regardless of what timestamp is embedded in it.

**File:** `Lambda/agent_executor.py` → `handle_delete_file_api`

---

## 10. Delete Timeout — Synchronous Index Rebuild Exceeding API Gateway 30s Limit

**Problem:**
Delete requests were timing out with "Deletion failed timed out and file still exists" error.

**Root Cause:**
`handle_delete_file_api` was calling `rebuild_master_index()` synchronously. This function downloads all processed documents, re-embeds them, and uploads a new FAISS index — taking 30–60+ seconds, which exceeds API Gateway's hard 30s timeout.

**Solution (4 fixes applied):**
1. Replaced synchronous `rebuild_master_index()` with async Lambda self-invocation (`InvocationType='Event'`, `action: rebuild_index`).
2. Parallelized S3 listing of uploads + images using `ThreadPoolExecutor(max_workers=2)`.
3. Removed `time.sleep(0.5)` delay.
4. Removed query cache clearing (S3 lifecycle handles expiry).

**File:** `Lambda/agent_executor.py` → `handle_delete_file_api`

---

## 11. DOCX Text Extraction — Table Content Missing

**Problem:**
Hebrew formal documents stored in DOCX format were returning empty or near-empty text extractions. The agent couldn't answer questions about their content.

**Root Cause:**
`extract_docx` in `office_converter.py` only iterated `doc.paragraphs`. Many Hebrew formal documents store all their content in tables (`doc.tables`), which were completely ignored.

**Solution:**
Added iteration over `doc.tables` → `table.rows` → `row.cells` to extract cell text in addition to paragraph text.

**File:** `Lambda/office_converter.py` → `extract_docx`

---

## 12. Processing Status — Stale "Extracting Word document content..." Message

**Problem:**
After a DOCX file finished processing, the frontend still showed "Extracting Word document content..." instead of "Complete".

**Root Cause:**
`handle_processing_status` was checking the `progress/` file *before* checking the `processed/` completion marker. The progress file contained the last in-progress message and was being returned even after processing had finished.

**Solution:**
Reordered the checks: check `processed/` (completion marker) first, then fall through to `progress/` only if not yet complete.

**File:** `Lambda/agent_executor.py` → `handle_processing_status`

---

## 13. Missing `semantic_cache.py` — ModuleNotFoundError on Every Query

**Problem:**
Every agent query failed with `ModuleNotFoundError: No module named 'semantic_cache'`.

**Root Cause:**
`semantic_cache.py` was imported in `agent_executor.py` but was not included in the agent Docker image's `COPY` instructions.

**Solution:**
Added `COPY semantic_cache.py ${LAMBDA_TASK_ROOT}` to `agent.Dockerfile`.

**File:** `Lambda/agent.Dockerfile`

---

## 14. CloudWatch Logs VPC Endpoint — Lambda Logs Not Appearing

**Problem:**
Lambda functions inside the VPC were not writing logs to CloudWatch. Log groups existed but were empty.

**Root Cause:**
The Lambda functions use VPC Interface Endpoints for all AWS service access (no NAT Gateway). The `logs` VPC endpoint security group was missing an ingress rule for the VPC CIDR (`10.0.0.0/16` on port 443), so Lambda couldn't reach the endpoint.

**Solution:**
Added a VPC CIDR ingress rule to the CloudWatch Logs VPC endpoint security group in `Security_Groups.tf`.

**File:** `Security_Groups.tf`

---

## 15. Delete UI — File Remains Visible After Successful Delete

**Problem:**
After clicking delete and seeing the green checkmark, the file remained visible in the list for several seconds, confusing users into thinking the delete had failed.

**Root Cause (two parts):**
1. The frontend called `fetchUploadedFiles()` only 500ms after the delete success response — not enough time for S3 to reflect the deletion consistently.
2. (Underlying) The processed file key mismatch (Problem #9) meant the file wasn't actually being deleted from S3 at all.

**Solution:**
- Fixed the S3 key mismatch (Problem #9) so the file is actually deleted.
- Increased the post-delete refresh delay from 500ms to 2000ms in `index.html`.

**File:** `index.html` → delete button `onclick` handler

---

## Key Architecture Insights

| Insight | Detail |
|---|---|
| Line endings | Project uses CRLF (`\r\n`) — all Python edits must account for this |
| Ingestion runtime | Custom runtime (`python:3.11-slim-bookworm` + `awslambdaric`), not official AWS Lambda base image |
| No NAT Gateway | Lambda is in VPC with no NAT — all AWS access via VPC Interface Endpoints |
| S3 bucket | `pdfquery-rag-documents-production` |
| Key prefixes | `uploads/`, `processed/`, `progress/`, `images/`, `vector_store/master/`, `agent-status/`, `session-history/`, `chat-history/` |
| Processed file format | `processed/{ingest_timestamp}_{base_name}.json` |
| Frontend file list format | `{upload_timestamp}_{base_name}` (timestamps differ from ingest timestamp) |
| Index rebuild | Always async — never call `rebuild_master_index()` synchronously in an API handler |
| Image size filtering | Uses `file_size` metadata in FAISS index — never `head_object` per image |
| Terraform rebuild trigger | Uses `filemd5()` of source files — changing source auto-triggers Docker rebuild |
| GuardDuty detector ID | Changed between sessions: `dfbf85425bb24fe08f08c282244f45ed` → `b4374bb9c8ec4cb0a7291e1f99d4ac25` |

---

## 16. Semantic Cache Returning Stale Results for Newly Uploaded Documents

**Problem:**
After uploading a new document, querying about it returned a cached response from a previous similar query — which said the document didn't exist, because it was cached before the document was uploaded.

**Root Cause:**
`process_agent_query_background` checked the semantic cache before going to Bedrock. A query about a document that was previously answered with "not found" had a 0.90 similarity score match in the cache, so the stale "not found" response was returned instead of a fresh search.

**Solution:**
Added a cache bypass for document-specific queries. If the query contains Hebrew words (3+ chars), file extensions, or document reference words (`document`, `file`, `מסמך`, `קובץ`, `חוברת`), the cache is skipped entirely and a fresh response is generated.

Also fixed a bug introduced in the same change: the cache bypass code was trying to use `cached_result['response']` when `cached_result` was `None`, causing the background query to crash silently.

**File:** `Lambda/agent_executor.py` → `process_agent_query_background`

---

## 17. Non-PDF Documents Missing from FAISS Index (.docx, .pptx, .xlsx)

**Problem:**
Documents uploaded as `.docx`, `.pptx`, or `.xlsx` were processed successfully (appeared in `processed/`) but were completely absent from the FAISS vector index. Queries about these documents returned "not found" even though the files existed.

**Root Cause:**
In `rebuild_master_index()` (both in `agent_executor.py` and `worker.py`), the `base_name` was computed as:
```python
base_name = source_file.split('/')[-1].replace('.pdf', '')
```
This only strips `.pdf` extensions. For `.docx` files, the extension was left in the name, so the document was indexed as `חוברת הגשה - גרסה1.3 () משרד האוצר FINOPS.docx` instead of `חוברת הגשה - גרסה1.3 () משרד האוצר FINOPS`. The same bug existed in the search/filter logic, causing mismatches when trying to find documents by name.

**Confirmed via:** Downloaded the FAISS `index.pkl` locally and inspected all 121 source names — none of the 4 recently uploaded Hebrew `.docx` files were present.

**Solution:**
Replaced all 4 occurrences of `.replace('.pdf', '')` with proper extension stripping using `rsplit('.', 1)[0]`:

1. `agent_executor.py` → `rebuild_master_index` — main rebuild function
2. `agent_executor.py` → `unique_sources` extraction in `handle_search_action`
3. `agent_executor.py` → `doc_filter` comparison in `handle_search_action`
4. `worker.py` → fallback rebuild-from-scratch path (404 branch)

After deploying, triggered a manual index rebuild via async Lambda invocation to re-index all 4 missing documents.

**Files:** `Lambda/agent_executor.py`, `Lambda/worker.py`

---

## 18. Hebrew Document Name Not Extracted from Search Query

**Problem:**
When the Bedrock Agent called the `/search` action with a query like `חוברת הגשה - גרסה1.3 () משרד האוצר FINOPS`, the document name extraction patterns all failed, logging `⚠️ No document name extracted from query`. The search returned results from the wrong document.

**Root Cause:**
Two issues:
1. The Bedrock Agent strips framing words (like `המסמך`) before passing the query to the search action, so the `המסמך NAME` pattern never fired.
2. The fallback patterns only matched English alphanumeric patterns (`\d+-\d+-...`) and didn't handle Hebrew document names with version numbers and parentheses.

**Solution:**
Added a final fallback: if the query contains 5+ Hebrew characters AND has either a version pattern (`גרסה`, `version`, `\d+\.\d+`) or parentheses `()`, treat the entire query as the document name.

```python
hebrew_chars = sum(1 for c in decoded_input if '\u05d0' <= c <= '\u05ea')
has_version = bool(re.search(r'גרסה|version|v\d|\d+\.\d+', decoded_input, re.IGNORECASE))
has_parens = '(' in decoded_input or ')' in decoded_input
if hebrew_chars > 5 and (has_version or has_parens):
    doc_name_in_query = decoded_input.strip().rstrip('?')
```

**File:** `Lambda/agent_executor.py` → `handle_search_action` fallback pattern section

---

## 19. Conversation Context Lost Between Messages

**Problem:**
The agent treated every message as a new conversation with no memory of previous questions/answers in the same session.

**Root Cause:**
`process_agent_query_background` was passing `sessionState={'sessionAttributes': {'conversationHistory': history_text[:20000]}}` to `bedrock_client.invoke_agent()`. This `sessionAttributes` field is not used by Bedrock Agent for conversation memory — it's just a passthrough for custom data. Passing it was actually overriding/interfering with Bedrock's native session management.

**Solution:**
Removed the `sessionState` parameter entirely. Bedrock Agent manages conversation context natively via `sessionId` — as long as the same `sessionId` is used across turns, the agent remembers the conversation automatically.

**File:** `Lambda/agent_executor.py` → `process_agent_query_background`

---

## 20. Chat Input Box Too Small — Text Cut Off

**Problem:**
The chat input box was a single-line `<input type="text">` that didn't grow when the user typed long messages. Text was cut off and users couldn't see what they were typing.

**Solution:**
Replaced the `<input type="text">` with a `<textarea>` that auto-resizes as the user types:
- CSS: `resize:none; overflow-y:hidden; min-height:46px; max-height:200px`
- JS: On `input` event, set `height='auto'` then `height=scrollHeight+'px'` (capped at 200px)
- Enter key sends message; Shift+Enter inserts newline
- After sending, height resets to `auto`

**File:** `index.html` → `.input-area` CSS, `#user-input` element, input event handler, keydown handler

---

## 21. Fuzzy Match Threshold Too Low — Wrong Document Selected

**Problem:**
When querying about `חוברת הגשה - גרסה1.3 () משרד האוצר FINOPS`, the fuzzy matcher selected `חוברת הגשה- 16.2024` instead because they share the words `חוברת` and `הגשה`, giving a similarity ratio above the 0.75 threshold.

**Root Cause:**
The fuzzy match threshold in `handle_search_action` was set to 0.75, which was too permissive for Hebrew document names that share common words.

**Solution:**
Raised the fuzzy match threshold from `0.75` to `0.88`.

**File:** `Lambda/agent_executor.py` → `handle_search_action` fuzzy matching section

---

## Key Architecture Insights (Updated)

| Insight | Detail |
|---|---|
| `.replace('.pdf', '')` bug | Was used everywhere to strip file extensions — only works for PDFs. Use `rsplit('.', 1)[0]` instead to handle any extension |
| FAISS source name format | Stored WITHOUT file extension (e.g., `חוברת הגשה - גרסה1.3`) — must strip extension before indexing |
| Bedrock Agent session memory | Use native `sessionId` — do NOT pass `sessionState/sessionAttributes` for conversation history, it breaks native memory |
| Semantic cache bypass | Always bypass cache for Hebrew/document-specific queries to avoid stale "not found" responses after new uploads |
| Index rebuild after deploy | After deploying new Lambda code that fixes indexing bugs, must manually trigger `{"action": "rebuild_index"}` to re-index missing documents |
| FAISS index inspection | Download `index.pkl` from S3 and use `pickle.load()` → `data[0]._dict` to inspect all source names in the index |

---

## 22. Bedrock Agent Context Limit — "Input is too long for requested model"

**Problem:**
After ~15-20 turns in a long conversation, the agent crashed with:
`validationException: Input is too long for requested model`

Users got a failed query with no response.

**Root Cause:**
Bedrock Agent accumulates the full conversation history internally per `sessionId` — every turn adds the user message + agent response + all search results (~6KB) to its internal context. After enough turns this exceeds the model's input limit.

The model is Claude Sonnet 4.5 which has a 200K token window, but the issue was that each search call returned 6KB of document chunks, and Bedrock stored all of them across all turns. With long detailed Hebrew document analysis sessions, this accumulated quickly.

**Confirmed via logs:**
- `save-chat` payload growing: 87KB → 90KB → 94KB over 3 messages
- Error: `validationException: Input is too long for requested model`

**Solution — Self-managed context injection:**
Instead of relying on Bedrock's native session memory (which grows unboundedly), we now:

1. Use a **fresh per-call session ID** (`session_id_timestamp`) on every invocation — Bedrock starts clean each time
2. **Inject context manually** into every `inputText`:
   - Always include the **first user message** (original topic, capped at 500 chars)
   - Always include the **last 3 Q&A pairs** (recent context, each capped at 600 chars)
3. **Safety net**: if the injected query is somehow still too long, retry with bare query

This mirrors how production AI assistants (including Amazon Q) work — each call is self-contained with only the relevant context injected, rather than relying on stateful session accumulation.

**Also fixed:**
- `NameError` bug: `recent_turns` was only defined inside `if history:` block but referenced outside it — fixed by initializing `recent_turns = []` before the block
- Removed unused `compressed_history` variable
- Reduced search results from 30 → 15 text chunks per call to further reduce per-turn context size without quality loss (top 15 are already the most relevant)

**File:** `Lambda/agent_executor.py` → `process_agent_query_background`
