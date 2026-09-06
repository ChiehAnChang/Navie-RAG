"""Orchestrate source-document splitting, chunk indexing, and scoped RAG answers."""

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import SETTINGS
from app.knowledge_base_registry import KnowledgeBaseRegistry


QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
            You answer questions using only the provided context.
            If the context does not contain enough information, say that you do not know based on the indexed sources.
            Do not invent facts. Keep the answer clear and concise.
            
            Output Format Example:
            
            Your Question is: \n{question}\n\n
            
            My Answer to the Question is: \n<generated answer>\n\n
            
            """,
        ),
        (
            "human",
            "Question:\n{question}\n\nRetrieved context:\n{context}",
        ),
    ]
)


class RAGService:
    """Manage RAG operations with shared clients and in-memory knowledge bases."""

    def __init__(self) -> None:
        """Initialize clients, storage, and chains using application SETTINGS.

        No caller-supplied parameters.

        Returns:
            None.

        Assumptions:
            Model, credential, and splitter settings are configured correctly.

        Raises:
            Exception: A dependency fails to initialize.
        """
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model=SETTINGS.embedding_model,
            google_api_key=SETTINGS.google_api_key,
        )
        self.llm = ChatGoogleGenerativeAI(
            model=SETTINGS.gemini_model,
            google_api_key=SETTINGS.google_api_key,
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=SETTINGS.chunk_size,
            chunk_overlap=SETTINGS.chunk_overlap,
        )
        self.knowledge_bases = KnowledgeBaseRegistry()
        # Each chain formats a prompt, calls the model, then extracts text.
        self.answer_generation_chain = QA_PROMPT | self.llm | StrOutputParser()

    def ingest(self, documents: list[Document], knowledge_base_id: str | None = None,) -> tuple[str, int]:
        """Split source documents and insert their chunks into a collection's index.

        Args:
            documents: Loaded source Documents containing text and source metadata.
            knowledge_base_id: Existing collection UUID; None or empty creates one.

        Returns:
            (knowledge_base_id, chunks_added) for this ingestion call.

        Assumptions:
            Text is already extracted. One file may yield multiple source Documents.
            Source metadata is recommended for attribution; page is optional.

        Raises:
            ValueError: No usable chunks are produced.
            KeyError: The requested knowledge base does not exist.
            Exception: Chunk embedding or vector index insertion fails.
        """

        # Split source Documents into chunk Documents, carrying source metadata forward.
        chunks = self.splitter.split_documents(documents)
        
        if not chunks:
            raise ValueError("No usable text was found in the source.")

        # Reuse the collection scope: embed and insert new chunks into its index.
        if knowledge_base_id:
            self.knowledge_bases.add_documents(knowledge_base_id, documents, chunks)
            return knowledge_base_id, len(chunks)

        # Initial insertion: embed each chunk, index its vector, and retain its
        # text/metadata in the FAISS wrapper docstore with an internal ID mapping.
        vector_index = FAISS.from_documents(chunks, self.embeddings) 
        
        # Register the prepared index with source documents and chunks under a new UUID.
        new_knowledge_base_id = self.knowledge_bases.create(vector_index, documents, chunks)
        return new_knowledge_base_id, len(chunks)

    def ask(self, question: str, knowledge_base_id: str, k: int | None = None):
        """Answer a question using chunks from the selected collection scope.

        Args:
            question: Question text to answer.
            knowledge_base_id: UUID selecting the knowledge base's vector index.
            k: Maximum chunks to retrieve; None or zero uses the default.

        Returns:
            (answer, retrieved_documents), where retrieved_documents are chunks
            containing text and source metadata, not full source documents.

        Assumptions:
            The question is nonempty and k is positive or None.
            The knowledge base exists in this service's registry.

        Raises:
            KeyError: The knowledge base does not exist.
            Exception: Retrieval or answer generation fails.
        """
        
        # Select one collection scope; this does not search across knowledge bases.
        knowledge_base = self.knowledge_bases.get(knowledge_base_id)
        
        # Use the provided k or the default from global SETTINGS.
        retrieval_k = k or SETTINGS.default_retrieval_k
        
        # Embed the question, search chunk vectors, and return linked chunk Documents.
        retrieved_documents = knowledge_base.vector_index.similarity_search(question, k=retrieval_k)

        context_sections = []
        # Start at 1 for readable source labels; these are not list indices.
        for source_number, document in enumerate(retrieved_documents, start=1):
            context_section = f"[Source {source_number}]\n{document.page_content}"
            context_sections.append(context_section)

        # Join the retrieved chunks into a single context string for the model.
        context = "\n\n".join(context_sections)

        answer = self.answer_generation_chain.invoke(
            {
                "question": question,
                "context": context,
            }
        )
        return answer, retrieved_documents


# Temporarily disabled: YouTube ingestion and/or summaries.
# Move each block back to its indicated scope before uncommenting.

# SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
#     [
#         (
#             "system",
#             "Summarize the provided source content. Focus on the important ideas and avoid filler.",
#         ),
#         (
#             "human",
#             "Source content:\n{content}"
#         ),
#     ]
# )

# Restore inside RAGService.__init__.
#         self.summary_chain = SUMMARY_PROMPT | self.llm | StrOutputParser()

# Restore as a RAGService method.
#     def summarize(self, knowledge_base_id: str) -> str:
#         """Summarize retained source text in one knowledge base without chunk retrieval.
#
#         Args:
#             knowledge_base_id: Knowledge base UUID string returned by ingestion.
#
#         Returns:
#             Generated summary; input is truncated to SETTINGS.max_summary_chars characters.
#
#         Raises:
#             KeyError: The knowledge base does not exist in this process registry.
#             Exception: The model call or summary generation fails.
#         """
#         knowledge_base = self.knowledge_bases.get(knowledge_base_id)
#         content = "\n\n".join(
#             document.page_content for document in knowledge_base.source_documents
#         )
#         content = content[: SETTINGS.max_summary_chars]
#         return self.summary_chain.invoke({"content": content})
