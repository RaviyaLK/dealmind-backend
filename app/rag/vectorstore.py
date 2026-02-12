import logging
import uuid
import shutil
import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Optional, Dict, Any
from app.config import settings
from app.rag.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB vector store for RAG operations."""

    _client = None

    COLLECTIONS = {
        "proposals": "dealmind_proposals",
        "rfps": "dealmind_rfps",
        "emails": "dealmind_emails",
        "transcripts": "dealmind_transcripts",
        "general": "dealmind_general",
    }

    @classmethod
    def get_client(cls) -> chromadb.ClientAPI:
        if cls._client is None:
            chroma_path = str(settings.chroma_path)
            try:
                cls._client = chromadb.PersistentClient(
                    path=chroma_path,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                logger.info("ChromaDB client initialised at %s", chroma_path)
            except Exception as e:
                logger.warning("ChromaDB store corrupted (%s), resetting...", e)
                shutil.rmtree(chroma_path, ignore_errors=True)
                settings.chroma_path
                cls._client = chromadb.PersistentClient(
                    path=chroma_path,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
        return cls._client

    def __init__(self):
        self._embedder = None

    @property
    def client(self):
        return self.get_client()

    @property
    def embedder(self):
        if self._embedder is None:
            self._embedder = EmbeddingService.get_instance()
        return self._embedder

    def get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        """Get or create a ChromaDB collection."""
        name = self.COLLECTIONS.get(collection_name, collection_name)
        try:
            return self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
            )
        except (KeyError, ValueError) as e:
            logger.warning("Collection '%s' corrupted (%s), recreating...", name, e)
            try:
                self.client.delete_collection(name)
            except Exception:
                pass
            try:
                return self.client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception:
                logger.error("Full ChromaDB reset required — wiping store...")
                chroma_path = str(settings.chroma_path)
                shutil.rmtree(chroma_path, ignore_errors=True)
                settings.chroma_path
                VectorStore._client = None
                return self.client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )

    def add_documents(
        self,
        collection_name: str,
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Add documents to a collection with embeddings."""
        collection = self.get_or_create_collection(collection_name)

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]

        logger.info("Indexing %d chunk(s) → collection '%s'", len(texts), collection_name)
        embeddings = self.embedder.embed_texts(texts)

        collection.add(
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas or [{}] * len(texts),
            ids=ids,
        )
        logger.debug("Indexed IDs: %s", ids[:3])
        return ids

    def query(
        self,
        collection_name: str,
        query_text: str,
        n_results: int = 5,
        where: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Query a collection for similar documents."""
        collection = self.get_or_create_collection(collection_name)
        query_embedding = self.embedder.embed_text(query_text)

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        n_found = len(results["documents"][0]) if results["documents"] else 0
        logger.debug("Query '%s…' → '%s' → %d results", query_text[:60], collection_name, n_found)

        return {
            "documents": results["documents"][0] if results["documents"] else [],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
            "distances": results["distances"][0] if results["distances"] else [],
            "ids": results["ids"][0] if results["ids"] else [],
        }

    def delete_by_metadata(self, collection_name: str, where: Dict) -> None:
        """Delete documents matching metadata filter."""
        collection = self.get_or_create_collection(collection_name)
        collection.delete(where=where)
        logger.info("Deleted docs from '%s' where %s", collection_name, where)

    def get_collection_count(self, collection_name: str) -> int:
        """Get number of documents in a collection."""
        collection = self.get_or_create_collection(collection_name)
        return collection.count()


vector_store = VectorStore()
