#!/usr/bin/env python
"""
Lumenis AI — Populate Medical Knowledge Collection in Qdrant

CLI script to parse condition profile data and ingest it into Qdrant.
Supports deleting existing collections (--reset) and printing stats.

Usage:
  python scripts/ingest_knowledge.py --file data/medical_knowledge/radiology_conditions.json --reset
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Add backend directory to sys.path so we can import app modules
# Script runs from project root
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root / "backend"))

from app.services.knowledge_ingestion import KnowledgeIngestionPipeline
from app.services.qdrant_store import QdrantStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest_knowledge")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Populate the Qdrant vector store with medical knowledge."
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=str(project_root / "data" / "medical_knowledge" / "radiology_conditions.json"),
        help="Path to the JSON file containing medical conditions database.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the Qdrant collection before ingesting.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    json_path = Path(args.file)
    if not json_path.exists():
        logger.error("Error: Input file does not exist at %s", json_path)
        sys.exit(1)

    logger.info("Initializing Qdrant client ...")
    try:
        store = QdrantStore()
    except Exception as exc:
        logger.exception("Failed to connect to Qdrant: %s", exc)
        sys.exit(1)

    if args.reset:
        logger.info("Resetting collection '%s' as requested ...", store.COLLECTION_NAME)
        try:
            store.delete_collection()
            store.ensure_collection()
            logger.info("Collection reset complete.")
        except Exception as exc:
            logger.error("Failed to reset collection: %s", exc)
            sys.exit(1)

    logger.info("Starting ingestion from %s ...", json_path)
    try:
        pipeline = KnowledgeIngestionPipeline(qdrant_store=store)
        total_chunks = pipeline.ingest_conditions_file(json_path)
        
        # Display collection stats
        info = store.get_collection_info()
        logger.info("Ingestion completed successfully!")
        logger.info("=== Collection Summary ===")
        logger.info("  Name:          %s", info["name"])
        logger.info("  Status:        %s", info["status"])
        logger.info("  Points Count:  %s", info["points_count"])
        logger.info("  Dense Dim:     %s", info["config"]["dense_vector_size"])
        logger.info("==========================")
        
    except Exception as exc:
        logger.exception("Ingestion pipeline failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
