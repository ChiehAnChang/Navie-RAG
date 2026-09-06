"""Expose ingestion and question answering APIs scoped by knowledge_base_id.

This module handles HTTP input, output, and error mapping.
RAG_Orchestration.RAGService handles splitting, embedding, retrieval, and
generation, using KnowledgeBaseRegistry internally for storage.
Clients retain the ID returned by ingestion to add sources or ask questions.
In routes, payload is parsed JSON and request is the HTTP request object.
request.app.state.rag retrieves the service created at startup without creating
a new knowledge base.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from backend.config import SETTINGS
from backend.loaders import load_text, load_uploaded_file
from backend.RAG_Orchestration import RAGService
from backend.api_models import (
    AnswerResponse,
    IngestResponse,
    QuestionRequest,
    SourceItem,
    TextIngestRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
        Create RAGService at startup before accepting requests.

        Requests in one process share this object; each worker has its own registry.
        The registry is stored in memory and does not survive restarts.
        Initialization failure aborts startup. Shutdown clears the app service reference.
        RAGService has no close method; clearing the reference does not explicitly close connections.
    """
    app.state.rag = RAGService()
    try:
        yield
    finally:
        # Mark the service unavailable on normal shutdown or a lifespan exception.
        app.state.rag = None


app = FastAPI(
    title=SETTINGS.app_title,
    version=SETTINGS.app_version,
    lifespan=lifespan,
)

# Allow local frontend integration; restrict allowed origins in production.
# CORS controls browser cross-origin access, not identity or knowledge base permissions.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health_test")
def health_test() -> dict[str, str]:
    """
        Check that the API process responds, without probing Gemini or external services.
    """
    return {"status": "ok"}


@app.get("/knowledge-bases", response_model=list[str])
def list_knowledge_bases(request: Request) -> list[str]:
    """List the collection IDs available in this API process."""
    return request.app.state.rag.knowledge_bases.list_ids()


@app.post("/ingest/text", response_model=IngestResponse)
def ingest_text(payload: TextIngestRequest, request: Request) -> IngestResponse:
    """
        Pass pasted text to RAGService for splitting and indexing, then return the result.

        Pydantic validates the payload before this function; map ValueError/KeyError to HTTP 400.
    """
    rag = request.app.state.rag
    try:
        documents = load_text(payload.text, payload.source_name)
        knowledge_base_id, _ = rag.ingest(
            documents, knowledge_base_id=payload.knowledge_base_id
        )
        return IngestResponse(
            knowledge_base_id=knowledge_base_id,
            source=payload.source_name,
        )
    except (ValueError, KeyError) as exception_message:
        raise HTTPException(status_code=400, detail=str(exception_message)) from exception_message


@app.post("/ingest/file", response_model=IngestResponse)
def ingest_file(
    request: Request,
    file: UploadFile = File(...),
    knowledge_base_id: str | None = Form(default=None),
) -> IngestResponse:
    """
        Extract source Documents from a multipart/form-data upload for RAGService.

        File/Form supply the file and ID, so this route does not use a JSON request model.
        FastAPI runs this synchronous route in a thread pool to keep parsing and embedding off the event loop.
        Return 400 for input errors such as missing filenames, unsupported files, or unknown knowledge bases.
    """
    rag = request.app.state.rag
    try:
        if not file.filename:
            raise ValueError("Uploaded file must have a filename.")

        content = file.file.read()
        documents = load_uploaded_file(file.filename, content)
        knowledge_base_id, _ = rag.ingest(
            documents, knowledge_base_id=knowledge_base_id
        )
        return IngestResponse(
            knowledge_base_id=knowledge_base_id,
            source=file.filename,
        )
    except (ValueError, KeyError) as exception_message:
        raise HTTPException(status_code=400, detail=str(exception_message)) from exception_message


@app.post("/ask", response_model=AnswerResponse)
def ask(payload: QuestionRequest, request: Request) -> AnswerResponse:
    """
        Retrieve from one knowledge base and return the generated answer and retrieved chunks.

        Return 404 for an unknown knowledge base and 502 for other retrieval or generation failures.
    """
    rag = request.app.state.rag
    try:
        answer, documents = rag.ask(
            question=payload.question,
            knowledge_base_id=payload.knowledge_base_id,
            k=payload.k,
        )
        # rag.ask already retrieved and generated; format the sources for the API response here.
        # SourceItem validates field types, not source credibility or support for the answer.
        sources = [
            SourceItem(
                source=str(doc.metadata.get("source", "unknown")),
                page=doc.metadata.get("page"),
                content=doc.page_content,
            )
            for doc in documents
        ]
        return AnswerResponse(answer=answer, sources=sources)

    except KeyError as exception_message:
        raise HTTPException(status_code=404, detail=str(exception_message)) from exception_message

    except Exception as exception_message:
        raise HTTPException(status_code=502, detail=f"RAG request failed: {exception_message}") from exception_message
