"""Interactive fin-engine console (v1.5.0).

    python repl.py

A terminal REPL over the unified accounting engine: post double-entry journal
entries into the starter chart of accounts and ask metric questions, all
computed deterministically (no Ollama needed). Type `help` for commands.
"""

import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fin_engine import (
    Journal, JournalEntry, Posting, starter_chart, trial_balance,
    pnl_from_journal, balance_sheet_from_journal, cash_flow_from_journal,
    reconcile, advise, configure_logging, health_check, JournalStore,
)
from fin_engine.router import QueryRouter, detect_metric

configure_logging()  # honours FIN_ENGINE_LOG_LEVEL (default WARNING = quiet)

TODAY = "2026-11-30"  # default as-of / posting date for this session


class _NoKB:
    """Stand-in knowledge base: the REPL answers metrics deterministically and
    never needs RAG, so general questions just say so."""

    def answer(self, q):
        from fin_engine.rag.pipeline import Answer
        return Answer("(general-knowledge questions need Ollama; not wired in "
                      "the REPL — ask a metric instead)", [], False)


HELP = """\
Commands:
  post <id> <date> <desc> | <acct> <amt> ; <acct> <amt> ; ...
        Post a balanced entry. Amounts: debit +, credit -. Must sum to 0.
        e.g.  post E1 2026-11-05 cash sale | 1000 9000 ; 4000 -9000
  ask <question>           Ask a metric, e.g.  ask what is our working capital
  advise <question>        Business advice: engine figures + your decision docs,
                           reasoned by local Ollama (granite4.2:8b). Needs Ollama.
                           e.g.  advise should I take on more inventory?
  accounts                 List the chart of accounts
  trial                    Show the trial balance
  pnl [period]             Show the P&L (default 2026-11)
  bs                       Show the balance sheet
  cashflow [period]        Show the (direct-method) cash-flow statement
  check                    Run reconciliation
  history                  Audit trail: each entry with who recorded it and when
  health                   Check Ollama is up and the models are pulled
  seed                     Load a small sample company
  help                     This text
  quit                     Exit

Entries persist to a SQLite file (FIN_ENGINE_DB, default ./fin-engine.db) and
reload on the next launch. The file is gitignored (it holds business records).
"""

SAMPLE = [
    ("E0", "2026-11-01", "owner capital", [("1000", "20000"), ("3000", "-20000")]),
    ("E1", "2026-11-05", "cash sale",     [("1000", "9000"), ("4000", "-9000")]),
    ("E2", "2026-11-06", "inventory/credit", [("1200", "4000"), ("2000", "-4000")]),
    ("E3", "2026-11-10", "cogs",          [("5000", "2500"), ("1200", "-2500")]),
    ("E4", "2026-11-15", "rent",          [("6100", "1200"), ("1000", "-1200")]),
]


def _post(journal, chart, raw):
    """Parse and post `<id> <date> <desc> | <acct> <amt> ; ...`."""
    if "|" not in raw:
        return "need '|' separating header from postings (see help)"
    header, body = raw.split("|", 1)
    parts = header.split(None, 2)
    if len(parts) < 3:
        return "header needs: <id> <date> <description>"
    entry_id, date, desc = parts
    postings = []
    for leg in body.split(";"):
        leg = leg.strip()
        if not leg:
            continue
        toks = leg.split()
        if len(toks) != 2:
            return f"posting {leg!r} must be '<acct> <amount>'"
        try:
            postings.append(Posting(toks[0], toks[1]))
        except (InvalidOperation, ValueError, TypeError) as e:
            return f"bad posting {leg!r}: {e}"
    try:
        journal.post(JournalEntry(entry_id, date, desc, postings))
    except (ValueError, KeyError) as e:
        return f"rejected: {e}"
    return f"posted {entry_id} ({len(postings)} legs)"


def _make_advisor():
    """Build the real Ollama RAG stack and ingest the sample decision docs.

    Lazy: only called on the first `advise`, so the REPL starts without Ollama.
    Returns (kb, generate) or raises with a clear message if Ollama is absent.
    """
    from fin_engine import Config
    from fin_engine.rag import KnowledgeBaseA, OllamaEmbedder
    from fin_engine.rag.pipeline import _ollama_generate
    cfg = Config.from_env()
    h = health_check(cfg)
    if not h.ok:
        raise RuntimeError(h.detail or "Ollama health check failed")
    kb = KnowledgeBaseA(embedder=OllamaEmbedder(model=cfg.embed_model,
                                                host=cfg.ollama_host))
    sample = Path(__file__).resolve().parent / "data" / "kb_a_sample"
    for md in sorted(sample.glob("*.md")):
        kb.ingest_file(md)
    # Generator that honours the configured host + model.
    def generate(prompt: str) -> str:
        return _ollama_generate(prompt, model=cfg.gen_model, host=cfg.ollama_host)
    return kb, generate


ENTITY = "demo"


def main():
    # Persist to a SQLite file so entries survive restarts (v1.5.5). Path from
    # FIN_ENGINE_DB, default ./fin-engine.db (gitignored — it holds records).
    db_path = os.getenv("FIN_ENGINE_DB", "fin-engine.db")
    store = JournalStore(db_path)

    # Load an existing journal for the entity; if the DB is empty, start fresh
    # with the starter chart and persist it so the chart is there next time.
    journal = store.load_journal(ENTITY)
    if journal.chart is None:
        chart = starter_chart(ENTITY)
        journal = Journal(ENTITY, chart=chart)
        store.save_chart(chart)
        loaded_msg = f"new ledger ({db_path})"
    else:
        chart = journal.chart
        loaded_msg = f"loaded {len(journal.entries)} entries from {db_path}"

    router = QueryRouter(kb_a=_NoKB(),
                         accounting_provider=lambda: (journal, chart, "2026-11", TODAY))
    advisor = {"kb": None, "gen": None}  # built on first `advise`
    print(f"fin-engine interactive console — {loaded_msg}. "
          "Type 'help', or 'seed' for sample data.")
    try:
        while True:
            try:
                line = input("fin> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            cmd, _, rest = line.partition(" ")
            cmd = cmd.lower()
            rest = rest.strip()

            if cmd in ("quit", "exit", "q"):
                break
            try:
                _dispatch(cmd, rest, journal, chart, router, advisor, store)
            except Exception as e:  # never let one bad command kill the console
                print(f"error: {e}")
    finally:
        store.close()


def _dispatch(cmd, rest, journal, chart, router, advisor, store):
        if cmd == "help":
            print(HELP)
        elif cmd == "seed":
            existing = {e.entry_id for e in journal.entries}
            n = 0
            for eid, date, desc, legs in SAMPLE:
                if eid in existing:
                    continue  # idempotent: don't re-post, don't crash
                journal.post(JournalEntry(eid, date, desc,
                                          [Posting(a, v) for a, v in legs]))
                n += 1
            store.save_journal(journal)  # persist new entries
            print(f"seeded {n} new entries"
                  + (" (sample already loaded)" if n == 0 else ""))
        elif cmd == "post":
            msg = _post(journal, chart, rest)
            store.save_journal(journal)  # persist if the post succeeded
            print(msg)
        elif cmd == "ask":
            if detect_metric(rest) is None:
                print("couldn't spot a metric; try: revenue, net profit, working "
                      "capital, current ratio, total assets, ...")
            else:
                print(router.ask(rest).answer)
        elif cmd == "history":
            if not journal.entries:
                print("  (no entries yet)")
            for e in journal.entries:
                print(f"  {e.entry_id:<6} {e.date}  {e.status.value:<8} "
                      f"by {e.created_by} at {e.created_at}  — {e.description}")
        elif cmd == "health":
            h = health_check()
            print(f"  Ollama up: {h.ollama_up}")
            print(f"  gen model present: {h.gen_model_present}")
            print(f"  embed model present: {h.embed_model_present}")
            print(f"  overall OK: {h.ok}" + (f"  — {h.detail}" if h.detail else ""))
        elif cmd == "advise":
            if not rest:
                print("usage: advise <question>")
                return
            if advisor["kb"] is None:
                try:
                    advisor["kb"], advisor["gen"] = _make_advisor()
                except Exception as e:
                    print(f"advisor unavailable (needs Ollama): {e}")
                    return
            try:
                adv = advise(rest, journal, chart, "2026-11", TODAY,
                             advisor["kb"], advisor["gen"])
            except Exception as e:
                print(f"advise failed: {e}")
                return
            print("  Verified figures (engine, not the model):")
            for key in ("net_profit", "working_capital", "current_ratio",
                        "total_assets", "equity"):
                print(f"    {key}: {adv.figures[key]}")
            print(f"\n  Recommendation (granite4.2:8b):\n    {adv.recommendation}")
            if adv.citations:
                print(f"  sources: {', '.join(adv.citations)}")
        elif cmd == "accounts":
            for a in chart.accounts():
                flag = "" if a.is_active else " (inactive)"
                print(f"  {a.code}  {a.name:<22} {a.group.value}{flag}")
        elif cmd == "trial":
            tb = trial_balance(journal, chart, as_of=TODAY)
            for l in tb.lines:
                print(f"  {l.code}  {l.name:<22} Dr {l.debit:>10,}  Cr {l.credit:>10,}")
            print(f"  TOTALS  Dr {tb.total_debits:,}  Cr {tb.total_credits:,}  "
                  f"balanced={tb.balanced}")
        elif cmd == "pnl":
            p = pnl_from_journal(journal, chart, rest or "2026-11")
            print(f"  Revenue {p.revenue:,}  COGS {p.cogs:,}  Gross {p.gross_profit:,}")
            print(f"  EBIT {p.ebit:,}  PBT {p.pbt:,}  Net {p.net_profit:,}")
        elif cmd == "cashflow":
            cf = cash_flow_from_journal(journal, chart, rest or "2026-11")
            print(f"  Operating {cf.operating:,}  Investing {cf.investing:,}  "
                  f"Financing {cf.financing:,}")
            print(f"  Net change in cash {cf.net_change:,}")
        elif cmd == "bs":
            bs = balance_sheet_from_journal(journal, chart, as_of=TODAY)
            print(f"  Assets {bs.total_assets:,} = Liab {bs.total_liabilities:,} "
                  f"+ Equity {bs.equity:,}")
            print(f"  Working capital {bs.working_capital:,}  "
                  f"current ratio {bs.current_ratio}")
            for w in bs.validation_warnings():
                print(f"  ! {w}")
        elif cmd == "check":
            rep = reconcile(journal, chart, as_of=TODAY)
            print(f"  reconcile passed={rep.passed}  ({len(rep.checks)} checks, "
                  f"{len(rep.failures)} failures)")
            for f in rep.failures:
                print(f"  ! {f.name}: {f.detail}")
        else:
            print(f"unknown command {cmd!r}; type 'help'")


if __name__ == "__main__":
    main()
