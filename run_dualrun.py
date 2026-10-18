#!/usr/bin/env python3
"""Dual-run agent CLI.

  python run_dualrun.py scenarios
        List the one-click single-request scenarios.

  python run_dualrun.py single --scenario "Bad IBAN checksum"      (or --file request.json)
        Send ONE request to both implementations and show the comparison.

  python run_dualrun.py bulk [--n 1000] [--seed 7] [--parity-fix] [--out out]
        Generate N requests, send each to both implementations, compare, write reports.
        Exit code 1 if any payment mismatches.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from wirepay_core import report  # noqa: E402
from wirepay_core.config import load_agent_config, load_spec  # noqa: E402
from wirepay_core.engine import run_dual  # noqa: E402
from wirepay_core.generator import SCENARIOS, generate_requests, scenario_request  # noqa: E402
from wirepay_core.runtime import adapters_from_config  # noqa: E402


def _setup(a):
    cfg = load_agent_config(a.config)
    if getattr(a, "parity_fix", False):
        cfg.setdefault("new", {"type": "standin"})["parity_fix"] = True
    old, new, notes = adapters_from_config(cfg, ROOT)
    for n in notes:
        print("note:", n)
    pd = cfg.get("processing_date", "auto")
    return old, new, (date.today().isoformat() if pd == "auto" else str(pd))


def cmd_scenarios(_a) -> int:
    for k in SCENARIOS:
        print(" -", k)
    return 0


def cmd_single(a) -> int:
    old, new, today = _setup(a)
    if a.file:
        req = json.loads(Path(a.file).read_text(encoding="utf-8"))
    else:
        req = scenario_request(a.scenario, today)
    req.setdefault("processingDate", today)
    run = run_dual([req], old, new, load_spec(a.spec))
    r = run.results[0]
    print(f"\nPayment {r.request_id}: {r.verdict}\n")
    print(f"  {'rule':<6} {'check':<26} {'old':<26} {'new':<26} result")
    for c in r.checks:
        print(f"  {c.rule_id:<6} {c.title[:25]:<26} {c.old[:25]:<26} {c.new[:25]:<26} {c.status}")
        if c.explanation:
            print(f"         -> {c.explanation}")
    return 1 if r.verdict == "MISMATCH" and not a.no_fail else 0


def cmd_bulk(a) -> int:
    old, new, today = _setup(a)
    reqs, _ = generate_requests(a.n, a.seed, today)
    run = run_dual(reqs, old, new, load_spec(a.spec))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.to_html(run), encoding="utf-8")
    (out / "report.csv").write_text(report.to_csv(run), encoding="utf-8")
    (out / "report.json").write_text(report.to_json(run), encoding="utf-8")
    c = run.counts
    print(f"\nSent {c['total']} identical requests to the old and the new implementation")
    print(f"  exact match          {c['match']}\n  expected differences {c['expected']}\n  MISMATCHES           {c['mismatch']}\n  parity               {c['parity_pct']}%\n")
    for r in run.rule_report:
        mark = {"VALIDATED": "ok  ", "INVALIDATED": "FAIL", "UNTESTED": "n/a "}[r["status"]]
        print(f"  [{mark}] {r['id']}  {r['title']:<42} checked {r['checked']:>5}  expected {r['expected']:>4}  mismatch {r['mismatch']:>4}")
    for p in run.patterns:
        print(f"\n  {p['pattern_id']} {p['category']} - {p['count']} payment(s), rules {', '.join(p['rules'])}\n      {p['explanation']}\n      fix: {p['fix']}")
    print(f"\nReports written to {out}/")
    return 1 if (c["mismatch"] and not a.no_fail) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "agent.yaml"))
    ap.add_argument("--spec", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scenarios").set_defaults(fn=cmd_scenarios)
    s = sub.add_parser("single")
    s.add_argument("--scenario", default="Clean USD payment", choices=list(SCENARIOS))
    s.add_argument("--file")
    s.add_argument("--parity-fix", action="store_true")
    s.add_argument("--no-fail", action="store_true")
    s.set_defaults(fn=cmd_single)
    b = sub.add_parser("bulk")
    b.add_argument("--n", type=int, default=1000)
    b.add_argument("--seed", type=int, default=7)
    b.add_argument("--parity-fix", action="store_true")
    b.add_argument("--no-fail", action="store_true")
    b.add_argument("--out", default=str(ROOT / "out"))
    b.set_defaults(fn=cmd_bulk)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
