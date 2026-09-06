import logging
from typing import List, Optional
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        self._model: Optional[SentenceTransformer] = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            logger.info("Loading SentenceTransformer model 'all-MiniLM-L6-v2'...")
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
        return self._model

    def embed_text(self, text: str) -> List[float]:
        model = self._get_model()
        return model.encode([text], convert_to_numpy=True)[0].tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        model = self._get_model()
        return model.encode(texts, convert_to_numpy=True).tolist()

embedding_service = EmbeddingService()
