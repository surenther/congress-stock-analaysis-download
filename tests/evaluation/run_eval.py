#!/usr/bin/env python3
"""
CLI Evaluation Runner for Congressional RAG.

Usage:
    # Run all 200+ benchmark items in reference/offline mode:
    python -m tests.evaluation.run_eval

    # Run live against the RAG microservice (requires running containers):
    python -m tests.evaluation.run_eval --live --limit 20

    # Save Markdown report to a file:
    python -m tests.evaluation.run_eval --output rag_eval_report.md
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

from tests.evaluation.evaluator import (
    AggregateEvaluationReport,
    ItemEvaluationResult,
    RagEvaluator,
)


async def run_live_query(
    client: httpx.AsyncClient,
    rag_base_url: str,
    token: str,
    query: str,
    chamber: str,
    top_k: int = 5
) -> Dict[str, Any]:
    """Execute live query against RAG service."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "prompt": query,
        "top_k": top_k,
    }
    if chamber and chamber != "Combined":
        payload["filters"] = {"chamber": chamber}

    resp = await client.post(f"{rag_base_url}/api/v1/rag/query", json=payload, headers=headers, timeout=60.0)
    if resp.status_code == 200:
        return resp.json()
    elif resp.status_code == 403:
        return {"status": "forbidden", "answer": "CHAMBER_SCOPE_VIOLATION: Access denied", "sources": []}
    else:
        return {"status": "error", "answer": f"Error {resp.status_code}: {resp.text}", "sources": []}


def main():
    parser = argparse.ArgumentParser(description="Evaluate Congressional RAG against 200+ Benchmark Dataset")
    parser.add_argument("--live", action="store_true", help="Run against live running RAG microservice")
    parser.add_argument("--rag-url", default="http://localhost:8516", help="RAG service base URL")
    parser.add_argument("--token", default=os.getenv("TEST_ADMIN_TOKEN", ""), help="JWT Bearer token for live queries")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of evaluated queries")
    parser.add_argument("--output", type=str, default=None, help="Output markdown report path")
    args = parser.parse_args()

    evaluator = RagEvaluator()
    items = evaluator.items
    if args.limit:
        items = items[:args.limit]

    print(f"\n========================================================")
    print(f" Loaded {len(items)} Congressional RAG benchmark items")
    print(f" Mode: {'LIVE HTTP' if args.live else 'OFFLINE REFERENCE'}")
    print(f"========================================================\n")

    results: List[ItemEvaluationResult] = []

    if args.live:
        if not args.token:
            print("ERROR: --live mode requires --token or TEST_ADMIN_TOKEN env variable.")
            sys.exit(1)

        async def run_all():
            async with httpx.AsyncClient() as client:
                for idx, item in enumerate(items, start=1):
                    print(f"[{idx}/{len(items)}] Evaluating {item['id']}: {item['query'][:55]}...")
                    live_res = await run_live_query(
                        client, args.rag_url, args.token, item["query"], item.get("chamber", "Combined")
                    )
                    retrieved_chunks = [s.get("chunk_text", "") for s in live_res.get("sources", [])]
                    answer = live_res.get("answer", "")
                    res = evaluator.evaluate_item(item, retrieved_chunks, answer)
                    results.append(res)

        asyncio.run(run_all())
    else:
        # Reference offline validation: tests the golden dataset itself
        for item in items:
            # Simulate high-quality retrieval for ground-truth chunks
            retrieved = list(item.get("ground_truth_chunks", []))
            answer = item.get("reference_answer", "")
            res = evaluator.evaluate_item(item, retrieved, answer)
            results.append(res)

    report = evaluator.aggregate_results(results)
    markdown_report = report.to_markdown()

    print("\n" + markdown_report + "\n")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(markdown_report, encoding="utf-8")
        print(f"Saved evaluation report to {out_path.resolve()}")


if __name__ == "__main__":
    main()
