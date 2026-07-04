"""Pydantic-модели API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobResponse(BaseModel):
    id: str
    filename: str
    status: str
    stage: Optional[str] = None
    progress_current: int = 0
    progress_total: int = 0
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    job_type: Optional[str] = "single"
    batch_id: Optional[str] = None
    folder_path: Optional[str] = None
    created_by: Optional[str] = None
    files_total: int = 0
    files_done: int = 0
    files_failed: int = 0
    created_at: str
    updated_at: str


class JobLogEntry(BaseModel):
    id: int
    job_id: str
    level: str
    stage: Optional[str] = None
    message: str
    created_at: str


class IngestFolderRequest(BaseModel):
    folder_path: str = Field(..., min_length=1, description="Путь на сервере, напр. data/inbox/batch1")
    extractor: Optional[str] = Field(default=None, description="ollama | yandex | auto (только mode=full)")
    recursive: bool = False
    mode: str = Field(
        default="full",
        description="full — LLM-пайплайн; import_pairs — пары doc+json по имени",
    )


class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Запрос на естественном языке")
    limit: int = Field(default=10, ge=1, le=50)
    entity_type: Optional[str] = None
    job_id: Optional[str] = None


class SemanticSearchResponse(BaseModel):
    query: str
    chunks: List[Dict[str, Any]]
    entities: List[Dict[str, Any]]


class GraphQueryRequest(BaseModel):
    entity_name: str
    depth: int = Field(default=2, ge=1, le=4)


class AgentQueryRequest(BaseModel):
    question: str = Field(..., min_length=5)
    max_iterations: int = Field(default=5, ge=1, le=10)


class AgentQueryResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    ranked_results: Optional[List[Dict[str, Any]]] = None
    pipeline: Optional[str] = None


class GraphViewResponse(BaseModel):
    nodes: List[Dict[str, str]]
    edges: List[Dict[str, str]]
    center: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    neo4j: Optional[str] = None
    qdrant: Optional[str] = None
    components: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None
