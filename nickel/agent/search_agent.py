"""RAG-агент: вопрос → поиск в БД → ответ пользователю."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from agent.tools import SearchTools
from services.analytics import find_knowledge_gaps, generate_recommendations, generate_literature_review
from services.fact_format import format_fact_answer, fact_display_fields


SYSTEM_PROMPT = """Ты — эксперт-аналитик R&D в горно-металлургической отрасли.
Отвечай на русском языке чётко и по делу, как в диалоге с коллегой.

Правила:
- Используй только факты из предоставленного контекста базы знаний.
- Если данных недостаточно — скажи об этом прямо.
- Указывай числовые значения и единицы измерения.
- В конце кратко упомяни источник (документ), если он есть в контексте.
- Не выводи JSON и не перечисляй score/ranked hits.
"""


class KnowledgeAgent:
    """Агент: планирует инструменты, ищет в SQLite/Qdrant/Neo4j, формирует ответ."""

    def __init__(self):
        self.tools = SearchTools()
        self._role: Optional[str] = None

    def _plan_tools(self, question: str) -> List[Dict[str, Any]]:
        q = question.lower()
        plan: List[Dict[str, Any]] = []

        comparative = any(
            w in q for w in [
                "отечествен", "зарубеж", "миров", "ru vs", "ru/en",
                "сравни практик", "domestic", "global practice", "vs мир",
            ]
        )
        if comparative:
            plan.append({"tool": "compare_practices", "args": {"query": question, "limit": 12}})
        else:
            args: Dict[str, Any] = {"query": question, "limit": 15}
            entity_types = {
                "Material": ["никел", "мед", "сульфат", "nickel", "copper", "cu"],
                "Process": ["электроэкстракц", "выщелачиван", "leaching", "smelting"],
                "Equipment": ["ванн", "ячейк", "cell", "furnace"],
                "Facility": ["cerro", "olympic", "завод", "mine"],
            }
            for etype, keywords in entity_types.items():
                if any(kw in q for kw in keywords):
                    args["entity_type"] = etype
                    break
            if any(w in q for w in ["патент", "patent"]):
                args["document_kind"] = "patent"
            elif any(w in q for w in ["гost", "гост", "норматив", "regulation"]):
                args["document_kind"] = "regulation"
            year_match = re.search(r"\b(19|20)\d{2}\b", question)
            if year_match:
                y = int(year_match.group())
                args["year_from"] = y - 2
                args["year_to"] = y + 2
            plan.append({"tool": "hybrid_search", "args": args})

        if any(w in q for w in ["связ", "граф", "relationship", "цепоч"]):
            entities = re.findall(r"[A-ZА-Я][a-zа-яё\-]+(?:\s[A-ZА-Я][a-zа-яё\-]+)?", question)
            if entities:
                plan.append({"tool": "explore_graph", "args": {"entity_name": entities[0], "depth": 2}})

        if any(w in q for w in ["обзор", "literature", "литобзор"]):
            plan.append({"tool": "_lit_review", "args": {"topic": question}})

        if any(w in q for w in ["мг/л", "концентрац", "≤", "≥", "<", ">"]):
            plan.append({"tool": "_numeric_search", "args": {"query": question}})

        if any(w in q for w in ["пробел", "рекомендац", "gap"]):
            plan.append({"tool": "_recommendations", "args": {"topic": question}})

        return plan

    def _collect_ranked(self, tool_results: List[Dict]) -> List[Dict[str, Any]]:
        ranked: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        for tr in tool_results:
            data = tr.get("result", {})
            if data.get("mode") == "domestic_vs_global":
                for side in (data.get("domestic"), data.get("global")):
                    if not side:
                        continue
                    for item in side.get("ranked_results", []):
                        key = (item.get("result_type", ""), str(item.get("id", "")))
                        if key not in seen:
                            seen.add(key)
                            ranked.append(item)
                continue
            for item in data.get("results", []) + data.get("ranked_results", []):
                key = (item.get("result_type", ""), str(item.get("id", "")))
                if key not in seen:
                    seen.add(key)
                    ranked.append(item)
            for row in data.get("neighbors", []):
                ranked.append({
                    "result_type": "graph_edge",
                    "id": f"{row.get('source')}:{row.get('relation')}:{row.get('target')}",
                    "title": f"{row.get('source', '?')} → {row.get('target', '?')}",
                    "snippet": f"Связь: {row.get('relation', 'related_to')}",
                    "score": 0.5,
                    "sources": ["graph"],
                })

        ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
        return ranked

    def _enrich_fact_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        if item.get("result_type") != "fact":
            return item
        raw = item.get("raw") or item
        if not item.get("answer") and raw.get("subject"):
            display = fact_display_fields(raw)
            item.setdefault("title", display["title"])
            item.setdefault("answer", display["answer"])
            item.setdefault("value", display["value"])
            item.setdefault("description", display["description"])
        return item

    def _synthesize(self, question: str, tool_results: List[Dict]) -> str:
        comparison = next(
            (tr["result"] for tr in tool_results if tr.get("result", {}).get("mode") == "domestic_vs_global"),
            None,
        )
        ranked = [self._enrich_fact_item(i) for i in self._collect_ranked(tool_results)]
        facts = [r for r in ranked if r.get("result_type") == "fact"]

        if comparison:
            comp = comparison.get("comparison", {})
            parts = [comp.get("summary") or "Сравнение отечественной и мировой практики:"]
            if comp.get("shared_topics"):
                parts.append(f"Общие темы: {', '.join(comp['shared_topics'][:6])}.")
            if comp.get("ru_only_topics"):
                parts.append(f"Только в RU-практике: {', '.join(comp['ru_only_topics'][:5])}.")
            if comp.get("global_only_topics"):
                parts.append(f"Только в мировой практике: {', '.join(comp['global_only_topics'][:5])}.")
            if facts:
                parts.append("")
                parts.append(self._format_facts_answer(facts[:3]))
            return "\n".join(p for p in parts if p)

        lit = next((tr["result"] for tr in tool_results if tr.get("result", {}).get("summary")), None)
        if lit and lit.get("summary") and not facts:
            return lit["summary"]

        rec = next((tr["result"] for tr in tool_results if "recommendations" in tr.get("result", {})), None)
        if rec and not facts:
            actions = rec.get("recommendations", {}).get("suggested_actions", [])[:5]
            if actions:
                return "Рекомендации:\n" + "\n".join(f"• {a}" for a in actions)

        numeric = next((tr["result"] for tr in tool_results if tr.get("result", {}).get("results")), None)
        if not facts and numeric and numeric.get("results"):
            lines = []
            for r in numeric["results"][:5]:
                props = r.get("properties") or r.get("matched_constraint") or {}
                val = props.get("value") or props.get("description")
                if val:
                    lines.append(f"• {r.get('subject')} → {r.get('object')}: {val}")
            if lines:
                return "По числовым критериям:\n" + "\n".join(lines)

        if not facts:
            chunks = [r for r in ranked if r.get("result_type") == "chunk"]
            if chunks:
                top = chunks[0]
                snippet = (top.get("snippet") or "")[:500]
                return f"Нашёл фрагмент документа «{top.get('title', 'документ')}»:\n\n{snippet}"

            return (
                "В базе знаний пока нет данных по этому вопросу. "
                "Попробуйте переформулировать запрос или загрузите документы в разделе «Импорт»."
            )

        facts = self._rerank_facts_for_question(facts, question)
        return self._format_facts_answer(facts)

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
                if "year" in obj or "tonnes" in val or "treated" in obj:
                    score += 5
            return score

        return sorted(facts, key=relevance, reverse=True)

    def _format_facts_answer(self, facts: List[Dict[str, Any]]) -> str:
        if len(facts) == 1:
            f = facts[0]
            answer = f.get("answer") or f.get("snippet") or ""
            src = (f.get("metadata") or {}).get("source_document") or (f.get("raw") or {}).get("source_document")
            if src and src not in answer:
                answer += f"\n\nИсточник: {src}."
            return answer.strip()

        top = facts[0]
        top_answer = top.get("answer") or top.get("snippet") or ""
        rest = facts[1:5]
        if top.get("value") and len(rest) <= 2:
            lines = [top_answer]
            for f in rest:
                lines.append(f"• {f.get('answer') or f.get('snippet')}")
            return "\n\n".join(lines)

        lines = ["Нашёл в базе знаний:"]
        for i, f in enumerate(facts[:6], 1):
            answer = f.get("answer") or f.get("snippet") or f.get("title", "")
            src = (f.get("metadata") or {}).get("source_document") or (f.get("raw") or {}).get("source_document")
            line = f"{i}. {answer}"
            if src:
                line += f" ({src})"
            lines.append(line)
        return "\n".join(lines)

    def _context_for_llm(self, ranked: List[Dict[str, Any]]) -> str:
        lines = []
        for i, item in enumerate(ranked[:12], 1):
            if item.get("result_type") == "fact":
                raw = item.get("raw") or item
                display = fact_display_fields(raw) if raw.get("subject") else item
                src = (item.get("metadata") or {}).get("source_document") or raw.get("source_document", "")
                lines.append(
                    f"{i}. {display.get('title', item.get('title'))}\n"
                    f"   Ответ: {display.get('answer') or item.get('answer')}\n"
                    f"   Источник: {src or '—'}"
                )
            else:
                lines.append(f"{i}. {item.get('title', '—')}: {item.get('snippet', '')[:200]}")
        return "\n".join(lines)

    def query(
        self,
        question: str,
        max_iterations: int = 5,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._role = role
        plan = self._plan_tools(question)[:max_iterations]
        tool_calls = []
        tool_results = []

        for step in plan:
            if step["tool"].startswith("_"):
                if step["tool"] == "_lit_review":
                    result = generate_literature_review(step["args"]["topic"])
                elif step["tool"] == "_recommendations":
                    result = {
                        "recommendations": generate_recommendations(step["args"]["topic"]),
                        "gaps": find_knowledge_gaps(),
                    }
                elif step["tool"] == "_numeric_search":
                    from services.numeric_query import search_by_numeric_query
                    result = search_by_numeric_query(step["args"]["query"])
                else:
                    result = {}
            else:
                args = dict(step["args"])
                if role:
                    args["role"] = role
                result = self.tools.execute(step["tool"], args)
            tool_calls.append({
                "tool": step["tool"],
                "args": step["args"],
                "result_count": len(result.get("ranked_results", result.get("results", []))),
            })
            tool_results.append({"result": result})

        ranked = [self._enrich_fact_item(i) for i in self._collect_ranked(tool_results)]
        answer = self._synthesize(question, tool_results)
        confidence = min(0.95, 0.35 + 0.05 * len(ranked))

        return {
            "question": question,
            "answer": answer,
            "sources": ranked[:15],
            "ranked_results": ranked[:15],
            "tool_calls": tool_calls,
            "pipeline": "agent_sqlite",
            "confidence": confidence,
            "llm_synthesized": False,
        }

    async def query_with_llm(self, question: str, role: Optional[str] = None) -> Dict[str, Any]:
        base = self.query(question, role=role)
        ranked = base.get("ranked_results", [])
        context = self._context_for_llm(ranked)

        try:
            from langchain_ollama import ChatOllama
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = ChatOllama(
                model=os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud"),
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=0.2,
            )
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"Вопрос пользователя: {question}\n\nДанные из базы знаний:\n{context}"),
            ]
            response = await llm.ainvoke(messages)
            base["answer"] = response.content
            base["llm_synthesized"] = True
        except Exception:
            base["llm_synthesized"] = False
        return base
