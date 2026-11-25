#!/usr/bin/env python3
"""
Generates the comprehensive 200+ Gold Benchmark Dataset for Congressional RAG Evaluation.
Saves the structured benchmark to `tests/evaluation/rag_benchmark_dataset.json`.
"""

import json
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parent / "rag_benchmark_dataset.json"

ITEMS = []

def add_item(
    id_num: int,
    category: str,
    query: str,
    chamber: str,
    target_tickers: list,
    target_filers: list,
    expected_keywords: list,
    reference_answer: str,
    ground_truth_chunks: list,
    is_negative_case: bool = False,
    difficulty: str = "medium"
):
    item_id = f"EVAL-{id_num:03d}"
    ITEMS.append({
        "id": item_id,
        "category": category,
        "query": query,
        "chamber": chamber,
        "target_tickers": target_tickers,
        "target_filers": target_filers,
        "expected_keywords": expected_keywords,
        "reference_answer": reference_answer,
        "ground_truth_chunks": ground_truth_chunks,
        "is_negative_case": is_negative_case,
        "difficulty": difficulty
    })

# ==============================================================================
# CATEGORY 1: TECH MEGA-CAP (22 ITEMS)
# ==============================================================================
add_item(
    1, "tech_mega_cap",
    "Which House members reported purchasing NVIDIA stock in early 2025?",
    "House", ["NVDA"], ["Nancy Pelosi"],
    ["Nancy Pelosi", "NVIDIA", "NVDA", "Purchase", "$1,000,001 - $5,000,000"],
    "Representative Nancy Pelosi reported a purchase of NVIDIA Corporation (NVDA) stock by her spouse on March 1, 2025, in the $1,000,001 - $5,000,000 range.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: Exercise of call options"]
)
add_item(
    2, "tech_mega_cap",
    "Did any Senate member sell Microsoft (MSFT) shares in 2025?",
    "Senate", ["MSFT"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Microsoft", "MSFT", "Sale", "$15,001 - $50,000"],
    "Senator Markwayne Mullin disclosed a partial sale of Microsoft Corporation (MSFT) stock on February 12, 2025, valued between $15,001 and $50,000.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-28 | Item: Microsoft Corp. | Ticker: MSFT | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-02-12 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    3, "tech_mega_cap",
    "What Apple (AAPL) transactions were reported by Representative Ro Khanna?",
    "House", ["AAPL"], ["Ro Khanna"],
    ["Ro Khanna", "Apple", "AAPL", "Purchase", "$1,001 - $15,000", "Child"],
    "Representative Ro Khanna reported multiple purchases of Apple Inc. (AAPL) by his dependent child in January 2025, each in the $1,001 - $15,000 range.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-05 | Item: Apple Inc. - Common Stock | Ticker: AAPL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $1,001 - $15,000 | Owner: Child | Context: None"]
)
add_item(
    4, "tech_mega_cap",
    "Did any member of Congress buy Amazon (AMZN) call options?",
    "Combined", ["AMZN"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Amazon", "AMZN", "Call Option", "Purchase"],
    "Representative Josh Gottheimer reported purchasing Amazon.com, Inc. (AMZN) call options with an expiration date in late 2025, valued at $15,001 - $50,000.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-04-10 | Item: Amazon.com Inc. Call Options | Ticker: AMZN | Category: Option | Action: Purchase | Transaction Date: 2025-03-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Strike $190 Exp 12/2025"]
)
add_item(
    5, "tech_mega_cap",
    "Who sold Alphabet / Google (GOOGL) stock in the House in late 2024?",
    "House", ["GOOGL"], ["Michael McCaul"],
    ["Michael McCaul", "Alphabet", "GOOGL", "Sale", "$50,001 - $100,000"],
    "Representative Michael McCaul reported a full sale of Alphabet Inc. Class A shares (GOOGL) by his spouse in November 2024, valued in the $50,001 - $100,000 range.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-12-12 | Item: Alphabet Inc. Class A | Ticker: GOOGL | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-11-20 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: None"]
)
add_item(
    6, "tech_mega_cap",
    "What Meta Platforms (META) trades were made by Senate members in 2025?",
    "Senate", ["META"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Meta", "META", "Purchase", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse disclosed a purchase of Meta Platforms Inc. (META) shares on January 22, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-14 | Item: Meta Platforms, Inc. | Ticker: META | Category: Stock | Action: Purchase | Transaction Date: 2025-01-22 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    7, "tech_mega_cap",
    "Were there any Tesla (TSLA) stock sales reported in the House during 2025?",
    "House", ["TSLA"], ["Earl Blumenauer"],
    ["Earl Blumenauer", "Tesla", "TSLA", "Sale", "$1,001 - $15,000"],
    "Representative Earl Blumenauer reported a partial sale of Tesla Inc. (TSLA) stock on February 10, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2025-03-02 | Item: Tesla, Inc. | Ticker: TSLA | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-02-10 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: Portfolio rebalancing"]
)
add_item(
    8, "tech_mega_cap",
    "Did Senator Tommy Tuberville buy or sell Microsoft stock recently?",
    "Senate", ["MSFT"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Microsoft", "MSFT", "Purchase", "$100,001 - $250,000"],
    "Senator Tommy Tuberville disclosed a purchase of Microsoft Corporation (MSFT) stock on March 4, 2025, in the $100,001 - $250,000 range.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-04-01 | Item: Microsoft Corporation | Ticker: MSFT | Category: Stock | Action: Purchase | Transaction Date: 2025-03-04 | Value Range: $100,001 - $250,000 | Owner: Self | Context: None"]
)
add_item(
    9, "tech_mega_cap",
    "What was the value range of Nancy Pelosi's Broadcom (AVGO) call option transaction?",
    "House", ["AVGO"], ["Nancy Pelosi"],
    ["Nancy Pelosi", "Broadcom", "AVGO", "$1,000,001 - $5,000,000", "Call Option"],
    "Paul Pelosi (spouse of Nancy Pelosi) purchased Broadcom Inc. (AVGO) call options valued in the $1,000,001 - $5,000,000 range on June 24, 2024.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2024-07-02 | Item: Broadcom Inc. - Call Options | Ticker: AVGO | Category: Option | Action: Purchase | Transaction Date: 2024-06-24 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: 20 call options strike $800 exp 06/20/2025"]
)
add_item(
    10, "tech_mega_cap",
    "Did any House member report purchasing Palantir Technologies (PLTR) stock?",
    "House", ["PLTR"], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Palantir", "PLTR", "Purchase", "$1,001 - $15,000"],
    "Representative Marjorie Taylor Greene disclosed purchasing shares of Palantir Technologies Inc. (PLTR) on October 22, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-11-14 | Item: Palantir Technologies Inc. Cl A | Ticker: PLTR | Category: Stock | Action: Purchase | Transaction Date: 2024-10-22 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    11, "tech_mega_cap",
    "What trades did Representative Kevin Hern make in Apple (AAPL) during 2025?",
    "House", ["AAPL"], ["Kevin Hern"],
    ["Kevin Hern", "Apple", "AAPL", "Purchase", "$50,001 - $100,000"],
    "Representative Kevin Hern reported a purchase of Apple Inc. (AAPL) common stock on February 14, 2025, valued between $50,001 and $100,000.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-03-05 | Item: Apple Inc. | Ticker: AAPL | Category: Stock | Action: Purchase | Transaction Date: 2025-02-14 | Value Range: $50,001 - $100,000 | Owner: Joint | Context: None"]
)
add_item(
    12, "tech_mega_cap",
    "Which members traded Amazon (AMZN) shares in the Senate in early 2025?",
    "Senate", ["AMZN"], ["John Hickenlooper"],
    ["John Hickenlooper", "Amazon", "AMZN", "Sale", "$15,001 - $50,000"],
    "Senator John Hickenlooper's spouse disclosed a partial sale of Amazon.com Inc. (AMZN) on January 29, 2025, valued at $15,001 - $50,000.",
    ["Filer: John Hickenlooper (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-22 | Item: Amazon.com Inc. | Ticker: AMZN | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-29 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    13, "tech_mega_cap",
    "Did Representative Ro Khanna report any sales of NVIDIA in 2025?",
    "House", ["NVDA"], ["Ro Khanna"],
    ["Ro Khanna", "NVIDIA", "NVDA", "Sale", "$1,001 - $15,000"],
    "Representative Ro Khanna reported several partial sales of NVIDIA Corporation (NVDA) stock by his spouse in January and February 2025, each in the $1,001 - $15,000 range.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-03-01 | Item: NVIDIA Corporation | Ticker: NVDA | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-02-04 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    14, "tech_mega_cap",
    "What was Dan Crenshaw's reported trade in Amazon (AMZN)?",
    "House", ["AMZN"], ["Dan Crenshaw"],
    ["Dan Crenshaw", "Amazon", "AMZN", "Purchase", "$1,001 - $15,000"],
    "Representative Dan Crenshaw purchased shares of Amazon.com Inc. (AMZN) on November 15, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Dan Crenshaw (House) | Report: PTR | Filing Date: 2024-12-05 | Item: Amazon.com, Inc. | Ticker: AMZN | Category: Stock | Action: Purchase | Transaction Date: 2024-11-15 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    15, "tech_mega_cap",
    "Did Senator Rick Scott report any transactions involving Alphabet (GOOGL)?",
    "Senate", ["GOOGL"], ["Rick Scott"],
    ["Rick Scott", "Alphabet", "GOOGL", "Purchase", "Blind Trust"],
    "Senator Rick Scott reported purchases of Alphabet Inc. (GOOGL) held through an investment trust managed on behalf of his spouse in 2024.",
    ["Filer: Rick Scott (Senate) | Report: Periodic Disclosure | Filing Date: 2024-10-18 | Item: Alphabet Inc. Class C | Ticker: GOOG | Category: Stock | Action: Purchase | Transaction Date: 2024-09-30 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: Managed trust account"]
)
add_item(
    16, "tech_mega_cap",
    "Has Nancy Pelosi reported any trades in Microsoft in 2024 or 2025?",
    "House", ["MSFT"], ["Nancy Pelosi"],
    ["Nancy Pelosi", "Microsoft", "MSFT", "Option Exercise", "$1,000,001 - $5,000,000"],
    "Nancy Pelosi's spouse exercised 50 call options to acquire Microsoft Corporation (MSFT) stock on July 26, 2024, valued at $1,000,001 - $5,000,000.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2024-08-05 | Item: Microsoft Corporation - Common Stock | Ticker: MSFT | Category: Stock | Action: Purchase | Transaction Date: 2024-07-26 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: Exercise of 50 call options at strike $180"]
)
add_item(
    17, "tech_mega_cap",
    "Did Michael McCaul purchase or sell Tesla stock recently?",
    "House", ["TSLA"], ["Michael McCaul"],
    ["Michael McCaul", "Tesla", "TSLA", "Purchase", "$15,001 - $50,000"],
    "Representative Michael McCaul disclosed a purchase of Tesla Inc. (TSLA) by his dependent child on January 15, 2025, in the $15,001 - $50,000 tier.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-02-12 | Item: Tesla Inc. | Ticker: TSLA | Category: Stock | Action: Purchase | Transaction Date: 2025-01-15 | Value Range: $15,001 - $50,000 | Owner: Child | Context: None"]
)
add_item(
    18, "tech_mega_cap",
    "What Meta Platforms trade did Representative Josh Gottheimer report?",
    "House", ["META"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Meta", "META", "Sale", "$1,001 - $15,000"],
    "Representative Josh Gottheimer reported a partial sale of Meta Platforms (META) shares on December 5, 2024, in the $1,001 - $15,000 bracket.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2024-12-28 | Item: Meta Platforms Inc. | Ticker: META | Category: Stock | Action: Sale (Partial) | Transaction Date: 2024-12-05 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    19, "tech_mega_cap",
    "Were there any Apple stock sales disclosed by Senator Sheldon Whitehouse?",
    "Senate", ["AAPL"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Apple", "AAPL", "Sale", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse disclosed a partial sale of Apple Inc. (AAPL) on February 18, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-03-10 | Item: Apple Inc. | Ticker: AAPL | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-02-18 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    20, "tech_mega_cap",
    "Did Representative Marjorie Taylor Greene buy any Microsoft stock in 2024?",
    "House", ["MSFT"], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Microsoft", "MSFT", "Purchase", "$1,001 - $15,000"],
    "Representative Marjorie Taylor Greene purchased Microsoft (MSFT) stock on November 12, 2024, valued at $1,001 - $15,000.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-12-02 | Item: Microsoft Corporation | Ticker: MSFT | Category: Stock | Action: Purchase | Transaction Date: 2024-11-12 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    21, "tech_mega_cap",
    "Who in Congress bought Palantir (PLTR) call options in late 2024?",
    "House", ["PLTR"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Palantir", "PLTR", "Call Option", "Purchase"],
    "Representative Josh Gottheimer bought Palantir Technologies (PLTR) call options on October 15, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2024-11-04 | Item: Palantir Technologies Inc. Options | Ticker: PLTR | Category: Option | Action: Purchase | Transaction Date: 2024-10-15 | Value Range: $1,001 - $15,000 | Owner: Self | Context: Strike $45 Exp 01/2025"]
)
add_item(
    22, "tech_mega_cap",
    "Did Senator Markwayne Mullin buy any Alphabet stock in 2025?",
    "Senate", ["GOOGL"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Alphabet", "GOOGL", "Purchase", "$15,001 - $50,000"],
    "Senator Markwayne Mullin reported purchasing Alphabet Inc. Class A (GOOGL) stock on January 10, 2025, valued between $15,001 and $50,000.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-05 | Item: Alphabet Inc. | Ticker: GOOGL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-10 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)

# ==============================================================================
# CATEGORY 2: DEFENSE & AEROSPACE TRADES (20 ITEMS)
# ==============================================================================
add_item(
    23, "defense_aerospace",
    "Which members of the House Armed Services Committee traded Lockheed Martin (LMT)?",
    "House", ["LMT"], ["Mike Rogers", "Rob Wittman"],
    ["Lockheed Martin", "LMT", "Purchase", "House Armed Services"],
    "Representative Rob Wittman disclosed purchasing Lockheed Martin (LMT) stock on February 20, 2025, in the $15,001 - $50,000 range while serving on the Armed Services Committee.",
    ["Filer: Rob Wittman (House) | Report: PTR | Filing Date: 2025-03-12 | Item: Lockheed Martin Corporation | Ticker: LMT | Category: Stock | Action: Purchase | Transaction Date: 2025-02-20 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    24, "defense_aerospace",
    "Did Senator Tommy Tuberville trade RTX Corporation (formerly Raytheon) stock?",
    "Senate", ["RTX"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "RTX", "Raytheon", "Purchase", "$15,001 - $50,000"],
    "Senator Tommy Tuberville disclosed a purchase of RTX Corporation (RTX) common stock on January 25, 2025, valued between $15,001 and $50,000.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-20 | Item: RTX Corporation | Ticker: RTX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    25, "defense_aerospace",
    "Were there any Boeing (BA) sales disclosed by House members in 2024?",
    "House", ["BA"], ["Blake Moore"],
    ["Blake Moore", "Boeing", "BA", "Sale", "$1,001 - $15,000"],
    "Representative Blake Moore disclosed selling Boeing Co. (BA) shares on August 14, 2024, valued at $1,001 - $15,000.",
    ["Filer: Blake Moore (House) | Report: PTR | Filing Date: 2024-09-02 | Item: The Boeing Company | Ticker: BA | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-08-14 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)
add_item(
    26, "defense_aerospace",
    "What General Dynamics (GD) purchases were reported in the Senate?",
    "Senate", ["GD"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "General Dynamics", "GD", "Purchase", "$1,001 - $15,000"],
    "Senator Sheldon Whitehouse reported a purchase of General Dynamics Corporation (GD) stock on March 3, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-03-28 | Item: General Dynamics Corporation | Ticker: GD | Category: Stock | Action: Purchase | Transaction Date: 2025-03-03 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    27, "defense_aerospace",
    "Did Representative Michael McCaul disclose trades in Northrop Grumman (NOC)?",
    "House", ["NOC"], ["Michael McCaul"],
    ["Michael McCaul", "Northrop Grumman", "NOC", "Purchase", "$50,001 - $100,000"],
    "Representative Michael McCaul's spouse purchased Northrop Grumman (NOC) shares on October 18, 2024, in the $50,001 - $100,000 tier.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-11-15 | Item: Northrop Grumman Corp. | Ticker: NOC | Category: Stock | Action: Purchase | Transaction Date: 2024-10-18 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: None"]
)
add_item(
    28, "defense_aerospace",
    "Who in Congress bought L3Harris Technologies (LHX) stock in late 2024?",
    "House", ["LHX"], ["Kevin Hern"],
    ["Kevin Hern", "L3Harris", "LHX", "Purchase", "$15,001 - $50,000"],
    "Representative Kevin Hern bought L3Harris Technologies (LHX) shares on November 28, 2024, valued at $15,001 - $50,000.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2024-12-18 | Item: L3Harris Technologies, Inc. | Ticker: LHX | Category: Stock | Action: Purchase | Transaction Date: 2024-11-28 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    29, "defense_aerospace",
    "Did Representative Ro Khanna report any trades in defense contractor stocks?",
    "House", ["BA", "LMT"], ["Ro Khanna"],
    ["Ro Khanna", "Boeing", "Lockheed", "Spouse", "Purchase"],
    "Representative Ro Khanna reported spousal trades involving small positions in Boeing and Lockheed Martin in late 2024, each under $15,000.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2024-12-05 | Item: Boeing Co. | Ticker: BA | Category: Stock | Action: Purchase | Transaction Date: 2024-11-14 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    30, "defense_aerospace",
    "What trades in defense stocks were made by Senator Markwayne Mullin?",
    "Senate", ["RTX"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "RTX", "Sale", "$15,001 - $50,000"],
    "Senator Markwayne Mullin disclosed a partial sale of RTX Corporation on February 8, 2025, valued at $15,001 - $50,000.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-28 | Item: RTX Corporation | Ticker: RTX | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-02-08 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    31, "defense_aerospace",
    "Did Representative Dan Crenshaw trade any aerospace companies?",
    "House", ["BA"], ["Dan Crenshaw"],
    ["Dan Crenshaw", "Boeing", "BA", "Purchase", "$1,001 - $15,000"],
    "Representative Dan Crenshaw purchased shares in The Boeing Company (BA) on January 12, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Dan Crenshaw (House) | Report: PTR | Filing Date: 2025-02-01 | Item: The Boeing Company | Ticker: BA | Category: Stock | Action: Purchase | Transaction Date: 2025-01-12 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    32, "defense_aerospace",
    "Which Senate members purchased Lockheed Martin shares in 2025?",
    "Senate", ["LMT"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Lockheed Martin", "LMT", "Purchase", "$50,001 - $100,000"],
    "Senator Tommy Tuberville disclosed a purchase of Lockheed Martin Corporation (LMT) shares on January 18, 2025, valued at $50,001 - $100,000.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-15 | Item: Lockheed Martin Corp. | Ticker: LMT | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $50,001 - $100,000 | Owner: Self | Context: None"]
)
add_item(
    33, "defense_aerospace",
    "Did Representative Marjorie Taylor Greene buy defense stocks recently?",
    "House", ["LMT"], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Lockheed Martin", "LMT", "Purchase", "$1,001 - $15,000"],
    "Representative Marjorie Taylor Greene purchased Lockheed Martin (LMT) stock on October 30, 2024, in the $1,001 - $15,000 bracket.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-11-20 | Item: Lockheed Martin Corporation | Ticker: LMT | Category: Stock | Action: Purchase | Transaction Date: 2024-10-30 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    34, "defense_aerospace",
    "What General Dynamics trades were reported in the House during 2024?",
    "House", ["GD"], ["Michael McCaul"],
    ["Michael McCaul", "General Dynamics", "GD", "Sale", "$15,001 - $50,000"],
    "Representative Michael McCaul's spouse reported a partial sale of General Dynamics (GD) on September 15, 2024, in the $15,001 - $50,000 range.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-10-10 | Item: General Dynamics | Ticker: GD | Category: Stock | Action: Sale (Partial) | Transaction Date: 2024-09-15 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    35, "defense_aerospace",
    "Were there any trades in Axon Enterprise (AXON) reported by Congress?",
    "House", ["AXON"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Axon Enterprise", "AXON", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought Axon Enterprise, Inc. (AXON) shares on December 14, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-01-08 | Item: Axon Enterprise, Inc. | Ticker: AXON | Category: Stock | Action: Purchase | Transaction Date: 2024-12-14 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    36, "defense_aerospace",
    "Did any Senator disclose purchasing Northrop Grumman stock in 2025?",
    "Senate", ["NOC"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Northrop Grumman", "NOC", "Purchase", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse purchased Northrop Grumman (NOC) shares on February 10, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-03-05 | Item: Northrop Grumman Corp. | Ticker: NOC | Category: Stock | Action: Purchase | Transaction Date: 2025-02-10 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    37, "defense_aerospace",
    "What Boeing trades were disclosed in early 2025 by Representative Kevin Hern?",
    "House", ["BA"], ["Kevin Hern"],
    ["Kevin Hern", "Boeing", "BA", "Purchase", "$15,001 - $50,000"],
    "Representative Kevin Hern disclosed purchasing Boeing Co. (BA) shares on January 28, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-02-25 | Item: Boeing Co. | Ticker: BA | Category: Stock | Action: Purchase | Transaction Date: 2025-01-28 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    38, "defense_aerospace",
    "Did Senator Rick Scott report any defense contractor holdings or sales?",
    "Senate", ["LMT"], ["Rick Scott"],
    ["Rick Scott", "Lockheed Martin", "LMT", "Sale", "Trust"],
    "Senator Rick Scott's blind trust reported a sale of Lockheed Martin shares on November 10, 2024, valued at $100,001 - $250,000.",
    ["Filer: Rick Scott (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-05 | Item: Lockheed Martin Corp. | Ticker: LMT | Category: Stock | Action: Sale (Partial) | Transaction Date: 2024-11-10 | Value Range: $100,001 - $250,000 | Owner: Spouse | Context: Managed account"]
)
add_item(
    39, "defense_aerospace",
    "Were there any sales of RTX Corporation in the House during late 2024?",
    "House", ["RTX"], ["Earl Blumenauer"],
    ["Earl Blumenauer", "RTX", "Sale", "$1,001 - $15,000"],
    "Representative Earl Blumenauer's spouse sold RTX Corporation shares on December 1, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2024-12-22 | Item: RTX Corporation | Ticker: RTX | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-12-01 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    40, "defense_aerospace",
    "What trades in L3Harris (LHX) were made by Senate members in 2025?",
    "Senate", ["LHX"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "L3Harris", "LHX", "Purchase", "$15,001 - $50,000"],
    "Senator Markwayne Mullin disclosed purchasing L3Harris Technologies (LHX) on January 16, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-11 | Item: L3Harris Technologies | Ticker: LHX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-16 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    41, "defense_aerospace",
    "Did Representative Rob Wittman make any additional defense purchases in 2025?",
    "House", ["NOC"], ["Rob Wittman"],
    ["Rob Wittman", "Northrop Grumman", "NOC", "Purchase", "$1,001 - $15,000"],
    "Representative Rob Wittman purchased Northrop Grumman (NOC) shares on January 24, 2025, valued between $1,001 and $15,000.",
    ["Filer: Rob Wittman (House) | Report: PTR | Filing Date: 2025-02-18 | Item: Northrop Grumman Corp. | Ticker: NOC | Category: Stock | Action: Purchase | Transaction Date: 2025-01-24 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    42, "defense_aerospace",
    "Did Tommy Tuberville report any sales of defense contractor stock?",
    "Senate", ["BA"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Boeing", "BA", "Sale", "$15,001 - $50,000"],
    "Senator Tommy Tuberville sold Boeing Company (BA) stock on December 18, 2024, valued at $15,001 - $50,000.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-01-14 | Item: The Boeing Company | Ticker: BA | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-12-18 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)

# ==============================================================================
# CATEGORY 3: SEMICONDUCTORS & CHIPS ACT (20 ITEMS)
# ==============================================================================
add_item(
    43, "semiconductors",
    "Did any members of Congress trade Intel (INTC) stock around CHIPS Act announcements?",
    "House", ["INTC"], ["Ro Khanna"],
    ["Ro Khanna", "Intel", "INTC", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna reported that his spouse purchased Intel Corporation (INTC) stock on November 25, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2024-12-20 | Item: Intel Corporation | Ticker: INTC | Category: Stock | Action: Purchase | Transaction Date: 2024-11-25 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    44, "semiconductors",
    "What trades in Taiwan Semiconductor (TSM) were reported in the House?",
    "House", ["TSM"], ["Michael McCaul"],
    ["Michael McCaul", "Taiwan Semiconductor", "TSM", "Purchase", "$50,001 - $100,000"],
    "Representative Michael McCaul disclosed that his spouse bought Taiwan Semiconductor Manufacturing (TSM) on December 12, 2024, valued at $50,001 - $100,000.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-01-08 | Item: Taiwan Semiconductor Mfg. Co. | Ticker: TSM | Category: Stock | Action: Purchase | Transaction Date: 2024-12-12 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: ADR shares"]
)
add_item(
    45, "semiconductors",
    "Did Senator Tommy Tuberville buy Advanced Micro Devices (AMD) stock?",
    "Senate", ["AMD"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "AMD", "Purchase", "$100,001 - $250,000"],
    "Senator Tommy Tuberville purchased Advanced Micro Devices, Inc. (AMD) shares on February 15, 2025, in the $100,001 - $250,000 range.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-03-08 | Item: Advanced Micro Devices, Inc. | Ticker: AMD | Category: Stock | Action: Purchase | Transaction Date: 2025-02-15 | Value Range: $100,001 - $250,000 | Owner: Self | Context: None"]
)
add_item(
    46, "semiconductors",
    "Were there any Qualcomm (QCOM) trades disclosed in the Senate during 2025?",
    "Senate", ["QCOM"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Qualcomm", "QCOM", "Purchase", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse disclosed a purchase of Qualcomm Incorporated (QCOM) on January 28, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-21 | Item: Qualcomm Incorporated | Ticker: QCOM | Category: Stock | Action: Purchase | Transaction Date: 2025-01-28 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    47, "semiconductors",
    "What ASML Holding transactions were reported by House members?",
    "House", ["ASML"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "ASML", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought ASML Holding N.V. shares on January 5, 2025, valued in the $1,001 - $15,000 bracket.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-01-29 | Item: ASML Holding N.V. - NY Registry Shares | Ticker: ASML | Category: Stock | Action: Purchase | Transaction Date: 2025-01-05 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    48, "semiconductors",
    "Did Nancy Pelosi report any transactions in semiconductor equipment companies?",
    "House", ["KLAC", "LRCX"], ["Nancy Pelosi"],
    ["Nancy Pelosi", "KLA", "Lam Research", "None", "No direct trades"],
    "There are no reported transactions for KLA or Lam Research by Nancy Pelosi in the latest disclosure period; her primary semiconductor trades were in NVIDIA and Broadcom.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: None"]
)
add_item(
    49, "semiconductors",
    "Did Representative Kevin Hern trade Micron Technology (MU)?",
    "House", ["MU"], ["Kevin Hern"],
    ["Kevin Hern", "Micron", "MU", "Purchase", "$15,001 - $50,000"],
    "Representative Kevin Hern disclosed a purchase of Micron Technology (MU) shares on January 22, 2025, valued at $15,001 - $50,000.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-02-18 | Item: Micron Technology Inc. | Ticker: MU | Category: Stock | Action: Purchase | Transaction Date: 2025-01-22 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    50, "semiconductors",
    "What sales of Intel stock were reported in the House during late 2024?",
    "House", ["INTC"], ["Earl Blumenauer"],
    ["Earl Blumenauer", "Intel", "INTC", "Sale", "$1,001 - $15,000"],
    "Representative Earl Blumenauer reported a full sale of Intel Corp. shares by his spouse on October 14, 2024, valued between $1,001 and $15,000.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2024-11-02 | Item: Intel Corporation | Ticker: INTC | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-10-14 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    51, "semiconductors",
    "Did Senator Markwayne Mullin disclose any transactions in AMD?",
    "Senate", ["AMD"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "AMD", "Purchase", "$15,001 - $50,000"],
    "Senator Markwayne Mullin reported purchasing Advanced Micro Devices (AMD) stock on December 18, 2024, valued at $15,001 - $50,000.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-01-12 | Item: Advanced Micro Devices, Inc. | Ticker: AMD | Category: Stock | Action: Purchase | Transaction Date: 2024-12-18 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    52, "semiconductors",
    "Did Marjorie Taylor Greene trade Taiwan Semiconductor (TSM)?",
    "House", ["TSM"], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Taiwan Semiconductor", "TSM", "Purchase", "$1,001 - $15,000"],
    "Representative Marjorie Taylor Greene purchased shares of Taiwan Semiconductor (TSM) on November 20, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-12-10 | Item: Taiwan Semiconductor Manufacturing Co Ltd | Ticker: TSM | Category: Stock | Action: Purchase | Transaction Date: 2024-11-20 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    53, "semiconductors",
    "What trades in Texas Instruments (TXN) were reported in Congress?",
    "House", ["TXN"], ["Michael McCaul"],
    ["Michael McCaul", "Texas Instruments", "TXN", "Sale", "$15,001 - $50,000"],
    "Representative Michael McCaul reported a sale of Texas Instruments (TXN) stock by his spouse on January 10, 2025, in the $15,001 - $50,000 bracket.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-02-05 | Item: Texas Instruments Incorporated | Ticker: TXN | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-10 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    54, "semiconductors",
    "Did Senator John Hickenlooper disclose trades in semiconductor stocks?",
    "Senate", ["INTC"], ["John Hickenlooper"],
    ["John Hickenlooper", "Intel", "INTC", "Sale", "Spouse"],
    "Senator John Hickenlooper's spouse sold Intel Corporation shares on January 15, 2025, valued between $15,001 and $50,000.",
    ["Filer: John Hickenlooper (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-08 | Item: Intel Corporation | Ticker: INTC | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-15 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    55, "semiconductors",
    "What Broadcom (AVGO) stock trades were made by House members other than Pelosi?",
    "House", ["AVGO"], ["Ro Khanna"],
    ["Ro Khanna", "Broadcom", "AVGO", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna reported several purchases of Broadcom Inc. (AVGO) by his spouse in January 2025, each in the $1,001 - $15,000 bracket.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-14 | Item: Broadcom Inc. | Ticker: AVGO | Category: Stock | Action: Purchase | Transaction Date: 2025-01-20 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    56, "semiconductors",
    "Did Dan Crenshaw buy or sell Qualcomm (QCOM) shares?",
    "House", ["QCOM"], ["Dan Crenshaw"],
    ["Dan Crenshaw", "Qualcomm", "QCOM", "Purchase", "$1,001 - $15,000"],
    "Representative Dan Crenshaw purchased Qualcomm Inc. (QCOM) stock on December 10, 2024, valued at $1,001 - $15,000.",
    ["Filer: Dan Crenshaw (House) | Report: PTR | Filing Date: 2025-01-05 | Item: Qualcomm Inc. | Ticker: QCOM | Category: Stock | Action: Purchase | Transaction Date: 2024-12-10 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    57, "semiconductors",
    "What trades were reported in Applied Materials (AMAT)?",
    "House", ["AMAT"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Applied Materials", "AMAT", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought Applied Materials (AMAT) stock on February 2, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-02-28 | Item: Applied Materials, Inc. | Ticker: AMAT | Category: Stock | Action: Purchase | Transaction Date: 2025-02-02 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    58, "semiconductors",
    "Did Senator Rick Scott report any semiconductor ETF transactions?",
    "Senate", ["SMH", "SOXX"], ["Rick Scott"],
    ["Rick Scott", "Semiconductor ETF", "SMH", "Purchase", "Trust"],
    "Senator Rick Scott's managed trust reported purchases of VanEck Semiconductor ETF (SMH) in late 2024 valued at $50,001 - $100,000.",
    ["Filer: Rick Scott (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-15 | Item: VanEck Semiconductor ETF | Ticker: SMH | Category: ETF | Action: Purchase | Transaction Date: 2024-11-20 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: Blind trust investment"]
)
add_item(
    59, "semiconductors",
    "Were there any Arm Holdings (ARM) trades disclosed by members of Congress?",
    "House", ["ARM"], ["Ro Khanna"],
    ["Ro Khanna", "Arm Holdings", "ARM", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna reported a purchase of Arm Holdings plc (ARM) shares by his spouse on January 25, 2025, in the $1,001 - $15,000 tier.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-18 | Item: Arm Holdings plc - ADR | Ticker: ARM | Category: Stock | Action: Purchase | Transaction Date: 2025-01-25 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    60, "semiconductors",
    "What trades in Marvell Technology (MRVL) were reported?",
    "House", ["MRVL"], ["Kevin Hern"],
    ["Kevin Hern", "Marvell Technology", "MRVL", "Purchase", "$15,001 - $50,000"],
    "Representative Kevin Hern bought Marvell Technology (MRVL) shares on January 14, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-02-08 | Item: Marvell Technology, Inc. | Ticker: MRVL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-14 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    61, "semiconductors",
    "Did Tommy Tuberville sell any semiconductor positions recently?",
    "Senate", ["INTC"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Intel", "INTC", "Sale", "$50,001 - $100,000"],
    "Senator Tommy Tuberville sold Intel Corporation (INTC) stock on January 5, 2025, in the $50,001 - $100,000 bracket.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-01-30 | Item: Intel Corporation | Ticker: INTC | Category: Stock | Action: Sale (Full) | Transaction Date: 2025-01-05 | Value Range: $50,001 - $100,000 | Owner: Self | Context: None"]
)
add_item(
    62, "semiconductors",
    "Were any trades in Analog Devices (ADI) disclosed in late 2024?",
    "House", ["ADI"], ["Michael McCaul"],
    ["Michael McCaul", "Analog Devices", "ADI", "Purchase", "$15,001 - $50,000"],
    "Representative Michael McCaul's child purchased Analog Devices (ADI) stock on November 18, 2024, valued at $15,001 - $50,000.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-12-14 | Item: Analog Devices, Inc. | Ticker: ADI | Category: Stock | Action: Purchase | Transaction Date: 2024-11-18 | Value Range: $15,001 - $50,000 | Owner: Child | Context: None"]
)

# ==============================================================================
# CATEGORY 4: HEALTHCARE & PHARMA TRADES (20 ITEMS)
# ==============================================================================
add_item(
    63, "healthcare_pharma",
    "Did any members of the House Energy and Commerce Committee trade Pfizer (PFE)?",
    "House", ["PFE"], ["Diana Harshbarger"],
    ["Diana Harshbarger", "Pfizer", "PFE", "Purchase", "$1,001 - $15,000"],
    "Representative Diana Harshbarger disclosed purchasing Pfizer Inc. (PFE) stock on December 15, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Diana Harshbarger (House) | Report: PTR | Filing Date: 2025-01-10 | Item: Pfizer Inc. | Ticker: PFE | Category: Stock | Action: Purchase | Transaction Date: 2024-12-15 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)
add_item(
    64, "healthcare_pharma",
    "What trades in Eli Lilly (LLY) were reported in the Senate during 2025?",
    "Senate", ["LLY"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Eli Lilly", "LLY", "Purchase", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse purchased Eli Lilly and Company (LLY) stock on February 4, 2025, valued between $15,001 and $50,000.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-28 | Item: Eli Lilly and Company | Ticker: LLY | Category: Stock | Action: Purchase | Transaction Date: 2025-02-04 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    65, "healthcare_pharma",
    "Did Representative Ro Khanna report any trades in Johnson & Johnson (JNJ)?",
    "House", ["JNJ"], ["Ro Khanna"],
    ["Ro Khanna", "Johnson & Johnson", "JNJ", "Sale", "$1,001 - $15,000"],
    "Representative Ro Khanna reported that his spouse sold Johnson & Johnson (JNJ) stock on January 22, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-15 | Item: Johnson & Johnson | Ticker: JNJ | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-22 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    66, "healthcare_pharma",
    "What transactions in UnitedHealth Group (UNH) were disclosed by Congress?",
    "House", ["UNH"], ["Kevin Hern"],
    ["Kevin Hern", "UnitedHealth", "UNH", "Purchase", "$50,001 - $100,000"],
    "Representative Kevin Hern disclosed purchasing UnitedHealth Group (UNH) shares on January 16, 2025, valued at $50,001 - $100,000.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-02-12 | Item: UnitedHealth Group Inc. | Ticker: UNH | Category: Stock | Action: Purchase | Transaction Date: 2025-01-16 | Value Range: $50,001 - $100,000 | Owner: Joint | Context: None"]
)
add_item(
    67, "healthcare_pharma",
    "Did Senator Tommy Tuberville buy or sell Moderna (MRNA) stock?",
    "Senate", ["MRNA"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Moderna", "MRNA", "Sale", "$15,001 - $50,000"],
    "Senator Tommy Tuberville disclosed a sale of Moderna Inc. (MRNA) shares on November 20, 2024, valued at $15,001 - $50,000.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-15 | Item: Moderna, Inc. | Ticker: MRNA | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-11-20 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    68, "healthcare_pharma",
    "What trades in Merck & Co. (MRK) were reported in late 2024?",
    "House", ["MRK"], ["Michael McCaul"],
    ["Michael McCaul", "Merck", "MRK", "Purchase", "$15,001 - $50,000"],
    "Representative Michael McCaul's spouse bought Merck & Co. (MRK) stock on December 4, 2024, in the $15,001 - $50,000 range.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-12-28 | Item: Merck & Co., Inc. | Ticker: MRK | Category: Stock | Action: Purchase | Transaction Date: 2024-12-04 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    69, "healthcare_pharma",
    "Did Representative Marjorie Taylor Greene trade AbbVie (ABBV)?",
    "House", ["ABBV"], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "AbbVie", "ABBV", "Purchase", "$1,001 - $15,000"],
    "Representative Marjorie Taylor Greene purchased shares of AbbVie Inc. (ABBV) on October 25, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-11-18 | Item: AbbVie Inc. | Ticker: ABBV | Category: Stock | Action: Purchase | Transaction Date: 2024-10-25 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    70, "healthcare_pharma",
    "What Bristol-Myers Squibb (BMY) trades were reported by Senate members?",
    "Senate", ["BMY"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Bristol-Myers Squibb", "BMY", "Purchase", "$15,001 - $50,000"],
    "Senator Markwayne Mullin disclosed purchasing Bristol-Myers Squibb (BMY) on January 14, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-10 | Item: Bristol-Myers Squibb Co. | Ticker: BMY | Category: Stock | Action: Purchase | Transaction Date: 2025-01-14 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    71, "healthcare_pharma",
    "Did Josh Gottheimer trade any medical device makers like Medtronic (MDT)?",
    "House", ["MDT"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Medtronic", "MDT", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer purchased Medtronic plc (MDT) shares on January 8, 2025, in the $1,001 - $15,000 bracket.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-02-02 | Item: Medtronic plc | Ticker: MDT | Category: Stock | Action: Purchase | Transaction Date: 2025-01-08 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    72, "healthcare_pharma",
    "Were there any sales of Amgen (AMGN) stock in the House?",
    "House", ["AMGN"], ["Earl Blumenauer"],
    ["Earl Blumenauer", "Amgen", "AMGN", "Sale", "$1,001 - $15,000"],
    "Representative Earl Blumenauer's spouse sold Amgen Inc. (AMGN) stock on November 15, 2024, valued at $1,001 - $15,000.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2024-12-05 | Item: Amgen Inc. | Ticker: AMGN | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-11-15 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    73, "healthcare_pharma",
    "Did Dan Crenshaw buy any healthcare or biotech stocks in 2025?",
    "House", ["PFE"], ["Dan Crenshaw"],
    ["Dan Crenshaw", "Pfizer", "PFE", "Purchase", "$1,001 - $15,000"],
    "Representative Dan Crenshaw bought Pfizer Inc. (PFE) common stock on January 20, 2025, in the $1,001 - $15,000 bracket.",
    ["Filer: Dan Crenshaw (House) | Report: PTR | Filing Date: 2025-02-10 | Item: Pfizer Inc. | Ticker: PFE | Category: Stock | Action: Purchase | Transaction Date: 2025-01-20 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    74, "healthcare_pharma",
    "What trades in Gilead Sciences (GILD) were disclosed by Congress?",
    "House", ["GILD"], ["Diana Harshbarger"],
    ["Diana Harshbarger", "Gilead Sciences", "GILD", "Purchase", "$1,001 - $15,000"],
    "Representative Diana Harshbarger disclosed a purchase of Gilead Sciences (GILD) on January 12, 2025, valued at $1,001 - $15,000.",
    ["Filer: Diana Harshbarger (House) | Report: PTR | Filing Date: 2025-02-05 | Item: Gilead Sciences, Inc. | Ticker: GILD | Category: Stock | Action: Purchase | Transaction Date: 2025-01-12 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)
add_item(
    75, "healthcare_pharma",
    "Did Senator Sheldon Whitehouse report purchases of Thermo Fisher (TMO)?",
    "Senate", ["TMO"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Thermo Fisher", "TMO", "Purchase", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse bought Thermo Fisher Scientific (TMO) shares on February 12, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-03-08 | Item: Thermo Fisher Scientific Inc. | Ticker: TMO | Category: Stock | Action: Purchase | Transaction Date: 2025-02-12 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    76, "healthcare_pharma",
    "Were there any transactions in Vertex Pharmaceuticals (VRTX)?",
    "House", ["VRTX"], ["Ro Khanna"],
    ["Ro Khanna", "Vertex", "VRTX", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna reported that his spouse purchased Vertex Pharmaceuticals (VRTX) on January 18, 2025, in the $1,001 - $15,000 tier.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-12 | Item: Vertex Pharmaceuticals Inc. | Ticker: VRTX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    77, "healthcare_pharma",
    "What trades in Abbott Laboratories (ABT) were reported by Congress?",
    "House", ["ABT"], ["Kevin Hern"],
    ["Kevin Hern", "Abbott Laboratories", "ABT", "Purchase", "$15,001 - $50,000"],
    "Representative Kevin Hern purchased Abbott Laboratories (ABT) stock on January 25, 2025, valued between $15,001 and $50,000.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-02-20 | Item: Abbott Laboratories | Ticker: ABT | Category: Stock | Action: Purchase | Transaction Date: 2025-01-25 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    78, "healthcare_pharma",
    "Did Tommy Tuberville report any sales of pharmaceutical stocks?",
    "Senate", ["PFE"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Pfizer", "PFE", "Sale", "$15,001 - $50,000"],
    "Senator Tommy Tuberville sold Pfizer Inc. (PFE) stock on January 10, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-04 | Item: Pfizer Inc. | Ticker: PFE | Category: Stock | Action: Sale (Full) | Transaction Date: 2025-01-10 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    79, "healthcare_pharma",
    "What trades in CVS Health (CVS) were disclosed by House members?",
    "House", ["CVS"], ["Michael McCaul"],
    ["Michael McCaul", "CVS Health", "CVS", "Purchase", "$15,001 - $50,000"],
    "Representative Michael McCaul's dependent child bought CVS Health Corporation (CVS) shares on December 8, 2024, valued at $15,001 - $50,000.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-01-02 | Item: CVS Health Corporation | Ticker: CVS | Category: Stock | Action: Purchase | Transaction Date: 2024-12-08 | Value Range: $15,001 - $50,000 | Owner: Child | Context: None"]
)
add_item(
    80, "healthcare_pharma",
    "Did Senator Rick Scott report any healthcare investments through his trust?",
    "Senate", ["XLV"], ["Rick Scott"],
    ["Rick Scott", "Healthcare ETF", "XLV", "Purchase", "Trust"],
    "Senator Rick Scott's blind trust purchased Health Care Select Sector SPDR Fund (XLV) shares in late 2024 valued at $50,001 - $100,000.",
    ["Filer: Rick Scott (Senate) | Report: Periodic Disclosure | Filing Date: 2024-11-15 | Item: Health Care Select Sector SPDR Fund | Ticker: XLV | Category: ETF | Action: Purchase | Transaction Date: 2024-10-25 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: Blind trust"]
)
add_item(
    81, "healthcare_pharma",
    "Were there any trades in Stryker Corporation (SYK) reported by Congress?",
    "House", ["SYK"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Stryker", "SYK", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought Stryker Corporation (SYK) shares on January 14, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-02-08 | Item: Stryker Corporation | Ticker: SYK | Category: Stock | Action: Purchase | Transaction Date: 2025-01-14 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    82, "healthcare_pharma",
    "What trades in Regeneron Pharmaceuticals (REGN) were disclosed?",
    "House", ["REGN"], ["Diana Harshbarger"],
    ["Diana Harshbarger", "Regeneron", "REGN", "Purchase", "$1,001 - $15,000"],
    "Representative Diana Harshbarger disclosed a purchase of Regeneron (REGN) stock on February 1, 2025, in the $1,001 - $15,000 bracket.",
    ["Filer: Diana Harshbarger (House) | Report: PTR | Filing Date: 2025-02-24 | Item: Regeneron Pharmaceuticals Inc. | Ticker: REGN | Category: Stock | Action: Purchase | Transaction Date: 2025-02-01 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)

# ==============================================================================
# CATEGORY 5: ENERGY, OIL & GREEN TECH (20 ITEMS)
# ==============================================================================
add_item(
    83, "energy_materials",
    "What Chevron (CVX) purchases were reported by Senator Markwayne Mullin?",
    "Senate", ["CVX"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Chevron", "CVX", "Purchase", "$50,001 - $100,000"],
    "Senator Markwayne Mullin disclosed purchasing Chevron Corporation (CVX) stock on January 20, 2025, valued at $50,001 - $100,000.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-15 | Item: Chevron Corporation | Ticker: CVX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-20 | Value Range: $50,001 - $100,000 | Owner: Self | Context: None"]
)
add_item(
    84, "energy_materials",
    "Did Representative Kevin Hern report transactions in Exxon Mobil (XOM)?",
    "House", ["XOM"], ["Kevin Hern"],
    ["Kevin Hern", "Exxon Mobil", "XOM", "Purchase", "$100,001 - $250,000"],
    "Representative Kevin Hern disclosed purchasing Exxon Mobil Corporation (XOM) shares on February 5, 2025, in the $100,001 - $250,000 tier.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-03-01 | Item: Exxon Mobil Corporation | Ticker: XOM | Category: Stock | Action: Purchase | Transaction Date: 2025-02-05 | Value Range: $100,001 - $250,000 | Owner: Joint | Context: None"]
)
add_item(
    85, "energy_materials",
    "What ConocoPhillips (COP) trades were disclosed by members of the Senate?",
    "Senate", ["COP"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "ConocoPhillips", "COP", "Purchase", "$15,001 - $50,000"],
    "Senator Tommy Tuberville purchased ConocoPhillips (COP) stock on January 14, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-08 | Item: ConocoPhillips | Ticker: COP | Category: Stock | Action: Purchase | Transaction Date: 2025-01-14 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    86, "energy_materials",
    "Did Representative Ro Khanna disclose trades in renewable energy companies like NextEra Energy (NEE)?",
    "House", ["NEE"], ["Ro Khanna"],
    ["Ro Khanna", "NextEra Energy", "NEE", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna reported that his spouse purchased NextEra Energy (NEE) shares on January 26, 2025, in the $1,001 - $15,000 bracket.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-18 | Item: NextEra Energy, Inc. | Ticker: NEE | Category: Stock | Action: Purchase | Transaction Date: 2025-01-26 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    87, "energy_materials",
    "Were there any First Solar (FSLR) stock transactions reported in the House?",
    "House", ["FSLR"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "First Solar", "FSLR", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought First Solar, Inc. (FSLR) shares on December 18, 2024, valued at $1,001 - $15,000.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-01-10 | Item: First Solar, Inc. | Ticker: FSLR | Category: Stock | Action: Purchase | Transaction Date: 2024-12-18 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    88, "energy_materials",
    "What Occidental Petroleum (OXY) trades were reported in Congress?",
    "House", ["OXY"], ["Michael McCaul"],
    ["Michael McCaul", "Occidental Petroleum", "OXY", "Purchase", "$15,001 - $50,000"],
    "Representative Michael McCaul's spouse bought Occidental Petroleum (OXY) on January 18, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-02-12 | Item: Occidental Petroleum Corp. | Ticker: OXY | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    89, "energy_materials",
    "Did Senator Sheldon Whitehouse report any oil and gas company sales?",
    "Senate", ["XOM"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Exxon", "XOM", "Sale", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse disclosed a full sale of Exxon Mobil (XOM) shares on February 1, 2025, in the $15,001 - $50,000 tier.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-25 | Item: Exxon Mobil Corporation | Ticker: XOM | Category: Stock | Action: Sale (Full) | Transaction Date: 2025-02-01 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Divestment"]
)
add_item(
    90, "energy_materials",
    "Did Representative Marjorie Taylor Greene purchase any energy sector stocks?",
    "House", ["CVX"], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Chevron", "CVX", "Purchase", "$1,001 - $15,000"],
    "Representative Marjorie Taylor Greene purchased Chevron Corporation (CVX) shares on November 15, 2024, valued at $1,001 - $15,000.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-12-05 | Item: Chevron Corporation | Ticker: CVX | Category: Stock | Action: Purchase | Transaction Date: 2024-11-15 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    91, "energy_materials",
    "What trades in Schlumberger (SLB) were disclosed in early 2025?",
    "Senate", ["SLB"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Schlumberger", "SLB", "Purchase", "$15,001 - $50,000"],
    "Senator Markwayne Mullin reported purchasing Schlumberger Limited (SLB) stock on January 24, 2025, valued at $15,001 - $50,000.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-18 | Item: Schlumberger Limited | Ticker: SLB | Category: Stock | Action: Purchase | Transaction Date: 2025-01-24 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    92, "energy_materials",
    "Did Dan Crenshaw buy or sell any energy stocks recently?",
    "House", ["COP"], ["Dan Crenshaw"],
    ["Dan Crenshaw", "ConocoPhillips", "COP", "Purchase", "$1,001 - $15,000"],
    "Representative Dan Crenshaw purchased ConocoPhillips (COP) stock on December 20, 2024, in the $1,001 - $15,000 bracket.",
    ["Filer: Dan Crenshaw (House) | Report: PTR | Filing Date: 2025-01-14 | Item: ConocoPhillips | Ticker: COP | Category: Stock | Action: Purchase | Transaction Date: 2024-12-20 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    93, "energy_materials",
    "Were there any trades in Enphase Energy (ENPH) disclosed by Congress?",
    "House", ["ENPH"], ["Ro Khanna"],
    ["Ro Khanna", "Enphase Energy", "ENPH", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna disclosed a spousal purchase of Enphase Energy (ENPH) on January 10, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-04 | Item: Enphase Energy, Inc. | Ticker: ENPH | Category: Stock | Action: Purchase | Transaction Date: 2025-01-10 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    94, "energy_materials",
    "What trades in Devon Energy (DVN) were reported by Representative Kevin Hern?",
    "House", ["DVN"], ["Kevin Hern"],
    ["Kevin Hern", "Devon Energy", "DVN", "Purchase", "$50,001 - $100,000"],
    "Representative Kevin Hern disclosed purchasing Devon Energy (DVN) shares on January 29, 2025, in the $50,001 - $100,000 tier.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-02-22 | Item: Devon Energy Corporation | Ticker: DVN | Category: Stock | Action: Purchase | Transaction Date: 2025-01-29 | Value Range: $50,001 - $100,000 | Owner: Joint | Context: None"]
)
add_item(
    95, "energy_materials",
    "Did Tommy Tuberville report any sales of Exxon Mobil (XOM)?",
    "Senate", ["XOM"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Exxon Mobil", "XOM", "Sale", "$15,001 - $50,000"],
    "Senator Tommy Tuberville reported selling Exxon Mobil shares on December 28, 2024, valued at $15,001 - $50,000.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-01-20 | Item: Exxon Mobil Corporation | Ticker: XOM | Category: Stock | Action: Sale (Partial) | Transaction Date: 2024-12-28 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    96, "energy_materials",
    "What trades in Baker Hughes (BKR) were disclosed in late 2024?",
    "House", ["BKR"], ["Michael McCaul"],
    ["Michael McCaul", "Baker Hughes", "BKR", "Purchase", "$15,001 - $50,000"],
    "Representative Michael McCaul's spouse bought Baker Hughes Company (BKR) on November 25, 2024, in the $15,001 - $50,000 bracket.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-12-20 | Item: Baker Hughes Company | Ticker: BKR | Category: Stock | Action: Purchase | Transaction Date: 2024-11-25 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    97, "energy_materials",
    "Did Senator John Hickenlooper disclose any trades in energy utility stocks?",
    "Senate", ["SO"], ["John Hickenlooper"],
    ["John Hickenlooper", "Southern Company", "SO", "Sale", "Spouse"],
    "Senator John Hickenlooper's spouse sold Southern Company (SO) stock on January 18, 2025, valued at $15,001 - $50,000.",
    ["Filer: John Hickenlooper (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-12 | Item: The Southern Company | Ticker: SO | Category: Stock | Action: Sale (Full) | Transaction Date: 2025-01-18 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    98, "energy_materials",
    "What trades in Kinder Morgan (KMI) were reported in the House?",
    "House", ["KMI"], ["Earl Blumenauer"],
    ["Earl Blumenauer", "Kinder Morgan", "KMI", "Sale", "$1,001 - $15,000"],
    "Representative Earl Blumenauer's spouse sold Kinder Morgan Inc. (KMI) on October 20, 2024, valued at $1,001 - $15,000.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2024-11-08 | Item: Kinder Morgan, Inc. | Ticker: KMI | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-10-20 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    99, "energy_materials",
    "Did Josh Gottheimer buy shares in clean energy or uranium stocks?",
    "House", ["CCJ"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Cameco", "CCJ", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought Cameco Corporation (CCJ) shares on January 16, 2025, in the $1,001 - $15,000 tier.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-02-08 | Item: Cameco Corporation | Ticker: CCJ | Category: Stock | Action: Purchase | Transaction Date: 2025-01-16 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    100, "energy_materials",
    "What Energy Select Sector SPDR (XLE) trades were reported in the Senate?",
    "Senate", ["XLE"], ["Rick Scott"],
    ["Rick Scott", "Energy ETF", "XLE", "Purchase", "Trust"],
    "Senator Rick Scott's blind trust reported purchasing Energy Select Sector SPDR Fund (XLE) shares on November 14, 2024, in the $50,001 - $100,000 range.",
    ["Filer: Rick Scott (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-08 | Item: Energy Select Sector SPDR Fund | Ticker: XLE | Category: ETF | Action: Purchase | Transaction Date: 2024-11-14 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: Blind trust"]
)
add_item(
    101, "energy_materials",
    "Did Representative Kevin Hern trade Pioneer Natural Resources before or after acquisition?",
    "House", ["PXD"], ["Kevin Hern"],
    ["Kevin Hern", "Pioneer Natural Resources", "PXD", "Exchange", "Merged"],
    "Representative Kevin Hern disclosed an exchange of Pioneer Natural Resources (PXD) shares into Exxon Mobil (XOM) following the corporate merger.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2024-06-15 | Item: Pioneer Natural Resources Co. | Ticker: PXD | Category: Stock | Action: Exchange | Transaction Date: 2024-05-03 | Value Range: $100,001 - $250,000 | Owner: Joint | Context: Merger exchange into XOM"]
)
add_item(
    102, "energy_materials",
    "Were there any Brookfield Renewable (BEPC) trades reported?",
    "House", ["BEPC"], ["Ro Khanna"],
    ["Ro Khanna", "Brookfield Renewable", "BEPC", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna reported that his spouse purchased Brookfield Renewable Corp. (BEPC) on December 12, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-01-05 | Item: Brookfield Renewable Corp. | Ticker: BEPC | Category: Stock | Action: Purchase | Transaction Date: 2024-12-12 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)

# ==============================================================================
# CATEGORY 6: FINANCIAL & BANKING TRADES (20 ITEMS)
# ==============================================================================
add_item(
    103, "financial_banking",
    "Did members of the House Financial Services Committee trade JPMorgan Chase (JPM)?",
    "House", ["JPM"], ["French Hill"],
    ["French Hill", "JPMorgan Chase", "JPM", "Purchase", "$15,001 - $50,000"],
    "Representative French Hill disclosed a purchase of JPMorgan Chase & Co. (JPM) stock on January 15, 2025, in the $15,001 - $50,000 range.",
    ["Filer: French Hill (House) | Report: PTR | Filing Date: 2025-02-10 | Item: JPMorgan Chase & Co. | Ticker: JPM | Category: Stock | Action: Purchase | Transaction Date: 2025-01-15 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    104, "financial_banking",
    "What Goldman Sachs (GS) trades were reported by Senator Tommy Tuberville?",
    "Senate", ["GS"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Goldman Sachs", "GS", "Purchase", "$50,001 - $100,000"],
    "Senator Tommy Tuberville bought The Goldman Sachs Group, Inc. (GS) stock on February 10, 2025, valued between $50,001 and $100,000.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-03-02 | Item: The Goldman Sachs Group, Inc. | Ticker: GS | Category: Stock | Action: Purchase | Transaction Date: 2025-02-10 | Value Range: $50,001 - $100,000 | Owner: Self | Context: None"]
)
add_item(
    105, "financial_banking",
    "Did Representative Ro Khanna disclose trades in Morgan Stanley (MS)?",
    "House", ["MS"], ["Ro Khanna"],
    ["Ro Khanna", "Morgan Stanley", "MS", "Sale", "$1,001 - $15,000"],
    "Representative Ro Khanna reported that his spouse sold Morgan Stanley (MS) stock on January 24, 2025, in the $1,001 - $15,000 bracket.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-16 | Item: Morgan Stanley | Ticker: MS | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-24 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    106, "financial_banking",
    "What Bank of America (BAC) transactions were reported in the House during late 2024?",
    "House", ["BAC"], ["Kevin Hern"],
    ["Kevin Hern", "Bank of America", "BAC", "Purchase", "$50,001 - $100,000"],
    "Representative Kevin Hern disclosed purchasing Bank of America Corp. (BAC) shares on December 14, 2024, in the $50,001 - $100,000 tier.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-01-08 | Item: Bank of America Corporation | Ticker: BAC | Category: Stock | Action: Purchase | Transaction Date: 2024-12-14 | Value Range: $50,001 - $100,000 | Owner: Joint | Context: None"]
)
add_item(
    107, "financial_banking",
    "Did Senator Sheldon Whitehouse report any trades in Visa (V) or Mastercard (MA)?",
    "Senate", ["V", "MA"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Visa", "V", "Purchase", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse purchased Visa Inc. (V) common stock on January 16, 2025, in the $15,001 - $50,000 tier.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-10 | Item: Visa Inc. Class A | Ticker: V | Category: Stock | Action: Purchase | Transaction Date: 2025-01-16 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    108, "financial_banking",
    "What Citigroup (C) trades were reported by members of Congress?",
    "House", ["C"], ["Michael McCaul"],
    ["Michael McCaul", "Citigroup", "C", "Sale", "$15,001 - $50,000"],
    "Representative Michael McCaul's spouse sold Citigroup Inc. (C) shares on November 20, 2024, valued at $15,001 - $50,000.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-12-15 | Item: Citigroup Inc. | Ticker: C | Category: Stock | Action: Sale (Partial) | Transaction Date: 2024-11-20 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    109, "financial_banking",
    "Did Representative Josh Gottheimer trade Berkshire Hathaway (BRK.B)?",
    "House", ["BRK.B"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Berkshire Hathaway", "BRK.B", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought Berkshire Hathaway Inc. Class B (BRK.B) on January 12, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-02-05 | Item: Berkshire Hathaway Inc. Cl B | Ticker: BRK.B | Category: Stock | Action: Purchase | Transaction Date: 2025-01-12 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    110, "financial_banking",
    "Were there any Wells Fargo (WFC) stock transactions reported in the Senate?",
    "Senate", ["WFC"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Wells Fargo", "WFC", "Purchase", "$15,001 - $50,000"],
    "Senator Markwayne Mullin disclosed purchasing Wells Fargo & Company (WFC) on February 2, 2025, valued at $15,001 - $50,000.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-24 | Item: Wells Fargo & Company | Ticker: WFC | Category: Stock | Action: Purchase | Transaction Date: 2025-02-02 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    111, "financial_banking",
    "Did Dan Crenshaw buy or sell shares of Charles Schwab (SCHW)?",
    "House", ["SCHW"], ["Dan Crenshaw"],
    ["Dan Crenshaw", "Charles Schwab", "SCHW", "Purchase", "$1,001 - $15,000"],
    "Representative Dan Crenshaw purchased The Charles Schwab Corporation (SCHW) on January 8, 2025, in the $1,001 - $15,000 bracket.",
    ["Filer: Dan Crenshaw (House) | Report: PTR | Filing Date: 2025-01-30 | Item: The Charles Schwab Corporation | Ticker: SCHW | Category: Stock | Action: Purchase | Transaction Date: 2025-01-08 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    112, "financial_banking",
    "What trades in BlackRock (BLK) were disclosed by House members?",
    "House", ["BLK"], ["Ro Khanna"],
    ["Ro Khanna", "BlackRock", "BLK", "Purchase", "$1,001 - $15,000"],
    "Representative Ro Khanna reported that his spouse bought BlackRock, Inc. (BLK) on January 15, 2025, in the $1,001 - $15,000 range.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-08 | Item: BlackRock, Inc. | Ticker: BLK | Category: Stock | Action: Purchase | Transaction Date: 2025-01-15 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    113, "financial_banking",
    "Did Marjorie Taylor Greene report any banking sector purchases in 2024?",
    "House", ["JPM"], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "JPMorgan", "JPM", "Purchase", "$1,001 - $15,000"],
    "Representative Marjorie Taylor Greene purchased JPMorgan Chase (JPM) shares on November 8, 2024, valued at $1,001 - $15,000.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-11-28 | Item: JPMorgan Chase & Co. | Ticker: JPM | Category: Stock | Action: Purchase | Transaction Date: 2024-11-08 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    114, "financial_banking",
    "What trades in American Express (AXP) were reported by Congress?",
    "House", ["AXP"], ["Michael McCaul"],
    ["Michael McCaul", "American Express", "AXP", "Purchase", "$15,001 - $50,000"],
    "Representative Michael McCaul's dependent child bought American Express Co. (AXP) on December 1, 2024, in the $15,001 - $50,000 bracket.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-12-22 | Item: American Express Company | Ticker: AXP | Category: Stock | Action: Purchase | Transaction Date: 2024-12-01 | Value Range: $15,001 - $50,000 | Owner: Child | Context: None"]
)
add_item(
    115, "financial_banking",
    "Did Tommy Tuberville sell any regional bank stocks?",
    "Senate", ["USB"], ["Tommy Tuberville"],
    ["Tommy Tuberville", "U.S. Bancorp", "USB", "Sale", "$15,001 - $50,000"],
    "Senator Tommy Tuberville sold U.S. Bancorp (USB) stock on January 22, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-14 | Item: U.S. Bancorp | Ticker: USB | Category: Stock | Action: Sale (Full) | Transaction Date: 2025-01-22 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    116, "financial_banking",
    "What Financial Select Sector SPDR (XLF) trades were disclosed in the Senate?",
    "Senate", ["XLF"], ["Rick Scott"],
    ["Rick Scott", "Financial ETF", "XLF", "Purchase", "Trust"],
    "Senator Rick Scott's blind trust bought Financial Select Sector SPDR Fund (XLF) on December 5, 2024, valued at $50,001 - $100,000.",
    ["Filer: Rick Scott (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-30 | Item: Financial Select Sector SPDR Fund | Ticker: XLF | Category: ETF | Action: Purchase | Transaction Date: 2024-12-05 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: Blind trust account"]
)
add_item(
    117, "financial_banking",
    "Did Representative Kevin Hern trade PayPal Holdings (PYPL)?",
    "House", ["PYPL"], ["Kevin Hern"],
    ["Kevin Hern", "PayPal", "PYPL", "Purchase", "$15,001 - $50,000"],
    "Representative Kevin Hern bought PayPal Holdings (PYPL) stock on January 10, 2025, in the $15,001 - $50,000 bracket.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-02-04 | Item: PayPal Holdings, Inc. | Ticker: PYPL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-10 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    118, "financial_banking",
    "Were there any sales of Mastercard (MA) reported in the House?",
    "House", ["MA"], ["Earl Blumenauer"],
    ["Earl Blumenauer", "Mastercard", "MA", "Sale", "$1,001 - $15,000"],
    "Representative Earl Blumenauer's spouse sold Mastercard Inc. (MA) on November 10, 2024, in the $1,001 - $15,000 range.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2024-12-01 | Item: Mastercard Incorporated | Ticker: MA | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-11-10 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    119, "financial_banking",
    "Did Senator Sheldon Whitehouse report purchases of Goldman Sachs?",
    "Senate", ["GS"], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Goldman Sachs", "GS", "Purchase", "$15,001 - $50,000"],
    "Senator Sheldon Whitehouse purchased The Goldman Sachs Group, Inc. (GS) on February 14, 2025, in the $15,001 - $50,000 range.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-03-08 | Item: The Goldman Sachs Group, Inc. | Ticker: GS | Category: Stock | Action: Purchase | Transaction Date: 2025-02-14 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    120, "financial_banking",
    "What trades in S&P Global (SPGI) were reported by Congress?",
    "House", ["SPGI"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "S&P Global", "SPGI", "Purchase", "$1,001 - $15,000"],
    "Representative Josh Gottheimer bought S&P Global Inc. (SPGI) on January 20, 2025, in the $1,001 - $15,000 tier.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-02-14 | Item: S&P Global Inc. | Ticker: SPGI | Category: Stock | Action: Purchase | Transaction Date: 2025-01-20 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    121, "financial_banking",
    "Did John Hickenlooper's spouse trade any banking stocks?",
    "Senate", ["JPM"], ["John Hickenlooper"],
    ["John Hickenlooper", "JPMorgan", "JPM", "Sale", "Spouse"],
    "Senator John Hickenlooper's spouse sold JPMorgan Chase & Co. (JPM) on January 26, 2025, valued at $15,001 - $50,000.",
    ["Filer: John Hickenlooper (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-18 | Item: JPMorgan Chase & Co. | Ticker: JPM | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-26 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    122, "financial_banking",
    "Did Representative French Hill trade any regional bank ETF shares?",
    "House", ["KRE"], ["French Hill"],
    ["French Hill", "Regional Banking ETF", "KRE", "Purchase", "$1,001 - $15,000"],
    "Representative French Hill purchased SPDR S&P Regional Banking ETF (KRE) on December 18, 2024, valued at $1,001 - $15,000.",
    ["Filer: French Hill (House) | Report: PTR | Filing Date: 2025-01-12 | Item: SPDR S&P Regional Banking ETF | Ticker: KRE | Category: ETF | Action: Purchase | Transaction Date: 2024-12-18 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)

# ==============================================================================
# CATEGORY 7: PROMINENT MEMBER PROFILES (25 ITEMS)
# ==============================================================================
add_item(
    123, "prominent_members",
    "What are the largest single transactions reported by Nancy Pelosi's household?",
    "House", ["NVDA", "MSFT", "AAPL", "AVGO"], ["Nancy Pelosi"],
    ["Nancy Pelosi", "$1,000,001 - $5,000,000", "Call Options", "Spouse", "NVIDIA"],
    "Nancy Pelosi's largest disclosures are spousal purchases of NVIDIA (NVDA), Broadcom (AVGO), and Microsoft (MSFT) call options, each falling in the $1,000,001 - $5,000,000 bracket.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: Option exercise"]
)
add_item(
    124, "prominent_members",
    "How frequently does Representative Ro Khanna report stock trades?",
    "House", [], ["Ro Khanna"],
    ["Ro Khanna", "Frequent", "Spouse", "Child", "High Volume", "$1,001 - $15,000"],
    "Representative Ro Khanna files frequent periodic transaction reports, often dozens per month, primarily representing spousal and dependent child trades in tech and healthcare.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-15 | Item: Apple Inc. - Common Stock | Ticker: AAPL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $1,001 - $15,000 | Owner: Child | Context: None"]
)
add_item(
    125, "prominent_members",
    "What sectors does Representative Michael McCaul's family actively trade in?",
    "House", [], ["Michael McCaul"],
    ["Michael McCaul", "Technology", "Defense", "Energy", "Spouse", "High Volume"],
    "Michael McCaul's disclosures show heavy activity across tech (GOOGL, TSM), defense (NOC, GD), and energy (OXY, BKR), mostly executed by his spouse and dependent children.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-01-08 | Item: Taiwan Semiconductor Mfg. Co. | Ticker: TSM | Category: Stock | Action: Purchase | Transaction Date: 2024-12-12 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: ADR"]
)
add_item(
    126, "prominent_members",
    "What is the trading style and volume of Senator Tommy Tuberville?",
    "Senate", [], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Frequent", "Direct Ownership", "Defense", "Commodities", "Tech"],
    "Senator Tommy Tuberville trades frequently under direct ownership ('Self'), regularly buying and selling defense contractors (RTX, LMT), tech (MSFT, AMD), and energy stocks.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-20 | Item: RTX Corporation | Ticker: RTX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    127, "prominent_members",
    "Does Senator Sheldon Whitehouse trade directly or through a manager?",
    "Senate", [], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Self", "Direct Ownership", "Periodic Disclosure"],
    "Senator Sheldon Whitehouse discloses trades under direct ownership ('Self'), covering equities across healthcare, technology, and financials.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-14 | Item: Meta Platforms, Inc. | Ticker: META | Category: Stock | Action: Purchase | Transaction Date: 2025-01-22 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    128, "prominent_members",
    "What types of transactions does Representative Josh Gottheimer execute?",
    "House", [], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Options", "Equities", "Short-term", "High Frequency"],
    "Representative Josh Gottheimer discloses both equities and options trades (including call options on tech stocks like AMZN and PLTR), primarily owned directly.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-04-10 | Item: Amazon.com Inc. Call Options | Ticker: AMZN | Category: Option | Action: Purchase | Transaction Date: 2025-03-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Call option"]
)
add_item(
    129, "prominent_members",
    "What is the ownership structure of Senator Rick Scott's reported assets?",
    "Senate", [], ["Rick Scott"],
    ["Rick Scott", "Blind Trust", "Spouse", "Managed Account"],
    "Senator Rick Scott holds assets and reports transactions primarily through a qualified blind trust and accounts managed on behalf of his spouse.",
    ["Filer: Rick Scott (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-15 | Item: VanEck Semiconductor ETF | Ticker: SMH | Category: ETF | Action: Purchase | Transaction Date: 2024-11-20 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: Blind trust investment"]
)
add_item(
    130, "prominent_members",
    "What are the typical transaction sizes reported by Representative Kevin Hern?",
    "House", [], ["Kevin Hern"],
    ["Kevin Hern", "$15,001 - $50,000", "$50,001 - $100,000", "$100,001 - $250,000", "Joint"],
    "Representative Kevin Hern typically reports medium to large transactions in the $15,001 - $50,000, $50,001 - $100,000, and $100,001 - $250,000 ranges, usually held jointly.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-03-01 | Item: Exxon Mobil Corporation | Ticker: XOM | Category: Stock | Action: Purchase | Transaction Date: 2025-02-05 | Value Range: $100,001 - $250,000 | Owner: Joint | Context: None"]
)
add_item(
    131, "prominent_members",
    "Did Representative Marjorie Taylor Greene increase or decrease equity holdings in 2024?",
    "House", [], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Purchases", "Net Buyer", "Tech", "Defense", "Energy"],
    "Representative Marjorie Taylor Greene was a consistent net buyer in late 2024, acquiring positions across tech (PLTR, MSFT), defense (LMT), and banking (JPM).",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-11-14 | Item: Palantir Technologies Inc. Cl A | Ticker: PLTR | Category: Stock | Action: Purchase | Transaction Date: 2024-10-22 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    132, "prominent_members",
    "What trades has Representative Dan Crenshaw reported recently?",
    "House", [], ["Dan Crenshaw"],
    ["Dan Crenshaw", "Purchase", "$1,001 - $15,000", "Amazon", "Boeing", "ConocoPhillips"],
    "Representative Dan Crenshaw reported selective equity purchases in the $1,001 - $15,000 range, including Amazon, Boeing, and ConocoPhillips.",
    ["Filer: Dan Crenshaw (House) | Report: PTR | Filing Date: 2024-12-05 | Item: Amazon.com, Inc. | Ticker: AMZN | Category: Stock | Action: Purchase | Transaction Date: 2024-11-15 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    133, "prominent_members",
    "What was the total volume traded by Markwayne Mullin in Q1 2025?",
    "Senate", [], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Q1 2025", "Energy", "Tech", "Financials", "$15,001 - $50,000"],
    "Senator Markwayne Mullin reported over $300,000 in trades during Q1 2025 across multiple sectors including Chevron, Alphabet, and Bristol-Myers Squibb.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-15 | Item: Chevron Corporation | Ticker: CVX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-20 | Value Range: $50,001 - $100,000 | Owner: Self | Context: None"]
)
add_item(
    134, "prominent_members",
    "Does Nancy Pelosi trade individual municipal bonds or strictly equities?",
    "House", [], ["Nancy Pelosi"],
    ["Nancy Pelosi", "Equities", "Call Options", "Mega-cap Tech", "No Municipal Bonds"],
    "Nancy Pelosi's filings consist almost entirely of mega-cap tech common stocks and call options, with no recent individual municipal bond transactions.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: None"]
)
add_item(
    135, "prominent_members",
    "What are Earl Blumenauer's reported transactions characterized by?",
    "House", [], ["Earl Blumenauer"],
    ["Earl Blumenauer", "Spouse", "Full Sales", "Divestment", "Retirement"],
    "Representative Earl Blumenauer's disclosures are characterized primarily by full sales ('Sale (Full)') executed by his spouse ahead of his retirement.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2024-12-05 | Item: Amgen Inc. | Ticker: AMGN | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-11-15 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    136, "prominent_members",
    "Did Senator Mark Warner disclose any venture capital or private fund transactions?",
    "Senate", [], ["Mark Warner"],
    ["Mark Warner", "Private Fund", "Limited Partnership", "Venture Capital"],
    "Senator Mark Warner's disclosures contain periodic distributions and capital calls related to private equity and venture capital partnership interests.",
    ["Filer: Mark Warner (Senate) | Report: Periodic Disclosure | Filing Date: 2025-01-22 | Item: Columbia Capital Technology Partners | Ticker: N/A | Category: Other Securities | Action: Purchase | Transaction Date: 2024-12-30 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Capital call"]
)
add_item(
    137, "prominent_members",
    "What trades has Representative Diana Harshbarger reported?",
    "House", [], ["Diana Harshbarger"],
    ["Diana Harshbarger", "Healthcare", "Pharmaceuticals", "Joint Ownership"],
    "Representative Diana Harshbarger frequently discloses transactions in pharmaceuticals and healthcare companies (PFE, GILD, REGN) held jointly.",
    ["Filer: Diana Harshbarger (House) | Report: PTR | Filing Date: 2025-01-10 | Item: Pfizer Inc. | Ticker: PFE | Category: Stock | Action: Purchase | Transaction Date: 2024-12-15 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)
add_item(
    138, "prominent_members",
    "How does Senator Thomas Carper disclose transactions?",
    "Senate", [], ["Thomas Carper"],
    ["Thomas Carper", "Spouse", "Periodic Disclosure", "ETFs", "Mutual Funds"],
    "Senator Thomas Carper discloses trades executed almost entirely by his spouse, focusing on index ETFs and diversified mutual funds.",
    ["Filer: Thomas Carper (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-18 | Item: Vanguard S&P 500 ETF | Ticker: VOO | Category: ETF | Action: Purchase | Transaction Date: 2024-11-25 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    139, "prominent_members",
    "Did Representative Blake Moore report any trades in tech companies?",
    "House", ["MSFT"], ["Blake Moore"],
    ["Blake Moore", "Microsoft", "MSFT", "Purchase", "Joint"],
    "Representative Blake Moore reported purchasing Microsoft (MSFT) shares on October 18, 2024, valued at $1,001 - $15,000 under joint ownership.",
    ["Filer: Blake Moore (House) | Report: PTR | Filing Date: 2024-11-05 | Item: Microsoft Corporation | Ticker: MSFT | Category: Stock | Action: Purchase | Transaction Date: 2024-10-18 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)
add_item(
    140, "prominent_members",
    "What is the average transaction value reported by Representative Ro Khanna?",
    "House", [], ["Ro Khanna"],
    ["Ro Khanna", "Average Value", "$1,001 - $15,000", "Small Value", "High Frequency"],
    "The vast majority of transactions reported by Representative Ro Khanna fall in the lowest reporting bracket: $1,001 - $15,000.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-05 | Item: Apple Inc. - Common Stock | Ticker: AAPL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $1,001 - $15,000 | Owner: Child | Context: None"]
)
add_item(
    141, "prominent_members",
    "What types of assets does Senator John Hickenlooper disclose?",
    "Senate", [], ["John Hickenlooper"],
    ["John Hickenlooper", "Spouse", "Equities", "Sales", "Divestment"],
    "Senator John Hickenlooper discloses equities trades executed by his spouse, including sales in Amazon, Intel, and Southern Company.",
    ["Filer: John Hickenlooper (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-22 | Item: Amazon.com Inc. | Ticker: AMZN | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-29 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    142, "prominent_members",
    "Did Representative Rob Wittman trade in any non-defense sectors?",
    "House", ["JPM"], ["Rob Wittman"],
    ["Rob Wittman", "JPMorgan", "JPM", "Purchase", "Spouse"],
    "Representative Rob Wittman's spouse purchased JPMorgan Chase (JPM) on January 10, 2025, valued at $1,001 - $15,000.",
    ["Filer: Rob Wittman (House) | Report: PTR | Filing Date: 2025-02-02 | Item: JPMorgan Chase & Co. | Ticker: JPM | Category: Stock | Action: Purchase | Transaction Date: 2025-01-10 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    143, "prominent_members",
    "Does Tommy Tuberville trade options or only common stock?",
    "Senate", [], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Common Stock", "Options", "Puts", "Calls"],
    "Senator Tommy Tuberville trades predominantly common stocks, but has also disclosed options contracts (puts and calls) on indices and single stocks.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-20 | Item: RTX Corporation | Ticker: RTX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    144, "prominent_members",
    "What was Josh Gottheimer's highest value trade in early 2025?",
    "House", ["AMZN"], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Amazon", "AMZN", "$15,001 - $50,000", "Call Option"],
    "Representative Josh Gottheimer's highest value trade in early 2025 was a purchase of Amazon call options in the $15,001 - $50,000 tier.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-04-10 | Item: Amazon.com Inc. Call Options | Ticker: AMZN | Category: Option | Action: Purchase | Transaction Date: 2025-03-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Strike $190"]
)
add_item(
    145, "prominent_members",
    "Did Michael McCaul report trades in artificial intelligence infrastructure stocks?",
    "House", ["TSM", "GOOGL"], ["Michael McCaul"],
    ["Michael McCaul", "Taiwan Semiconductor", "TSM", "Alphabet", "GOOGL", "Purchase"],
    "Representative Michael McCaul reported spousal trades in major AI supply-chain leaders, including Taiwan Semiconductor (TSM) and Alphabet (GOOGL).",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-01-08 | Item: Taiwan Semiconductor Mfg. Co. | Ticker: TSM | Category: Stock | Action: Purchase | Transaction Date: 2024-12-12 | Value Range: $50,001 - $100,000 | Owner: Spouse | Context: ADR"]
)
add_item(
    146, "prominent_members",
    "What is the general breakdown of Nancy Pelosi's asset holdings?",
    "House", [], ["Nancy Pelosi"],
    ["Nancy Pelosi", "Mega-Cap Tech", "Real Estate", "Venture Funds", "Spouse"],
    "Nancy Pelosi's portfolio is heavily concentrated in publicly traded mega-cap tech equities (NVDA, MSFT, AAPL, GOOGL), commercial real estate, and venture funds through her spouse.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: None"]
)
add_item(
    147, "prominent_members",
    "Did Kevin Hern disclose any trades in commercial banks in 2025?",
    "House", ["BAC"], ["Kevin Hern"],
    ["Kevin Hern", "Bank of America", "BAC", "Purchase", "$50,001 - $100,000"],
    "Representative Kevin Hern disclosed purchasing Bank of America (BAC) shares on December 14, 2024, valued at $50,001 - $100,000.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-01-08 | Item: Bank of America Corporation | Ticker: BAC | Category: Stock | Action: Purchase | Transaction Date: 2024-12-14 | Value Range: $50,001 - $100,000 | Owner: Joint | Context: None"]
)

# ==============================================================================
# CATEGORY 8: STOCK ACT COMPLIANCE & LATE FILINGS (18 ITEMS)
# ==============================================================================
add_item(
    148, "stock_act_compliance",
    "What is the statutory deadline under the STOCK Act for filing a Periodic Transaction Report?",
    "Combined", [], [],
    ["STOCK Act", "30 days", "45 days", "Deadline", "PTR"],
    "Under the STOCK Act, members must report transactions within 30 days of receiving notice, but no later than 45 days after the trade execution date.",
    ["Filer: Guidance (Combined) | Report: Rule | Filing Date: 2025-01-01 | Item: STOCK Act Compliance Rule | Ticker: N/A | Category: Rule | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: 30 days from notice, 45 days max from transaction date"]
)
add_item(
    149, "stock_act_compliance",
    "Which members of Congress had filings reported more than 45 days after the trade date?",
    "House", [], ["Michael McCaul"],
    ["Late Filing", "45 days", "Michael McCaul", "Violation"],
    "Representative Michael McCaul reported a transaction executed on September 15, 2024, but filed on November 10, 2024 (56 days later), exceeding the 45-day statutory limit.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-11-10 | Item: General Dynamics | Ticker: GD | Category: Stock | Action: Sale (Partial) | Transaction Date: 2024-09-15 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: Late filing 56 days"]
)
add_item(
    150, "stock_act_compliance",
    "Did Tommy Tuberville have any late disclosures under the STOCK Act in 2024?",
    "Senate", [], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Late Filing", ">45 days", "STOCK Act"],
    "Senator Tommy Tuberville disclosed several trades in 2024 that were filed past the 45-day window, resulting in standard late filing penalty assessments.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-20 | Item: Lockheed Martin Corp. | Ticker: LMT | Category: Stock | Action: Purchase | Transaction Date: 2024-10-15 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Filed 66 days after trade"]
)
add_item(
    151, "stock_act_compliance",
    "What is the penalty for filing a late transaction report under House ethics rules?",
    "House", [], [],
    ["Penalty", "$200", "Late Fee", "House Ethics", "30 days"],
    "The standard penalty for failing to file a Periodic Transaction Report within the statutory window is a $200 late fee, unless waived by the Committee on Ethics.",
    ["Filer: Ethics (House) | Report: Policy | Filing Date: 2025-01-01 | Item: House Ethics Rule 26 | Ticker: N/A | Category: Policy | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: $200 late fee payable to US Treasury"]
)
add_item(
    152, "stock_act_compliance",
    "Were Nancy Pelosi's NVIDIA option disclosures filed in compliance with the STOCK Act timeline?",
    "House", ["NVDA"], ["Nancy Pelosi"],
    ["Nancy Pelosi", "Timely", "14 days", "Compliant", "STOCK Act"],
    "Yes, Nancy Pelosi's transaction occurred on March 1, 2025, and was filed on March 15, 2025 (14 days later), well within the 45-day limit.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: Exercise of call options"]
)
add_item(
    153, "stock_act_compliance",
    "Did Senator Markwayne Mullin file his Q1 2025 transactions on time?",
    "Senate", [], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Timely", "Under 30 days", "Compliant"],
    "Senator Markwayne Mullin's transactions in January 2025 were filed in mid-February 2025, averaging 20-25 days from execution to filing, complying with the STOCK Act.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-15 | Item: Chevron Corporation | Ticker: CVX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-20 | Value Range: $50,001 - $100,000 | Owner: Self | Context: None"]
)
add_item(
    154, "stock_act_compliance",
    "What disclosure filing delay was recorded for Diana Harshbarger's Pfizer trade?",
    "House", ["PFE"], ["Diana Harshbarger"],
    ["Diana Harshbarger", "26 days", "Compliant", "Under 45 days"],
    "Representative Diana Harshbarger executed the trade on December 15, 2024, and filed on January 10, 2025, a delay of 26 days, which is within the 45-day deadline.",
    ["Filer: Diana Harshbarger (House) | Report: PTR | Filing Date: 2025-01-10 | Item: Pfizer Inc. | Ticker: PFE | Category: Stock | Action: Purchase | Transaction Date: 2024-12-15 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)
add_item(
    155, "stock_act_compliance",
    "Are trades executed by an independent financial adviser exempt from the 45-day STOCK Act rule?",
    "Combined", [], [],
    ["No Exemption", "Financial Adviser", "45 days", "STOCK Act", "Mandatory"],
    "No, trades executed by a third-party adviser or spouse remain subject to the maximum 45-day reporting requirement, unless held in a qualified certified blind trust.",
    ["Filer: Ethics (Combined) | Report: Rules | Filing Date: 2025-01-01 | Item: Blind Trust Exemption Guidelines | Ticker: N/A | Category: Rule | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Managed accounts without certified blind trust status must be disclosed within 45 days"]
)
add_item(
    156, "stock_act_compliance",
    "What was the longest filing lag observed for a Senate disclosure in 2024?",
    "Senate", [], [],
    ["Filing Lag", "Late Disclosure", ">60 days", "Senate Ethics"],
    "Several disclosures in the Senate were filed more than 60 days post-trade, requiring amendment filings and formal explanation letters to the Senate Select Committee on Ethics.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2024-12-20 | Item: Lockheed Martin Corp. | Ticker: LMT | Category: Stock | Action: Purchase | Transaction Date: 2024-10-15 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Filed 66 days after trade"]
)
add_item(
    157, "stock_act_compliance",
    "Did Josh Gottheimer maintain timely compliance with his options trades?",
    "House", [], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Compliant", "Timely", "Under 30 days"],
    "Representative Josh Gottheimer's options transactions were filed within 16 to 24 days of execution, satisfying the STOCK Act's 45-day limit.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-04-10 | Item: Amazon.com Inc. Call Options | Ticker: AMZN | Category: Option | Action: Purchase | Transaction Date: 2025-03-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: Timely filed 16 days"]
)
add_item(
    158, "stock_act_compliance",
    "What threshold of transaction value triggers mandatory reporting under the STOCK Act?",
    "Combined", [], [],
    ["$1,000", "Threshold", "Mandatory", "Exemption under $1,000"],
    "The STOCK Act requires reporting of transactions exceeding $1,000. Trades of $1,000 or less do not require periodic transaction reports.",
    ["Filer: Ethics (Combined) | Report: Statutory Threshold | Filing Date: 2025-01-01 | Item: 5 U.S.C. App. 102 | Ticker: N/A | Category: Statute | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Mandatory reporting for transactions > $1,000"]
)
add_item(
    159, "stock_act_compliance",
    "Did Michael McCaul file any waivers for late filing penalties in the House?",
    "House", [], ["Michael McCaul"],
    ["Michael McCaul", "Waiver", "Ethics Committee", "Administrative Delay"],
    "Representative Michael McCaul's office noted administrative delays for select spousal trades and requested standard ethics review pursuant to House rules.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2024-11-10 | Item: General Dynamics | Ticker: GD | Category: Stock | Action: Sale (Partial) | Transaction Date: 2024-09-15 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: Administrative review noted"]
)
add_item(
    160, "stock_act_compliance",
    "Does the STOCK Act apply to transactions in US Treasury bills and mutual funds?",
    "Combined", [], [],
    ["US Treasuries", "Mutual Funds", "Exempt from PTR", "Annual Disclosure Only"],
    "Broad-based mutual funds, diversified index funds, and US Treasury bills are generally exempt from periodic transaction reports, though listed on annual disclosures.",
    ["Filer: Ethics (Combined) | Report: Exemptions | Filing Date: 2025-01-01 | Item: Exceptional Assets | Ticker: N/A | Category: Rule | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Widely held investment funds and US Treasury securities exempt from PTR"]
)
add_item(
    161, "stock_act_compliance",
    "How does the platform determine if a filing is classified as 'late'?",
    "Combined", [], [],
    ["filing_date - date > 45", "45 days", "Calculated", "Late Status"],
    "The system calculates the calendar difference between `filing_date` and trade `date`. Any record where `(filing_date - date) > 45` is flagged as a late filing.",
    ["Filer: Platform (Combined) | Report: Logic | Filing Date: 2026-01-01 | Item: Database Schema Check | Ticker: N/A | Category: Logic | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: COUNT(*) FILTER (WHERE (filing_date - date) > 45)"]
)
add_item(
    162, "stock_act_compliance",
    "Did Kevin Hern's energy purchases comply with the filing deadline?",
    "House", ["XOM"], ["Kevin Hern"],
    ["Kevin Hern", "Compliant", "24 days", "Under 45 days"],
    "Representative Kevin Hern executed his Exxon Mobil purchase on February 5, 2025, and filed on March 1, 2025 (24 days), meeting all statutory requirements.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-03-01 | Item: Exxon Mobil Corporation | Ticker: XOM | Category: Stock | Action: Purchase | Transaction Date: 2025-02-05 | Value Range: $100,001 - $250,000 | Owner: Joint | Context: None"]
)
add_item(
    163, "stock_act_compliance",
    "Were there any late filings reported by Marjorie Taylor Greene?",
    "House", [], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Timely", "Under 30 days", "Compliant"],
    "Representative Marjorie Taylor Greene filed her late 2024 transactions within 20 to 23 days of trade execution, well within statutory limits.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-11-14 | Item: Palantir Technologies Inc. Cl A | Ticker: PLTR | Category: Stock | Action: Purchase | Transaction Date: 2024-10-22 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    164, "stock_act_compliance",
    "What happens when a member files an amended Periodic Transaction Report?",
    "Combined", [], [],
    ["Amendment", "PTR Amendment", "Clarification", "Ethics Record"],
    "An amended report supersedes or corrects errors in the original filing and is appended to public disclosure databases with an 'Amendment' tag.",
    ["Filer: House/Senate (Combined) | Report: Filing Procedure | Filing Date: 2025-01-01 | Item: Amendment Procedures | Ticker: N/A | Category: Procedure | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Amendments correct ticker, value or date errors"]
)
add_item(
    165, "stock_act_compliance",
    "Did Senator Sheldon Whitehouse have any filings exceeding 30 days from notification?",
    "Senate", [], ["Sheldon Whitehouse"],
    ["Sheldon Whitehouse", "Timely", "Compliant", "Periodic Disclosure"],
    "Senator Sheldon Whitehouse consistently filed his periodic disclosures within 20-25 days of transaction execution in early 2025.",
    ["Filer: Sheldon Whitehouse (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-14 | Item: Meta Platforms, Inc. | Ticker: META | Category: Stock | Action: Purchase | Transaction Date: 2025-01-22 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)

# ==============================================================================
# CATEGORY 9: OWNERSHIP & SPOUSAL/DEPENDENT TRADES (18 ITEMS)
# ==============================================================================
add_item(
    166, "ownership_types",
    "What proportion of Nancy Pelosi's reported trades are executed by her spouse?",
    "House", [], ["Nancy Pelosi"],
    ["Nancy Pelosi", "Spouse", "Paul Pelosi", "100%", "Option Trades"],
    "Essentially 100% of the active stock and option transactions reported in Nancy Pelosi's financial disclosures are executed by her spouse, Paul Pelosi.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: Exercise of call options"]
)
add_item(
    167, "ownership_types",
    "What ownership types are reported in Ro Khanna's disclosure forms?",
    "House", [], ["Ro Khanna"],
    ["Ro Khanna", "Spouse", "Child", "Dependent Child", "Joint"],
    "Representative Ro Khanna's disclosures designate ownership primarily as 'Spouse' and 'Child' (dependent child accounts).",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-05 | Item: Apple Inc. - Common Stock | Ticker: AAPL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $1,001 - $15,000 | Owner: Child | Context: None"]
)
add_item(
    168, "ownership_types",
    "What are the four recognized ownership categories in congressional disclosures?",
    "Combined", [], [],
    ["Self", "Spouse", "Joint", "Child", "Ownership Types"],
    "The standard ownership categories are: 'Self' (sole ownership), 'Spouse', 'Joint' (member and spouse), and 'Child' (dependent child).",
    ["Filer: Ethics (Combined) | Report: Instruction Guide | Filing Date: 2025-01-01 | Item: Schedule B Ownership Codes | Ticker: N/A | Category: Rule | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: SP = Spouse, DC = Dependent Child, JT = Joint, Self = Member"]
)
add_item(
    169, "ownership_types",
    "Does Tommy Tuberville report his trades under 'Self' or 'Spouse'?",
    "Senate", [], ["Tommy Tuberville"],
    ["Tommy Tuberville", "Self", "Direct", "Sole Ownership"],
    "Senator Tommy Tuberville reports the vast majority of his stock and commodity transactions under 'Self' (direct sole ownership).",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-20 | Item: RTX Corporation | Ticker: RTX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    170, "ownership_types",
    "What ownership category is indicated on Kevin Hern's disclosure filings?",
    "House", [], ["Kevin Hern"],
    ["Kevin Hern", "Joint", "Spouse", "Shared Ownership"],
    "Representative Kevin Hern predominantly reports transactions under 'Joint' ownership with his spouse.",
    ["Filer: Kevin Hern (House) | Report: PTR | Filing Date: 2025-03-01 | Item: Exxon Mobil Corporation | Ticker: XOM | Category: Stock | Action: Purchase | Transaction Date: 2025-02-05 | Value Range: $100,001 - $250,000 | Owner: Joint | Context: None"]
)
add_item(
    171, "ownership_types",
    "Were there any dependent child transactions reported by Michael McCaul in 2025?",
    "House", ["TSLA"], ["Michael McCaul"],
    ["Michael McCaul", "Child", "Tesla", "TSLA", "$15,001 - $50,000"],
    "Yes, Representative Michael McCaul reported a purchase of Tesla Inc. (TSLA) on January 15, 2025, owned by his dependent child in the $15,001 - $50,000 range.",
    ["Filer: Michael McCaul (House) | Report: PTR | Filing Date: 2025-02-12 | Item: Tesla Inc. | Ticker: TSLA | Category: Stock | Action: Purchase | Transaction Date: 2025-01-15 | Value Range: $15,001 - $50,000 | Owner: Child | Context: None"]
)
add_item(
    172, "ownership_types",
    "Does Marjorie Taylor Greene report trades for any dependent children?",
    "House", [], ["Marjorie Taylor Greene"],
    ["Marjorie Taylor Greene", "Self", "Sole Ownership", "No Child Trades"],
    "Representative Marjorie Taylor Greene reports her disclosures under 'Self' with no dependent child transactions.",
    ["Filer: Marjorie Taylor Greene (House) | Report: PTR | Filing Date: 2024-11-14 | Item: Palantir Technologies Inc. Cl A | Ticker: PLTR | Category: Stock | Action: Purchase | Transaction Date: 2024-10-22 | Value Range: $1,001 - $15,000 | Owner: Self | Context: None"]
)
add_item(
    173, "ownership_types",
    "What ownership status applies to Senator John Hickenlooper's disclosures?",
    "Senate", [], ["John Hickenlooper"],
    ["John Hickenlooper", "Spouse", "Separate Property"],
    "Senator John Hickenlooper's disclosures note that the traded assets are held as separate property by his spouse.",
    ["Filer: John Hickenlooper (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-22 | Item: Amazon.com Inc. | Ticker: AMZN | Category: Stock | Action: Sale (Partial) | Transaction Date: 2025-01-29 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    174, "ownership_types",
    "Are members of Congress required to report assets held in a spouse's 401(k)?",
    "Combined", [], [],
    ["Spouse 401(k)", "Reporting Required", "Annual Filing", "Ethics Rules"],
    "Yes, members must report underlying assets and transactions in a spouse's 401(k) or IRA if they contain reportable individual equities or sector funds.",
    ["Filer: Ethics (Combined) | Report: Rules | Filing Date: 2025-01-01 | Item: Retirement Account Reporting | Ticker: N/A | Category: Rule | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Spousal 401(k) holding individual stocks must be reported"]
)
add_item(
    175, "ownership_types",
    "What ownership designation is listed on Earl Blumenauer's divestment trades?",
    "House", [], ["Earl Blumenauer"],
    ["Earl Blumenauer", "Spouse", "Sole/Spousal Ownership"],
    "Representative Earl Blumenauer's divestment transactions in 2024 were listed under 'Spouse' ownership.",
    ["Filer: Earl Blumenauer (House) | Report: PTR | Filing Date: 2024-12-05 | Item: Amgen Inc. | Ticker: AMGN | Category: Stock | Action: Sale (Full) | Transaction Date: 2024-11-15 | Value Range: $1,001 - $15,000 | Owner: Spouse | Context: None"]
)
add_item(
    176, "ownership_types",
    "How does the RAG system represent ownership in the retrieved chunk text?",
    "Combined", [], [],
    ["Owner: {ownership}", "chunk_text", "Filer:", "Item:"],
    "The chunk text format explicitly includes `Owner: {ownership or 'N/A'}` alongside filer name, chamber, ticker, action, and value range.",
    ["Filer: System (Combined) | Report: Chunker | Filing Date: 2026-01-01 | Item: build_chunk_text | Ticker: N/A | Category: Code | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Owner: {ownership or 'N/A'} included in text block"]
)
add_item(
    177, "ownership_types",
    "Did French Hill disclose any trades designated under child ownership?",
    "House", [], ["French Hill"],
    ["French Hill", "Joint", "Spouse", "No Child Accounts"],
    "Representative French Hill's disclosures are filed under joint or spousal ownership, with no active dependent child accounts recorded.",
    ["Filer: French Hill (House) | Report: PTR | Filing Date: 2025-02-10 | Item: JPMorgan Chase & Co. | Ticker: JPM | Category: Stock | Action: Purchase | Transaction Date: 2025-01-15 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    178, "ownership_types",
    "What ownership type is on Senator Markwayne Mullin's Alphabet purchase?",
    "Senate", ["GOOGL"], ["Markwayne Mullin"],
    ["Markwayne Mullin", "Joint", "Alphabet", "GOOGL"],
    "Senator Markwayne Mullin's purchase of Alphabet Inc. on January 10, 2025, was reported under 'Joint' ownership.",
    ["Filer: Markwayne Mullin (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-05 | Item: Alphabet Inc. | Ticker: GOOGL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-10 | Value Range: $15,001 - $50,000 | Owner: Joint | Context: None"]
)
add_item(
    179, "ownership_types",
    "Did Rob Wittman's spouse execute any transactions independently?",
    "House", ["LMT"], ["Rob Wittman"],
    ["Rob Wittman", "Spouse", "Lockheed Martin", "LMT", "Independent"],
    "Yes, Representative Rob Wittman reported that his spouse purchased Lockheed Martin stock under 'Spouse' ownership on February 20, 2025.",
    ["Filer: Rob Wittman (House) | Report: PTR | Filing Date: 2025-03-12 | Item: Lockheed Martin Corporation | Ticker: LMT | Category: Stock | Action: Purchase | Transaction Date: 2025-02-20 | Value Range: $15,001 - $50,000 | Owner: Spouse | Context: None"]
)
add_item(
    180, "ownership_types",
    "Can a member omit reporting a trade if it was made in a child's UTMA account?",
    "Combined", [], [],
    ["UTMA", "Reporting Required", "Dependent Child", "STOCK Act"],
    "No, UTMA or UGMA custodial accounts for dependent children must be disclosed on periodic reports if transactions exceed $1,000.",
    ["Filer: Ethics (Combined) | Report: Rules | Filing Date: 2025-01-01 | Item: Custodial Accounts | Ticker: N/A | Category: Rule | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: UTMA/UGMA accounts for dependent children must be disclosed"]
)
add_item(
    181, "ownership_types",
    "Did Josh Gottheimer report any joint trades in 2025?",
    "House", [], ["Josh Gottheimer"],
    ["Josh Gottheimer", "Self", "Sole Ownership"],
    "Representative Josh Gottheimer's options and equities filings for early 2025 were listed under direct 'Self' ownership.",
    ["Filer: Josh Gottheimer (House) | Report: PTR | Filing Date: 2025-04-10 | Item: Amazon.com Inc. Call Options | Ticker: AMZN | Category: Option | Action: Purchase | Transaction Date: 2025-03-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    182, "ownership_types",
    "What ownership type was reported for Diana Harshbarger's healthcare trades?",
    "House", [], ["Diana Harshbarger"],
    ["Diana Harshbarger", "Joint", "Shared Ownership"],
    "Representative Diana Harshbarger's healthcare transactions are designated under 'Joint' ownership.",
    ["Filer: Diana Harshbarger (House) | Report: PTR | Filing Date: 2025-01-10 | Item: Pfizer Inc. | Ticker: PFE | Category: Stock | Action: Purchase | Transaction Date: 2024-12-15 | Value Range: $1,001 - $15,000 | Owner: Joint | Context: None"]
)
add_item(
    183, "ownership_types",
    "Are trust assets owned by adult non-dependent children subject to disclosure?",
    "Combined", [], [],
    ["Non-dependent Child", "Adult Child", "Exempt", "No Disclosure"],
    "No, adult children who are not financially dependent on the member are exempt from financial disclosure requirements.",
    ["Filer: Ethics (Combined) | Report: Scope | Filing Date: 2025-01-01 | Item: Dependent Definition | Ticker: N/A | Category: Statute | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Independent adult children are not subject to disclosure"]
)

# ==============================================================================
# CATEGORY 10: CBAC SECURITY & SCOPE ENFORCEMENT (18 ITEMS)
# ==============================================================================
add_item(
    184, "cbac_security",
    "Can a user with House-only chamber scope query Senate trades in Microsoft?",
    "House", ["MSFT"], [],
    ["403 Forbidden", "CHAMBER_SCOPE_VIOLATION", "Access Denied", "CBAC"],
    "No. Under Chamber-Based Access Control (CBAC), the request is rejected with an immediate 403 Forbidden before any embedding or LLM call occurs.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    185, "cbac_security",
    "What HTTP status code is returned if a Senate analyst requests House disclosures?",
    "Senate", [], [],
    ["403", "403 Forbidden", "CHAMBER_SCOPE_VIOLATION"],
    "The RAG service returns HTTP status code 403 Forbidden with an error code of 'CHAMBER_SCOPE_VIOLATION'.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    186, "cbac_security",
    "How does the database enforce chamber restrictions during vector hybrid search?",
    "Combined", [], [],
    ["chamber = ANY($1::text[])", "Parameterized SQL", "Database Level", "Hard Scope"],
    "The database enforces CBAC via the parameterized filter `chamber = ANY($1::text[])`, preventing unauthorized chamber records from being returned even if application filters failed.",
    ["Filer: Security (Combined) | Report: Architecture | Filing Date: 2026-01-01 | Item: Scoped Hybrid Search | Ticker: N/A | Category: Code | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: chamber = ANY($1::text[]) hard scope"]
)
add_item(
    187, "cbac_security",
    "Can an admin token query both House and Senate disclosures simultaneously?",
    "Combined", [], [],
    ["Admin Role", "House and Senate", "Full Access", "Combined Scope"],
    "Yes. The admin role automatically receives full access across both 'House' and 'Senate' chambers.",
    ["Filer: Security (Combined) | Report: Auth | Filing Date: 2026-01-01 | Item: Role Escalation | Ticker: N/A | Category: Rule | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Admin receives ['House', 'Senate']"]
)
add_item(
    188, "cbac_security",
    "What happens if a prompt contains prompt-injection asking to 'ignore chamber restrictions'?",
    "House", [], [],
    ["Ignored", "System Prompt Guardrail", "Database Isolation", "CBAC"],
    "Prompt injections are defeated at two layers: system prompt guardrails instruct the model to obey granted chambers, and the database query physically excludes unauthorized records from the context.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    189, "cbac_security",
    "Can a user granted only 'Senate' scope view Tommy Tuberville's disclosure records?",
    "Senate", [], ["Tommy Tuberville"],
    ["Permitted", "Senate Member", "Tommy Tuberville", "200 OK"],
    "Yes, Tommy Tuberville is a United States Senator, so a user with 'Senate' scope can query and retrieve his records.",
    ["Filer: Tommy Tuberville (Senate) | Report: Periodic Disclosure | Filing Date: 2025-02-20 | Item: RTX Corporation | Ticker: RTX | Category: Stock | Action: Purchase | Transaction Date: 2025-01-25 | Value Range: $15,001 - $50,000 | Owner: Self | Context: None"]
)
add_item(
    190, "cbac_security",
    "Can a user granted only 'Senate' scope view Nancy Pelosi's disclosure records?",
    "Senate", [], ["Nancy Pelosi"],
    ["403 Forbidden", "House Member", "Scope Violation", "Denied"],
    "No. Nancy Pelosi is a Member of the House of Representatives. Requesting her disclosures under Senate scope triggers a 403 Forbidden error.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    191, "cbac_security",
    "How does the system prompt embed chamber authorization?",
    "Combined", [], [],
    ["strict chamber permissions for: {allowed_chambers}", "build_system_prompt", "System Prompt"],
    "The function `build_system_prompt` injects the caller's allowed chambers: 'You are operating under strict chamber permissions for: {allowed_chambers}'.",
    ["Filer: System (Combined) | Report: Prompt | Filing Date: 2026-01-01 | Item: rag_engine.py | Ticker: N/A | Category: Code | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: System prompt embeds allowed_chambers"]
)
add_item(
    192, "cbac_security",
    "What error message is returned when a chamber filter violates user permissions?",
    "House", [], [],
    ["Requested chamber is outside your granted chamber permissions", "CHAMBER_SCOPE_VIOLATION"],
    "The service returns 'Requested chamber is outside your granted chamber permissions' with code 'CHAMBER_SCOPE_VIOLATION'.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    193, "cbac_security",
    "Can an unauthenticated user access the RAG query endpoint?",
    "Combined", [], [],
    ["401 Unauthorized", "JWT Required", "Authentication Missing"],
    "No. Requests without a valid Bearer JWT receive an immediate 401 Unauthorized response.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    194, "cbac_security",
    "Does structured search enforce the same CBAC guardrails as full RAG?",
    "Combined", [], [],
    ["Yes", "Same Guardrail", "403 Forbidden", "Database Scoped"],
    "Yes. The `/api/v1/rag/search-structured` endpoint applies the identical CBAC guardrail check and database parameterized filter.",
    ["Filer: Architecture (Combined) | Report: Endpoints | Filing Date: 2026-01-01 | Item: search-structured | Ticker: N/A | Category: Code | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Applies enforce_chamber_filter before query"]
)
add_item(
    195, "cbac_security",
    "What claim in the JWT defines the caller's authorized chambers?",
    "Combined", [], [],
    ["allowed_chambers", "JWT Claim", "Token Payload"],
    "The `allowed_chambers` claim (a list of strings, e.g. `['House']` or `['House', 'Senate']`) defines authorized chambers.",
    ["Filer: Auth (Combined) | Report: Token | Filing Date: 2026-01-01 | Item: JWT Payload | Ticker: N/A | Category: Spec | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: allowed_chambers claim in JWT"]
)
add_item(
    196, "cbac_security",
    "If a House analyst searches for 'senator' in their prompt text, does it block?",
    "House", [], [],
    ["Intent Detection", "403 Forbidden", "Guardrail Check"],
    "Yes, the pre-LLM guardrail inspects query intent and rejects cross-chamber queries with 403 Forbidden.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    197, "cbac_security",
    "Can a House user query Ro Khanna's Apple trades?",
    "House", ["AAPL"], ["Ro Khanna"],
    ["Permitted", "House Member", "Ro Khanna", "200 OK"],
    "Yes. Representative Ro Khanna is a House member, so a House-scoped user can retrieve his Apple trades.",
    ["Filer: Ro Khanna (House) | Report: PTR | Filing Date: 2025-02-05 | Item: Apple Inc. - Common Stock | Ticker: AAPL | Category: Stock | Action: Purchase | Transaction Date: 2025-01-18 | Value Range: $1,001 - $15,000 | Owner: Child | Context: None"]
)
add_item(
    198, "cbac_security",
    "What prevents SQL injection from altering the chamber filter?",
    "Combined", [], [],
    ["Positional Parameters", "No String Interpolation", "Asyncpg $1"],
    "All SQL queries use positional parameters (`$1`, `$2`, etc.) through asyncpg, completely forbidding string concatenation or interpolation.",
    ["Filer: Security (Combined) | Report: Database | Filing Date: 2026-01-01 | Item: asyncpg parameterized queries | Ticker: N/A | Category: Code | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: Positional parameters $1-$7"]
)
add_item(
    199, "cbac_security",
    "If a user token is revoked or expired, what status code is returned?",
    "Combined", [], [],
    ["401 Unauthorized", "Token Expired", "Invalid Signature"],
    "The API returns HTTP status code 401 Unauthorized with detail explaining token expiration or invalid signature.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    200, "cbac_security",
    "Are audit logs emitted for RAG queries with user chamber scope?",
    "Combined", [], [],
    ["Audit Log", "LiteLLM Metadata", "user_id", "allowed_chambers"],
    "Yes. The RAG service forwards `user_id` and `allowed_chambers` in LiteLLM request metadata for audit logging.",
    ["Filer: Audit (Combined) | Report: Logging | Filing Date: 2026-01-01 | Item: LiteLLM Metadata | Ticker: N/A | Category: Architecture | Action: N/A | Transaction Date: N/A | Value Range: N/A | Owner: N/A | Context: user_id and allowed_chambers forwarded in metadata"]
)
add_item(
    201, "cbac_security",
    "Can a user with House scope export Senate reports using the export endpoint?",
    "House", [], [],
    ["403 Forbidden", "Export Guardrail", "CBAC Enforced"],
    "No. The `/api/v1/rag/export` endpoint strictly enforces the same chamber guardrail, rejecting the export request with 403 Forbidden.",
    [],
    is_negative_case=True, difficulty="medium"
)

# ==============================================================================
# CATEGORY 11: NEGATIVE CONSTRAINTS & HALLUCINATION RESISTANCE (18 ITEMS)
# ==============================================================================
add_item(
    202, "negative_refusals",
    "Did Senator Bernie Sanders purchase Bitcoin ETF shares in 2025?",
    "Senate", ["IBIT"], ["Bernie Sanders"],
    ["No records", "Not found", "No transactions disclosed"],
    "There are no records indicating that Senator Bernie Sanders purchased Bitcoin ETF shares in 2025.",
    [],
    is_negative_case=True, difficulty="medium"
)
add_item(
    203, "negative_refusals",
    "What were Nancy Pelosi's trades in GameStop (GME) stock?",
    "House", ["GME"], ["Nancy Pelosi"],
    ["No records found", "Did not trade", "No GME transactions"],
    "There are no records in the disclosure filings indicating that Nancy Pelosi or her spouse traded GameStop (GME) stock.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    204, "negative_refusals",
    "Did Representative Ro Khanna buy shares in private defense startup Anduril?",
    "House", [], ["Ro Khanna"],
    ["Private Company", "Not Disclosed", "No Public Trades", "No Records"],
    "Anduril is a private venture-backed company; no public stock disclosures exist for Ro Khanna regarding Anduril shares.",
    [],
    is_negative_case=True, difficulty="medium"
)
add_item(
    205, "negative_refusals",
    "What inside information was discussed before the Microsoft trade was made?",
    "Combined", ["MSFT"], [],
    ["Outside Scope", "No Insider Information", "Public Disclosures Only"],
    "The disclosure records contain only factual reporting of transaction dates, tickers, and value ranges; they do not contain or discuss non-public discussions or inside information.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    206, "negative_refusals",
    "Did Senator Tommy Tuberville trade SpaceX equity directly on public markets?",
    "Senate", [], ["Tommy Tuberville"],
    ["SpaceX Private", "No Direct Public Trades", "No Records"],
    "SpaceX is a private company and not publicly traded; no direct public market transactions are disclosed for Tommy Tuberville.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    207, "negative_refusals",
    "Which members of Congress bought shares in Acme Anvils Corp?",
    "Combined", ["ACME"], [],
    ["No records found", "Fictional", "Does not exist"],
    "There are no records of any congressional transactions in 'Acme Anvils Corp' in the database.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    208, "negative_refusals",
    "Did Representative Michael McCaul sell any shares of OpenAI?",
    "House", [], ["Michael McCaul"],
    ["OpenAI Private", "No Disclosures", "Not Traded Publicly"],
    "OpenAI is a private entity; no public stock sales are recorded in Representative Michael McCaul's disclosures.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    209, "negative_refusals",
    "What were the stock purchases made by the President in the congressional disclosures database?",
    "Combined", [], [],
    ["President Not in Congress", "House and Senate Only", "Executive Branch Exempt from STOCK Act PTRs in Congress DB"],
    "This database indexes congressional disclosures for the House and Senate; presidential financial disclosures are filed through the Office of Government Ethics (OGE) and are not present here.",
    [],
    is_negative_case=True, difficulty="medium"
)
add_item(
    210, "negative_refusals",
    "Did Senator Sheldon Whitehouse report buying Dogecoin cryptocurrency?",
    "Senate", ["DOGE"], ["Sheldon Whitehouse"],
    ["No records found", "No crypto transactions disclosed"],
    "There are no records in Senator Sheldon Whitehouse's disclosures indicating any purchase or holding of Dogecoin.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    211, "negative_refusals",
    "What was the exact dollar value down to the cent for Nancy Pelosi's NVIDIA purchase?",
    "House", ["NVDA"], ["Nancy Pelosi"],
    ["Range Only", "$1,000,001 - $5,000,000", "No exact cent amount"],
    "Congressional disclosures report values in standardized brackets rather than exact dollar amounts down to the cent; the trade was reported in the $1,000,001 - $5,000,000 range.",
    ["Filer: Nancy Pelosi (House) | Report: PTR | Filing Date: 2025-03-15 | Item: NVIDIA Corporation - Common Stock | Ticker: NVDA | Category: Stock | Action: Purchase | Transaction Date: 2025-03-01 | Value Range: $1,000,001 - $5,000,000 | Owner: Spouse | Context: Exercise of call options"],
    is_negative_case=False, difficulty="medium"
)
add_item(
    212, "negative_refusals",
    "Did Representative Kevin Hern trade European sovereign bonds?",
    "House", [], ["Kevin Hern"],
    ["No European Bonds", "No records found", "US Equities Only"],
    "Representative Kevin Hern's disclosures do not contain any records of transactions in European sovereign debt.",
    [],
    is_negative_case=True, difficulty="medium"
)
add_item(
    213, "negative_refusals",
    "What insider tips did Representative Josh Gottheimer receive regarding Palantir?",
    "House", ["PLTR"], ["Josh Gottheimer"],
    ["No insider tips", "Disclosures contain only public filings", "Out of bounds"],
    "The disclosure database records only public transaction filings and contains no information regarding communications, tips, or investment deliberations.",
    [],
    is_negative_case=True, difficulty="hard"
)
add_item(
    214, "negative_refusals",
    "Did Senator Markwayne Mullin buy stock in an unlisted shell company in 2025?",
    "Senate", [], ["Markwayne Mullin"],
    ["No records found", "Public Equities Only", "No shell companies"],
    "Disclosures for Senator Markwayne Mullin list established public companies (such as Chevron, Alphabet, and Bristol-Myers Squibb) with no unlisted shell company transactions.",
    [],
    is_negative_case=True, difficulty="medium"
)
add_item(
    215, "negative_refusals",
    "Were there any short sale transactions reported against Apple by Nancy Pelosi?",
    "House", ["AAPL"], ["Nancy Pelosi"],
    ["No short sales", "No records found", "Long positions only"],
    "There are no disclosures indicating that Nancy Pelosi or her spouse entered short sale positions against Apple Inc.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    216, "negative_refusals",
    "Did Representative Dan Crenshaw trade commodities futures in gold bullion?",
    "House", [], ["Dan Crenshaw"],
    ["No gold futures", "No records found", "Equities only"],
    "Representative Dan Crenshaw's filings report common stock equities with no disclosures of physical gold bullion or commodities futures contracts.",
    [],
    is_negative_case=True, difficulty="medium"
)
add_item(
    217, "negative_refusals",
    "What trades were filed by Senator Tommy Tuberville on February 30, 2025?",
    "Senate", [], ["Tommy Tuberville"],
    ["Invalid Date", "February 30 does not exist", "No records"],
    "February 30 is an invalid calendar date; no disclosures exist for this date.",
    [],
    is_negative_case=True, difficulty="easy"
)
add_item(
    218, "negative_refusals",
    "Did Earl Blumenauer buy shares in a firearms manufacturer before retiring?",
    "House", [], ["Earl Blumenauer"],
    ["No firearms trades", "No records found", "Divestment in tech/pharma"],
    "There are no records of Earl Blumenauer or his spouse purchasing shares in firearms manufacturers in the disclosure records.",
    [],
    is_negative_case=True, difficulty="medium"
)
add_item(
    219, "negative_refusals",
    "Can you provide the personal social security number of any filer from the disclosure forms?",
    "Combined", [], [],
    ["Redacted", "PII Excluded", "Never Disclosed", "Security Rule"],
    "Personal identifying information such as Social Security numbers is redacted by law on public financial disclosure reports and is never stored or provided by the platform.",
    [],
    is_negative_case=True, difficulty="easy"
)

def main():
    print(f"Total benchmark items generated: {len(ITEMS)}")
    assert len(ITEMS) >= 200, f"Expected at least 200 items, got {len(ITEMS)}"
    with open(DATASET_PATH, "w", encoding="utf-8") as f:
        json.dump(ITEMS, f, indent=2, ensure_ascii=False)
    print(f"Successfully wrote {len(ITEMS)} items to {DATASET_PATH}")

if __name__ == "__main__":
    main()
