# Leidos RAG Pipeline — Amazon Q Project Context

## Standing Instructions

- **NEVER** update `PROBLEMS_AND_SOLUTIONS.md` unless the user explicitly confirms the fix is working (e.g., "it's working now", "confirmed", "that fixed it").
- When the user confirms a fix, append the new problem and solution to `d:\Projects\LEIDOS\PROBLEMS_AND_SOLUTIONS.md` using the same format as existing entries (Problem, Root Cause, Solution, File).
- Always prefer `fsReplace` for targeted code edits over rewriting entire files.
- Always run a syntax check (`python -m py_compile`) after editing any Python file.
- After fixing Python Lambda code, deploy with `terraform apply -auto-approve -target=null_resource.build_and_push_agent_image` for agent Lambda or `terraform apply -auto-approve -target=null_resource.build_and_push_ingestion_image` for ingestion Lambda.
- Project uses **CRLF line endings** (`\r\n`) — account for this in all string matching and file edits.
- Never call `rebuild_master_index()` synchronously inside an API handler — always use async Lambda invocation (`InvocationType='Event'`, `action: rebuild_index`).
- User prefers direct `fsReplace` edits over Python scripts for code changes.
- Write only the minimal amount of code needed — avoid verbose implementations.

---

## Project Architecture

**Type:** AWS-based RAG (Retrieval-Augmented Generation) document assistant
**IaC:** Terraform (all infrastructure defined in `d:\Projects\LEIDOS\*.tf`)
**Language:** Python 3.11 (Lambda), JavaScript (frontend)

### Components
| Component | Description |
|---|---|
| Bedrock Agent | Orchestrates queries, calls Lambda action group for search |
| FAISS Vector Store | Semantic search index stored in S3, loaded into Lambda memory |
| S3 | All storage — uploads, processed docs, images, vector store, progress, chat history |
| Agent Lambda | Handles all API routes + Bedrock Agent action group (`agent_executor.py`) |
| Ingestion Lambda | Processes uploaded documents — OCR, text extraction, image extraction (`worker.py`) |
| API Gateway | REST API fronting the Agent Lambda |
| Cognito | User authentication (MFA/TOTP enforced) |
| CloudFront | Serves `index.html` frontend |
| VPC | Lambda runs in VPC with **no NAT Gateway** — all AWS access via VPC Interface Endpoints |

### Data Flow
1. User uploads file → S3 `uploads/` via presigned URL
2. S3 event triggers Ingestion Lambda → OCR/extract → writes `processed/{ingest_ts}_{base_name}.json`
3. Ingestion Lambda rebuilds FAISS master index → uploads to `vector_store/master/`
4. User queries → API Gateway → Agent Lambda → Bedrock Agent → Lambda action group `/search` → FAISS → response

---

## File Locations & Naming Conventions

### Key Source Files
| File | Purpose |
|---|---|
| `Lambda/agent_executor.py` | Main agent Lambda handler (~3000+ lines). All API routes, FAISS search, file management, chat history, autofill |
| `Lambda/worker.py` | Ingestion worker. OCR, text/image extraction, parallel processing, progress tracking |
| `Lambda/office_converter.py` | DOCX/PPTX/XLSX text + image extractor |
| `Lambda/semantic_cache.py` | Semantic similarity cache for agent responses |
| `Lambda/agent.Dockerfile` | Agent Lambda Docker image |
| `Lambda/ingestion.Dockerfile` | Ingestion Lambda Docker image |
| `Lambda_agent.tf` | Agent Lambda Terraform config + env vars |
| `Lambda_ingest.tf` | Ingestion Lambda Terraform config + env vars |
| `Security_Groups.tf` | VPC security groups |
| `index.html` | Frontend — single-file SPA (file list, upload, chat, progress polling) |
| `PROBLEMS_AND_SOLUTIONS.md` | Log of all problems solved in this project |

### S3 Bucket
**Name:** `pdfquery-rag-documents-production`

| Prefix | Contents |
|---|---|
| `uploads/` | Raw uploaded files |
| `processed/` | Extracted text/image metadata JSON files |
| `progress/` | Processing progress files (per-file and per-worker) |
| `images/` | Extracted images from documents |
| `vector_store/master/` | FAISS index files (`index.faiss`, `index.pkl`) |
| `agent-status/` | Async agent query status files |
| `session-history/` | Bedrock session conversation history |
| `chat-history/` | Saved user chat sessions |
| `errors/` | Processing error markers |
| `cancelled/` | Upload cancellation markers |

### Naming Conventions
- Processed files: `processed/{ingest_timestamp}_{base_name}.json`
- Frontend file list returns: `{upload_timestamp}_{base_name}` — **these timestamps are always different from ingest timestamps**
- Worker progress files: `progress/{base_name}_worker_{n}.json`
- Delete API receives `{upload_timestamp}_{base_name}` — must list `processed/` and match by `base_name` to find actual key

---

## Key Insights & Gotchas

| # | Insight |
|---|---|
| 1 | **CRLF line endings** — project uses `\r\n`. Account for this in string matching. |
| 2 | **No NAT Gateway** — Lambda is in a VPC. All AWS service calls go through VPC Interface Endpoints. The `logs` endpoint needs VPC CIDR ingress rule (`10.0.0.0/16` on port 443). |
| 3 | **Ingestion runtime** — uses custom runtime (`python:3.11-slim-bookworm` + `awslambdaric`), NOT the official AWS Lambda base image. |
| 4 | **Timestamp mismatch** — `processed/` key uses ingestion timestamp; frontend sends upload timestamp. Never assume they match. Always list `processed/` and match by `base_name`. |
| 5 | **Index rebuild is slow** (30–60s) — NEVER call `rebuild_master_index()` synchronously in any API handler. Always fire async Lambda invocation. |
| 6 | **Image size filtering** — uses `file_size` metadata stored in FAISS index. Never call `head_object` per image (was causing 50–200 S3 calls per query). |
| 7 | **Terraform rebuild trigger** — uses `filemd5()` of source files. Changing a source file automatically triggers Docker rebuild + ECR push on next `terraform apply`. |
| 8 | **Parallel OCR** — PDFs >10 pages are split into up to 5 parallel Lambda workers. Progress is aggregated from per-worker S3 files. |
| 9 | **Hebrew documents** — many store content in DOCX tables, not paragraphs. Always extract both `doc.paragraphs` and `doc.tables`. |
| 10 | **`semantic_cache.py`** must be explicitly copied in `agent.Dockerfile` — it is not auto-included. |
| 11 | **API Gateway 30s timeout** — any synchronous operation that might exceed 30s must be made async. |
| 12 | **GuardDuty detector ID** — has changed between sessions. Always look it up dynamically rather than hardcoding. |
| 13 | **`AGENT_LAMBDA_NAME` env var** — must be set in `Lambda_agent.tf` for async self-invocation to work. |
| 14 | **`INGESTION_LAMBDA_NAME` env var** — must be set in `Lambda_ingest.tf` for parallel worker invocation. |

---

## Environment Variables

### Agent Lambda (`Lambda_agent.tf`)
| Variable | Value |
|---|---|
| `S3_BUCKET` | `pdfquery-rag-documents-production` |
| `BEDROCK_AGENT_ID` | (from Terraform) |
| `BEDROCK_AGENT_ALIAS_ID` | (from var) |
| `EMBEDDINGS_MODEL_ID` | `cohere.embed-multilingual-v3` |
| `AGENT_LAMBDA_NAME` | `${var.project_name}-agent-executor` |
| `INGESTION_LAMBDA_NAME` | (from ingestion Lambda resource) |
| `USER_POOL_ID` | (from Cognito) |
| `CLIENT_ID` | (from Cognito) |

### Ingestion Lambda (`Lambda_ingest.tf`)
| Variable | Value |
|---|---|
| `S3_BUCKET` | `pdfquery-rag-documents-production` |
| `INGESTION_LAMBDA_NAME` | `${var.project_name}-ingestion-worker` |

---

## Deployment Commands

```bash
# Deploy agent Lambda (after editing agent_executor.py, agent.Dockerfile, etc.)
terraform apply -auto-approve -target=null_resource.build_and_push_agent_image

# Deploy ingestion Lambda (after editing worker.py, office_converter.py, etc.)
terraform apply -auto-approve -target=null_resource.build_and_push_ingestion_image

# Deploy frontend (after editing index.html)
terraform apply -auto-approve -target=null_resource.deploy_frontend

# Full deploy
terraform apply -auto-approve

# Syntax check Python files
python -m py_compile Lambda/agent_executor.py
python -m py_compile Lambda/worker.py
python -m py_compile Lambda/office_converter.py
```
