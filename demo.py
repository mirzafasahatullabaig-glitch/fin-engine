"""Run the engine on the report's two worked examples and print the result.

    python demo.py

Shows that the engine returns the corrected PBT values (115,000 / 190,000)
that the local model got wrong in report §7.1.
"""

from decimal import Decimal

from fin_engine import calculate_pnl, classify_transaction
from fin_engine.models import AccountGroup, Ledger, LedgerLine


def _pct(frac: Decimal) -> str:
    return f"{frac * 100:.2f}%"


def show(title: str, ledger: Ledger) -> None:
    p = calculate_pnl(ledger)
    m = p.margins()
    print(f"\n=== {title} ===")
    print(f"  Revenue            {p.revenue:>12,}")
    print(f"  COGS               {p.cogs:>12,}")
    print(f"  Gross profit       {p.gross_profit:>12,}  ({_pct(m['gross'])})")
    print(f"  Operating expenses {p.operating_expenses:>12,}")
    print(f"  EBIT               {p.ebit:>12,}  ({_pct(m['operating'])})")
    print(f"  Finance costs      {p.finance_costs:>12,}")
    print(f"  PBT                {p.pbt:>12,}  ({_pct(m['pbt'])})")
    print(f"  Tax                {p.tax:>12,}")
    print(f"  Net profit         {p.net_profit:>12,}")
    print(f"  [formula v{p.formula_version}]")


if __name__ == "__main__":
    show("Example A — revenue 500,000 (report expects PBT 115,000)", Ledger(
        entity="demo", period="2026-11", lines=[
            LedgerLine(AccountGroup.REVENUE, "500000"),
            LedgerLine(AccountGroup.COGS, "280000"),
            LedgerLine(AccountGroup.OPERATING_EXPENSE, "100000"),
            LedgerLine(AccountGroup.FINANCE_COST, "5000"),
        ]))

    show("Example B — revenue 800,000 (report expects PBT 190,000)", Ledger(
        entity="demo", period="2026-11", lines=[
            LedgerLine(AccountGroup.REVENUE, "800000"),
            LedgerLine(AccountGroup.COGS, "420000"),
            LedgerLine(AccountGroup.OPERATING_EXPENSE, "180000"),
            LedgerLine(AccountGroup.FINANCE_COST, "10000"),
        ]))

    print("\n=== Dual-dimension classification (report §7.4) ===")
    for desc in ["Sale of goods", "Office rent", "Purchase of machinery",
                 "Bank loan received", "Electricity bill",
                 "Misc settlement 4471-X"]:
        c = classify_transaction(desc)
        flag = "  <-- REVIEW" if c.needs_review else ""
        print(f"  {desc:<26} {c.group.value:<18} {c.cash_flow.value:<10}{flag}")
