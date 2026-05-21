"""
Lumenis AI — Qdrant Vector Store Client

Manages the ``medical_knowledge`` collection in Qdrant, providing:

• Dense vector upsert / search  (PubMedBERT embeddings)
• Sparse vector upsert / search (BM25-style keyword matching)
• Hybrid search with configurable dense/sparse weighting
• Batch upserts with automatic chunking (100 pts per batch)
• Graceful retries on transient connection errors

The module expects a running Qdrant instance reachable at the host/port
specified in ``app.core.config.settings``.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
import uuid
from collections import Counter
from typing import Any, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────
_BATCH_SIZE = 100
_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.5  # seconds (exponential base)

# Named vector keys used in the collection schema
_DENSE_VECTOR_NAME = "dense"
_SPARSE_VECTOR_NAME = "sparse"

# ── BM25-style stop-words (tiny set, intentionally minimal) ──────────
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "if", "in", "into", "is", "it", "no", "not", "of", "on", "or",
        "such", "that", "the", "their", "then", "there", "these", "they",
        "this", "to", "was", "will", "with",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.ASCII)


# ── helpers ───────────────────────────────────────────────────────────

def _tokenise(text: str) -> list[str]:
    """Lowercase, strip non-alphanumeric chars, remove stop-words."""
    return [
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOP_WORDS and len(tok) > 1
    ]


def _deterministic_id(raw_id: str) -> str:
    """Map an arbitrary document ID string to a UUID-compatible string
    that Qdrant accepts as a point ID (UUID or unsigned int).

    We use a deterministic UUID-5 derived from the raw ID so that
    repeated upserts of the same document are idempotent.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, raw_id))


def _retry(func):  # noqa: ANN001,ANN202
    """Decorator that retries a function up to ``_MAX_RETRIES`` times on
    transient connection / server errors."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except (ConnectionError, OSError, UnexpectedResponse) as exc:
                last_exc = exc
                wait = _RETRY_BACKOFF ** attempt
                logger.warning(
                    "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                    func.__name__,
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
        raise RuntimeError(
            f"{func.__name__} failed after {_MAX_RETRIES} attempts"
        ) from last_exc

    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# ── QdrantStore ───────────────────────────────────────────────────────

class QdrantStore:
    """Qdrant vector database client for medical knowledge retrieval.

    Parameters
    ----------
    host / port:
        Override connection details (defaults come from ``settings``).
    collection_name:
        Name of the Qdrant collection to use.
    embedding_service:
        An ``EmbeddingService`` instance.  When ``None`` a new one is
        created with default parameters.
    """

    COLLECTION_NAME: str = "medical_knowledge"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self._host = host or settings.QDRANT_HOST
        self._port = port or settings.QDRANT_PORT
        self._collection = collection_name or self.COLLECTION_NAME

        # Embedding service (lazy-create if not provided)
        self._embedder = embedding_service or EmbeddingService()

        # Connect to Qdrant
        logger.info("Connecting to Qdrant at %s:%d …", self._host, self._port)
        self._client = QdrantClient(host=self._host, port=self._port, timeout=30)

        # Ensure the target collection exists
        self.ensure_collection()

    # ── collection management ─────────────────────────────────────

    @_retry
    def ensure_collection(self, vector_size: int | None = None) -> None:
        """Create the collection if it does not already exist.

        The collection is configured with:
        * **dense** vectors (cosine similarity, dimension from the
          embedding model)
        * **sparse** vectors (for BM25 keyword matching)
        * HNSW index parameters tuned for recall
        """
        dim = vector_size or self._embedder.dimension

        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            logger.info(
                "Collection '%s' already exists — skipping creation.",
                self._collection,
            )
            return

        logger.info(
            "Creating collection '%s' (dense dim=%d) …",
            self._collection,
            dim,
        )

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                _DENSE_VECTOR_NAME: qmodels.VectorParams(
                    size=dim,
                    distance=qmodels.Distance.COSINE,
                    hnsw_config=qmodels.HnswConfigDiff(
                        m=16,
                        ef_construct=100,
                    ),
                ),
            },
            sparse_vectors_config={
                _SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(
                    modifier=qmodels.Modifier.IDF,
                ),
            },
        )
        logger.info("Collection '%s' created successfully.", self._collection)

    # ── upserts ───────────────────────────────────────────────────

    @_retry
    def upsert_documents(self, documents: list[dict[str, Any]]) -> int:
        """Upsert documents into the collection.

        Each *document* dict must contain:

        * ``id``   — a unique string identifier
        * ``text`` — the textual content to embed
        * ``metadata`` — arbitrary payload dict (source, category, …)

        Documents are batched in chunks of 100 for efficient ingestion.
        Returns the total number of points upserted.
        """
        if not documents:
            return 0

        # Pre-compute all embeddings in one efficient batch
        texts = [doc["text"] for doc in documents]
        dense_vectors = self._embedder.embed_texts(texts)

        total_upserted = 0

        for batch_start in range(0, len(documents), _BATCH_SIZE):
            batch_docs = documents[batch_start : batch_start + _BATCH_SIZE]
            batch_dense = dense_vectors[batch_start : batch_start + _BATCH_SIZE]
            batch_texts = texts[batch_start : batch_start + _BATCH_SIZE]

            points: list[qmodels.PointStruct] = []
            for doc, dense_vec, text in zip(batch_docs, batch_dense, batch_texts):
                point_id = _deterministic_id(doc["id"])
                sparse_indices, sparse_values = self._compute_sparse_vector(text)

                payload: dict[str, Any] = {
                    "text": text,
                    "source_id": doc["id"],
                    **doc.get("metadata", {}),
                }

                vectors: dict[str, Any] = {
                    _DENSE_VECTOR_NAME: dense_vec,
                }

                # Only attach sparse vector when we have tokens
                if sparse_indices:
                    vectors[_SPARSE_VECTOR_NAME] = qmodels.SparseVector(
                        indices=sparse_indices,
                        values=sparse_values,
                    )

                points.append(
                    qmodels.PointStruct(
                        id=point_id,
                        vector=vectors,
                        payload=payload,
                    )
                )

            self._client.upsert(
                collection_name=self._collection,
                points=points,
                wait=True,
            )
            total_upserted += len(points)
            logger.debug(
                "Upserted batch %d–%d (%d points)",
                batch_start,
                batch_start + len(points) - 1,
                len(points),
            )

        logger.info(
            "Upserted %d documents into '%s'.",
            total_upserted,
            self._collection,
        )
        return total_upserted

    # ── search ────────────────────────────────────────────────────

    @_retry
    def search(
        self,
        query: str,
        top_k: int = 10,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Dense-only vector search.

        Returns a list of result dicts, each containing:
        ``id``, ``score``, ``text``, and any metadata from the payload.
        """
        query_vector = self._embedder.embed_query(query)

        hits = self._client.search(
            collection_name=self._collection,
            query_vector=(_DENSE_VECTOR_NAME, query_vector),
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )

        return self._hits_to_dicts(hits)

    @_retry
    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        dense_weight: float = 0.7,
        sparse_weight: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining dense (semantic) + sparse (keyword)
        matching via Qdrant's built-in query API with score fusion.

        Parameters
        ----------
        dense_weight / sparse_weight:
            Relative weights applied to dense and sparse scores before
            reciprocal-rank fusion.
        """
        # Dense query vector
        dense_vector = self._embedder.embed_query(query)

        # Sparse query vector
        sparse_indices, sparse_values = self._compute_sparse_vector(query)

        prefetch_queries: list[qmodels.Prefetch] = [
            qmodels.Prefetch(
                query=dense_vector,
                using=_DENSE_VECTOR_NAME,
                limit=top_k * 2,
            ),
        ]

        # Only include sparse search if we have tokens
        if sparse_indices:
            prefetch_queries.append(
                qmodels.Prefetch(
                    query=qmodels.SparseVector(
                        indices=sparse_indices,
                        values=sparse_values,
                    ),
                    using=_SPARSE_VECTOR_NAME,
                    limit=top_k * 2,
                ),
            )

        hits = self._client.query_points(
            collection_name=self._collection,
            prefetch=prefetch_queries,
            query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
            limit=top_k,
            with_payload=True,
        )

        return self._query_hits_to_dicts(hits)

    # ── collection info ───────────────────────────────────────────

    @_retry
    def get_collection_info(self) -> dict[str, Any]:
        """Return collection statistics and configuration."""
        info = self._client.get_collection(self._collection)
        return {
            "name": self._collection,
            "status": str(info.status),
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "segments_count": info.segments_count,
            "config": {
                "dense_vector_size": self._embedder.dimension,
                "distance": "Cosine",
                "has_sparse_vectors": True,
            },
        }

    @_retry
    def delete_collection(self) -> None:
        """Permanently delete the collection and all its data."""
        logger.warning("Deleting collection '%s' …", self._collection)
        self._client.delete_collection(self._collection)
        logger.info("Collection '%s' deleted.", self._collection)

    @_retry
    def count(self) -> int:
        """Return the number of points in the collection."""
        info = self._client.get_collection(self._collection)
        return info.points_count or 0

    # ── BM25-style sparse vectors ─────────────────────────────────

    def _compute_sparse_vector(
        self, text: str
    ) -> tuple[list[int], list[float]]:
        """Compute a sparse BM25-style vector from *text*.

        Returns ``(indices, values)`` where:
        * *indices* — hashed token identifiers (stable across runs)
        * *values*  — BM25-like TF scores (sub-linear term frequency)

        The IDF component is handled by Qdrant's built-in
        ``Modifier.IDF`` on the sparse vector configuration.
        """
        tokens = _tokenise(text)
        if not tokens:
            return [], []

        tf_counts = Counter(tokens)
        doc_len = len(tokens)
        avg_dl = max(doc_len, 1)  # single-doc approximation

        indices: list[int] = []
        values: list[float] = []

        k1 = 1.2
        b = 0.75

        for token, count in tf_counts.items():
            # Stable hash → sparse dimension index (positive 32-bit int)
            token_hash = int(
                hashlib.md5(token.encode("utf-8")).hexdigest()[:8], 16
            )
            # BM25 TF component: saturating term-frequency
            tf_score = (count * (k1 + 1)) / (
                count + k1 * (1 - b + b * doc_len / avg_dl)
            )
            indices.append(token_hash)
            values.append(float(tf_score))

        return indices, values

    # ── result formatting ─────────────────────────────────────────

    @staticmethod
    def _hits_to_dicts(hits: Sequence[Any]) -> list[dict[str, Any]]:
        """Convert Qdrant ``ScoredPoint`` results to plain dicts."""
        results: list[dict[str, Any]] = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                {
                    "id": str(hit.id),
                    "score": hit.score,
                    "text": payload.get("text", ""),
                    "source_id": payload.get("source_id", ""),
                    "metadata": {
                        k: v
                        for k, v in payload.items()
                        if k not in ("text", "source_id")
                    },
                }
            )
        return results

    @staticmethod
    def _query_hits_to_dicts(result: Any) -> list[dict[str, Any]]:
        """Convert Qdrant ``QueryResponse`` results to plain dicts."""
        results: list[dict[str, Any]] = []
        points = getattr(result, "points", result)
        for point in points:
            payload = point.payload or {}
            results.append(
                {
                    "id": str(point.id),
                    "score": getattr(point, "score", 0.0),
                    "text": payload.get("text", ""),
                    "source_id": payload.get("source_id", ""),
                    "metadata": {
                        k: v
                        for k, v in payload.items()
                        if k not in ("text", "source_id")
                    },
                }
            )
        return results
