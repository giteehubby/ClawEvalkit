# Task: Knapsack Optimization

You are given a set of items with weights and values, and a knapsack with a weight capacity limit. Select items to maximize total value without exceeding the capacity.

## Input Files

- `workspace/items.json` — JSON file containing a list of 8 items (each with name, weight, value) and a capacity constraint

## Goal

Find the optimal selection of items that maximizes total value while staying within the weight capacity.

## Requirements

1. Read the items and capacity from `workspace/items.json`.
2. Solve the 0/1 knapsack problem (each item can be taken at most once).
3. Create `workspace/solution.json` containing:
   - `selected_items` — list of item names selected
   - `total_value` — sum of values of selected items (integer)
   - `total_weight` — sum of weights of selected items (integer)
   - `algorithm` — string describing the approach used (e.g., "dynamic programming", "branch and bound")

## Notes

- This is a 0/1 knapsack: items cannot be split.
- The optimal solution is unique for this dataset.
- Total weight must not exceed the given capacity.
- All weights and values are positive integers.
