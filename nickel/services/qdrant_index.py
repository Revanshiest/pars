"""Индексация чанков и сущностей в Qdrant."""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)


class QdrantIndexer:
    CHUNKS_COLLECTION = "document_chunks"
    ENTITIES_COLLECTION = "kg_entities"

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        embedding_dim: int = 1024,
    ):
        self.host = host or os.getenv("QDRANT_HOST", "localhost")
        self.port = port or int(os.getenv("QDRANT_PORT", "6333"))
        self.embedding_dim = embedding_dim
        self.client = QdrantClient(host=self.host, port=self.port)
        self._embeddings = None

    @property
    def embeddings(self):
        if self._embeddings is None:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            self._embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
        return self._embeddings

    def ensure_collections(self):
        for name in (self.CHUNKS_COLLECTION, self.ENTITIES_COLLECTION):
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim, distance=Distance.COSINE
                    ),
                )

    def index_chunks(
        self,
        chunks: List[Dict[str, Any]],
        job_id: str,
        document_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        self.ensure_collections()
        meta = metadata or {}
        texts = [c["text"] for c in chunks]
        vectors = self.embeddings.embed_documents(texts)

        points = []
        for chunk, vector in zip(chunks, vectors):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{job_id}:{chunk['id']}"))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "job_id": job_id,
                        "document": document_name,
                        "chunk_id": chunk["id"],
                        "text": chunk["text"][:2000],
                        "headers": chunk.get("headers", ""),
                        "type": "chunk",
                        "document_kind": meta.get("document_kind"),
                        "year": meta.get("year"),
                        "author": meta.get("author"),
                        "geography": meta.get("geography"),
                    },
                )
            )

        self.client.upsert(collection_name=self.CHUNKS_COLLECTION, points=points)
        return len(points)

    def index_entities(
        self,
        entities: List[Dict[str, str]],
        job_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        if not entities:
            return 0
        meta = metadata or {}
        self.ensure_collections()
        texts = [f"{e['name']} ({e['type']})" for e in entities]
        vectors = self.embeddings.embed_documents(texts)

        points = []
        for entity, vector in zip(entities, vectors):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{job_id}:{entity['name']}:{entity['type']}"))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "job_id": job_id,
                        "name": entity["name"],
                        "type": entity["type"],
                        "type_filter": "entity",
                        "document_kind": meta.get("document_kind"),
                        "geography": meta.get("geography"),
                    },
                )
            )

        self.client.upsert(collection_name=self.ENTITIES_COLLECTION, points=points)
        return len(points)

    @staticmethod
    def _matches_metadata(payload: Dict, filters: Optional[Dict[str, Any]]) -> bool:
        if not filters:
            return True
        if filters.get("document_kind") and payload.get("document_kind") != filters["document_kind"]:
            return False
        if filters.get("geography") and payload.get("geography") != filters["geography"]:
            return False
        if filters.get("author"):
            author = (payload.get("author") or "").lower()
            if filters["author"].lower() not in author:
                return False
        year = payload.get("year")
        if year is not None:
            try:
                year = int(year)
            except (TypeError, ValueError):
                year = None
        if filters.get("year") is not None and year != filters["year"]:
            return False
        if filters.get("year_from") is not None and (year is None or year < filters["year_from"]):
            return False
        if filters.get("year_to") is not None and (year is None or year > filters["year_to"]):
            return False
        return True

    def search_chunks(
        self,
        query: str,
        limit: int = 10,
        job_id: Optional[str] = None,
        document: Optional[str] = None,
        metadata_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        self.ensure_collections()
        vector = self.embeddings.embed_query(query)
        filters = []
        if job_id:
            filters.append(FieldCondition(key="job_id", match=MatchValue(value=job_id)))
        if document:
            filters.append(FieldCondition(key="document", match=MatchValue(value=document)))
        if metadata_filters:
            if metadata_filters.get("document_kind"):
                filters.append(FieldCondition(
                    key="document_kind", match=MatchValue(value=metadata_filters["document_kind"])
                ))
            if metadata_filters.get("geography"):
                filters.append(FieldCondition(
                    key="geography", match=MatchValue(value=metadata_filters["geography"])
                ))

        query_filter = Filter(must=filters) if filters else None
        fetch_limit = limit * 4 if metadata_filters else limit
        results = self.client.search(
            collection_name=self.CHUNKS_COLLECTION,
            query_vector=vector,
            query_filter=query_filter,
            limit=fetch_limit,
        )
        hits = [
            {
                "score": hit.score,
                "text": hit.payload.get("text"),
                "document": hit.payload.get("document"),
                "chunk_id": hit.payload.get("chunk_id"),
                "headers": hit.payload.get("headers"),
                "document_kind": hit.payload.get("document_kind"),
                "year": hit.payload.get("year"),
                "author": hit.payload.get("author"),
                "geography": hit.payload.get("geography"),
            }
            for hit in results
            if self._matches_metadata(hit.payload or {}, metadata_filters)
        ]
        return hits[:limit]

    def search_entities(
        self,
        query: str,
        entity_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict]:
        self.ensure_collections()
        vector = self.embeddings.embed_query(query)
        filters = []
        if entity_type:
            filters.append(FieldCondition(key="type", match=MatchValue(value=entity_type)))

        query_filter = Filter(must=filters) if filters else None
        results = self.client.search(
            collection_name=self.ENTITIES_COLLECTION,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
        )
        return [
            {
                "score": hit.score,
                "name": hit.payload.get("name"),
                "type": hit.payload.get("type"),
            }
            for hit in results
        ]

    def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        entity_type: Optional[str] = None,
    ) -> Dict[str, List[Dict]]:
        return {
            "chunks": self.search_chunks(query, limit=limit),
            "entities": self.search_entities(query, entity_type=entity_type, limit=limit),
        }
