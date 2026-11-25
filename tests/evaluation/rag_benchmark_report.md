# Congressional RAG Evaluation Benchmark Report

## 1. Global Performance Summary

| Evaluation Metric | Value | Benchmark Target | Status |
| :--- | :---: | :---: | :---: |
| **Evaluated Queries** | `219` | `≥ 200` | PASS |
| **Mean Reciprocal Rank (MRR)** | `1.0000` | `≥ 0.7000` | PASS |
| **nDCG@5** | `1.0000` | `≥ 0.6500` | PASS |
| **nDCG@10** | `1.0000` | `≥ 0.6000` | PASS |
| **Hit Rate@5 (Recall@5)** | `1.0000` | `≥ 0.8500` | PASS |
| **Precision@5** | `1.0000` | `≥ 0.4000` | PASS |
| **Faithfulness / Groundedness** | `0.7361` | `≥ 0.9000` | FAIL |
| **Factual Entity Recall** | `0.7252` | `≥ 0.8000` | FAIL |
| **Token F1 Score** | `1.0000` | `≥ 0.6000` | PASS |
| **CBAC Chamber Security Rate** | `100.0%` | `100.0%` | PASS |
| **Negative Refusal Accuracy** | `95.9%` | `≥ 95.0%` | PASS |

## 2. Category-Specific Breakdown

| Category | Queries | MRR | nDCG@5 | Hit Rate@5 | Faithfulness | Fact Recall |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `cbac_security` | 18 | 1.000 | 1.000 | 1.000 | 0.750 | 0.551 |
| `defense_aerospace` | 20 | 1.000 | 1.000 | 1.000 | 0.761 | 0.863 |
| `energy_materials` | 20 | 1.000 | 1.000 | 1.000 | 0.758 | 0.850 |
| `financial_banking` | 20 | 1.000 | 1.000 | 1.000 | 0.742 | 0.850 |
| `healthcare_pharma` | 20 | 1.000 | 1.000 | 1.000 | 0.765 | 0.880 |
| `negative_refusals` | 18 | 1.000 | 1.000 | 1.000 | 0.667 | 0.176 |
| `ownership_types` | 18 | 1.000 | 1.000 | 1.000 | 0.801 | 0.708 |
| `prominent_members` | 25 | 1.000 | 1.000 | 1.000 | 0.704 | 0.751 |
| `semiconductors` | 20 | 1.000 | 1.000 | 1.000 | 0.717 | 0.885 |
| `stock_act_compliance` | 18 | 1.000 | 1.000 | 1.000 | 0.722 | 0.381 |
| `tech_mega_cap` | 22 | 1.000 | 1.000 | 1.000 | 0.720 | 0.945 |