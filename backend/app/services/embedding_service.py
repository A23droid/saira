import logging
import math
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

    def _validate_vector(self, vec: List[float]) -> Optional[List[float]]:
        if not vec or len(vec) != 384:
            logger.warning(f"Invalid vector dimension: {len(vec) if vec else 0}")
            return None
        for val in vec:
            if math.isnan(val) or math.isinf(val):
                logger.warning("Invalid value (NaN/Inf) in vector")
                return None
        if all(v == 0.0 for v in vec):
            logger.warning("Zero vector detected")
            return None
        return vec

    def embed_text(self, text: str) -> Optional[List[float]]:
        if not text or not text.strip():
            return None
        model = self._get_model()
        vec = model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0].tolist()
        return self._validate_vector(vec)

    def embed_texts(self, texts: List[str]) -> List[Optional[List[float]]]:
        model = self._get_model()
        if not texts:
            return []
        
        valid_texts = [t if t and t.strip() else " " for t in texts]
        vecs = model.encode(valid_texts, normalize_embeddings=True, convert_to_numpy=True).tolist()
        
        return [self._validate_vector(v) for v in vecs]

embedding_service = EmbeddingService()
