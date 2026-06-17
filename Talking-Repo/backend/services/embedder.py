"""Embedding service using sentence-transformers/all-MiniLM-L6-v2 (384-dim)."""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import List

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIMENSION = 384

_lock = threading.Lock()


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer  # type: ignore
    logger.info("Loading embedding model %s ...", MODEL_NAME)
    return SentenceTransformer(MODEL_NAME)


def embed(texts: List[str]) -> List[List[float]]:
    with _lock:
        model = _model()
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False,
                           normalize_embeddings=False, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


def embed_one(text: str) -> List[float]:
    return embed([text])[0]
