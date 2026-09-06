"""Load source Documents containing extracted text and metadata.

These loaders do not split text into chunks or generate embeddings.
The RAG service performs those steps before indexing a knowledge base.
"""

import tempfile
from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_core.documents import Document


def load_text(text: str, source_name: str = "pasted-text") -> list[Document]:
    """Wrap pasted text as one source Document with source metadata."""
    return [
        Document(
            page_content=text,
            metadata={"source": source_name, "source_type": "txt"},
        )
    ]


def load_uploaded_file(filename: str, content: bytes) -> list[Document]:
    """Extract source Documents from a file before chunking.

    Args:
        filename: Original filename used in source metadata.
        content: Uploaded file bytes.

    Returns:
        Source Documents with text and metadata. Text files yield one Document;
        the PDF loader may yield multiple Documents, typically one per page.

    Raises:
        ValueError: The file type is unsupported.
        Exception: File parsing fails.
    """
    suffix = Path(filename).suffix.lower()
    source_type = suffix.removeprefix(".")

    if suffix in {".txt", ".md"}:
        text = content.decode("utf-8", errors="replace")
        return [
            Document(
                page_content=text,
                metadata={"source": filename, "source_type": source_type},
            )
        ]

    if suffix not in {".pdf", ".docx"}:
        raise ValueError(
            "Unsupported file type. Use PDF, DOCX, TXT, or MD."
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as temp_file:
        temp_file.write(content)
        temp_file.flush()

        if suffix == ".pdf":
            documents = PyPDFLoader(temp_file.name).load()
        else:
            documents = Docx2txtLoader(temp_file.name).load()

    for doc in documents:
        doc.metadata["source"] = filename
        doc.metadata["source_type"] = source_type

    return documents
