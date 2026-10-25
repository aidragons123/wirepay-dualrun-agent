"""Live Agent - the SAME request goes to the OLD and the NEW implementation, live, and the answers are compared.

Run with:  streamlit run streamlit_app.py     (or `make ui`)
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from wirepay_core import capture, ui  # noqa: E402
from wirepay_core.brand import TWIN_RUN as AGENT  # noqa: E402
from wirepay_core.engine import run_dual  # noqa: E402
from wirepay_core.generator import SCENARIOS, generate_requests, scenario_request  # noqa: E402
from wirepay_core.shell import Ctx, run_app  # noqa: E402

FIELDS = [("debtorName", "Debtor name"), ("debtorAccount", "Debtor IBAN"), ("creditorName", "Creditor name"),
          ("creditorAccount", "Creditor IBAN"), ("creditorBic", "Creditor BIC"), ("amount", "Amount"),
          ("currency", "Currency"), ("valueDate", "Value date"), ("chargeBearer", "Charge bearer"), ("remittanceInfo", "Remittance text")]


def dual(ctx: Ctx, requests: list[dict], label: str, notes: str, source: str, kind: str):
    try:
        old, new, notes_ = ctx.adapters()
        spec = ctx.spec()
        run = ctx.execute(lambda say, on_count: run_dual(requests, old, new, spec, progress=say, on_count=on_count))
    except Exception as exc:
        st.error(f"The run failed: {exc}")
        return None
    for n in notes_:
        st.toast(n)
    return run, ctx.record(run, label, notes, source=source, kind=kind)


def quick_start(ctx: Ctx) -> None:
    reqs, _ = generate_requests(1000, 7, date.today())
    if dual(ctx, reqs, "Sample batch", "1,000 generated requests", "generated-1000-seed7", "dual-run"):
        pass


def single_tab(ctx: Ctx, proc: date) -> None:
    c1, c2 = st.columns([1.1, 1], gap="large")
    with c1:
        scenario = st.selectbox("Start from a scenario", list(SCENARIOS))
        base = scenario_request(scenario, proc)
        k = f"{scenario}-{proc}"
        as_json = st.toggle("Edit as JSON", key=f"js_{k}")
        if as_json:
            text = st.text_area("Request", json.dumps(base, indent=2, ensure_ascii=False), height=380, key=f"txt_{k}")
        else:
            payload = dict(base)
            a, b = st.columns(2)
            for i, (key, title) in enumerate(FIELDS):
                payload[key] = (a if i % 2 == 0 else b).text_input(title, str(base.get(key, "")), key=f"f_{key}_{k}")
    with c2:
        with st.container(border=True):
            st.markdown("#### Send to both")
            st.caption("The identical request, with the same processing date, goes to the old and the new service.")
            go = st.button("Send to both services", type="primary", width="stretch", key="go_single")
    if go:
        try:
            req = json.loads(text) if as_json else {k_: v for k_, v in payload.items() if v != "" or k_ in base}
        except json.JSONDecodeError as exc:
            st.error(f"That is not valid JSON: {exc}")
            return
        req.setdefault("processingDate", proc.isoformat())
        out = dual(ctx, [req], scenario, "", "single request", "single")
        if out:
            st.session_state["twin_single"] = out[1]
            st.rerun()          # refresh the sidebar's latest-run card
    rid = st.session_state.get("twin_single")
    if rid:
        sm, run = ctx.store.load_run(rid)
        st.divider()
        r = run.results[0]
        if r.verdict == "MATCH":
            st.success("Both services agree on every rule.")
        elif r.verdict == "EXPECTED_DIFFERENCE":
            st.info("The services differ only where a documented new feature explains it.")
        else:
            st.error("The services disagree in a way nothing documents.")
        ui.inspector(r, "single")


def batch_tab(ctx: Ctx, proc: date) -> None:
    left, right = st.columns([1.6, 1], gap="large")
    reqs, ready, source = [], False, ""
    with left:
        with st.container(border=True):
            st.markdown("#### Requests")
            mode = st.radio("Source", ["Generate", "Upload requests"], horizontal=True, label_visibility="collapsed")
            if mode == "Generate":
                a, b = st.columns(2)
                n = a.slider("Requests", 10, 5000, 1000, step=10)
                seed = b.number_input("Random seed", 1, 9999, 7)
                st.caption("Realistic edge cases are mixed in: bad IBANs, long names, EUR bank holidays, half-cent fees, same-day payments, rejections.")
                ready, source = True, f"generated-{n}-seed{int(seed)}"
            else:
                up = st.file_uploader("JSONL or CSV of requests", type=["jsonl", "json", "csv"])
                if up is not None:
                    try:
                        reqs = capture.parse_requests_bytes(up.getvalue(), up.name)
                        ready, source = True, up.name
                        st.success(f"{len(reqs):,} requests read from {up.name}.")
                    except capture.CaptureError as exc:
                        st.error(f"Could not read that file: {exc}")
        with st.container(border=True):
            st.markdown("#### Name it")
            label = st.text_input("Run name", placeholder="Release 2.4 candidate", key="b_label")
            notes = st.text_area("Notes (optional)", height=70, key="b_notes")
    with right:
        gate = ctx.gate()
        with st.container(border=True):
            st.markdown("#### What will happen")
            st.markdown("1. Every request goes unchanged to the old and the new service.\n2. Each pair of answers is compared rule by rule.\n3. The run is saved and judged against the release gate.")
            st.caption(f"Release gate: at most {gate.max_mismatches} mismatches, at least {gate.min_parity_pct}% parity.")
        go = st.button("Send all to both services", type="primary", width="stretch", disabled=not ready, key="go_batch")
    if go:
        if mode == "Generate":
            reqs, _ = generate_requests(int(n), int(seed), proc)
        if dual(ctx, reqs, label.strip(), notes.strip(), source, "dual-run"):
            ctx.go("overview")


def workbench(ctx: Ctx) -> None:
    ui.page_header(AGENT.run_page_title, AGENT.run_page_hint)
    with st.expander("Services and processing date", expanded=False):
        a, b, c = st.columns([1, 1, 0.8])
        with a:
            st.markdown("**Old service**")
            ctx.picker("old")
        with b:
            st.markdown("**New service**")
            ctx.picker("new")
        proc = c.date_input("Processing date", value=date.today(), help="Sent as processingDate. The stand-ins use it for the “value date in the past” rule.")
        st.session_state["proc_date"] = proc
    proc = st.session_state.get("proc_date", date.today())
    t1, t2 = st.tabs(["One payment", "Batch"])
    with t1:
        single_tab(ctx, proc)
    with t2:
        batch_tab(ctx, proc)


run_app(AGENT, ROOT, workbench, quick_start)
