"""Orchestrate indexing, QA, and summarization of loaded documents."""

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
            
            My Answer to the Question is: \n{answer}\n\n
            
            """,
        ),
        (
            "human",
            "Question:\n{question}\n\nRetrieved context:\n{context}",
        ),
    ]
)

SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Summarize the provided source content. Focus on the important ideas and avoid filler.",
        ),
        (
            "human", 
            "Source content:\n{content}"
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
        self.summary_chain = SUMMARY_PROMPT | self.llm | StrOutputParser()

    def ingest(self, documents: list[Document], knowledge_base_id: str | None = None,) -> tuple[str, int]:
        """Split, embed, and store documents in a knowledge base.

        Assumptions:
                    Text is already extracted and yields at least one usable chunk.
                    Source metadata is recommended for attribution; page is optional.
        
        Args:
            documents: Loaded Documents containing text and optional metadata.
            knowledge_base_id: Existing knowledge base ID; None or empty creates one.

        Returns:
            (knowledge_base_id, chunks_added) for this ingestion call.

        Raises:
            ValueError: No usable chunks are produced.
        """

        # Use splitter to break documents into smaller chunks for embedding and retrieval.
        chunks = self.splitter.split_documents(documents)
        
        # If no chunks are produced, raise an error to indicate the source was not usable.
        if not chunks:
            raise ValueError("No usable text was found in the source.")

        # A knowledge base groups documents for retrieval and summarization.
        # If provided, add the new documents and chunks to the existing knowledge base.
        if knowledge_base_id:
            self.knowledge_bases.add_documents(knowledge_base_id, documents, chunks)
            return knowledge_base_id, len(chunks)

        # If no knowledge base ID is provided, create a new knowledge base with the chunks.
        # The FAISS wrapper embeds the chunks and builds a searchable index.
        # We give FAISS the chunks and our embeddings method to create the vector store.
        vector_index = FAISS.from_documents(chunks, self.embeddings) 
        
        # Keep source documents as well, since summarization uses their text.
        new_knowledge_base_id = self.knowledge_bases.create(vector_index, documents, chunks)
        return new_knowledge_base_id, len(chunks)

    def ask(self, question: str, knowledge_base_id: str, k: int | None = None):
        """Answer a question using chunks retrieved from a knowledge base.
        
        Assumptions:
            The question is nonempty and k is positive or None.
            The knowledge base was created in this service's knowledge base registry.
            
        Args:
            question: Question text to answer.
            knowledge_base_id: ID of the knowledge base to search.
            k: Maximum chunks to retrieve; None or zero uses the default.

        Returns:
            (answer, retrieved_documents), including chunk metadata.
        """
        
        # Retrieve the knowledge base selected by the caller.
        knowledge_base = self.knowledge_bases.get(knowledge_base_id)
        
        # Use the provided k or the default from global SETTINGS.
        retrieval_k = k or SETTINGS.default_retrieval_k
        
        # The wrapper embeds the question and searches the existing index.
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

    