# Naive RAG with Gemini + LangChain

A small learning project providing a frontend-friendly RAG API for text and uploaded documents.

## What it does

- Upload PDF, DOCX, TXT, or MD files
- Paste raw text/transcripts
- Group multiple sources in a knowledge base identified by `knowledge_base_id`
- Split documents with `RecursiveCharacterTextSplitter`
- Embed with Gemini Embedding 2
- Store/search with FAISS
- Answer questions with Gemini 3.8 Flash
- Return retrieved chunks to the frontend as sources

## Architecture

```text
File / Text
        |
        v
     Loader
        |
        v
RecursiveCharacterTextSplitter
        |
        v
Gemini Embeddings
        |
        v
      FAISS
        |
question -> similarity search -> context -> Gemini -> answer
```

This is intentionally **Naive RAG**. It does not include reranking, hybrid search, query rewriting, agents, persistent vector databases, auth, or production deployment patterns.

## Storage model

A file is loaded into source `Document` objects (text + metadata), then split into
chunk `Document` objects that carry source metadata. Each chunk gets its own
embedding. Inserting chunks into `vector_index` means the FAISS wrapper stores
vectors in its index and chunk text/metadata in its docstore, linked by internal
IDs. The retained `source_documents` and `chunks` lists do not contain embeddings.

Initial insertion happens in `FAISS.from_documents`; registry `create` registers
the prepared data under a UUID. Later ingestion uses `add_documents` to insert
new chunks into that collection's index. Retrieval searches only the selected
collection. See the concise file-to-index example at the top of
`app/knowledge_base_registry.py`.

In a relational DB analogy: database `rag_app`, schema `public`, and tables
`knowledge_bases`, `documents`, and `chunks`. A collection is one knowledge-base
record with related documents/chunks, not a database or schema. These SQL tables
and foreign keys are not implemented by the in-memory registry.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.
Python 3.12 is selected by `.python-version`; `uv sync` installs it if needed
and creates the local `.venv` using the committed `uv.lock`.

```bash
cp .env.example .env
# Set your Gemini API key and review all configuration values in .env

uv sync --locked
uv run uvicorn app.main:app --reload --port 8000
```

Use `uv add <package>` to add runtime dependencies and update `uv.lock`.
Keep `pyproject.toml`, `.python-version`, and `uv.lock` in Git; `.venv` and
your local `.env` are ignored. No test directory or test dependencies are included.

All eight settings in `.env.example` are required, including the application
metadata, model names, chunk sizes, and retrieval count. Supply them through
environment variables or `.env`; environment variables take precedence. There
are no application configuration defaults. Missing any setting from both sources
raises a Pydantic validation error when the application is imported, aborting startup.

Open FastAPI docs at:

```text
http://localhost:8000/docs
```

## Main API flow

`GET /health_test` returns `{"status":"ok"}` to check that the API responds.
It does not probe Gemini or other external services.

### 1. Ingest text

```bash
curl -X POST http://localhost:8000/ingest/text \
  -H "Content-Type: application/json" \
  -d '{"text":"RAG retrieves relevant document chunks before generating an answer.","source_name":"notes"}'
```

Keep the returned `knowledge_base_id` in frontend state. It is a UUID selecting a collection scope, not a topic name or file ID. Reuse it when adding sources or asking questions. A UI may label that scope "RAG Tutorial", but this storage model has no display-name field or automatic topic classification.

Both text and file ingestion return `knowledge_base_id` and `source`.
Chunk counts remain internal and are not included in the API response.

### 2. Add a document to the same knowledge base

```bash
curl -X POST http://localhost:8000/ingest/file \
  -F "file=@notes.pdf" \
  -F "knowledge_base_id=YOUR_KNOWLEDGE_BASE_ID"
```

### 3. Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"knowledge_base_id":"YOUR_KNOWLEDGE_BASE_ID","question":"What are the main ideas?","k":4}'
```

The response contains both `answer` and the retrieved `sources`, so a frontend can render citations/snippets.

## Code layout

- `app/knowledge_base_registry.py`: `KnowledgeBase` groups source documents, chunks, and their vector index; `KnowledgeBaseRegistry` manages them by ID in memory.
- `app/RAG_Orchestration.py`: RAG service imported by the API, handling ingestion, retrieval, and answer generation.
- `app/api_models.py` and `app/main.py`: request/response models and HTTP routes.

## Important demo limitation

Knowledge bases live only in Python memory. Restarting the API deletes them. That is deliberate for a small learning project. A later production-oriented version can replace `KnowledgeBaseRegistry` + FAISS with Qdrant, Pinecone, pgvector, or another persistent vector database without changing the public API much.
