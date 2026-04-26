"""
Index VoC documents into ChromaDB with Korean embeddings.

Reads from PostgreSQL, embeds with ko-sroberta-multitask,
stores in a persistent ChromaDB collection with metadata
for filtered retrieval.

Usage:
    python rag/index.py
"""

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from sqlalchemy import create_engine, text

DB_URL = "postgresql://hns_user:hns_local_dev_only@localhost:5433/hns_platform"
CHROMA_DIR = "./chroma_data"
COLLECTION_NAME = "hns_voc"
EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"


def load_documents(engine):
    """Fetch VoC documents from PostgreSQL."""
    query = text("""
        SELECT id, source, date, raw_text, signal_type,
               churn_score, positive_score, net_signal,
               competitor_mentioned
        FROM voc_documents
        WHERE raw_text IS NOT NULL
    """)
    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()
    return rows


def build_collection(rows, collection):
    """Add documents to ChromaDB collection in batches."""
    batch_size = 200
    total = len(rows)

    for i in range(0, total, batch_size):
        batch = rows[i:i + batch_size]

        ids = [f"doc_{row.id}" for row in batch]
        documents = [row.raw_text for row in batch]
        metadatas = [
            {
                "source": row.source or "",
                "date": row.date or "",
                "signal_type": row.signal_type or "",
                "churn_score": int(row.churn_score or 0),
                "positive_score": int(row.positive_score or 0),
                "net_signal": int(row.net_signal or 0),
                "competitor_mentioned": bool(row.competitor_mentioned),
            }
            for row in batch
        ]

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        loaded = min(i + batch_size, total)
        print(f"  indexed {loaded}/{total}")

    return total


def main():
    engine = create_engine(DB_URL)

    # Load from PostgreSQL
    rows = load_documents(engine)
    print(f"loaded {len(rows)} documents from PostgreSQL")

    # Initialize ChromaDB with Korean embedding model
    print(f"loading embedding model: {EMBEDDING_MODEL}")
    embed_fn = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )

    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Delete existing collection if re-indexing
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
        metadata={"description": "HNS VoC documents with causal signals"}
    )

    # Index documents
    total = build_collection(rows, collection)
    print(f"done: {total} documents in collection '{COLLECTION_NAME}'")


if __name__ == "__main__":
    main()