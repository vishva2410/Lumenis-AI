"""
Lumenis AI — Medical Text Embedding Service

Generates dense vector embeddings for medical/clinical text using
PubMedBERT (or a lightweight fallback).  Designed for downstream
retrieval in the Qdrant vector store.

Key features
────────────
• PubMedBERT fine-tuned on MS MARCO (medical-domain–optimised)
• Automatic device selection: CUDA → MPS → CPU
• Thread-safe LRU cache for repeated text lookups
• Graceful fallback to all-MiniLM-L6-v2 when the primary model
  is unavailable (e.g. first cold-start on a CI runner)
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from threading import Lock
from typing import Sequence

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────
def _best_device() -> str:
    """Return the best available PyTorch device string."""
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _cache_key(text: str) -> str:
    """Produce a compact, collision-resistant key for the LRU cache."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Thread-safe LRU cache ────────────────────────────────────────────
class _EmbeddingCache:
    """A simple thread-safe LRU cache backed by an ``OrderedDict``.

    ``functools.lru_cache`` is not suitable here because the cached
    values are large NumPy arrays and we need explicit eviction control
    and thread safety.
    """

    def __init__(self, maxsize: int = 1024) -> None:
        self._maxsize = maxsize
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            return None

    def put(self, key: str, value: list[float]) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._maxsize:
                    self._cache.popitem(last=False)
                self._cache[key] = value

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._cache)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


# ── Embedding service ─────────────────────────────────────────────────
class EmbeddingService:
    """Medical text embedding service with caching.

    Uses a PubMedBERT-based bi-encoder fine-tuned on MS MARCO for
    sentence-level similarity.  Falls back to the lightweight
    ``all-MiniLM-L6-v2`` if the primary model cannot be loaded (e.g.
    when running offline without a cached download).

    Parameters
    ----------
    model_name:
        HuggingFace model identifier.  ``None`` ⇒ use the default
        PubMedBERT model.
    device:
        PyTorch device string (``"cpu"``, ``"cuda"``, ``"mps"``).
        ``None`` ⇒ auto-detect.
    cache_size:
        Maximum number of embedding vectors to keep in the LRU cache.
    """

    DEFAULT_MODEL: str = "pritamdeka/S-PubMedBert-MS-MARCO"
    FALLBACK_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        cache_size: int = 1024,
    ) -> None:
        self._device = device or _best_device()
        self._cache = _EmbeddingCache(maxsize=cache_size)
        self._model: SentenceTransformer | None = None
        self._model_name: str = ""

        target_model = model_name or self.DEFAULT_MODEL
        self._model = self._load_model(target_model)

    # ── model loading ─────────────────────────────────────────────
    def _load_model(self, model_name: str) -> SentenceTransformer:
        """Attempt to load *model_name*; fall back on failure."""
        t0 = time.perf_counter()
        try:
            logger.info(
                "Loading embedding model '%s' on device '%s' …",
                model_name,
                self._device,
            )
            model = SentenceTransformer(model_name, device=self._device)
            elapsed = time.perf_counter() - t0
            self._model_name = model_name

            # Probe the output dimension with a dummy encoding
            dim = model.get_sentence_embedding_dimension()
            logger.info(
                "Model '%s' loaded in %.2fs — dimension=%d, device=%s",
                model_name,
                elapsed,
                dim,
                self._device,
            )
            return model
        except Exception as exc:
            logger.warning(
                "Failed to load model '%s': %s. Trying fallback …",
                model_name,
                exc,
            )
            if model_name == self.FALLBACK_MODEL:
                raise RuntimeError(
                    f"Cannot load even the fallback model '{self.FALLBACK_MODEL}'"
                ) from exc
            return self._load_model(self.FALLBACK_MODEL)

    # ── public API ────────────────────────────────────────────────

    def embed_text(self, text: str) -> list[float]:
        """Embed a single piece of text, returning a unit-length vector.

        Results are cached so repeated calls with the same string are
        virtually free.
        """
        if not text or not text.strip():
            return [0.0] * self.dimension

        key = _cache_key(text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        embedding = self._encode([text])[0]
        self._cache.put(key, embedding)
        return embedding

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch-embed a list of texts (more efficient than repeated
        single calls because ``sentence-transformers`` will bucket and
        pad internally).

        Individual results are stored in the cache.
        """
        if not texts:
            return []

        # Separate cached vs. uncached texts
        results: list[list[float] | None] = [None] * len(texts)
        to_encode_indices: list[int] = []
        to_encode_texts: list[str] = []

        for idx, t in enumerate(texts):
            if not t or not t.strip():
                results[idx] = [0.0] * self.dimension
                continue
            key = _cache_key(t)
            cached = self._cache.get(key)
            if cached is not None:
                results[idx] = cached
            else:
                to_encode_indices.append(idx)
                to_encode_texts.append(t)

        # Batch-encode only the uncached texts
        if to_encode_texts:
            new_embeddings = self._encode(to_encode_texts)
            for i, idx in enumerate(to_encode_indices):
                results[idx] = new_embeddings[i]
                self._cache.put(_cache_key(texts[idx]), new_embeddings[i])

        return results  # type: ignore[return-value]

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query.

        For symmetric bi-encoder models (like PubMedBERT MS-MARCO) this
        is semantically identical to ``embed_text``.  The method exists
        as a dedicated entry-point so that future asymmetric models can
        apply a query-specific prompt/prefix.
        """
        if not query or not query.strip():
            return [0.0] * self.dimension
        # Do NOT cache queries — they are typically unique
        return self._encode([query])[0]

    # ── properties ────────────────────────────────────────────────

    @property
    def dimension(self) -> int:
        """Return the embedding dimensionality of the loaded model."""
        assert self._model is not None
        dim = self._model.get_sentence_embedding_dimension()
        assert dim is not None
        return int(dim)

    @property
    def model_name(self) -> str:
        """Return the identifier of the currently loaded model."""
        return self._model_name

    @property
    def cache_stats(self) -> dict[str, int]:
        """Return current cache occupancy."""
        return {"size": self._cache.size}

    # ── internals ─────────────────────────────────────────────────

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Run inference and return L2-normalised embeddings."""
        assert self._model is not None
        with torch.no_grad():
            embeddings: np.ndarray = self._model.encode(
                list(texts),
                batch_size=64,
                show_progress_bar=False,
                normalize_embeddings=True,  # L2 normalise → cosine = dot product
                convert_to_numpy=True,
            )
        # sentence-transformers may return a single vector for a single
        # text; ensure we always have 2-D.
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)
        return [vec.tolist() for vec in embeddings]
