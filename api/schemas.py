"""Request and response models for the HNS agent API."""

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    query: str


class AnalyzeResponse(BaseModel):
    query: str
    query_type: str
    answer: str


class HealthResponse(BaseModel):
    status: str
    tables: int
    voc_count: int