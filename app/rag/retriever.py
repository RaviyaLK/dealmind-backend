from typing import List, Dict, Any, Optional
from app.rag.vectorstore import vector_store
from langchain_text_splitters import RecursiveCharacterTextSplitter


class DocumentChunker:
    """Handles text splitting for RAG indexing."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks."""
        return self.splitter.split_text(text)

    def chunk_with_metadata(
        self, text: str, base_metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Split text into chunks with metadata for each chunk."""
        chunks = self.splitter.split_text(text)
        results = []
        for i, chunk in enumerate(chunks):
            meta = {**base_metadata, "chunk_index": i, "total_chunks": len(chunks)}
            results.append({"text": chunk, "metadata": meta})
        return results


class RAGRetriever:
    """Retrieves relevant context from the vector store for proposal generation and analysis."""

    def __init__(self):
        self.chunker = DocumentChunker()

    def index_document(
        self,
        text: str,
        collection_name: str,
        document_id: str,
        metadata: Dict[str, Any],
    ) -> List[str]:
        """Index a document by chunking and storing in vector DB."""
        chunks_with_meta = self.chunker.chunk_with_metadata(text, {
            **metadata,
            "document_id": document_id,
        })

        texts = [c["text"] for c in chunks_with_meta]
        metadatas = [c["metadata"] for c in chunks_with_meta]

        ids = vector_store.add_documents(
            collection_name=collection_name,
            texts=texts,
            metadatas=metadatas,
        )

        return ids

    def retrieve_for_proposal(
        self,
        deal_context: str,
        requirements: List[str],
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant sections from ALL collections for generating a new proposal.

        Searches proposals, rfps, and general collections so that uploaded RFPs,
        case studies, SOWs, and other supporting docs are all considered.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Build a rich query from deal context and requirements
        query = f"Deal context: {deal_context}\n\nKey requirements:\n"
        query += "\n".join(f"- {req}" for req in requirements[:5])

        # Search across all relevant collections
        collections_to_search = ["proposals", "rfps", "general"]
        all_results = []

        for coll_name in collections_to_search:
            try:
                results = vector_store.query(
                    collection_name=coll_name,
                    query_text=query,
                    n_results=n_results,
                )
                for doc, meta, dist in zip(
                    results["documents"], results["metadatas"], results["distances"]
                ):
                    all_results.append({
                        "text": doc,
                        "source": meta.get("filename", meta.get("category", "Unknown")),
                        "collection": coll_name,
                        "relevance_score": 1 - dist,
                        "document_id": meta.get("document_id", ""),
                    })
                logger.debug(
                    "retrieve_for_proposal: collection '%s' returned %d results",
                    coll_name,
                    len(results["documents"]),
                )
            except Exception as e:
                logger.warning(
                    "retrieve_for_proposal: collection '%s' query failed (non-fatal): %s",
                    coll_name,
                    e,
                )

        # Sort by relevance and return top results
        all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        top_results = all_results[:n_results]
        logger.info(
            "retrieve_for_proposal: total %d results across %d collections, returning top %d",
            len(all_results),
            len(collections_to_search),
            len(top_results),
        )
        return top_results

    def retrieve_for_analysis(
        self,
        query: str,
        collection_names: List[str],
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Retrieve context from multiple collections for deal analysis."""
        all_results = []

        for collection in collection_names:
            results = vector_store.query(
                collection_name=collection,
                query_text=query,
                n_results=n_results,
            )
            for doc, meta, dist in zip(
                results["documents"], results["metadatas"], results["distances"]
            ):
                all_results.append({
                    "text": doc,
                    "source": meta.get("filename", "Unknown"),
                    "collection": collection,
                    "relevance_score": 1 - dist,
                })

        # Sort by relevance and return top results
        all_results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return all_results[:n_results * 2]

    def query(
        self,
        query_text: str,
        collection_name: str = "proposals",
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """Query the vector store and return formatted results."""
        results = vector_store.query(
            collection_name=collection_name,
            query_text=query_text,
            n_results=n_results,
        )

        formatted = []
        for doc, meta, dist in zip(
            results["documents"], results["metadatas"], results["distances"]
        ):
            formatted.append({
                "id": meta.get("document_id", ""),
                "content": doc,
                "score": 1 - dist,
                "metadata": meta,
            })
        return formatted

    def clear_collection(self, collection_name: str) -> None:
        """Clear/delete a collection from the vector store."""
        name = vector_store.COLLECTIONS.get(collection_name, collection_name)
        try:
            vector_store.client.delete_collection(name)
        except Exception:
            pass  # Collection may not exist

    def get_stats(self) -> Dict[str, int]:
        """Get document counts across all collections."""
        stats = {}
        for key in vector_store.COLLECTIONS:
            stats[key] = vector_store.get_collection_count(key)
        return stats


rag_retriever = RAGRetriever()
chunker = DocumentChunker()
