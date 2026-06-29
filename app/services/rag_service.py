"""Intelligent RAG retrieval with similarity threshold and metadata filters."""

import logging
from functools import lru_cache
from typing import Optional

from sentence_transformers import SentenceTransformer

from config.settings import (
    EMBEDDING_CACHE_SIZE,
    EMBEDDING_MODEL,
    RAG_TOP_K,
    SIMILARITY_THRESHOLD,
)
from database.chroma_store import build_metadata_filter, get_collection
from models.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class RAGService:
    """Retrieve relevant document chunks from ChromaDB."""

    def __init__(self):
        self._model: Optional[SentenceTransformer] = None

    def init_embedding_model(self) -> bool:
        try:
            self._model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Embedding model loaded: %s", EMBEDDING_MODEL)
            return True
        except Exception as exc:
            logger.error("Failed to load embedding model: %s", exc)
            return False

    @property
    def is_ready(self) -> bool:
        return self._model is not None and get_collection() is not None

    def search(
        self,
        question: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        document_id: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> list[RetrievedChunk]:
        """Retrieve and rank chunks above the similarity threshold."""
        collection = get_collection()
        if not collection or not self._model:
            return []

        k = top_k or RAG_TOP_K
        query_embedding = self._encode(question)
        where = build_metadata_filter(user_id=user_id, document_id=document_id, session_id=session_id)

        try:
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": k,
                "include": ["documents", "distances", "metadatas"],
            }
            if where:
                query_kwargs["where"] = where

            results = collection.query(**query_kwargs)
        except Exception as exc:
            logger.warning("ChromaDB query failed: %s", exc)
            return self._search_without_filter(question, k)

        if not results or not results.get("documents") or not results["documents"][0]:
            return []

        chunks: list[RetrievedChunk] = []
        for doc, distance, meta in zip(
            results["documents"][0],
            results["distances"][0],
            results["metadatas"][0],
        ):
            if not doc:
                continue
            score = 1.0 - float(distance)
            if score < SIMILARITY_THRESHOLD:
                continue
            chunks.append(
                RetrievedChunk(
                    content=doc,
                    score=score,
                    document_id=(meta or {}).get("document_id"),
                    metadata=meta or {},
                )
            )

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks

    def _search_without_filter(self, question: str, k: int) -> list[RetrievedChunk]:
        """Fallback search when metadata filter fails (legacy docs without metadata)."""
        collection = get_collection()
        if not collection or not self._model:
            return []
        try:
            query_embedding = self._encode(question)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                include=["documents", "distances", "metadatas"],
            )
            if not results or not results.get("documents"):
                return []
            chunks = []
            for doc, distance, meta in zip(
                results["documents"][0],
                results["distances"][0],
                results["metadatas"][0],
            ):
                if not doc:
                    continue
                score = 1.0 - float(distance)
                if score >= SIMILARITY_THRESHOLD:
                    chunks.append(
                        RetrievedChunk(
                            content=doc,
                            score=score,
                            document_id=(meta or {}).get("document_id"),
                            metadata=meta or {},
                        )
                    )
            chunks.sort(key=lambda c: c.score, reverse=True)
            return chunks
        except Exception as exc:
            logger.warning("Fallback ChromaDB search failed: %s", exc)
            return []

    def _encode(self, text: str) -> list[float]:
        return list(self._cached_encode(text))

    @lru_cache(maxsize=EMBEDDING_CACHE_SIZE)
    def _cached_encode(self, text: str) -> tuple:
        return tuple(self._model.encode([text]).tolist()[0])

    def add_documents(
        self,
        chunks: list[str],
        ids: list[str],
        metadatas: list[dict],
    ) -> int:
        """Embed and store document chunks in ChromaDB."""
        collection = get_collection()
        if not collection or not self._model:
            raise RuntimeError("RAG service not initialized.")

        embeddings = self._model.encode(chunks, show_progress_bar=False).tolist()
        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return len(chunks)
