# Task: Financial Calculations

You are given a set of five financial math problems.

## Input Files

- `workspace/problems.json` — JSON file containing 5 financial problems with all necessary parameters

## Goal

Solve each problem and produce a JSON file with the answers and explanations.

## Requirements

1. Read the problems from `workspace/problems.json`.
2. Solve each problem using the appropriate financial formula.
3. Create `workspace/answers.json` containing an object with keys `problem_1` through `problem_5`.
4. Each problem entry must have:
   - `answer` — the numeric result (rounded to 2 decimal places)
   - `explanation` — a string explaining the calculation steps
5. Problems cover:
   - **Problem 1**: Compound interest calculation
   - **Problem 2**: Percentage markup on cost
   - **Problem 3**: Progressive income tax calculation
   - **Problem 4**: Monthly loan payment (amortization)
   - **Problem 5**: Break-even analysis (units to break even)

## Notes

- Use standard financial formulas.
- Compound interest: A = P × (1 + r/n)^(n×t)
- Loan payment: PMT = P × [r(1+r)^n] / [(1+r)^n − 1] where r is monthly rate
- Round final answers to 2 decimal places.
- Explanations should describe the formula and steps used.
