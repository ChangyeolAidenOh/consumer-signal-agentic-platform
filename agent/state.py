"""Agent state definition for LangGraph."""

from typing import TypedDict


class AgentState(TypedDict):
    query: str
    query_type: str          # "voc" / "trend" / "switching" / "mixed" / "methodology"
    retrieved_docs: str      # retrieved VoC text from ChromaDB
    sql_result: str          # query result from PostgreSQL
    final_answer: str