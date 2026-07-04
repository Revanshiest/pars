"""Загрузка извлечённых троек в Neo4j с типовыми labels и версионированием."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from ontology.schema import NODE_TYPES, RELATIONS, RELATION_META


class Neo4jLoader:
    VALID_LABELS = set(NODE_TYPES)
    VALID_RELATIONS = set(RELATIONS)

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

    @staticmethod
    def _typed_rel_name(relation: str) -> str:
        """CamelCase имя типизированного ребра для Cypher."""
        if relation not in Neo4jLoader.VALID_RELATIONS:
            relation = "related_to"
        parts = relation.split("_")
        return "".join(p[:1].upper() + p[1:] for p in parts if p)

    @staticmethod
    def _neo4j_safe_constraints(constraints: Any) -> List[str]:
        if not isinstance(constraints, list):
            return []
        out: List[str] = []
        for item in constraints:
            if isinstance(item, (str, int, float, bool)):
                out.append(str(item))
            elif item is not None:
                out.append(json.dumps(item, ensure_ascii=False))
        return out[:50]

    @staticmethod
    def fact_to_triple(fact: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "subject": fact["subject"],
            "subject_type": fact["subject_type"],
            "relation": fact["relation"],
            "object": fact["object"],
            "object_type": fact["object_type"],
            "properties": fact.get("properties") or {},
            "confidence": fact.get("confidence"),
            "geography": fact.get("geography"),
            "verification_status": fact.get("verification_status", "pending"),
            "version": fact.get("version", 1),
            "fact_id": fact.get("id"),
            "source_chunk": fact.get("source_chunk"),
            "source_page": fact.get("source_page"),
        }

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
                "properties_json": json.dumps(props, ensure_ascii=False),
                "numeric_constraints": self._neo4j_safe_constraints(props.get("numeric_constraints")),
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
                      r.properties_json = t.properties_json, r.confidence = t.confidence,
                      r.geography = t.geography, r.numeric_constraints = t.numeric_constraints,
                      r.source_chunk = t.source_chunk, r.doi = t.doi,
                      r.source_page = t.source_page,
                      r.fair_metadata = t.fair_metadata, r.version = t.version,
                      r.verification_status = t.verification_status
        ON MATCH SET r.updated_at = datetime(), r.type = t.relation,
                     r.properties_json = t.properties_json, r.version = t.version,
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
                    self._apply_typed_rel(session, item)

        return {"relationships_loaded": total, "entities_in_batch": len(batch)}

    def _apply_typed_rel(self, session, item: Dict[str, Any]):
        rel_type = self._typed_rel_name(item["relation"])
        session.run(
            f"""
            MATCH (s:Entity {{id: $subj_id}})-[r:REL {{fact_id: $fact_id}}]->(o:Entity {{id: $obj_id}})
            MERGE (s)-[tr:{rel_type} {{fact_id: $fact_id}}]->(o)
            SET tr.type = r.type, tr.confidence = r.confidence, tr.geography = r.geography,
                tr.verification_status = r.verification_status, tr.version = r.version
            """,
            subj_id=item["subj_id"], obj_id=item["obj_id"], fact_id=item["fact_id"],
        )

    def update_fact(self, fact: Dict[str, Any]) -> bool:
        """Обновляет связь в Neo4j после ручной правки факта."""
        fid = fact.get("id") or self.fact_id(fact["subject"], fact["relation"], fact["object"])
        old_subj = fact.get("_prev_subject") or fact["subject"]
        old_obj = fact.get("_prev_object") or fact["object"]
        old_rel = fact.get("_prev_relation") or fact["relation"]

        with self._driver.session() as session:
            session.run(
                "MATCH ()-[r:REL {fact_id: $fid}]->() DELETE r",
                fid=fid,
            )
            for rel_name in {self._typed_rel_name(old_rel), self._typed_rel_name(fact["relation"])}:
                try:
                    session.run(
                        f"MATCH ()-[r:{rel_name} {{fact_id: $fid}}]->() DELETE r",
                        fid=fid,
                    )
                except Exception:
                    pass

        triple = {
            "subject": fact["subject"],
            "subject_type": fact["subject_type"],
            "object": fact["object"],
            "object_type": fact["object_type"],
            "relation": fact["relation"],
            "properties": fact.get("properties") or {},
            "confidence": fact.get("confidence"),
            "geography": fact.get("geography"),
            "verification_status": fact.get("verification_status", "pending"),
            "version": fact.get("version", 1),
            "fact_id": fid,
            "source_chunk": fact.get("source_chunk"),
            "source_page": fact.get("source_page"),
        }
        self.load_triples([triple], source_document=fact.get("source_document"))
        return True

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

    def delete_facts_by_ids(self, fact_ids: List[str]) -> int:
        if not fact_ids:
            return 0
        with self._driver.session() as session:
            session.run(
                """
                MATCH ()-[r:REL]->()
                WHERE r.fact_id IN $fact_ids
                DELETE r
                """,
                fact_ids=fact_ids,
            )
        return len(fact_ids)

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
        depth = max(1, min(depth, 4))
        rel_clause = ""
        params: Dict[str, Any] = {"name": entity_name, "depth": depth}
        if relation_filter:
            rel_clause = "AND ALL(rel IN relationships(path) WHERE rel.type IN $relations)"
            params["relations"] = relation_filter
        type_clause = ""
        if type_filter:
            type_clause = "AND connected.type IN $types"
            params["types"] = type_filter

        cypher = f"""
        MATCH path = (start:Entity)-[rels:REL*1..$depth]-(connected:Entity)
        WHERE toLower(start.name) CONTAINS toLower($name)
        {rel_clause}
        {type_clause}
        WITH start, connected, relationships(path) AS rp
        UNWIND rp AS r
        RETURN DISTINCT start.name AS source, connected.name AS target,
               connected.type AS target_type, r.type AS relation
        LIMIT 80
        """
        try:
            return self.query(cypher, params)
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

        def add_edge(
            src: str, tgt: str, relation: str,
            src_name: str = "", tgt_name: str = "",
            src_type: str = "", tgt_type: str = "",
        ):
            if not src or not tgt:
                return
            rel = relation or "related_to"
            key = (src, tgt, rel)
            if key in seen_edges:
                return
            seen_edges.add(key)
            meta = RELATION_META.get(rel, {})
            edges.append({
                "id": f"{src}:{rel}:{tgt}",
                "source": src,
                "target": tgt,
                "relation": rel,
                "label": meta.get("label_ru") or rel.replace("_", " "),
                "description": meta.get("description", ""),
                "source_name": src_name,
                "target_name": tgt_name,
                "source_type": src_type,
                "target_type": tgt_type,
            })

        if center_entity:
            rows = self.query(
                """
                MATCH (start:Entity)
                WHERE toLower(start.name) = toLower($center)
                   OR toLower(start.name) CONTAINS toLower($center)
                WITH start LIMIT 1
                MATCH (start)-[r:REL*0..4]-(n:Entity)
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
                MATCH (s:Entity)-[rel:REL]->(o:Entity)
                WITH s, o, rel LIMIT $limit
                RETURN s.id AS src_id, s.name AS src_name, s.type AS src_type,
                       o.id AS tgt_id, o.name AS tgt_name, o.type AS tgt_type,
                       rel.type AS relation
                """,
                {"limit": limit},
            )

        for row in rows:
            add_node(row.get("src_id"), row.get("src_name"), row.get("src_type"))
            if row.get("tgt_id"):
                add_node(row.get("tgt_id"), row.get("tgt_name"), row.get("tgt_type"))
                add_edge(
                    row.get("src_id"), row.get("tgt_id"), row.get("relation"),
                    src_name=row.get("src_name") or "",
                    tgt_name=row.get("tgt_name") or "",
                    src_type=row.get("src_type") or "",
                    tgt_type=row.get("tgt_type") or "",
                )

        return {
            "nodes": list(nodes_map.values())[:limit],
            "edges": edges,
            "center": center_entity,
        }

    @staticmethod
    def graph_view_from_facts(
        facts: List[Dict[str, Any]],
        limit: int = 200,
        center_entity: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fallback-визуализация из SQLite, если Neo4j пуст или недоступен."""
        limit = max(1, min(limit, 500))
        nodes_map: Dict[str, Dict[str, str]] = {}
        edges: List[Dict[str, str]] = []
        seen_edges: set[tuple[str, str, str]] = set()

        def add_node(nid: str, name: str, ntype: str):
            if nid and nid not in nodes_map:
                nodes_map[nid] = {"id": nid, "name": name or nid, "type": ntype or "Concept"}

        def add_edge(
            src: str, tgt: str, relation: str,
            src_name: str = "", tgt_name: str = "",
            src_type: str = "", tgt_type: str = "",
        ):
            if not src or not tgt:
                return
            rel = relation or "related_to"
            key = (src, tgt, rel)
            if key in seen_edges:
                return
            seen_edges.add(key)
            meta = RELATION_META.get(rel, {})
            edges.append({
                "id": f"{src}:{rel}:{tgt}",
                "source": src,
                "target": tgt,
                "relation": rel,
                "label": meta.get("label_ru") or rel.replace("_", " "),
                "description": meta.get("description", ""),
                "source_name": src_name,
                "target_name": tgt_name,
                "source_type": src_type,
                "target_type": tgt_type,
            })

        filtered = facts
        if center_entity:
            ce = center_entity.lower()
            filtered = [
                f for f in facts
                if ce in f.get("subject", "").lower() or ce in f.get("object", "").lower()
            ] or facts

        for f in filtered[: limit * 3]:
            sid = Neo4jLoader._entity_id(f["subject"], f["subject_type"])
            oid = Neo4jLoader._entity_id(f["object"], f["object_type"])
            add_node(sid, f["subject"], f["subject_type"])
            add_node(oid, f["object"], f["object_type"])
            add_edge(
                sid, oid, f["relation"],
                src_name=f["subject"], tgt_name=f["object"],
                src_type=f["subject_type"], tgt_type=f["object_type"],
            )
            if len(nodes_map) >= limit:
                break

        return {
            "nodes": list(nodes_map.values())[:limit],
            "edges": edges,
            "center": center_entity,
            "source": "sqlite",
        }

    def sync_from_store(self, batch_size: int = 200) -> Dict[str, Any]:
        from services.store import get_store

        facts = [
            f for f in get_store().list_facts(limit=100_000)
            if f.get("verification_status") != "rejected"
        ]
        if not facts:
            return {"relationships_loaded": 0, "facts": 0}

        self.init_schema()
        total = 0
        errors: List[str] = []
        triples = [self.fact_to_triple(f) for f in facts]
        for i in range(0, len(triples), batch_size):
            chunk = triples[i : i + batch_size]
            try:
                result = self.load_triples(chunk, job_id="sqlite-sync", source_document="sqlite_sync")
                total += result.get("relationships_loaded", 0)
            except Exception as e:
                errors.append(str(e)[:200])
                if len(errors) >= 5:
                    break
        return {
            "relationships_loaded": total,
            "facts": len(facts),
            "errors": errors,
            "stats": self.stats(),
        }
