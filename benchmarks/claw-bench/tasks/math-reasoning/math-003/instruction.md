# Task: Statistical Analysis

You are given a dataset with two groups. Perform a two-sample statistical analysis.

## Input Files

- `workspace/dataset.csv` — CSV file with 50 rows and two columns: `value` (numeric) and `group` (either "A" or "B")

## Goal

Compute descriptive statistics for each group, perform an independent two-sample t-test, and determine statistical significance.

## Requirements

1. Read the dataset from `workspace/dataset.csv`.
2. Compute statistics for each group separately.
3. Perform an independent two-sample t-test (Welch's t-test, which does not assume equal variances).
4. Create `workspace/analysis.json` containing:
   - `mean_a` — mean of group A values (float)
   - `mean_b` — mean of group B values (float)
   - `std_a` — sample standard deviation of group A (float, using ddof=1)
   - `std_b` — sample standard deviation of group B (float, using ddof=1)
   - `t_statistic` — the t-statistic from Welch's t-test (float)
   - `p_value` — the two-tailed p-value (float)
   - `conclusion` — either `"significant"` or `"not_significant"` at alpha = 0.05

## Notes

- Use sample standard deviation (ddof=1, i.e., dividing by N-1).
- Use Welch's t-test (does not assume equal variances).
- The conclusion should be `"significant"` if p_value < 0.05, otherwise `"not_significant"`.
- Round floating-point results to reasonable precision (at least 4 decimal places).
