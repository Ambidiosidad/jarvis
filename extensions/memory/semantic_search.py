"""
J.A.R.V.I.S. Semantic Search Engine
======================================
Búsqueda semántica local usando Qdrant + Ollama embeddings.
Replica la funcionalidad de búsqueda vectorial de Supermemory
pero 100% offline.

Pipeline:
1. Texto → Ollama (nomic-embed-text) → vector 768d
2. Vector → Qdrant → resultados por similitud semántica
3. Fallback a SQLite LIKE si Qdrant no está disponible
"""
import os
import httpx
from typing import Optional

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://jarvis_ollama:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://jarvis_qdrant:6333")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
COLLECTION = "jarvis_memories"
VECTOR_SIZE = 768  # nomic-embed-text output dimension

_qdrant_ready = False


async def _get_embedding(text: str) -> Optional[list[float]]:
    """Get embedding vector from Ollama."""
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(f"{OLLAMA_URL}/api/embed", json={
                "model": EMBED_MODEL,
                "input": text,
            })
            if r.status_code == 200:
                data = r.json()
                embeddings = data.get("embeddings", [])
                if embeddings:
                    return embeddings[0]
    except Exception:
        pass
    return None


async def init_collection():
    """Initialize Qdrant collection for memories."""
    global _qdrant_ready
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # Check if collection exists
            r = await c.get(f"{QDRANT_URL}/collections/{COLLECTION}")
            if r.status_code == 200:
                _qdrant_ready = True
                return True

            # Create collection
            r = await c.put(f"{QDRANT_URL}/collections/{COLLECTION}", json={
                "vectors": {
                    "size": VECTOR_SIZE,
                    "distance": "Cosine",
                }
            })
            if r.status_code == 200:
                _qdrant_ready = True
                return True
    except Exception:
        _qdrant_ready = False
    return False


async def index_memory(memory_id: int, content: str,
                       metadata: dict = None):
    """Index a memory in Qdrant for semantic search."""
    if not _qdrant_ready:
        await init_collection()
    if not _qdrant_ready:
        return False

    embedding = await _get_embedding(content)
    if not embedding:
        return False

    payload = {"content": content, "memory_id": memory_id}
    if metadata:
        payload.update(metadata)

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.put(
                f"{QDRANT_URL}/collections/{COLLECTION}/points",
                json={
                    "points": [{
                        "id": memory_id,
                        "vector": embedding,
                        "payload": payload,
                    }]
                })
            return r.status_code == 200
    except Exception:
        return False


async def search_similar(query: str, limit: int = 10,
                         min_score: float = 0.3) -> list[dict]:
    """
    Search memories by semantic similarity.
    Returns list of {memory_id, content, score, metadata}
    """
    if not _qdrant_ready:
        await init_collection()
    if not _qdrant_ready:
        return []

    embedding = await _get_embedding(query)
    if not embedding:
        return []

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                json={
                    "vector": embedding,
                    "limit": limit,
                    "score_threshold": min_score,
                    "with_payload": True,
                })
            if r.status_code != 200:
                return []

            results = r.json().get("result", [])
            return [{
                "memory_id": hit["id"],
                "content": hit.get("payload", {}).get("content", ""),
                "score": hit["score"],
                "category": hit.get("payload", {}).get("category", ""),
                "memory_type": hit.get("payload", {}).get("memory_type", ""),
            } for hit in results]
    except Exception:
        return []


async def delete_point(memory_id: int):
    """Remove a memory from the vector index."""
    if not _qdrant_ready:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            await c.post(
                f"{QDRANT_URL}/collections/{COLLECTION}/points/delete",
                json={"points": [memory_id]})
    except Exception:
        pass


def is_ready() -> bool:
    """Check if semantic search is available."""
    return _qdrant_ready
