"""RAG-агент: hybrid ranked pipeline + comparative mode."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List

from agent.tools import SearchTools
from services.analytics import find_knowledge_gaps, generate_recommendations, generate_literature_review


SYSTEM_PROMPT = """Ты — эксперт-аналитик R&D в горно-металлургической отрасли.
Отвечай на русском языке, структурированно и с указанием источников.

У тебя есть инструменты:
- hybrid_search — единый ranked pipeline (vector + graph + facts)
- compare_practices — сравнение отечественной и мировой практики
- explore_graph — обход Neo4j от сущности
- graph_stats — статистика базы знаний

Алгоритм:
1. Разбери вопрос на ключевые сущности.
2. Для сравнения RU vs мир — compare_practices; иначе hybrid_search.
3. Сформируй ответ: консенсус, противоречия, пробелы.
4. Укажи уверенность и количество источников.
"""


class KnowledgeAgent:
    """ReAct-агент с hybrid pipeline (без раздельных vector/graph вызовов)."""

    def __init__(self):
        self.tools = SearchTools()

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
                "Material": ["никел", "мед", "сульфат", "nickel", "copper"],
                "Process": ["электроэкстракц", "выщелачиван", "leaching"],
                "Equipment": ["ванн", "ячейк", "cell", "furnace"],
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

        if any(w in q for w in ["мг/л", "концентрац", "≤", "≥"]):
            plan.append({"tool": "_numeric_search", "args": {"query": question}})

        if any(w in q for w in ["пробел", "рекомендац", "gap"]):
            plan.append({"tool": "_recommendations", "args": {"topic": question}})

        return plan

    def _synthesize(self, question: str, tool_results: List[Dict]) -> str:
        sections = []
        ranked = []
        comparison = None

        for tr in tool_results:
            data = tr.get("result", {})
            if data.get("mode") == "domestic_vs_global":
                comparison = data
                continue
            if "results" in data:
                ranked.extend(data["results"])
            for item in data.get("ranked_results", []):
                ranked.append(item)
            if "neighbors" in data:
                for row in data["neighbors"]:
                    ranked.append({
                        "result_type": "graph_edge",
                        "title": f"{row.get('source', '?')} → {row.get('target', '?')}",
                        "snippet": str(row),
                        "score": 0.5,
                    })

        ranked.sort(key=lambda x: x.get("score", 0), reverse=True)

        if comparison:
            comp = comparison.get("comparison", {})
            sections.append("### Отечественная vs мировая практика\n\n")
            sections.append(comp.get("summary", "") + "\n\n")
            if comp.get("ru_only_topics"):
                sections.append(f"**Только RU:** {', '.join(comp['ru_only_topics'][:8])}\n\n")
            if comp.get("global_only_topics"):
                sections.append(f"**Только мировая:** {', '.join(comp['global_only_topics'][:8])}\n\n")
            if comp.get("shared_topics"):
                sections.append(f"**Общие темы:** {', '.join(comp['shared_topics'][:8])}\n\n")

        if ranked:
            sections.append("### Ranked результаты (hybrid pipeline)\n\n")
            for i, item in enumerate(ranked[:10], 1):
                rtype = item.get("result_type", "item")
                score = item.get("score", 0)
                title = item.get("title", "—")
                snippet = (item.get("snippet") or "")[:350]
                sources = ", ".join(item.get("sources", []))
                sections.append(
                    f"{i}. [{rtype}] **{title}** (score={score:.3f}, src={sources})\n"
                    f"   {snippet}\n\n"
                )

        lit = next((tr["result"] for tr in tool_results if tr.get("result", {}).get("summary")), None)
        if lit and lit.get("summary"):
            sections.append("\n### Литературный обзор\n")
            sections.append(lit["summary"] + "\n")

        rec = next((tr["result"] for tr in tool_results if "recommendations" in tr.get("result", {})), None)
        if rec:
            sections.append("\n### Рекомендации\n")
            for action in rec.get("recommendations", {}).get("suggested_actions", [])[:5]:
                sections.append(f"- {action}\n")

        if not sections:
            return (
                f"По запросу «{question}» данных не найдено. "
                "Загрузите документы через POST /api/v1/documents/upload."
            )

        confidence = min(0.95, 0.35 + 0.04 * len(ranked))
        header = (
            f"## Ответ\n\n**Вопрос:** {question}\n\n"
            f"**Уверенность:** {confidence:.0%} ({len(ranked)} ranked hits)\n\n"
        )
        return header + "".join(sections)

    def query(self, question: str, max_iterations: int = 5) -> Dict[str, Any]:
        plan = self._plan_tools(question)[:max_iterations]
        tool_calls = []
        sources = []
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
                result = self.tools.execute(step["tool"], step["args"])
            tool_calls.append({
                "tool": step["tool"],
                "args": step["args"],
                "result_preview": str(result)[:500],
            })
            tool_results.append({"result": result})
            sources.extend(result.get("results", result.get("ranked_results", [])))

        answer = self._synthesize(question, tool_results)

        return {
            "question": question,
            "answer": answer,
            "sources": sources[:20],
            "ranked_results": sources[:20],
            "tool_calls": tool_calls,
            "pipeline": "hybrid_vector_graph",
        }

    async def query_with_llm(self, question: str) -> Dict[str, Any]:
        base = self.query(question)
        try:
            from langchain_ollama import ChatOllama
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = ChatOllama(
                model=os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud"),
                base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=0.2,
            )
            context = json.dumps(base.get("ranked_results", base["sources"])[:12], ensure_ascii=False, indent=2)
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=f"Вопрос: {question}\n\nRanked контекст:\n{context}"),
            ]
            response = await llm.ainvoke(messages)
            base["answer"] = response.content
            base["llm_synthesized"] = True
        except Exception:
            base["llm_synthesized"] = False
        return base
