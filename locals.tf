# locals.tf

locals {
  # This creates a unique ID (the first 8 chars of the hash)
  # every time your Python code file changes.
  agent_source_hash = substr(filemd5("Lambda/agent_executor.py"), 0, 8)
}