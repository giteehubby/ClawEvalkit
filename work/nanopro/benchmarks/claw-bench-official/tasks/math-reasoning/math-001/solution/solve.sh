#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="${1:-workspace}"

python3 << PYEOF
import json

with open("$WORKSPACE/problems.json") as f:
    data = json.load(f)

answers = {}

for prob in data["problems"]:
    pid = prob["id"]

    if prob["type"] == "compound_interest":
        P = prob["principal"]
        r = prob["annual_rate"]
        t = prob["years"]
        n = prob["compounds_per_year"]
        A = P * (1 + r / n) ** (n * t)
        answers[pid] = {
            "answer": round(A, 2),
            "explanation": (
                f"Using compound interest formula A = P(1 + r/n)^(nt): "
                f"A = {P} * (1 + {r}/{n})^({n}*{t}) = {P} * {(1 + r/n)**(n*t):.6f} = {round(A, 2)}"
            ),
        }

    elif prob["type"] == "percentage_markup":
        cost = prob["cost"]
        markup = prob["markup_percent"]
        price = cost * (1 + markup / 100)
        answers[pid] = {
            "answer": round(price, 2),
            "explanation": (
                f"Selling price = cost * (1 + markup/100) = {cost} * (1 + {markup}/100) "
                f"= {cost} * {1 + markup/100} = {round(price, 2)}"
            ),
        }

    elif prob["type"] == "tax_calculation":
        income = prob["income"]
        brackets = prob["brackets"]
        total_tax = 0.0
        parts = []
        for b in brackets:
            lo = b["min"]
            hi = b["max"] if b["max"] is not None else income
            rate = b["rate"]
            if income > lo:
                taxable = min(income, hi) - lo
                tax = taxable * rate
                total_tax += tax
                parts.append(f"{taxable} * {rate} = {tax}")
        answers[pid] = {
            "answer": round(total_tax, 2),
            "explanation": (
                f"Progressive tax: {' + '.join(parts)} = {round(total_tax, 2)}"
            ),
        }

    elif prob["type"] == "loan_payment":
        P = prob["principal"]
        annual_rate = prob["annual_rate"]
        n = prob["months"]
        r = annual_rate / 12
        pmt = P * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
        answers[pid] = {
            "answer": round(pmt, 2),
            "explanation": (
                f"Monthly payment formula: PMT = P * r(1+r)^n / ((1+r)^n - 1) "
                f"where P={P}, r={r:.6f} (monthly), n={n}. PMT = {round(pmt, 2)}"
            ),
        }

    elif prob["type"] == "break_even":
        fc = prob["fixed_costs"]
        price = prob["price_per_unit"]
        vc = prob["variable_cost_per_unit"]
        units = fc / (price - vc)
        answers[pid] = {
            "answer": round(units, 2),
            "explanation": (
                f"Break-even units = fixed_costs / (price - variable_cost) "
                f"= {fc} / ({price} - {vc}) = {fc} / {price - vc} = {round(units, 2)}"
            ),
        }

with open("$WORKSPACE/answers.json", "w") as f:
    json.dump(answers, f, indent=2)

print("Answers saved to $WORKSPACE/answers.json")
PYEOF
