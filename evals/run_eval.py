"""
Evaluation runner v2 for the HNS agent.

Runs all questions through the agent, records answers,
checks query type accuracy, and reports per-category breakdown.

Usage:
    python -m evals.run_eval
"""

import json
import time
from collections import defaultdict
from pathlib import Path

from agent.graph import build_graph

EVAL_PATH = Path("evals/evaluation_set.json")
RESULT_PATH = Path("evals/eval_results.json")


def run_evaluation():
    with open(EVAL_PATH, encoding="utf-8") as f:
        questions = json.load(f)

    total = len(questions)
    print(f"loaded {total} questions")
    print("building agent...\n")
    app = build_graph()

    results = []
    type_correct = 0
    category_stats = defaultdict(lambda: {"total": 0, "correct": 0})

    for q in questions:
        qid = q["id"]
        query = q["query"]
        expected_type = q["expected_type"]
        category = q.get("eval_category", "unknown")

        if not query.strip():
            print(f"[{qid}/{total}] (empty query) skip")
            results.append({
                "id": qid,
                "query": query,
                "expected_type": expected_type,
                "actual_type": "skip",
                "type_correct": False,
                "eval_category": category,
                "eval_strategy": q.get("eval_strategy", ""),
                "reference": q["reference"],
                "eval_criteria": q["eval_criteria"],
                "agent_answer": "empty query - skipped",
                "elapsed_sec": 0,
            })
            category_stats[category]["total"] += 1
            continue

        label = query[:40] + "..." if len(query) > 40 else query
        print(f"[{qid}/{total}] {label}", end=" ", flush=True)

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
                category_stats[category]["correct"] += 1
            category_stats[category]["total"] += 1

            results.append({
                "id": qid,
                "query": query,
                "expected_type": expected_type,
                "actual_type": actual_type,
                "type_correct": type_match,
                "eval_category": category,
                "eval_strategy": q.get("eval_strategy", ""),
                "reference": q["reference"],
                "eval_criteria": q["eval_criteria"],
                "agent_answer": answer,
                "elapsed_sec": elapsed,
            })

            status = "OK" if type_match else "MISMATCH"
            print(f"type={actual_type} [{status}] ({elapsed}s)")

        except Exception as e:
            elapsed = round(time.time() - start, 1)
            print(f"ERROR: {e}")
            results.append({
                "id": qid,
                "query": query,
                "expected_type": expected_type,
                "actual_type": "error",
                "type_correct": False,
                "eval_category": category,
                "eval_strategy": q.get("eval_strategy", ""),
                "reference": q["reference"],
                "eval_criteria": q["eval_criteria"],
                "agent_answer": str(e),
                "elapsed_sec": elapsed,
            })
            category_stats[category]["total"] += 1

    # Summary
    print(f"\n{'='*60}")
    print(f"OVERALL: {type_correct}/{total} ({round(type_correct/total*100, 1)}%)")

    avg_time = round(
        sum(r["elapsed_sec"] for r in results) / max(len(results), 1), 1
    )
    print(f"avg response time: {avg_time}s")

    # Per-category breakdown
    print(f"\n{'category':<25} {'accuracy':<15} {'correct/total'}")
    print("-" * 55)
    for cat in sorted(category_stats.keys()):
        s = category_stats[cat]
        pct = round(s["correct"] / max(s["total"], 1) * 100, 1)
        print(f"{cat:<25} {pct:>5}%         {s['correct']}/{s['total']}")

    # Mismatches summary
    mismatches = [r for r in results if not r["type_correct"] and r["actual_type"] != "skip"]
    if mismatches:
        print(f"\nMISMATCHES ({len(mismatches)}):")
        for r in mismatches:
            label = r["query"][:50]
            print(f"  #{r['id']} [{r['eval_category']}] expected={r['expected_type']} got={r['actual_type']} | {label}")

    # Save results
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nresults saved to {RESULT_PATH}")


if __name__ == "__main__":
    run_evaluation()
