"""Чат-агент: инструменты → контекст из БД → один запрос YandexGPT → ответ."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from agent.tool_registry import catalog_for_prompt, select_tools
from agent.tools import SearchTools
from services.fact_format import fact_display_fields, format_fact_answer
from services.graph_view import _json_safe
from services.verification import enrich_fact
from services.logging_config import get_logger
from services.user_messages import Msg
from services.yandex_llm import yandex_complete

logger = get_logger(__name__)


SYNTHESIS_SYSTEM = """Ты — ведущий аналитик R&D в горно-металлургии (никель, медь, гидро- и пирометаллургия).
Отвечай на русском языке развёрнуто и профессионально, как опытному инженеру-коллеге.

Структура ответа (4–8 предложений, связный текст без нумерации):
1. Прямой ответ на вопрос — с числами, единицами и формулировками из контекста.
2. Контекст: что известно из источников, какие процессы/условия упоминаются.
3. Ограничения: если данных мало, честно укажи пробелы и что стоит догрузить в базу.
4. Заверши строкой «Источники: …» — перечисли названия документов через запятую.

Запрещено: JSON, score, названия инструментов, фразы «найдено в базе», «результаты поиска».
Не выдумывай факты — опирайся только на предоставленный контекст."""


class YandexKnowledgeAgent:
    """Агент с набором tools и ровно одним вызовом YandexGPT на ответ."""

    def __init__(self):
        self.tools = SearchTools()

    def _execute_tool(self, name: str, arguments: Dict[str, Any], role: Optional[str]) -> Dict[str, Any]:
        args = dict(arguments)
        if role:
            args["role"] = role

        if name == "search_facts":
            return self.tools.execute("hybrid_search", args)

        if name == "compare_practices":
            return self.tools.execute("compare_practices", args)

        if name == "numeric_search":
            from services.numeric_query import search_by_numeric_query
            return search_by_numeric_query(args.get("query", ""), limit=args.get("limit", 20))

        if name == "explore_graph":
            return self._explore_graph_sqlite(
                args.get("entity_name", ""),
                limit=args.get("limit", 20),
                role=role,
            )

        if name == "glossary_lookup":
            from services.glossary import text_glossary_lookup
            matches = text_glossary_lookup(args.get("text", ""), top_k=8)
            return {"matches": matches, "count": len(matches)}

        if name == "knowledge_stats":
            from services.store import get_store
            store = get_store()
            facts = store.list_facts(role=role, limit=1)
            with store._connect() as conn:
                facts_total = conn.execute("SELECT COUNT(*) FROM verified_facts").fetchone()[0]
                glossary = conn.execute("SELECT COUNT(*) FROM glossary").fetchone()[0]
                docs = conn.execute(
                    "SELECT COUNT(DISTINCT source_document) FROM verified_facts WHERE source_document IS NOT NULL"
                ).fetchone()[0]
            return {
                "facts_total": facts_total,
                "glossary_terms": glossary,
                "source_documents": docs,
                "sample_fact_exists": bool(facts),
            }

        return {"error": f"Unknown tool: {name}"}

    def _explore_graph_sqlite(
        self,
        entity_name: str,
        *,
        limit: int = 20,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        from services.graph_view import explore_entity_neighbors
        if not entity_name.strip():
            return {"entity": entity_name, "edges": [], "triples": []}
        try:
            return explore_entity_neighbors(entity_name, limit=min(limit, 12), role=role)
        except Exception as exc:
            return {"entity": entity_name, "error": str(exc), "edges": []}

    def _rerank_facts_for_question(self, facts: List[Dict[str, Any]], question: str) -> List[Dict[str, Any]]:
        from services.query_tokens import extract_search_terms

        terms = extract_search_terms(question)
        q = question.lower()

        def relevance(f: Dict[str, Any]) -> float:
            raw = f.get("raw") or f
            obj = (raw.get("object") or "").lower()
            props = raw.get("properties") or {}
            val = str(props.get("value") or "").lower()
            desc = str(props.get("description") or f.get("description") or "").lower()
            score = float(f.get("score") or 0)
            for t in terms:
                if t in obj:
                    score += 3
                if t in val or t in desc:
                    score += 2
            if any(w in q for w in ["содержан", "grade", "content", "cu", "мед"]):
                if "grade" in obj or "cu" in val:
                    score += 5
            if any(w in q for w in ["переработ", "tonnes", "capacity", "годов"]):
                if "treated" in obj or "tonnes" in val or "year" in obj.lower():
                    score += 5
            return score

        return sorted(facts, key=relevance, reverse=True)

    def _format_tool_context(self, tool_name: str, result: Dict[str, Any], question: str = "") -> str:
        if result.get("error"):
            return f"[{tool_name}] Ошибка: {result['error']}"

        if tool_name == "search_facts":
            items = result.get("results") or result.get("ranked_results") or []
            facts = [i for i in items if i.get("result_type") == "fact"]
            other = [i for i in items if i.get("result_type") != "fact"]
            if question and facts:
                facts = self._rerank_facts_for_question(facts, question)
            lines = []
            for item in facts[:6]:
                raw = item.get("raw") or item
                d = fact_display_fields(raw) if raw.get("subject") else item
                src = (item.get("metadata") or {}).get("source_document") or raw.get("source_document", "")
                lines.append(f"• {d.get('answer') or item.get('answer')} [{src}]")
            for item in other[:3]:
                lines.append(f"• {item.get('title', '—')}: {(item.get('snippet') or '')[:180]}")
            return "Факты из базы знаний:\n" + ("\n".join(lines) if lines else "нет данных")

        if tool_name == "compare_practices":
            comp = result.get("comparison") or {}
            parts = [comp.get("summary") or "Сравнение RU vs мир"]
            if comp.get("shared_topics"):
                parts.append("Общее: " + ", ".join(comp["shared_topics"][:6]))
            if comp.get("ru_only_topics"):
                parts.append("Только RU: " + ", ".join(comp["ru_only_topics"][:5]))
            if comp.get("global_only_topics"):
                parts.append("Только global: " + ", ".join(comp["global_only_topics"][:5]))
            return "Сравнение отечественной и мировой практики:\n" + "\n".join(parts)

        if tool_name == "numeric_search":
            rows = result.get("results") or []
            lines = []
            for r in rows[:8]:
                props = r.get("properties") or r.get("matched_constraint") or {}
                val = props.get("value") or props.get("description") or ""
                lines.append(f"- {r.get('subject')} → {r.get('object')}: {val}")
            return f"Числовые параметры ({len(rows)} записей):\n" + ("\n".join(lines) if lines else "нет")

        if tool_name == "explore_graph":
            edges = result.get("edges") or []
            lines = [
                f"- {e.get('source')} —[{e.get('relation')}]-> {e.get('target')}"
                for e in edges[:15]
            ]
            return f"Связи сущности «{result.get('entity')}» ({len(edges)}):\n" + (
                "\n".join(lines) if lines else "нет связей"
            )

        if tool_name == "glossary_lookup":
            matches = result.get("matches") or []
            lines = [f"- {m.get('canonical')} ← {m.get('matched_form')} (score {m.get('score')})" for m in matches[:8]]
            return f"[glossary_lookup] {len(matches)} совпадений:\n" + ("\n".join(lines) if lines else "нет")

        if tool_name == "knowledge_stats":
            return (
                f"[knowledge_stats] Фактов: {result.get('facts_total')}, "
                f"документов: {result.get('source_documents')}, "
                f"терминов глоссария: {result.get('glossary_terms')}"
            )

        return f"[{tool_name}] {json.dumps(result, ensure_ascii=False)[:1500]}"

    def _collect_sources(self, tool_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ranked: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for tr in tool_results:
            data = tr.get("result", {})
            items = list(data.get("results", []) + data.get("ranked_results", []))
            for block in (data.get("domestic"), data.get("global")):
                if isinstance(block, dict):
                    items.extend(block.get("ranked_results", []))
            for item in items:
                fid = str(item.get("id", item.get("title", "")))
                if fid in seen:
                    continue
                seen.add(fid)
                if item.get("result_type") == "fact":
                    raw = item.get("raw") or item
                    d = fact_display_fields(raw)
                    item = {**item, "answer": d["answer"], "value": d["value"], "title": d["title"]}
                ranked.append(item)
            for e in data.get("edges", []):
                ranked.append({
                    "result_type": "graph_edge",
                    "title": f"{e.get('source')} → {e.get('target')}",
                    "answer": e.get("relation"),
                    "snippet": e.get("relation"),
                })
        ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
        ranked = ranked[:12]
        for idx, item in enumerate(ranked):
            if item.get("result_type") != "fact" or idx >= 8:
                continue
            raw = item.get("raw") or item
            if not isinstance(raw, dict) or not raw.get("subject"):
                continue
            try:
                enriched = enrich_fact(dict(raw))
                item["credibility"] = enriched.get("credibility")
                item["provenance"] = enriched.get("provenance")
                meta = dict(item.get("metadata") or {})
                prov = enriched.get("provenance") or {}
                meta.setdefault("geography", enriched.get("geography") or raw.get("geography"))
                meta.setdefault(
                    "verification_status",
                    enriched.get("verification_status") or raw.get("verification_status"),
                )
                meta.setdefault("source_document", prov.get("source_document") or raw.get("source_document"))
                meta.setdefault("document_kind", prov.get("document_kind"))
                meta.setdefault("doi", prov.get("doi"))
                meta.setdefault("year", prov.get("year"))
                item["metadata"] = meta
            except Exception:
                pass
        return [_json_safe(item) for item in ranked]

    async def query(
        self,
        question: str,
        max_iterations: int = 5,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        plan = select_tools(question)[:max_iterations]
        tool_calls: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []
        context_blocks: List[str] = []

        async def _run_step(step: Dict[str, Any]) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
            name = step["name"]
            args = step.get("arguments") or {}
            result = await asyncio.to_thread(self._execute_tool, name, args, role)
            return name, args, result

        steps_out = await asyncio.gather(*[_run_step(step) for step in plan])
        for name, args, result in steps_out:
            tool_calls.append({"tool": name, "args": args, "result_count": _result_count(result)})
            tool_results.append({"tool": name, "result": result})
            context_blocks.append(self._format_tool_context(name, result, question))

        tools_used = [s["name"] for s in plan]
        context_text = "\n\n".join(context_blocks) if context_blocks else "Контекст пуст."
        sources = self._collect_sources(tool_results)

        user_prompt = (
            f"Вопрос пользователя:\n{question}\n\n"
            f"--- Данные из базы знаний ---\n{context_text}\n\n"
            f"Дай развёрнутый ответ (4–8 предложений). Без нумерованных списков."
        )

        try:
            answer = await yandex_complete(SYNTHESIS_SYSTEM, user_prompt, temperature=0.35)
            llm_ok = True
        except Exception as exc:
            logger.warning("YandexGPT unavailable: %s", exc)
            answer = self._fallback_answer(question, tool_results)
            llm_ok = False

        if not sources:
            answer = Msg.AGENT_NO_DATA
            confidence = 0.0
        else:
            confidence = round(min(0.95, 0.4 + 0.05 * len(sources)), 2)

        return {
            "question": question,
            "answer": answer,
            "sources": sources,
            "ranked_results": sources,
            "tool_calls": tool_calls,
            "tools_used": tools_used,
            "pipeline": "yandex_agent",
            "confidence": confidence,
            "llm_synthesized": llm_ok,
            "yandex_requests": 1 if llm_ok else 0,
        }

    def _fallback_answer(
        self,
        question: str,
        tool_results: List[Dict[str, Any]],
    ) -> str:
        parts = [Msg.AGENT_LLM_DOWN, ""]
        has_data = False
        for tr in tool_results:
            block = self._format_tool_context(tr["tool"], tr["result"], question)
            if "нет данных" not in block.lower():
                has_data = True
            parts.append(block)
        if not has_data:
            return Msg.AGENT_NO_DATA
        return "\n\n".join(parts)


def _result_count(result: Dict[str, Any]) -> int:
    for key in ("results", "ranked_results", "edges", "matches", "triples"):
        if isinstance(result.get(key), list):
            return len(result[key])
    if result.get("facts_total") is not None:
        return int(result["facts_total"])
    return 0
