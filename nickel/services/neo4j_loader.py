"""Загрузка извлечённых троек в Neo4j с типовыми labels и версионированием."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from ontology.schema import NODE_TYPES


class Neo4jLoader:
    VALID_LABELS = set(NODE_TYPES)

    CONSTRAINTS = [
        "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
    ]

    INDEXES = [
        "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name)",
        "CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.type)",
        "CREATE INDEX rel_fact_id IF NOT EXISTS FOR ()-[r:REL]-() ON (r.fact_id)",
    ]

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "nickel_kg_pass")
        self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def init_schema(self):
        with self._driver.session() as session:
            for stmt in self.CONSTRAINTS + self.INDEXES:
                try:
                    session.run(stmt)
                except Exception:
                    pass

    @staticmethod
    def fact_id(subject: str, relation: str, obj: str) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{subject}:{relation}:{obj}"))

    @staticmethod
    def _entity_id(name: str, entity_type: str) -> str:
        return f"{entity_type}:{name}".lower().replace(" ", "_")

    @staticmethod
    def _safe_label(entity_type: str) -> str:
        return entity_type if entity_type in Neo4jLoader.VALID_LABELS else "Concept"

    def _apply_type_labels(self, session, entity_id: str, entity_type: str):
        label = self._safe_label(entity_type)
        session.run(
            f"MATCH (n:Entity {{id: $id}}) SET n:{label}",
            id=entity_id,
        )

    def load_triples(
        self,
        triples: List[Dict[str, Any]],
        job_id: Optional[str] = None,
        source_document: Optional[str] = None,
    ) -> Dict[str, int]:
        batch = []
        for t in triples:
            props = t.get("properties") or {}
            fid = t.get("fact_id") or self.fact_id(t["subject"], t["relation"], t["object"])
            batch.append({
                "fact_id": fid,
                "version": t.get("version", 1),
                "subject": t["subject"],
                "subject_type": t["subject_type"],
                "subj_id": self._entity_id(t["subject"], t["subject_type"]),
                "object": t["object"],
                "object_type": t["object_type"],
                "obj_id": self._entity_id(t["object"], t["object_type"]),
                "relation": t["relation"],
                "properties": props,
                "numeric_constraints": props.get("numeric_constraints") or [],
                "confidence": t.get("confidence"),
                "geography": t.get("geography"),
                "source_chunk": t.get("source_chunk") or props.get("source_chunk"),
                "source_page": t.get("source_page") or props.get("source_page") or props.get("page"),
                "doi": props.get("doi"),
                "fair_metadata": json.dumps(props.get("fair") or {}, ensure_ascii=False),
                "verification_status": t.get("verification_status", "pending"),
            })

        total = 0
        chunk_size = 200
        load_cypher = """
        UNWIND $batch AS t
        MERGE (s:Entity {id: t.subj_id})
        ON CREATE SET s.name = t.subject, s.type = t.subject_type,
                      s.created_at = datetime(), s.job_id = $job_id,
                      s.source_document = $source_document
        ON MATCH SET s.updated_at = datetime()
        MERGE (o:Entity {id: t.obj_id})
        ON CREATE SET o.name = t.object, o.type = t.object_type,
                      o.created_at = datetime(), o.job_id = $job_id,
                      o.source_document = $source_document
        ON MATCH SET o.updated_at = datetime()
        MERGE (s)-[r:REL {fact_id: t.fact_id}]->(o)
        ON CREATE SET r.type = t.relation, r.created_at = datetime(),
                      r.properties = t.properties, r.confidence = t.confidence,
                      r.geography = t.geography, r.numeric_constraints = t.numeric_constraints,
                      r.source_chunk = t.source_chunk, r.doi = t.doi,
                      r.source_page = t.source_page,
                      r.fair_metadata = t.fair_metadata, r.version = t.version,
                      r.verification_status = t.verification_status
        ON MATCH SET r.updated_at = datetime(), r.type = t.relation,
                     r.properties = t.properties, r.version = t.version,
                     r.source_chunk = t.source_chunk, r.doi = t.doi,
                     r.source_page = t.source_page,
                     r.verification_status = t.verification_status
        RETURN count(r) AS rel_count
        """
        with self._driver.session() as session:
            for i in range(0, len(batch), chunk_size):
                chunk = batch[i : i + chunk_size]
                result = session.run(
                    load_cypher,
                    batch=chunk,
                    job_id=job_id,
                    source_document=source_document,
                )
                record = result.single()
                total += record["rel_count"] if record else 0
                for item in chunk:
                    self._apply_type_labels(session, item["subj_id"], item["subject_type"])
                    self._apply_type_labels(session, item["obj_id"], item["object_type"])

        return {"relationships_loaded": total, "entities_in_batch": len(batch)}

    def delete_fact(self, fact: Dict[str, Any]) -> bool:
        """Удаляет связь из Neo4j при reject/delete."""
        fid = fact.get("id") or self.fact_id(
            fact["subject"], fact["relation"], fact["object"]
        )
        cypher = """
        MATCH ()-[r:REL {fact_id: $fact_id}]->()
        DELETE r
        RETURN count(r) AS deleted
        """
        fallback = """
        MATCH (s:Entity)-[r:REL]->(o:Entity)
        WHERE s.name = $subject AND o.name = $object AND r.type = $relation
        DELETE r
        RETURN count(r) AS deleted
        """
        with self._driver.session() as session:
            result = session.run(cypher, fact_id=fid)
            record = result.single()
            if record and record["deleted"]:
                return True
            result = session.run(
                fallback,
                subject=fact["subject"],
                object=fact["object"],
                relation=fact["relation"],
            )
            record = result.single()
            return bool(record and record["deleted"])

    def query(self, cypher: str, params: Optional[dict] = None) -> List[Dict]:
        with self._driver.session() as session:
            result = session.run(cypher, params or {})
            return [dict(record) for record in result]

    def search_neighbors(
        self,
        entity_name: str,
        depth: int = 2,
        relation_filter: Optional[List[str]] = None,
        type_filter: Optional[List[str]] = None,
    ) -> List[Dict]:
        fallback = """
        MATCH path = (start:Entity)-[*1..$depth]-(connected:Entity)
        WHERE toLower(start.name) CONTAINS toLower($name)
        RETURN DISTINCT start.name AS source,
               connected.name AS target,
               connected.type AS target_type
        LIMIT 50
        """
        try:
            return self.query(fallback, {"name": entity_name, "depth": depth})
        except Exception:
            simple = """
            MATCH (start:Entity)-[r:REL]->(connected:Entity)
            WHERE toLower(start.name) CONTAINS toLower($name)
            RETURN start.name AS source, connected.name AS target,
                   connected.type AS target_type, r.type AS relation
            LIMIT 50
            """
            return self.query(simple, {"name": entity_name})

    def stats(self) -> Dict[str, int]:
        rows = self.query(
            "MATCH (n:Entity) WITH count(n) AS entities "
            "MATCH ()-[r:REL]->() RETURN entities, count(r) AS relationships"
        )
        if rows:
            return {"entities": rows[0]["entities"], "relationships": rows[0]["relationships"]}
        return {"entities": 0, "relationships": 0}

    def export_graph_view(
        self,
        limit: int = 200,
        center_entity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Экспорт узлов и рёбер для SVG-визуализации."""
        limit = max(1, min(limit, 500))
        nodes_map: Dict[str, Dict[str, str]] = {}
        edges: List[Dict[str, str]] = []
        seen_edges: set[tuple[str, str, str]] = set()

        def add_node(nid: str, name: str, ntype: str):
            if nid and nid not in nodes_map:
                nodes_map[nid] = {"id": nid, "name": name or nid, "type": ntype or "Concept"}

        def add_edge(src: str, tgt: str, relation: str):
            if not src or not tgt:
                return
            rel = relation or "related_to"
            key = (src, tgt, rel)
            if key in seen_edges:
                return
            seen_edges.add(key)
            edges.append({
                "source": src,
                "target": tgt,
                "relation": rel,
                "label": rel.replace("_", " "),
            })

        if center_entity:
            rows = self.query(
                """
                MATCH (start:Entity)
                WHERE toLower(start.name) = toLower($center)
                   OR toLower(start.name) CONTAINS toLower($center)
                WITH start LIMIT 1
                MATCH (start)-[r:REL*0..2]-(n:Entity)
                WITH collect(DISTINCT n)[..$limit] AS nodeList
                UNWIND nodeList AS n1
                OPTIONAL MATCH (n1)-[rel:REL]->(n2:Entity)
                WHERE n2 IN nodeList
                RETURN n1.id AS src_id, n1.name AS src_name, n1.type AS src_type,
                       n2.id AS tgt_id, n2.name AS tgt_name, n2.type AS tgt_type,
                       rel.type AS relation
                """,
                {"center": center_entity, "limit": limit},
            )
        else:
            rows = self.query(
                """
                MATCH (n:Entity)
                WITH n ORDER BY n.name LIMIT $limit
                WITH collect(n) AS nodeList
                UNWIND nodeList AS n1
                OPTIONAL MATCH (n1)-[rel:REL]->(n2:Entity)
                WHERE n2 IN nodeList
                RETURN n1.id AS src_id, n1.name AS src_name, n1.type AS src_type,
                       n2.id AS tgt_id, n2.name AS tgt_name, n2.type AS tgt_type,
                       rel.type AS relation
                """,
                {"limit": limit},
            )

        for row in rows:
            add_node(row.get("src_id"), row.get("src_name"), row.get("src_type"))
            if row.get("tgt_id"):
                add_node(row.get("tgt_id"), row.get("tgt_name"), row.get("tgt_type"))
                add_edge(row.get("src_id"), row.get("tgt_id"), row.get("relation"))

        return {
            "nodes": list(nodes_map.values())[:limit],
            "edges": edges,
            "center": center_entity,
        }
