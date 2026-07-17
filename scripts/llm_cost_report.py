"""
Minimal LLM observability report: aggregates audit_log by model and prints
call count, total tokens, average latency, and total estimated cost. This is
the report a Lead AI Engineer should be able to produce on request -- "how
much did the last batch cost, and did the verify-pass rate spike" -- without
grepping raw logs.

Run: python -m scripts.llm_cost_report
"""
from collections import defaultdict

from common.db import get_session
from common.models import AuditLog


def run():
    with get_session() as session:
        rows = session.query(AuditLog).all()

    if not rows:
        print("No audit_log rows yet -- run a pipeline first.")
        return

    by_model = defaultdict(list)
    for row in rows:
        by_model[row.model].append(row)

    print(f"{'model':<28} {'calls':>6} {'input_tok':>10} {'output_tok':>11} {'avg_ms':>8} {'total_cost_usd':>15}")
    grand_total_cost = 0.0
    for model, entries in sorted(by_model.items()):
        input_tok = sum(e.input_tokens or 0 for e in entries)
        output_tok = sum(e.output_tokens or 0 for e in entries)
        avg_latency = sum(e.latency_ms or 0 for e in entries) / len(entries)
        total_cost = sum(float(e.estimated_cost_usd or 0) for e in entries)
        grand_total_cost += total_cost
        print(f"{model:<28} {len(entries):>6} {input_tok:>10} {output_tok:>11} {avg_latency:>8.0f} {total_cost:>15.6f}")

    print(f"\nTotal estimated cost: ${grand_total_cost:.6f} across {len(rows)} calls")


if __name__ == "__main__":
    run()
