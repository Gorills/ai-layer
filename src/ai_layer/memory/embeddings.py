from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from ai_layer.core.config import get_settings

TOKEN_RE = re.compile(r"[\w.-]+", re.UNICODE)
SCHEMA_EMBEDDING_DIMENSIONS = 384


class HashEmbedding:
    """Offline fallback. Token-hash vector; deterministic but less semantic than FastEmbed."""

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for token in TOKEN_RE.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = -1.0 if digest[4] & 1 else 1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FastEmbedEmbedding:
    def __init__(self, model_name: str, expected_dimensions: int = SCHEMA_EMBEDDING_DIMENSIONS):
        from fastembed import TextEmbedding
        self.model_name = model_name
        self.expected_dimensions = expected_dimensions
        self.model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = [vector.tolist() for vector in self.model.embed(texts)]
        for vector in vectors:
            if len(vector) != self.expected_dimensions:
                raise RuntimeError(
                    f"Embedding model {self.model_name!r} returned {len(vector)} dimensions; "
                    f"AI Layer schema requires {self.expected_dimensions}."
                )
        return vectors


def embedding_signature() -> dict[str, object]:
    """Identity of the vector space persisted by the current schema.

    The signature is stored beside the freshness marker so changing provider/model cannot silently
    compare new query vectors with an index produced in a different vector space.
    """
    settings = get_settings()
    if settings.embedding_dimensions != SCHEMA_EMBEDDING_DIMENSIONS:
        raise RuntimeError(
            f"AI_LAYER_EMBEDDING_DIMENSIONS={settings.embedding_dimensions} is unsupported by the current schema; "
            f"PostgreSQL schema requires {SCHEMA_EMBEDDING_DIMENSIONS}."
        )
    provider = settings.embedding_provider.lower().strip()
    if provider not in {"hash", "fastembed"}:
        raise RuntimeError(f"Unsupported embedding provider: {settings.embedding_provider}")
    return {
        "provider": provider,
        "model": settings.embedding_model if provider == "fastembed" else "hash-v1",
        "dimensions": SCHEMA_EMBEDDING_DIMENSIONS,
    }


@lru_cache(maxsize=1)
def get_embedder():
    settings = get_settings()
    signature = embedding_signature()
    if signature["provider"] == "hash":
        return HashEmbedding(SCHEMA_EMBEDDING_DIMENSIONS)
    return FastEmbedEmbedding(settings.embedding_model, SCHEMA_EMBEDDING_DIMENSIONS)
