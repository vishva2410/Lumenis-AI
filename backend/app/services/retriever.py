"""
Lumenis AI — Hybrid Retriever & Re-ranking Service

Combines sparse/dense retrieval results from Qdrant and applies a
Cross-Encoder re-ranker (ms-marco-MiniLM-L-6-v2) to select the most
clinically relevant literature chunks for a given finding.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

import numpy as np
import torch
from pydantic import BaseModel, Field

from app.services.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)


class RetrievedDocument(BaseModel):
    """Structured representation of a retrieved literature chunk."""

    text: str = Field(..., description="The textual content of the chunk.")
    source_id: str = Field(..., description="The unique ID of the source condition/document.")
    relevance_score: float = Field(..., description="Normalized relevance score (0 to 1).")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional document metadata.")


def _best_device() -> str:
    """Return the best available PyTorch device string."""
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class HybridRetriever:
    """Retrieves and re-ranks medical knowledge documents.

    Uses reciprocal rank fusion (RRF) from Qdrant's sparse/dense search
    and refines the candidates using a Cross-Encoder model.
    """

    CROSS_ENCODER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(
        self,
        qdrant_store: QdrantStore | None = None,
        device: str | None = None,
    ) -> None:
        self._qdrant = qdrant_store or QdrantStore()
        self._device = device or _best_device()
        self._cross_encoder = None  # Loaded lazily

    def _load_cross_encoder(self) -> None:
        """Lazy-load the Cross-Encoder model."""
        if self._cross_encoder is not None:
            return

        from sentence_transformers import CrossEncoder

        t0 = time.perf_counter()
        try:
            logger.info(
                "Loading Cross-Encoder model '%s' on device '%s' ...",
                self.CROSS_ENCODER_MODEL,
                self._device,
            )
            self._cross_encoder = CrossEncoder(
                self.CROSS_ENCODER_MODEL,
                device=self._device,
            )
            elapsed = time.perf_counter() - t0
            logger.info(
                "Cross-Encoder model loaded in %.2fs on device %s",
                elapsed,
                self._device,
            )
        except Exception as exc:
            logger.error(
                "Failed to load Cross-Encoder model '%s': %s. Will fall back to raw hybrid scores.",
                self.CROSS_ENCODER_MODEL,
                exc,
            )
            self._cross_encoder = False  # Sentinel for failed load

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        prefetch_k: int = 15,
    ) -> list[RetrievedDocument]:
        """Retrieve and re-rank the top K documents for the given query.

        Parameters
        ----------
        query:
            The search query (e.g. 'Pulmonary Nodule right upper lobe').
        top_k:
            Number of final documents to return.
        prefetch_k:
            Number of candidate documents to fetch from Qdrant before re-ranking.
        """
        if not query or not query.strip():
            return []

        # 1. Fetch candidate documents using Qdrant hybrid search
        try:
            hits = self._qdrant.hybrid_search(query, top_k=prefetch_k)
        except Exception as exc:
            logger.error("Qdrant hybrid search failed for query '%s': %s", query, exc)
            return []

        if not hits:
            logger.debug("No candidate documents found in Qdrant for query '%s'", query)
            return []

        # 2. Try loading the Cross-Encoder
        self._load_cross_encoder()

        # 3. Fallback if Cross-Encoder loading failed
        if self._cross_encoder is False:
            logger.warning("Using raw Qdrant hybrid scores due to Cross-Encoder loading failure.")
            # Normalize Qdrant scores if possible (Qdrant RRF scores are typically small floats,
            # we just sort by them and return the top_k)
            sorted_hits = sorted(hits, key=lambda h: h.get("score", 0.0), reverse=True)
            return [
                RetrievedDocument(
                    text=hit["text"],
                    source_id=hit["source_id"],
                    relevance_score=max(0.0, min(1.0, hit.get("score", 0.5))),
                    metadata=hit.get("metadata", {}),
                )
                for hit in sorted_hits[:top_k]
            ]

        # 4. Perform Cross-Encoder re-ranking
        try:
            assert self._cross_encoder is not None
            # Form query-document pairs
            pairs = [[query, hit["text"]] for hit in hits]
            
            # Predict scores (logits)
            scores = self._cross_encoder.predict(pairs, show_progress_bar=False)
            
            # If a single item was predicted, scores might be scalar
            if isinstance(scores, (int, float, np.float32, np.float64)):
                scores = [scores]

            # Normalize scores using sigmoid function: 1 / (1 + exp(-x))
            # Typically Cross-Encoder logits for MS MARCO range from -10 to 10.
            # Sigmoid maps this smoothly to a 0-1 range representing relevance.
            normalized_scores = [float(1.0 / (1.0 + np.exp(-s))) for s in scores]

            # Attach scores and sort
            ranked_hits = []
            for hit, score in zip(hits, normalized_scores):
                ranked_hits.append(
                    RetrievedDocument(
                        text=hit["text"],
                        source_id=hit["source_id"],
                        relevance_score=score,
                        metadata=hit.get("metadata", {}),
                    )
                )

            # Sort by relevance score descending
            ranked_hits.sort(key=lambda x: x.relevance_score, reverse=True)
            
            logger.debug(
                "Re-ranked %d candidates down to top %d. Best score: %.4f",
                len(hits),
                min(top_k, len(ranked_hits)),
                ranked_hits[0].relevance_score if ranked_hits else 0.0,
            )
            return ranked_hits[:top_k]

        except Exception as exc:
            logger.error("Cross-Encoder re-ranking failed: %s. Falling back to hybrid scores.", exc)
            sorted_hits = sorted(hits, key=lambda h: h.get("score", 0.0), reverse=True)
            return [
                RetrievedDocument(
                    text=hit["text"],
                    source_id=hit["source_id"],
                    relevance_score=0.5,  # neutral fallback score
                    metadata=hit.get("metadata", {}),
                )
                for hit in sorted_hits[:top_k]
            ]
