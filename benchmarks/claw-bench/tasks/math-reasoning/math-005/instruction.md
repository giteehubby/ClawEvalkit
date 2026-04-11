# Task: Algorithm Design — Longest Increasing Subsequence

You are given a problem description and an input array. Find the longest strictly increasing subsequence (LIS) and write a working algorithm.

## Input Files

- `workspace/problem.md` — problem description
- `workspace/input.json` — JSON file with the input array of 20 integers

## Goal

Solve the LIS problem and implement a reusable algorithm.

## Requirements

1. Read the input array from `workspace/input.json`.
2. Find the length of the longest strictly increasing subsequence.
3. Find one such subsequence (any valid one).
4. Create `workspace/solution.json` containing:
   - `length` — the length of the LIS (integer)
   - `subsequence` — one valid longest increasing subsequence (array of integers)
5. Create `workspace/algorithm.py` — a working Python script that:
   - Reads from `workspace/input.json`
   - Computes the LIS length and one valid subsequence
   - Writes the result to `workspace/solution.json`
   - Uses an efficient algorithm (O(n²) dynamic programming or O(n log n) patience sorting)

## Notes

- The subsequence must be strictly increasing (no equal elements).
- Elements in the subsequence must appear in the same order as in the input array.
- The algorithm.py must be a standalone script that produces correct output when run.
- Do NOT use brute-force enumeration of all subsequences.
- Multiple valid subsequences of the same maximum length may exist; any one is acceptable.
