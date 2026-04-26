"""FastAPI application wrapping the HNS agent."""
import os

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text

from agent.graph import build_graph
from api.schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse

DB_URL = os.getenv("DATABASE_URL", "postgresql://hns_user:hns_local_dev_only@localhost:5433/hns_platform")

app = FastAPI(
    title="HNS Consumer Signal Agent API",
    description="LangGraph agent for H&S consumer signal analysis",
    version="0.1.0",
)

agent = None


@app.on_event("startup")
def startup():
    """Build agent graph once on startup."""
    global agent
    agent = build_graph()


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    """Run the agent on a user query and return the analysis."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")

    result = agent.invoke({
        "query": req.query,
        "query_type": "",
        "retrieved_docs": "",
        "sql_result": "",
        "final_answer": "",
    })

    return AnalyzeResponse(
        query=req.query,
        query_type=result["query_type"],
        answer=result["final_answer"],
    )


@app.get("/health", response_model=HealthResponse)
def health():
    """Health check — verifies DB connection and returns basic stats."""
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
            ).scalar()
            voc_count = conn.execute(
                text("SELECT COUNT(*) FROM voc_documents")
            ).scalar()
        return HealthResponse(status="ok", tables=tables, voc_count=voc_count)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))