"""FastAPI application wrapping the HNS agent."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, text

from agent.config import LLM_MODEL, LLM_PROVIDER
from agent.graph import build_graph
from agent.tools import warm_up
from api.schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse

DB_URL = os.getenv("DATABASE_URL", "postgresql://hns_user:hns_local_dev_only@localhost:5437/hns_platform")

agent = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Build the agent graph and warm the retriever once per process."""
    global agent
    print(f"llm provider={LLM_PROVIDER} model={LLM_MODEL}")
    agent = build_graph()
    warm_up()
    yield


app = FastAPI(
    title="HNS Consumer Signal Agent API",
    description="LangGraph agent for H&S consumer signal analysis",
    version="0.1.0",
    lifespan=lifespan,
)


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    """Run the agent on a user query and return the analysis."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty")
    if agent is None:
        raise HTTPException(status_code=503, detail="agent is not ready")

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
    """Health check: verifies the DB connection and reports basic stats and the LLM in use."""
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            tables = conn.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'")
            ).scalar()
            voc_count = conn.execute(
                text("SELECT COUNT(*) FROM voc_documents")
            ).scalar()
        return HealthResponse(
            status="ok",
            tables=tables,
            voc_count=voc_count,
            llm_provider=LLM_PROVIDER,
            llm_model=LLM_MODEL,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/", include_in_schema=False)
def root():
    """Redirect the bare service URL to the interactive API docs."""
    return RedirectResponse(url="/docs")
