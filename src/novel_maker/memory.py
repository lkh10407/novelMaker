"""RAG Memory Store — long-term novel memory using ChromaDB + Gemini embeddings.

Stores chapter content, events, and character arcs as embeddings for
semantic retrieval, solving the context window limitation for long novels.
"""

from __future__ import annotations

import logging
from pathlib import Path

import chromadb
from google import genai

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-004"
COLLECTION_NAME = "novel_memory"


class MemoryStore:
    """Persistent vector store for novel content backed by ChromaDB."""

    def __init__(self, project_dir: Path, client: genai.Client):
        db_path = project_dir / "memory_db"
        db_path.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(db_path))
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self.genai_client = client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store_chapter(
        self,
        chapter_num: int,
        content: str,
        characters: list[str] | None = None,
        events: list[str] | None = None,
    ) -> None:
        """Chunk and embed a completed chapter into the vector store."""
        characters = characters or []
        events = events or []

        docs: list[str] = []
        metas: list[dict] = []
        ids: list[str] = []

        # 1. Content chunks
        chunks = self._chunk_text(content)
        for i, chunk in enumerate(chunks):
            docs.append(chunk)
            metas.append({
                "chapter": chapter_num,
                "type": "content",
                "characters": ",".join(characters),
                "chunk_index": i,
            })
            ids.append(f"ch{chapter_num}_content_{i}")

        # 2. Event entries
        for i, event in enumerate(events):
            docs.append(event)
            metas.append({
                "chapter": chapter_num,
                "type": "event",
                "characters": ",".join(characters),
                "chunk_index": 0,
            })
            ids.append(f"ch{chapter_num}_event_{i}")

        # 3. Character arc summary (combine characters into one entry)
        if characters:
            arc_text = f"{chapter_num}장 등장인물: {', '.join(characters)}"
            docs.append(arc_text)
            metas.append({
                "chapter": chapter_num,
                "type": "character_arc",
                "characters": ",".join(characters),
                "chunk_index": 0,
            })
            ids.append(f"ch{chapter_num}_arc")

        if not docs:
            return

        embeddings = await self._embed(docs)

        # Upsert to handle re-runs gracefully
        self.collection.upsert(
            ids=ids,
            documents=docs,
            embeddings=embeddings,
            metadatas=metas,
        )
        logger.info(
            "MemoryStore: stored %d entries for chapter %d",
            len(docs), chapter_num,
        )

    async def query_relevant(
        self,
        query_texts: list[str],
        n_results: int = 5,
    ) -> list[str]:
        """Search for the most relevant passages given query texts."""
        if not query_texts or self.collection.count() == 0:
            return []

        query_embeddings = await self._embed(query_texts)

        results = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            include=["documents", "metadatas"],
        )

        # Flatten and deduplicate while preserving order
        seen: set[str] = set()
        passages: list[str] = []
        for doc_list in results.get("documents", []):
            if doc_list is None:
                continue
            for doc in doc_list:
                if doc and doc not in seen:
                    seen.add(doc)
                    passages.append(doc)

        return passages[:n_results]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _chunk_text(
        text: str,
        chunk_size: int = 500,
        overlap: int = 100,
    ) -> list[str]:
        """Split text into overlapping chunks."""
        if not text:
            return []

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk.strip())
            start += chunk_size - overlap

        return chunks

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via Gemini text-embedding-004."""
        response = await self.genai_client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=texts,
        )
        return [e.values for e in response.embeddings]
