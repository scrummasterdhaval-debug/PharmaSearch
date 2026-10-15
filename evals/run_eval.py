"""Score the search index against hand-graded relevance judgements.

This is the gate that makes fast, loosely-supervised iteration on ranking safe:
a change either moves these numbers up or it does not ship.

    python -m evals.run_eval            # report
    python -m evals.run_eval --check    # non-zero exit if below threshold
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.corpus import load_corpus
from app.index import SearchIndex

GOLDEN = Path(__file__).parent / "golden.json"

# Thresholds are a ratchet, set at the measured baseline. Raise them as
# relevance improves; never lower them to make a red build go green.
THRESHOLDS = {
    "regulatory_language": {"precision@1": 1.00, "recall@3": 1.00, "mrr": 1.00},
    # Ratcheted up after synonym expansion landed (was 0.50 / 0.67 / 0.61).
    "plain_language": {"precision@1": 0.58, "recall@3": 0.87, "mrr": 0.75},
}


def evaluate(index: SearchIndex, queries: list[dict]) -> dict:
    hits_at_1 = 0
    recall_at_3_total = 0.0
    reciprocal_rank_total = 0.0
    per_query = []

    for case in queries:
        relevant = set(case["relevant"])
        ranked = [hit.document.id for hit in index.search(case["q"], limit=10)]

        top1 = bool(ranked) and ranked[0] in relevant
        hits_at_1 += int(top1)

        found_in_3 = len(relevant & set(ranked[:3]))
        recall_at_3 = found_in_3 / len(relevant)
        recall_at_3_total += recall_at_3

        rank_of_first = next((i + 1 for i, doc in enumerate(ranked) if doc in relevant), None)
        reciprocal_rank = 1 / rank_of_first if rank_of_first else 0.0
        reciprocal_rank_total += reciprocal_rank

        per_query.append(
            {
                "query": case["q"],
                "top1": top1,
                "recall@3": round(recall_at_3, 3),
                "rank_of_first_relevant": rank_of_first,
                "returned": ranked[:3],
            }
        )

    n = len(queries)
    return {
        "queries": n,
        "precision@1": round(hits_at_1 / n, 4),
        "recall@3": round(recall_at_3_total / n, 4),
        "mrr": round(reciprocal_rank_total / n, 4),
        "per_query": per_query,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit non-zero if below threshold")
    parser.add_argument("--verbose", action="store_true", help="show failing queries")
    args = parser.parse_args()

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    index = SearchIndex(load_corpus())

    failed_gate = False
    for tier, queries in golden["tiers"].items():
        report = evaluate(index, queries)
        limits = THRESHOLDS[tier]
        print(f"\n{tier}  ({report['queries']} queries)")
        for metric in ("precision@1", "recall@3", "mrr"):
            value, floor = report[metric], limits[metric]
            status = "ok" if value >= floor else "BELOW"
            print(f"  {metric:<12} {value:.3f}  (floor {floor:.2f}) {status}")
            if value < floor:
                failed_gate = True

        failures = [q for q in report["per_query"] if not q["top1"]]
        if failures and (args.verbose or args.check):
            for q in failures:
                print(f"    miss: {q['query']!r}")
                print(f"          first relevant at rank {q['rank_of_first_relevant']}, got {q['returned']}")

    if args.check:
        print("\nFAIL: relevance below threshold" if failed_gate else "\nPASS")
        return 1 if failed_gate else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
