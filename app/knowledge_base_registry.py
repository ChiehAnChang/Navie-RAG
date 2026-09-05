"""Store source documents, chunks, and their vector index by knowledge base ID.

Example:
    Add ingestion.txt containing "Load documents. Search relevant chunks."
    to a collection that the user thinks of as "RAG Tutorial":

    registry._knowledge_bases
    +-- "550e8400-e29b-41d4-a716-446655440000" -> KnowledgeBase
        +-- source_documents: [Document(
        |       page_content="Load documents. Search relevant chunks.",
        |       metadata={"source": "ingestion.txt", "source_type": "file"})]
        +-- chunks: [
        |       Document(page_content="Load documents.", metadata=M),
        |       Document(page_content="Search relevant chunks.", metadata=M)]
        +-- vector_index: FAISS wrapper
            +-- index: vector 0 = [0.2, 0.8, 0.1]
            |          vector 1 = [0.7, 0.1, 0.4]
            +-- index_to_docstore_id: {0: "chunk-a", 1: "chunk-b"}
            +-- docstore: "chunk-a" -> first chunk's text + metadata
                          "chunk-b" -> second chunk's text + metadata

    M abbreviates each chunk's metadata inherited from the source Document:
    {"source": "ingestion.txt", "source_type": "file"}.
    Boundaries, chunk IDs, and 3D vectors are illustrative, not actual output.
    Real chunk boundaries/overlap and vector dimensions depend on configuration.

Storage flow:
    File -> source Document(s) -> chunks -> one embedding per chunk -> FAISS.
    Source documents and chunks are both Document objects containing text and
    metadata; embedding vectors live in the FAISS index, not in these lists.
    One file can yield multiple source Documents, such as one per PDF page.

    "Insert chunks into vector_index" means passing chunks to the FAISS wrapper:
    it embeds each chunk's text, stores the vectors in its index, and stores the
    chunk Documents (text + metadata) in its docstore, linked by internal IDs.
    Initial insertion uses FAISS.from_documents in the RAG service; later
    insertion uses vector_index.add_documents here. create only registers data.

Collection scope:
    knowledge_base_id is a UUID selecting one collection's documents and index.
    A caller can group files by topic, such as "RAG Tutorial", and reuse this ID
    to add files or search that collection. The ID is not a topic name; this
    model stores no display name and does not automatically classify documents.

DB analogy:
    Database: rag_app -> schema: public -> tables: knowledge_bases, documents,
    chunks. A knowledge_base_id would be a knowledge_bases primary key, with
    related documents/chunks rows. Here these are Python objects, not SQL tables
    or enforced foreign keys. A collection is not a separate database/schema.
    Storage is process-local memory: no persistence, worker sharing, or rollback.
"""

from dataclasses import dataclass, field
from uuid import uuid4

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document


@dataclass
class KnowledgeBase:
    """Group the source documents, chunks, and vector index for one collection.

    Attributes:
        vector_index: FAISS wrapper storing chunk vectors and linked Documents.
        source_documents: Loaded Documents before splitting, retained for summaries.
        chunks: Split Documents with text and source metadata, used for retrieval.

    Both lists contain Document objects, not embeddings. The dataclass creates
    an initializer for these fields; it does not create a DB table.
    """

    vector_index: FAISS
    # Each knowledge base gets its own lists.
    source_documents: list[Document] = field(default_factory=list)
    chunks: list[Document] = field(default_factory=list)


class KnowledgeBaseRegistry:
    """Manage collection scopes by UUID using an in-memory dictionary."""

    def __init__(self) -> None:
        """Initialize an empty knowledge base registry.

        No caller-supplied parameters.

        Returns:
            None.
        """
        # Map each collection ID to its source documents, chunks, and index.
        self._knowledge_bases: dict[str, KnowledgeBase] = {}

    def create(
        self,
        vector_index: FAISS,
        source_documents: list[Document],
        chunks: list[Document],
    ) -> str:
        """Register a prepared knowledge base and return its collection ID.

        Args:
            vector_index: FAISS wrapper already containing the supplied chunks.
            source_documents: Loaded Documents before splitting.
            chunks: Split Documents whose embeddings are already indexed.

        Returns:
            A UUID string identifying this collection for ingestion and retrieval.

        Assumptions:
            The caller has built the index from these chunks; no consistency check
            or embedding generation occurs here.
        """
        # UUID v4 is a random Universally Unique Identifier, used like a primary key.
        knowledge_base_id = str(uuid4())
        # Register the prepared index; chunk insertion has already happened.
        # Copy list containers while retaining the Document and index references.
        self._knowledge_bases[knowledge_base_id] = KnowledgeBase(
            vector_index=vector_index,
            source_documents=list(source_documents),
            chunks=list(chunks),
        )
        return knowledge_base_id

    def get(self, knowledge_base_id: str) -> KnowledgeBase:
        """Return the knowledge base defining the requested collection scope.

        Args:
            knowledge_base_id: UUID string returned by create.

        Returns:
            The stored KnowledgeBase object, not a copy.

        Raises:
            KeyError: The knowledge base does not exist in this registry.
        """
        knowledge_base = self._knowledge_bases.get(knowledge_base_id)
        if knowledge_base is None:
            raise KeyError(f"Knowledge base '{knowledge_base_id}' was not found.")
        return knowledge_base

    def add_documents(
        self,
        knowledge_base_id: str,
        source_documents: list[Document],
        chunks: list[Document],
    ) -> None:
        """Insert new chunks into the selected vector index and retain source text.

        Args:
            knowledge_base_id: Existing collection ID returned by create.
            source_documents: Newly loaded Documents before splitting.
            chunks: New chunks containing text and inherited source metadata.

        Returns:
            None. Updates the existing knowledge base in place.

        Assumptions:
            The caller has split the source documents. No deduplication or
            transaction rollback is provided.

        Raises:
            KeyError: The knowledge base does not exist.
            Exception: Chunk embedding or vector index insertion fails.
        """
        knowledge_base = self.get(knowledge_base_id)
        # Embed each chunk and insert its vector plus linked text/metadata via FAISS.
        # If insertion raises, the source and chunk lists below are not extended.
        knowledge_base.vector_index.add_documents(chunks)
        # Retain the source text and chunks alongside the updated vector index.
        knowledge_base.source_documents.extend(source_documents)
        knowledge_base.chunks.extend(chunks)
