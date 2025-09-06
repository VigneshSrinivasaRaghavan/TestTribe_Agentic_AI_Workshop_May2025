# Day 2 — Requirement Gap Checker Agent

Question

Implement an agent `requirement_gap_checker` that reads one or more requirement
files and identifies missing or under-specified requirements (gaps). The agent
should return a JSON report listing gaps with suggested requirement text.

Requirements

- Input: one or many `.txt` files under `data/requirements` (CLI: `--inputs ...`).
- Output: JSON file `outputs/requirement_gap_checker/gaps.json` and a short
  markdown summary `outputs/requirement_gap_checker/summary.md`.
- The JSON must contain `gaps` (array) and `summary`.
- Each gap must include: `id`, `source_file`, `category`, `description`,
  `severity`, `suggested_requirement`.

Expected gap item schema

{
  "id": "G-001",
  "source_file": "login.txt",
  "category": "security|performance|error-handling|acceptance",
  "description": "Short description of the missing requirement",
  "severity": "High|Medium|Low",
  "suggested_requirement": "One-line actionable requirement text"
}


