#!/usr/bin/env python3
"""
Test file and reference implementation for Congressional RAG Evaluations.

Covers:
1. Exact mathematical unit tests for Information Retrieval (IR) chunk metrics:
   - MRR (Mean Reciprocal Rank)
   - nDCG@K (Normalized Discounted Cumulative Gain at K)
   - Hit Rate@K (Recall@K)
   - Precision@K
2. Generation & Answer Evaluation metrics:
   - Faithfulness & Hallucination detection
   - Factual Entity Recall
   - Token Overlap F1 Score
   - Negative Refusal Accuracy
   - Chamber-Based Access Control (CBAC) Leakage Detection
3. Benchmark Dataset Integrity:
   - Validates that the gold dataset contains at least 200 unique test queries.
   - Validates schema consistency, category distributions, and difficulty ratings.
4. Reference Test Execution:
   - Executes offline baseline evaluation across all 200+ benchmark items.
   - Optional live integration test against running RAG microservice.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Set

import pytest

try:
    from tests.evaluation.evaluator import (
        RagEvaluator,
        calculate_fact_recall,
        calculate_faithfulness,
        calculate_token_f1,
        check_cbac_leakage,
        check_refusal_patterns,
        dcg_at_k,
        hit_rate_at_k,
        ndcg_at_k,
        precision_at_k,
        reciprocal_rank,
    )
except ImportError:
    from evaluation.evaluator import (
        RagEvaluator,
        calculate_fact_recall,
        calculate_faithfulness,
        calculate_token_f1,
        check_cbac_leakage,
        check_refusal_patterns,
        dcg_at_k,
        hit_rate_at_k,
        ndcg_at_k,
        precision_at_k,
        reciprocal_rank,
    )

pytestmark = pytest.mark.contract

# Path to the 200+ gold benchmark dataset
DATASET_PATH = Path(__file__).resolve().parent / "rag_benchmark_dataset.json"


# ==============================================================================
# 1. MATHEMATICAL UNIT TESTS: RETRIEVAL / CHUNK METRICS
# ==============================================================================

def test_reciprocal_rank_calculation():
    """Validates RR = 1 / rank of first relevant item."""
    relevant: Set[str] = {"chunk_target"}

    # Rank 1 -> 1 / 1 = 1.0
    assert reciprocal_rank(["chunk_target", "chunk_b", "chunk_c"], relevant) == 1.0

    # Rank 2 -> 1 / 2 = 0.5
    assert reciprocal_rank(["chunk_a", "chunk_target", "chunk_c"], relevant) == 0.5

    # Rank 3 -> 1 / 3 = 0.3333...
    assert math.isclose(
        reciprocal_rank(["chunk_a", "chunk_b", "chunk_target"], relevant),
        1.0 / 3.0,
        rel_tol=1e-4
    )

    # Not found -> 0.0
    assert reciprocal_rank(["chunk_a", "chunk_b", "chunk_c"], relevant) == 0.0

    # Empty inputs -> 0.0
    assert reciprocal_rank([], relevant) == 0.0
    assert reciprocal_rank(["chunk_a"], set()) == 0.0


def test_dcg_and_ndcg_calculation():
    """
    Validates DCG@K and nDCG@K against textbook formulations.
    Formula: DCG@K = sum_{i=1}^K (2^{rel_i} - 1) / log2(i + 1)
    """
    # Manual check:
    # rel = [2.0, 1.0, 0.0]
    # i=1: (2^2 - 1) / log2(2) = 3.0 / 1.0 = 3.0
    # i=2: (2^1 - 1) / log2(3) = 1.0 / 1.5849625 = 0.6309297
    # i=3: (2^0 - 1) / log2(4) = 0.0 / 2.0 = 0.0
    # Expected DCG@3 = 3.6309297
    expected_dcg = 3.0 + (1.0 / math.log2(3))
    computed_dcg = dcg_at_k([2.0, 1.0, 0.0], k=3)
    assert math.isclose(computed_dcg, expected_dcg, rel_tol=1e-5)

    # When retrieved order equals the ideal order, nDCG must be exactly 1.0
    relevance_map = {"chunk_high": 2.0, "chunk_med": 1.0}
    perfect_retrieval = ["chunk_high", "chunk_med", "chunk_none"]
    assert ndcg_at_k(perfect_retrieval, relevance_map, k=3) == 1.0

    # Sub-optimal ordering: chunk_med retrieved before chunk_high
    suboptimal = ["chunk_med", "chunk_high", "chunk_none"]
    ndcg_sub = ndcg_at_k(suboptimal, relevance_map, k=3)
    assert 0.0 < ndcg_sub < 1.0


def test_hit_rate_and_precision_calculation():
    """Validates Hit Rate (Recall@K) and Precision@K."""
    relevant = {"chunk_alpha", "chunk_beta"}
    retrieved = ["chunk_alpha", "chunk_x", "chunk_beta", "chunk_y", "chunk_z"]

    # Hit Rate@1: chunk_alpha is at rank 1 -> Hit Rate = 1.0
    assert hit_rate_at_k(retrieved, relevant, k=1) == 1.0

    # Hit Rate@5 with irrelevant list -> 0.0
    assert hit_rate_at_k(["c1", "c2", "c3"], relevant, k=5) == 0.0

    # Precision@3: 2 hits out of 3 evaluated = 2/3
    assert math.isclose(precision_at_k(retrieved, relevant, k=3), 2.0 / 3.0, rel_tol=1e-4)


# ==============================================================================
# 2. GENERATION & ANSWER EVALUATION UNIT TESTS
# ==============================================================================

def test_faithfulness_and_hallucination_detection():
    """
    Validates that claims not present in retrieved context are flagged as ungrounded.
    """
    context = [
        "Filer: Nancy Pelosi (House) | Item: NVIDIA Corporation | Ticker: NVDA | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000"
    ]

    # Grounded answer: all figures and tickers exist in context
    grounded_answer = "Representative Nancy Pelosi purchased NVDA stock in the $1,000,001 - $5,000,000 range."
    assert calculate_faithfulness(grounded_answer, context) == 1.0

    # Hallucinated answer: claims TSLA, MSFT, and $50,000,000 which are NOT in context
    hallucinated_answer = "Representative Nancy Pelosi bought TSLA and MSFT for $50,000,000 on March 1, 2025."
    faith_score = calculate_faithfulness(hallucinated_answer, context)
    assert faith_score < 0.5  # Heavy penalty for hallucinated tickers and amounts


def test_fact_recall_and_token_f1():
    """Validates factual keyword coverage and SQuAD token F1 score."""
    expected_facts = ["Nancy Pelosi", "NVIDIA", "NVDA", "Purchase", "$1,000,001 - $5,000,000"]
    candidate = "Nancy Pelosi reported a purchase of NVIDIA (NVDA) stock in the $1,000,001 - $5,000,000 range."

    # 100% of the critical facts are present in candidate
    assert calculate_fact_recall(candidate, expected_facts) == 1.0

    # Token F1 against exact reference
    prec, rec, f1 = calculate_token_f1(candidate, candidate)
    assert f1 == 1.0


def test_cbac_leakage_detection():
    """Validates that cross-chamber data in retrieved chunks triggers security violation."""
    house_chunks = ["Filer: Nancy Pelosi (House) | Item: NVIDIA | Ticker: NVDA"]
    senate_chunks = ["Filer: Tommy Tuberville (Senate) | Item: Lockheed Martin | Ticker: LMT"]

    # House user with House chunks: OK
    assert check_cbac_leakage(house_chunks, "House") is True

    # House user receiving Senate chunks: LEAK DETECTED
    assert check_cbac_leakage(senate_chunks, "House") is False

    # Senate user receiving House chunks: LEAK DETECTED
    assert check_cbac_leakage(house_chunks, "Senate") is False

    # Admin / Combined user: OK for both
    assert check_cbac_leakage(senate_chunks, "Combined") is True


def test_refusal_patterns_on_negative_queries():
    """Validates that 'not found' or out-of-scope responses are correctly identified."""
    assert check_refusal_patterns("There are no records found for this member.") is True
    assert check_refusal_patterns("The requested information does not exist in disclosure records.") is True
    assert check_refusal_patterns("Senator Tommy Tuberville purchased RTX stock.") is False


# ==============================================================================
# 3. BENCHMARK DATASET INTEGRITY TESTS (≥ 200 QUERIES)
# ==============================================================================

def test_benchmark_dataset_contains_at_least_200_queries():
    """Ensures the evaluation benchmark dataset meets the ≥ 200 query requirement."""
    evaluator = RagEvaluator(DATASET_PATH)
    total_queries = len(evaluator.items)
    assert total_queries >= 200, f"Expected at least 200 queries, found {total_queries}"


def test_benchmark_dataset_schema_and_categories():
    """Validates structural integrity and category distribution across the benchmark."""
    evaluator = RagEvaluator(DATASET_PATH)
    required_keys = {"id", "category", "query", "chamber", "expected_keywords", "reference_answer"}

    categories: Set[str] = set()
    chambers: Set[str] = set()

    for idx, item in enumerate(evaluator.items, start=1):
        missing = required_keys - set(item.keys())
        assert not missing, f"Item {idx} ({item.get('id')}) is missing keys: {missing}"
        assert len(item["query"].strip()) > 10, f"Item {item['id']} query is too short"
        assert len(item["reference_answer"].strip()) > 10, f"Item {item['id']} answer is too short"
        categories.add(item["category"])
        chambers.add(item["chamber"])

    # Ensure coverage of essential congressional stock domains
    expected_categories = {
        "tech_mega_cap",
        "defense_aerospace",
        "semiconductors",
        "healthcare_pharma",
        "energy_materials",
        "financial_banking",
        "prominent_members",
        "stock_act_compliance",
        "ownership_types",
        "cbac_security",
        "negative_refusals",
    }
    assert expected_categories.issubset(categories)
    assert chambers == {"House", "Senate", "Combined"}


# ==============================================================================
# 4. REFERENCE BENCHMARK EXECUTION TEST
# ==============================================================================

def test_rag_benchmark_reference_evaluation():
    """
    Executes the full evaluation pipeline across all 200+ benchmark items in offline mode.
    Validates that baseline retrieval and generation metrics meet production thresholds.
    """
    evaluator = RagEvaluator(DATASET_PATH)
    results = []

    for item in evaluator.items:
        retrieved = list(item.get("ground_truth_chunks", []))
        answer = item.get("reference_answer", "")
        res = evaluator.evaluate_item(item, retrieved, answer)
        results.append(res)

    report = evaluator.aggregate_results(results)

    # Core IR and generation validation gates
    assert report.total_queries >= 200
    assert report.mean_reciprocal_rank >= 0.70, f"MRR too low: {report.mean_reciprocal_rank}"
    assert report.mean_ndcg_at_5 >= 0.65, f"nDCG@5 too low: {report.mean_ndcg_at_5}"
    assert report.mean_hit_rate_at_5 >= 0.85, f"Hit Rate@5 too low: {report.mean_hit_rate_at_5}"
    assert report.cbac_compliance_rate == 1.0, "CBAC security violation detected"
    assert report.refusal_accuracy_rate >= 0.90, "Refusal accuracy too low"


# ==============================================================================
# 5. LIVE INTEGRATION TEST (OPTIONAL / RUN_LLM_TESTS)
# ==============================================================================

@pytest.mark.integration
@pytest.mark.llm
async def test_live_rag_evaluation_sample(run_llm_tests: bool, client, base_urls, admin_token: str):
    """
    Executes a sample of benchmark queries against the live RAG microservice.
    Requires RUN_LLM_TESTS=true and active docker-compose stack.
    """
    if not run_llm_tests:
        pytest.skip("RUN_LLM_TESTS is false; skipping live evaluation calls.")

    evaluator = RagEvaluator(DATASET_PATH)
    sample_items = evaluator.items[:5]  # Test 5 queries to conserve live LLM spend
    headers = {"Authorization": f"Bearer {admin_token}"}

    for item in sample_items:
        payload = {"prompt": item["query"], "top_k": 5}
        resp = await client.post(f"{base_urls.rag}/api/v1/rag/query", json=payload, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        retrieved_chunks = [s.get("chunk_text", "") for s in data.get("sources", [])]
        answer = data.get("answer", "")

        eval_res = evaluator.evaluate_item(item, retrieved_chunks, answer)
        assert eval_res.cbac_compliant is True
