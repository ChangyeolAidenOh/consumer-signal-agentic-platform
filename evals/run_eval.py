"""
Evaluation runner for the HNS agent.

Runs all questions from evaluation_set.json through the agent,
records answers, and checks query type classification accuracy.

Usage:
    python -m evals.run_eval
"""

import json
import time
from pathlib import Path

from agent.graph import build_graph


EVAL_PATH = Path("evals/evaluation_set.json")
RESULT_PATH = Path("evals/eval_results.json")


def run_evaluation():
    with open(EVAL_PATH) as f:
        questions = json.load(f)

    print(f"loaded {len(questions)} questions")
    print("building agent...\n")
    app = build_graph()

    results = []
    type_correct = 0
    type_total = 0

    for q in questions:
        qid = q["id"]
        query = q["query"]
        expected_type = q["expected_type"]

        print(f"[{qid}/50] {query[:40]}...", end=" ", flush=True)

        start = time.time()
        try:
            output = app.invoke({
                "query": query,
                "query_type": "",
                "retrieved_docs": "",
                "sql_result": "",
                "final_answer": "",
            })
            elapsed = round(time.time() - start, 1)

            actual_type = output["query_type"]
            answer = output["final_answer"]

            type_match = actual_type == expected_type
            if type_match:
                type_correct += 1
            type_total += 1

            results.append({
                "id": qid,
                "query": query,
                "expected_type": expected_type,
                "actual_type": actual_type,
                "type_correct": type_match,
                "reference": q["reference"],
                "eval_criteria": q["eval_criteria"],
                "agent_answer": answer,
                "elapsed_sec": elapsed,
            })

            status = "OK" if type_match else "MISMATCH"
            print(f"type={actual_type} [{status}] ({elapsed}s)")

        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "id": qid,
                "query": query,
                "expected_type": expected_type,
                "actual_type": "error",
                "type_correct": False,
                "reference": q["reference"],
                "eval_criteria": q["eval_criteria"],
                "agent_answer": str(e),
                "elapsed_sec": 0,
            })

    # Summary
    print(f"\n{'='*60}")
    print(f"query type accuracy: {type_correct}/{type_total} ({round(type_correct/type_total*100, 1)}%)")

    avg_time = round(sum(r["elapsed_sec"] for r in results) / len(results), 1)
    print(f"average response time: {avg_time}s")

    # Save results
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"results saved to {RESULT_PATH}")


if __name__ == "__main__":
    run_evaluation()
