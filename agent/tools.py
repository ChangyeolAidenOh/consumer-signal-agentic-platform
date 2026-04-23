"""Tools for the agent: VoC search (ChromaDB) and SQL query (PostgreSQL)."""

import os
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from sqlalchemy import create_engine, text


DB_URL = os.getenv("DATABASE_URL", "postgresql://hns_user:hns_local_dev_only@localhost:5433/hns_platform")
CHROMA_DIR = "./chroma_data"
COLLECTION_NAME = "hns_voc"
EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"

_embed_fn = None
_chroma_collection = None
_engine = None


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
    return _embed_fn


def _get_collection():
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        _chroma_collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=_get_embed_fn(),
        )
    return _chroma_collection


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL)
    return _engine


def search_voc(query: str, n_results: int = 5, signal_filter: str = None) -> str:
    """Search VoC documents by semantic similarity. Returns formatted text."""
    collection = _get_collection()

    where = None
    if signal_filter:
        where = {"signal_type": signal_filter}

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    docs = results["documents"][0]
    metas = results["metadatas"][0]

    if not docs:
        return "no relevant VoC documents found."

    output = []
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        preview = doc[:300]
        output.append(
            f"[{i+1}] source={meta['source']} | "
            f"signal={meta['signal_type']} | "
            f"competitor={meta['competitor_mentioned']}\n"
            f"{preview}"
        )
    return "\n\n".join(output)


def query_trend(sql: str) -> str:
    """Run a read-only SQL query against PostgreSQL. Returns formatted text."""
    engine = _get_engine()

    # Safety: only allow SELECT
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return "error: only SELECT queries allowed."

    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())

        if not rows:
            return "query returned no results."

        # Format as simple table
        header = " | ".join(columns)
        lines = [header, "-" * len(header)]
        for row in rows[:20]:  # limit output size
            lines.append(" | ".join(str(v) for v in row))

        if len(rows) > 20:
            lines.append(f"... ({len(rows)} total rows)")

        return "\n".join(lines)

    except Exception as e:
        return f"SQL error: {e}"


# Pre-built queries for common questions
CANNED_QUERIES = {
    "segment_summary": """
        SELECT s.segment, s.n_docs, s.churn_rate, s.competitor_rate,
               s.switching_probability AS p_switch,
               i.risk_level, i.intervention_timing, i.recommended_action
        FROM segment_summary s
        JOIN switching_implications i ON s.segment = i.segment
        ORDER BY s.switching_probability DESC
    """,
    "antitro_timeline": """
        SELECT date, hns_core, antitro, ratio,
               CASE WHEN ratio >= 1.0 THEN 'ANTITRO_LEADS'
                    ELSE 'HNS_LEADS'
               END AS status
        FROM (
            SELECT date,
                   "헤드앤숄더샴푸" AS hns_core,
                   "안티트로샴푸" AS antitro,
                   CASE WHEN "헤드앤숄더샴푸" > 0
                        THEN ROUND(("안티트로샴푸" / "헤드앤숄더샴푸")::NUMERIC, 3)
                   END AS ratio
            FROM trend_monthly
            WHERE "안티트로샴푸" > 0
        ) sub
        ORDER BY date
    """,
    "churn_by_source": """
        SELECT source, signal_type, COUNT(*) AS cnt
        FROM voc_documents
        GROUP BY source, signal_type
        ORDER BY source, signal_type
    """,
    "monthly_churn": """
        SELECT month, total, churn, positive,
               ROUND(churn_rate::NUMERIC * 100, 1) AS churn_pct
        FROM temporal_signals
        ORDER BY month DESC
        LIMIT 12
    """,
    "churn_reasons": """
        SELECT signal_type, COUNT(*) AS cnt,
               ROUND(COUNT(*)::NUMERIC / (SELECT COUNT(*) FROM voc_documents) * 100, 1) AS pct
        FROM voc_documents
        WHERE signal_type = '이탈위험'
        GROUP BY signal_type
        UNION ALL
        SELECT '  churn_signals breakdown' AS signal_type, NULL, NULL
        UNION ALL
        SELECT unnest(string_to_array(
                   REPLACE(REPLACE(REPLACE(churn_signals, '[', ''), ']', ''), '''', ''),
                   ', '
               )) AS signal_type,
               COUNT(*) AS cnt, NULL AS pct
        FROM voc_documents
        WHERE churn_score > 0 AND churn_signals != '[]'
        GROUP BY 1
        ORDER BY cnt DESC NULLS FIRST
        """,
    "lda_coherence": """
        SELECT source, mode, optimal_k, coherence, keywords
        FROM lda_topics
        ORDER BY coherence DESC
        LIMIT 10
    """,
    "bertopic_summary": """
        SELECT bertopic_id, COUNT(*) AS doc_count
        FROM bertopic_documents
        GROUP BY bertopic_id
        ORDER BY bertopic_id
    """,
    "consensus_signals": """
        SELECT lda_topic, bertopic_id, overlap_keywords, bertopic_count, confidence
        FROM lda_bertopic_consensus
        ORDER BY bertopic_count DESC
    """,
}


def query_canned(query_name: str) -> str:
    """Run a pre-built SQL query by name."""
    if query_name not in CANNED_QUERIES:
        available = ", ".join(CANNED_QUERIES.keys())
        return f"unknown query. available: {available}"
    return query_trend(CANNED_QUERIES[query_name])