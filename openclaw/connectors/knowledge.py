"""Knowledge Base connector — pgvector + full-text search against rivet DB."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from openclaw.connectors.base import ServiceConnector

logger = logging.getLogger(__name__)


class KnowledgeConnector(ServiceConnector):
    """Async connector to the rivet PostgreSQL knowledge base (4,600+ atoms)."""

    def __init__(self, postgres_url: str) -> None:
        self._url = postgres_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        try:
            self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=3)
            logger.info("KnowledgeConnector connected to %s", self._url.split("@")[-1])
        except Exception:
            logger.exception("KnowledgeConnector failed to connect")
            self._pool = None

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def search(self, query_text: str, limit: int = 5) -> list[dict[str, Any]]:
        """Full-text search across knowledge atoms using PostgreSQL GIN index.

        Returns atoms ranked by relevance to the query.
        """
        if not self._pool:
            return []

        try:
            # Build tsquery from user text — plainto_tsquery handles natural language
            rows = await self._pool.fetch(
                """
                SELECT atom_id, atom_type, title, summary, content,
                       code, symptoms, causes, fixes, keywords, difficulty,
                       ts_rank(
                           to_tsvector('english', title || ' ' || summary || ' ' || content),
                           plainto_tsquery('english', $1)
                       ) AS rank
                FROM knowledge_atoms
                WHERE to_tsvector('english', title || ' ' || summary || ' ' || content)
                      @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $2
                """,
                query_text,
                limit,
            )
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("KB full-text search failed for: %s", query_text[:80])
            return []

    async def search_by_fault_code(self, fault_code: str, limit: int = 3) -> list[dict[str, Any]]:
        """Search atoms by fault/error code."""
        if not self._pool:
            return []

        try:
            rows = await self._pool.fetch(
                """
                SELECT atom_id, atom_type, title, summary, content,
                       code, symptoms, causes, fixes, keywords, difficulty
                FROM knowledge_atoms
                WHERE code = $1 OR $1 = ANY(keywords)
                LIMIT $2
                """,
                fault_code,
                limit,
            )
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("KB fault code search failed for: %s", fault_code)
            return []

    async def search_by_symptoms(self, symptom: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search atoms whose symptoms array matches the given text."""
        if not self._pool:
            return []

        try:
            rows = await self._pool.fetch(
                """
                SELECT atom_id, atom_type, title, summary, content,
                       code, symptoms, causes, fixes, keywords, difficulty
                FROM knowledge_atoms
                WHERE EXISTS (
                    SELECT 1 FROM unnest(symptoms) s
                    WHERE s ILIKE '%' || $1 || '%'
                )
                ORDER BY atom_type = 'fault' DESC
                LIMIT $2
                """,
                symptom,
                limit,
            )
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("KB symptom search failed for: %s", symptom[:80])
            return []

    async def get_by_type(self, atom_type: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get atoms by type: fault, pattern, concept, procedure."""
        if not self._pool:
            return []

        try:
            rows = await self._pool.fetch(
                """
                SELECT atom_id, atom_type, title, summary, code, keywords, difficulty
                FROM knowledge_atoms
                WHERE atom_type = $1
                ORDER BY updated_at DESC
                LIMIT $2
                """,
                atom_type,
                limit,
            )
            return [dict(r) for r in rows]
        except Exception:
            logger.exception("KB get_by_type failed for: %s", atom_type)
            return []

    async def health_check(self) -> dict:
        if not self._pool:
            return {"status": "unhealthy", "error": "not connected"}
        try:
            count = await self._pool.fetchval("SELECT count(*) FROM knowledge_atoms")
            return {"status": "healthy", "atoms": count}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def name(self) -> str:
        return "knowledge"
