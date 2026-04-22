"""CLI entry point for the HNS agent."""

import sys

from agent.graph import build_graph


def main():
    if len(sys.argv) < 2:
        print("usage: python -m agent.run \"your question here\"")
        return

    query = " ".join(sys.argv[1:])

    print(f"query: {query}")
    print("building agent...")

    app = build_graph()

    result = app.invoke({
        "query": query,
        "query_type": "",
        "retrieved_docs": "",
        "sql_result": "",
        "final_answer": "",
    })

    print(f"\ntype: {result['query_type']}")
    print(f"\n{'='*60}")
    print(result["final_answer"])


if __name__ == "__main__":
    main()