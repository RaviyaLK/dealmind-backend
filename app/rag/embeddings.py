import logging
from typing import List
from app.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Lazy-loading wrapper around sentence-transformers for generating embeddings."""

    _instance = None
    _model = None

    @classmethod
    def get_instance(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self):
        """Lazy load the sentence-transformers model on first use."""
        if EmbeddingService._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s ...", settings.EMBEDDING_MODEL)
            EmbeddingService._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            logger.info("Embedding model loaded (dim=%d).", EmbeddingService._model.get_sentence_embedding_dimension())

    @property
    def model(self):
        self._load_model()
        return EmbeddingService._model

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        logger.debug("Embedding %d text(s)...", len(texts))
        embeddings = self.model.encode(texts, normalize_embeddings=True, batch_size=32)
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        """Get the embedding dimension."""
        return self.model.get_sentence_embedding_dimension()


embedding_service = EmbeddingService()
