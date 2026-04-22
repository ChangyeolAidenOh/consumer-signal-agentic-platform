"""
Search VoC documents in ChromaDB.

Interactive CLI for testing retrieval quality before
building the full Agent pipeline.

Usage:
    python rag/search.py "안티트로 비교 후기"
    python rag/search.py "두피 가려움 효과 없음"
    python rag/search.py --filter-signal 이탈위험 "샴푸 추천"
"""

import argparse

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


CHROMA_DIR = "./chroma_data"
COLLECTION_NAME = "hns_voc"
EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"


def search(query: str, n_results: int = 5, signal_filter: str = None):
    """Query ChromaDB and return ranked results with metadata."""
    embed_fn = SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
    )

    # Optional metadata filter
    where = None
    if signal_filter:
        where = {"signal_type": signal_filter}

    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    return results


def display(results, query: str):
    """Print search results."""
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    print(f"\nquery: {query}")
    print(f"results: {len(docs)}")
    print("-" * 70)

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
        preview = doc[:120].replace("\n", " ")
        if len(doc) > 120:
            preview += "..."

        print(f"\n[{i+1}] distance: {dist:.4f}")
        print(f"    source: {meta['source']}  |  date: {meta['date']}  |  signal: {meta['signal_type']}")
        print(f"    competitor: {meta['competitor_mentioned']}  |  churn: {meta['churn_score']}  |  positive: {meta['positive_score']}")
        print(f"    text: {preview}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str)
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--filter-signal", type=str, default=None,
                        help="filter by signal_type (e.g. 이탈위험, 긍정, 중립)")
    args = parser.parse_args()

    results = search(args.query, n_results=args.n, signal_filter=args.filter_signal)
    display(results, args.query)


if __name__ == "__main__":
    main()