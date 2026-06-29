"""ChromaDB vector store wrapper with metadata filtering support."""

import logging
from typing import Any, Optional

import chromadb
from chromadb.api.models.Collection import Collection

from config.settings import COLLECTION_NAME, PERSIST_DIRECTORY

logger = logging.getLogger(__name__)

_chroma_client: Optional[chromadb.PersistentClient] = None
_collection: Optional[Collection] = None


def init_chroma() -> Optional[Collection]:
    """Initialize ChromaDB persistent client and collection."""
    global _chroma_client, _collection
    try:
        _chroma_client = chromadb.PersistentClient(path=PERSIST_DIRECTORY)
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB ready with %d documents.", _collection.count())
        return _collection
    except Exception as exc:
        logger.warning("ChromaDB unavailable: %s", exc)
        _collection = None
        return None


def get_collection() -> Optional[Collection]:
    return _collection


def get_or_create_collection() -> Optional[Collection]:
    if _collection is None:
        return init_chroma()
    return _collection


def build_metadata_filter(
    user_id: Optional[str] = None,
    document_id: Optional[str] = None,
    session_id: Optional[str] = None,
    include_global: bool = True,
) -> Optional[dict[str, Any]]:
    """Build ChromaDB where-clause for multi-user filtering."""
    conditions: list[dict[str, Any]] = []

    if user_id:
        if include_global:
            conditions.append({"$or": [{"user_id": user_id}, {"user_id": "system"}]})
        else:
            conditions.append({"user_id": user_id})
    if document_id:
        conditions.append({"document_id": document_id})
    if session_id:
        conditions.append({"session_id": session_id})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}
