"""Benchmark: how often does Granite 4.2 8B get accounting right vs the engine?

    python bench_granite_accounting.py [N]

Generates N random but realistic P&L problems. For each, the deterministic
engine computes the ground-truth PBT (report §7.2 formula), then Granite is
asked for the PBT from the same figures. We measure Granite's exact-match rate
and, crucially, how often it repeats the §7.1 bug: returning PBT = EBIT and
ignoring interest expense.

This quantifies the gap the whole project exists to close. Requires Ollama with
granite4.2:8b.
"""

import json
import random
import re
import sys
import urllib.request
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fin_engine import calculate_pnl
from fin_engine.models import AccountGroup, Ledger, LedgerLine

HOST = "http://localhost:11434"
MODEL = "granite4.2:8b"


def make_problem(rng: random.Random) -> dict:
    revenue = rng.randrange(100, 1000) * 1000
    cogs = int(revenue * rng.uniform(0.4, 0.65))
    opex = int(revenue * rng.uniform(0.1, 0.3))
    interest = rng.randrange(1, 40) * 1000
    tax = rng.randrange(0, 30) * 1000
    return {"revenue": revenue, "cogs": cogs, "opex": opex,
            "interest": interest, "tax": tax}


def truth(p: dict) -> dict:
    led = Ledger("bench", "p", [
        LedgerLine(AccountGroup.REVENUE, str(p["revenue"])),
        LedgerLine(AccountGroup.COGS, str(p["cogs"])),
        LedgerLine(AccountGroup.OPERATING_EXPENSE, str(p["opex"])),
        LedgerLine(AccountGroup.FINANCE_COST, str(p["interest"])),
        LedgerLine(AccountGroup.TAX, str(p["tax"])),
    ])
    r = calculate_pnl(led)
    return {"ebit": r.ebit, "pbt": r.pbt, "net": r.net_profit}


def ask_granite(p: dict) -> str:
    prompt = (
        "You are an accountant. Given these monthly figures, compute Profit "
        "Before Tax (PBT). Reply with ONLY a JSON object {\"pbt\": <number>} "
        "and no other text.\n\n"
        f"Revenue: {p['revenue']}\n"
        f"Cost of goods sold: {p['cogs']}\n"
        f"Operating expenses: {p['opex']}\n"
        f"Interest expense: {p['interest']}\n"
    )
    payload = json.dumps(
        {"model": MODEL, "prompt": prompt, "stream": False, "think": False,
         "format": "json"}
    ).encode()
    req = urllib.request.Request(f"{HOST}/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode()).get("response", "")


def parse_pbt(text: str) -> Decimal | None:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "pbt" in obj:
            return Decimal(str(obj["pbt"]).replace(",", ""))
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r'"pbt"\s*:\s*"?(-?[\d,]+(?:\.\d+)?)', text)
    return Decimal(m.group(1).replace(",", "")) if m else None


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    rng = random.Random(42)

    correct = 0
    ebit_bug = 0       # returned PBT == EBIT (the §7.1 failure)
    unparseable = 0
    print(f"Benchmarking {MODEL} on {n} PBT problems (seed 42)\n")

    for i in range(1, n + 1):
        p = make_problem(rng)
        t = truth(p)
        raw = ask_granite(p)
        got = parse_pbt(raw)

        if got is None:
            unparseable += 1
            verdict = "UNPARSEABLE"
        elif got == t["pbt"]:
            correct += 1
            verdict = "correct"
        elif got == t["ebit"]:
            ebit_bug += 1
            verdict = f"WRONG (=EBIT, ignored interest {p['interest']:,})"
        else:
            verdict = f"WRONG (got {got:,})"

        print(f"  {i:2}. truth PBT={t['pbt']:>10,}  granite={str(got):>12}  {verdict}")

    print(f"\n==== {MODEL} accounting accuracy ====")
    print(f"  correct PBT:      {correct}/{n}  ({100*correct//n}%)")
    print(f"  PBT=EBIT bug:     {ebit_bug}/{n}  (the §7.1 failure mode)")
    print(f"  unparseable:      {unparseable}/{n}")
    print(f"  deterministic engine: {n}/{n} correct by construction.")


if __name__ == "__main__":
    main()
