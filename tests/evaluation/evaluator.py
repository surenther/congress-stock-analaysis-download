#!/usr/bin/env python3
"""
Comprehensive RAG Evaluation Engine for Congressional Financial Disclosures.

Implements exact mathematical formulas for:
- Chunk / Retrieval Metrics:
    * MRR (Mean Reciprocal Rank)
    * nDCG@K (Normalized Discounted Cumulative Gain at K)
    * Hit Rate@K (Recall@K)
    * Precision@K
- Response / Generation Metrics:
    * Faithfulness / Groundedness (detecting hallucinations outside context)
    * Fact Recall (coverage of critical entities, amounts, dates)
    * Token Overlap F1 & ROUGE-L
    * Negative Case Refusal Accuracy (clean refusal when data is absent)
    * Chamber-Based Access Control (CBAC) Scope Enforcement & Leakage Detection
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ==============================================================================
# 1. MATHEMATICAL FORMULAS FOR RETRIEVAL METRICS
# ==============================================================================

def reciprocal_rank(
    retrieved_items: List[str],
    relevant_items: Set[str],
    similarity_threshold: float = 0.5
) -> float:
    """
    Compute Reciprocal Rank (RR): 1 / rank of the first relevant retrieved item.
    Formula:
        RR = 1 / min_{i} { i | retrieved[i] in relevant }
        RR = 0.0 if no relevant items are found in the retrieved list.
    """
    if not retrieved_items or not relevant_items:
        return 0.0

    for rank, item in enumerate(retrieved_items, start=1):
        if is_match(item, relevant_items, similarity_threshold):
            return 1.0 / rank
    return 0.0


def dcg_at_k(relevance_scores: List[float], k: int) -> float:
    """
    Discounted Cumulative Gain at K (DCG@K).
    Uses the standard logarithmic discounting formula:
        DCG@K = sum_{i=1}^{K} (2^{rel_i} - 1) / log2(i + 1)
    """
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k], start=1):
        dcg += (math.pow(2, rel) - 1.0) / math.log2(i + 1)
    return dcg


def ndcg_at_k(
    retrieved_items: List[str],
    relevance_map: Dict[str, float],
    k: int = 5,
    similarity_threshold: float = 0.5
) -> float:
    """
    Normalized Discounted Cumulative Gain at K (nDCG@K).
    Formula:
        nDCG@K = DCG@K / IDCG@K
    Where IDCG@K is the Ideal DCG obtained by sorting all relevance scores in descending order.
    Returns 1.0 if IDCG is 0 (i.e. no items were relevant for this query).
    """
    if k <= 0:
        return 0.0

    # Map retrieved items to graded relevance scores
    actual_scores: List[float] = []
    for item in retrieved_items[:k]:
        score = 0.0
        for rel_key, rel_val in relevance_map.items():
            if is_match(item, {rel_key}, similarity_threshold):
                score = max(score, rel_val)
        actual_scores.append(score)

    # Pad with 0.0 if retrieved items < k
    while len(actual_scores) < k:
        actual_scores.append(0.0)

    actual_dcg = dcg_at_k(actual_scores, k)

    # Ideal DCG: best possible ordering of all known relevant items
    ideal_scores = sorted(list(relevance_map.values()), reverse=True)[:k]
    while len(ideal_scores) < k:
        ideal_scores.append(0.0)

    ideal_dcg = dcg_at_k(ideal_scores, k)

    if ideal_dcg <= 0.0:
        return 1.0 if actual_dcg == 0.0 else 0.0

    return actual_dcg / ideal_dcg


def hit_rate_at_k(
    retrieved_items: List[str],
    relevant_items: Set[str],
    k: int = 5,
    similarity_threshold: float = 0.5
) -> float:
    """
    Hit Rate@K (also known as Recall@K): 1.0 if ANY relevant item appears in top K, else 0.0.
    """
    if not retrieved_items or not relevant_items or k <= 0:
        return 0.0

    for item in retrieved_items[:k]:
        if is_match(item, relevant_items, similarity_threshold):
            return 1.0
    return 0.0


def precision_at_k(
    retrieved_items: List[str],
    relevant_items: Set[str],
    k: int = 5,
    similarity_threshold: float = 0.5
) -> float:
    """
    Precision@K: Fraction of top K retrieved items that are relevant.
    When retrieved list is smaller than K, normalizes against len(retrieved_items).
    """
    if not retrieved_items or not relevant_items or k <= 0:
        return 0.0

    eval_window = retrieved_items[:k]
    hits = sum(1 for item in eval_window if is_match(item, relevant_items, similarity_threshold))
    denom = max(len(eval_window), 1)
    return hits / float(denom)


# ==============================================================================
# 2. GENERATION / RESPONSE METRICS
# ==============================================================================

def normalize_text(text: str) -> str:
    """Lowercases text, strips punctuation, and collapses whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s\$]", " ", text)
    return " ".join(text.split())


def is_match(candidate: str, targets: Set[str], threshold: float = 0.5) -> bool:
    """Determines if candidate matches any target using Jaccard word token overlap."""
    c_tokens = set(normalize_text(candidate).split())
    if not c_tokens:
        return False

    for target in targets:
        t_tokens = set(normalize_text(target).split())
        if not t_tokens:
            continue
        intersection = len(c_tokens & t_tokens)
        union = len(c_tokens | t_tokens)
        jaccard = intersection / union if union > 0 else 0.0
        if jaccard >= threshold or (len(t_tokens) >= 3 and t_tokens.issubset(c_tokens)):
            return True
    return False


def calculate_token_f1(prediction: str, reference: str) -> Tuple[float, float, float]:
    """
    Computes token-level Precision, Recall, and F1 between prediction and reference answer.
    """
    pred_tokens = normalize_text(prediction).split()
    ref_tokens = normalize_text(reference).split()

    if not pred_tokens or not ref_tokens:
        return (1.0, 1.0, 1.0) if pred_tokens == ref_tokens else (0.0, 0.0, 0.0)

    common = set(pred_tokens) & set(ref_tokens)
    if not common:
        return (0.0, 0.0, 0.0)

    # Count occurrences of common tokens
    pred_common_count = sum(1 for t in pred_tokens if t in common)
    ref_common_count = sum(1 for t in ref_tokens if t in common)

    prec = pred_common_count / len(pred_tokens)
    rec = ref_common_count / len(ref_tokens)
    f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

    return (prec, rec, f1)


def calculate_fact_recall(answer: str, expected_keywords: List[str]) -> float:
    """
    Measures what proportion of critical factual entities/amounts appear in the answer.
    Formula:
        Fact Recall = (Count of expected keywords found in answer) / (Total expected keywords)
    """
    if not expected_keywords:
        return 1.0

    normalized_answer = normalize_text(answer)
    hits = 0
    for kw in expected_keywords:
        normalized_kw = normalize_text(kw)
        if normalized_kw in normalized_answer:
            hits += 1
        else:
            # Fallback to token subset matching for multi-word keywords
            kw_tokens = set(normalized_kw.split())
            if kw_tokens and kw_tokens.issubset(set(normalized_answer.split())):
                hits += 1

    return hits / float(len(expected_keywords))


COMMON_STOP_WORDS = {
    "PTR", "LLC", "INC", "CORP", "STOCK", "USA", "THE", "AND", "FOR", "NOT", "NEW",
    "YORK", "ACT", "CBAC", "ETF", "SPDR", "NONE", "HTTP", "JWT", "REST", "SQL", "ALL",
    "EST", "PST", "UTC", "API"
}


def calculate_faithfulness(answer: str, context_chunks: List[str]) -> float:
    """
    Evaluates whether facts stated in the answer are grounded in the retrieved contexts.
    Extracts key named entities, numbers, and ticker candidates from the answer,
    and checks if they appear in any of the retrieved contexts.
    Returns a score between 0.0 (total hallucination) and 1.0 (100% grounded).
    """
    if not answer or not context_chunks:
        # If context is empty and answer states "no records found", it is faithful
        if check_refusal_patterns(answer):
            return 1.0
        return 0.0

    context_blob = normalize_text(" ".join(context_chunks))

    # Extract salient claims/entities: tickers, amounts, proper names
    raw_items = re.findall(
        r"\b[A-Z]{2,5}\b|\$[\d,]+(?:\.\d+)?|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b",
        answer
    )
    salient_items = [it for it in raw_items if it.upper() not in COMMON_STOP_WORDS]

    if not salient_items:
        return 1.0

    grounded_count = 0
    for item in salient_items:
        norm_item = normalize_text(item)
        if norm_item in context_blob:
            grounded_count += 1

    return grounded_count / float(len(salient_items))


def check_refusal_patterns(answer: str) -> bool:
    """Returns True if the response contains standard plain refusal or 'not found' language."""
    refusal_keywords = [
        "no records", "not found", "no transactions", "no disclosures",
        "did not find", "does not contain", "no reported", "outside",
        "redacted", "does not exist", "cannot provide", "invalid date",
        "no direct", "exempt", "not present", "out of bounds", "no insider",
        "403 forbidden", "chamber_scope_violation", "access denied", "rejected"
    ]
    norm = answer.lower()
    return any(rk in norm for rk in refusal_keywords)


def check_cbac_leakage(
    retrieved_chunks: List[str],
    user_chamber: str
) -> bool:
    """
    Checks for security/chamber leakage in retrieved chunks:
    - If user_chamber is "House", checks that NO Senate disclosures were returned.
    - If user_chamber is "Senate", checks that NO House disclosures were returned.
    Returns True if compliant (NO leakage), False if a leak occurred.
    """
    if not retrieved_chunks or user_chamber == "Combined":
        return True

    for chunk in retrieved_chunks:
        chunk_lower = chunk.lower()
        if user_chamber == "House" and "(senate)" in chunk_lower:
            return False
        elif user_chamber == "Senate" and "(house)" in chunk_lower:
            return False

    return True


# ==============================================================================
# 3. BENCHMARK EVALUATOR RUNNER & REPORTER
# ==============================================================================

@dataclass
class ItemEvaluationResult:
    item_id: str
    category: str
    query: str
    chamber: str
    reciprocal_rank: float
    ndcg_at_5: float
    ndcg_at_10: float
    hit_rate_at_5: float
    precision_at_5: float
    fact_recall: float
    faithfulness: float
    token_f1: float
    cbac_compliant: bool
    refusal_accurate: bool
    is_negative_case: bool
    error: Optional[str] = None


@dataclass
class AggregateEvaluationReport:
    total_queries: int
    mean_reciprocal_rank: float
    mean_ndcg_at_5: float
    mean_ndcg_at_10: float
    mean_hit_rate_at_5: float
    mean_precision_at_5: float
    mean_fact_recall: float
    mean_faithfulness: float
    mean_token_f1: float
    cbac_compliance_rate: float
    refusal_accuracy_rate: float
    category_breakdown: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_markdown(self) -> str:
        """Formats the aggregate results as an executive evaluation report table."""
        lines = [
            "# Congressional RAG Evaluation Benchmark Report",
            "",
            "## 1. Global Performance Summary",
            "",
            "| Evaluation Metric | Value | Benchmark Target | Status |",
            "| :--- | :---: | :---: | :---: |",
            f"| **Evaluated Queries** | `{self.total_queries}` | `≥ 200` | {'PASS' if self.total_queries >= 200 else 'WARN'} |",
            f"| **Mean Reciprocal Rank (MRR)** | `{self.mean_reciprocal_rank:.4f}` | `≥ 0.7000` | {'PASS' if self.mean_reciprocal_rank >= 0.70 else 'FAIL'} |",
            f"| **nDCG@5** | `{self.mean_ndcg_at_5:.4f}` | `≥ 0.6500` | {'PASS' if self.mean_ndcg_at_5 >= 0.65 else 'FAIL'} |",
            f"| **nDCG@10** | `{self.mean_ndcg_at_10:.4f}` | `≥ 0.6000` | {'PASS' if self.mean_ndcg_at_10 >= 0.60 else 'FAIL'} |",
            f"| **Hit Rate@5 (Recall@5)** | `{self.mean_hit_rate_at_5:.4f}` | `≥ 0.8500` | {'PASS' if self.mean_hit_rate_at_5 >= 0.85 else 'FAIL'} |",
            f"| **Precision@5** | `{self.mean_precision_at_5:.4f}` | `≥ 0.4000` | {'PASS' if self.mean_precision_at_5 >= 0.40 else 'FAIL'} |",
            f"| **Faithfulness / Groundedness** | `{self.mean_faithfulness:.4f}` | `≥ 0.9000` | {'PASS' if self.mean_faithfulness >= 0.90 else 'FAIL'} |",
            f"| **Factual Entity Recall** | `{self.mean_fact_recall:.4f}` | `≥ 0.8000` | {'PASS' if self.mean_fact_recall >= 0.80 else 'FAIL'} |",
            f"| **Token F1 Score** | `{self.mean_token_f1:.4f}` | `≥ 0.6000` | {'PASS' if self.mean_token_f1 >= 0.60 else 'FAIL'} |",
            f"| **CBAC Chamber Security Rate** | `{self.cbac_compliance_rate * 100:.1f}%` | `100.0%` | {'PASS' if self.cbac_compliance_rate >= 0.999 else 'CRITICAL'} |",
            f"| **Negative Refusal Accuracy** | `{self.refusal_accuracy_rate * 100:.1f}%` | `≥ 95.0%` | {'PASS' if self.refusal_accuracy_rate >= 0.95 else 'WARN'} |",
            "",
            "## 2. Category-Specific Breakdown",
            "",
            "| Category | Queries | MRR | nDCG@5 | Hit Rate@5 | Faithfulness | Fact Recall |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
        for cat, stats in sorted(self.category_breakdown.items()):
            lines.append(
                f"| `{cat}` | {int(stats['count'])} | {stats['mrr']:.3f} | {stats['ndcg5']:.3f} | "
                f"{stats['hit5']:.3f} | {stats['faith']:.3f} | {stats['recall']:.3f} |"
            )
        return "\n".join(lines)


class RagEvaluator:
    """Orchestrates RAG benchmark execution and metric computation."""

    def __init__(self, dataset_path: Optional[Path] = None):
        if dataset_path is None:
            dataset_path = Path(__file__).resolve().parent / "rag_benchmark_dataset.json"
        self.dataset_path = dataset_path
        self.items: List[Dict[str, Any]] = self._load_dataset()

    def _load_dataset(self) -> List[Dict[str, Any]]:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Benchmark dataset not found at {self.dataset_path}")
        with open(self.dataset_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate_item(
        self,
        item: Dict[str, Any],
        retrieved_chunks: List[str],
        generated_answer: str
    ) -> ItemEvaluationResult:
        """Evaluates a single query run against the gold reference data."""
        gt_chunks = set(item.get("ground_truth_chunks", []))
        relevance_map = {chunk: 2.0 for chunk in gt_chunks}
        # If there are target tickers/filers, give 1.0 partial relevance to chunks mentioning them
        expected_keywords = item.get("expected_keywords", [])
        reference_answer = item.get("reference_answer", "")
        is_negative = item.get("is_negative_case", False)
        chamber = item.get("chamber", "Combined")

        # 1. Retrieval metrics
        if is_negative and not gt_chunks:
            # Negative test: correct retrieval is returning 0 or irrelevant chunks
            rr = 1.0 if not retrieved_chunks else 0.5
            ndcg5 = 1.0
            ndcg10 = 1.0
            hit5 = 1.0
            prec5 = 1.0
        else:
            rr = reciprocal_rank(retrieved_chunks, gt_chunks)
            ndcg5 = ndcg_at_k(retrieved_chunks, relevance_map, k=5)
            ndcg10 = ndcg_at_k(retrieved_chunks, relevance_map, k=10)
            hit5 = hit_rate_at_k(retrieved_chunks, gt_chunks, k=5)
            prec5 = precision_at_k(retrieved_chunks, gt_chunks, k=5)

        # 2. Generation metrics
        fact_rec = calculate_fact_recall(generated_answer, expected_keywords)
        faith = calculate_faithfulness(generated_answer, retrieved_chunks)
        _, _, tok_f1 = calculate_token_f1(generated_answer, reference_answer)

        # 3. Security & Refusal checks
        cbac_ok = check_cbac_leakage(retrieved_chunks, chamber)
        refusal_ok = True
        if is_negative:
            refusal_ok = check_refusal_patterns(generated_answer)
            if refusal_ok:
                faith = 1.0

        return ItemEvaluationResult(
            item_id=item["id"],
            category=item.get("category", "general"),
            query=item["query"],
            chamber=chamber,
            reciprocal_rank=rr,
            ndcg_at_5=ndcg5,
            ndcg_at_10=ndcg10,
            hit_rate_at_5=hit5,
            precision_at_5=prec5,
            fact_recall=fact_rec,
            faithfulness=faith,
            token_f1=tok_f1,
            cbac_compliant=cbac_ok,
            refusal_accurate=refusal_ok,
            is_negative_case=is_negative
        )

    def aggregate_results(self, results: List[ItemEvaluationResult]) -> AggregateEvaluationReport:
        """Aggregates item results into global and per-category metrics."""
        total = len(results)
        if total == 0:
            raise ValueError("No evaluation results to aggregate.")

        mrr = sum(r.reciprocal_rank for r in results) / total
        ndcg5 = sum(r.ndcg_at_5 for r in results) / total
        ndcg10 = sum(r.ndcg_at_10 for r in results) / total
        hit5 = sum(r.hit_rate_at_5 for r in results) / total
        prec5 = sum(r.precision_at_5 for r in results) / total
        fact_rec = sum(r.fact_recall for r in results) / total
        faith = sum(r.faithfulness for r in results) / total
        tok_f1 = sum(r.token_f1 for r in results) / total
        cbac_rate = sum(1 for r in results if r.cbac_compliant) / total
        refusal_rate = sum(1 for r in results if r.refusal_accurate) / total

        # Category breakdown
        cat_map: Dict[str, List[ItemEvaluationResult]] = {}
        for r in results:
            cat_map.setdefault(r.category, []).append(r)

        breakdown = {}
        for cat, items in cat_map.items():
            n = len(items)
            breakdown[cat] = {
                "count": float(n),
                "mrr": sum(x.reciprocal_rank for x in items) / n,
                "ndcg5": sum(x.ndcg_at_5 for x in items) / n,
                "hit5": sum(x.hit_rate_at_5 for x in items) / n,
                "faith": sum(x.faithfulness for x in items) / n,
                "recall": sum(x.fact_recall for x in items) / n,
            }

        return AggregateEvaluationReport(
            total_queries=total,
            mean_reciprocal_rank=mrr,
            mean_ndcg_at_5=ndcg5,
            mean_ndcg_at_10=ndcg10,
            mean_hit_rate_at_5=hit5,
            mean_precision_at_5=prec5,
            mean_fact_recall=fact_rec,
            mean_faithfulness=faith,
            mean_token_f1=tok_f1,
            cbac_compliance_rate=cbac_rate,
            refusal_accuracy_rate=refusal_rate,
            category_breakdown=breakdown
        )
