"""Advisor tests (offline: fake generator + fake KB, no Ollama).

Verifies the LLM step is grounded in ENGINE-verified figures: the numbers in
the prompt come from the deterministic engine, and the advisor never recomputes
them. Expected figures are hand-calculated.
"""

from decimal import Decimal

from fin_engine import Account, ChartOfAccounts, Journal, JournalEntry, Posting
from fin_engine.advisor import advise
from fin_engine.models import AccountGroup


class _FakeKB:
    """Returns one canned guidance chunk; records the query it saw."""
    def __init__(self):
        self.seen = None

    def retrieve(self, q, k=3):
        self.seen = q
        from fin_engine.rag.store import Chunk, Retrieved
        return [Retrieved(Chunk("c1", "Keep current ratio between 1.5 and 3.",
                                "playbook.md", {}), score=0.9)]


def _company():
    coa = ChartOfAccounts("demo")
    coa.add(Account("1000", "Cash", AccountGroup.ASSET))
    coa.add(Account("2000", "AP", AccountGroup.LIABILITY))
    coa.add(Account("3000", "Equity", AccountGroup.EQUITY, current=False))
    coa.add(Account("4000", "Sales", AccountGroup.REVENUE, current=False))
    coa.add(Account("6100", "Rent", AccountGroup.OPERATING_EXPENSE, current=False))
    j = Journal("demo", chart=coa)
    j.post(JournalEntry("E0", "2026-11-01", "capital",
                        [Posting("1000", "10000"), Posting("3000", "-10000")]))
    j.post(JournalEntry("E1", "2026-11-02", "sale",
                        [Posting("1000", "6000"), Posting("4000", "-6000")]))
    j.post(JournalEntry("E2", "2026-11-03", "rent",
                        [Posting("6100", "800"), Posting("1000", "-800")]))
    return j, coa


def test_advice_prompt_carries_verified_figures():
    j, coa = _company()
    captured = {}

    def fake_gen(prompt):
        captured["prompt"] = prompt
        return "Consider deploying idle cash."

    kb = _FakeKB()
    adv = advise("what should I do about liquidity?", j, coa,
                 period="2026-11", as_of="2026-11-30", kb_a=kb, generate=fake_gen)

    # Net profit = 6000 - 800 = 5200; equity = 10000 + 5200 = 15200.
    assert adv.figures["net_profit"] == Decimal("5200")
    assert adv.figures["equity"] == Decimal("15200")
    # The verified numbers must appear in the prompt handed to the model.
    assert "5200" in captured["prompt"]
    assert "net_profit" in captured["prompt"]
    # The model is told not to recompute.
    assert "Do NOT recompute" in captured["prompt"]
    # Guidance was retrieved and cited.
    assert kb.seen == "what should I do about liquidity?"
    assert "playbook.md" in adv.citations
    assert adv.recommendation == "Consider deploying idle cash."


def test_advice_figures_match_engine_not_model():
    # Even if the model "says" a wrong number, adv.figures stays engine-truth.
    j, coa = _company()
    adv = advise("x", j, coa, "2026-11", "2026-11-30", _FakeKB(),
                 generate=lambda p: "Your net profit is 999999.")
    assert adv.figures["net_profit"] == Decimal("5200")  # engine, not model
