"""
Lumenis AI — Knowledge Ingestion Pipeline

Reads structured clinical reference data (JSON) and splits each medical
condition into distinct, semantic chunks (Definition, Imaging Features,
and Clinical Significance).  Then embeds and ingests them into the Qdrant
vector store in batches.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.services.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)


class KnowledgeIngestionPipeline:
    """Manages parsing and ingestion of medical clinical reference data."""

    def __init__(self, qdrant_store: QdrantStore | None = None) -> None:
        self._qdrant = qdrant_store or QdrantStore()

    def ingest_conditions_file(self, file_path: str | Path) -> int:
        """Parse and ingest a radiology conditions JSON file.

        Parameters
        ----------
        file_path:
            Path to the JSON file containing the conditions list.

        Returns
        -------
        int
            The number of chunks successfully ingested.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Conditions database file not found: {path}")

        logger.info("Reading conditions database from %s ...", path)
        with open(path, "r", encoding="utf-8") as f:
            conditions = json.load(f)

        if not isinstance(conditions, list):
            raise ValueError("Invalid format: conditions file must be a JSON list.")

        logger.info("Found %d condition profiles. Processing into chunks ...", len(conditions))
        documents_to_upsert: list[dict[str, Any]] = []

        for cond in conditions:
            # Validate required fields
            cond_id = cond.get("id")
            name = cond.get("name")
            category = cond.get("category", "General")
            icd10 = cond.get("icd10", "N/A")
            definition = cond.get("definition")
            imaging_features = cond.get("imaging_features")
            clinical_significance = cond.get("clinical_significance")

            if not cond_id or not name:
                logger.warning("Skipping invalid condition profile (missing id or name): %s", cond)
                continue

            # Base metadata to attach to all chunks of this condition
            base_meta = {
                "condition_name": name,
                "category": category,
                "icd10": icd10,
            }

            # 1. Chunk: Definition
            if definition and definition.strip():
                def_text = f"Condition: {name} (ICD-10: {icd10}). Category: {category}. Definition: {definition.strip()}"
                documents_to_upsert.append({
                    "id": f"{cond_id}_def",
                    "text": def_text,
                    "metadata": {**base_meta, "chunk_type": "definition"},
                })

            # 2. Chunk: Imaging Features
            if imaging_features and imaging_features.strip():
                features_text = f"Condition: {name} (ICD-10: {icd10}). Typical Imaging Features and Presentation: {imaging_features.strip()}"
                documents_to_upsert.append({
                    "id": f"{cond_id}_features",
                    "text": features_text,
                    "metadata": {**base_meta, "chunk_type": "imaging_features"},
                })

            # 3. Chunk: Clinical Significance
            if clinical_significance and clinical_significance.strip():
                sig_text = f"Condition: {name} (ICD-10: {icd10}). Clinical Significance & Recommended Follow-up: {clinical_significance.strip()}"
                documents_to_upsert.append({
                    "id": f"{cond_id}_significance",
                    "text": sig_text,
                    "metadata": {**base_meta, "chunk_type": "clinical_significance"},
                })

        logger.info("Compiled %d semantic chunks from %d profiles.", len(documents_to_upsert), len(conditions))

        if not documents_to_upsert:
            logger.warning("No valid chunks compiled. Ingestion aborted.")
            return 0

        # Ingest into Qdrant
        t0 = time.perf_counter()
        logger.info("Upserting documents to Qdrant...")
        total_upserted = self._qdrant.upsert_documents(documents_to_upsert)
        elapsed = time.perf_counter() - t0
        
        logger.info(
            "Successfully ingested %d chunks into Qdrant in %.2fs",
            total_upserted,
            elapsed,
        )
        return total_upserted
