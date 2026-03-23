# Task: Resource Allocation (Linear Programming)

You are given a production planning problem. A factory produces three products, each requiring certain amounts of three shared resources. Find the production quantities that maximize total profit.

## Input Files

- `workspace/problem.json` — JSON file defining products (with profit and resource requirements) and resource limits

## Goal

Solve the linear programming problem to find optimal production quantities.

## Requirements

1. Read the problem definition from `workspace/problem.json`.
2. Formulate and solve the linear programming problem.
3. Create `workspace/solution.json` containing:
   - `product_A` — optimal quantity of product A (number, can be fractional)
   - `product_B` — optimal quantity of product B (number, can be fractional)
   - `product_C` — optimal quantity of product C (number, can be fractional)
   - `total_profit` — the maximum total profit (number)
   - `binding_constraints` — list of constraint names that are exactly met (tight) at the optimal solution

## Notes

- All quantities must be non-negative.
- A constraint is "binding" if it is exactly satisfied (used up completely) at the optimum.
- The optimal solution for this problem is unique.
- You may use any method: simplex, interior point, or manual calculation.
- Production quantities can be non-integer (continuous relaxation).
