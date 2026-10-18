"""
Agent 2 - DUAL-RUN.  The SAME request goes to the OLD and the NEW implementation, live,
and the two answers are compared.

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

from wirepay_core import ui  # noqa: E402
from wirepay_core.adapters import HttpAdapter  # noqa: E402
from wirepay_core.config import load_spec  # noqa: E402
from wirepay_core.engine import run_dual  # noqa: E402
from wirepay_core.generator import SCENARIOS, generate_requests, scenario_request  # noqa: E402
from wirepay_core.runtime import standin_adapters  # noqa: E402

st.set_page_config(page_title="Wire payments · Dual-run agent", page_icon="⚖️", layout="wide")
ui.inject_css()


@st.cache_resource(show_spinner="Compiling the Java services (old → Java 8, new → Java 18)…")
def _standins(parity_fix: bool):
    return standin_adapters(ROOT, parity_fix)


ui.hero("Agent 2 · Dual-run",
        "Same request in, same answer out?",
        "Send one request — or a thousand — to the old Java 8 service and the new Java 18 / ISO 20022 service "
        "at the same time, and compare what each one decides, rule by rule.")

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Old implementation")
    old_kind = st.radio("Old", ["Stand-in · Java 8 target", "External HTTP endpoint"], label_visibility="collapsed")
    old_url, old_auth = "", ""
    if old_kind == "External HTTP endpoint":
        old_url = st.text_input("Old URL", placeholder="https://wire-old.example/api/payments")
        old_auth = st.text_input("Old Authorization header", type="password")

    st.header("New implementation")
    new_kind = st.radio("New", ["Stand-in · parity gaps present", "Stand-in · parity gaps fixed", "External HTTP endpoint"],
                        label_visibility="collapsed")
    new_url, new_auth = "", ""
    if new_kind == "External HTTP endpoint":
        new_url = st.text_input("New URL", placeholder="https://wire-new.example/api/payments")
        new_auth = st.text_input("New Authorization header", type="password")
    else:
        st.caption("The stand-in has two deliberate gaps (fee rounding, same-day cut-off) so there is something "
                   "real to find. 'Fixed' shows a clean migration.")

    proc_date = st.date_input("Processing date", value=date.today(),
                              help="Sent as processingDate. The stand-ins use it for the 'value date in the past' rule.")


def build_adapters():
    parity_fix = new_kind.endswith("fixed")
    s_old, s_new, notes = _standins(parity_fix)
    if old_kind == "External HTTP endpoint":
        if not old_url:
            raise ValueError("Enter the old endpoint URL.")
        s_old = HttpAdapter(old_url, {"Authorization": old_auth} if old_auth else {}, label="old (external)")
    if new_kind == "External HTTP endpoint":
        if not new_url:
            raise ValueError("Enter the new endpoint URL.")
        s_new = HttpAdapter(new_url, {"Authorization": new_auth} if new_auth else {}, label="new (external)")
    return s_old, s_new, notes


tab_single, tab_bulk = st.tabs(["Single request", "Bulk run"])

# ------------------------------------------------------------------ single
with tab_single:
    label = st.selectbox("Scenario", list(SCENARIOS))
    req = scenario_request(label, proc_date)
    text = st.text_area("Request (editable JSON)", json.dumps(req, indent=2, ensure_ascii=False), height=300,
                        key=f"req_{label}_{proc_date}")
    if st.button("▶ Send to both implementations", type="primary", key="go_single"):
        try:
            payload = json.loads(text)
            payload.setdefault("processingDate", proc_date.isoformat())
            old_ad, new_ad, notes = build_adapters()
            run = run_dual([payload], old_ad, new_ad, load_spec())
            st.session_state["dual_single"] = (run, notes)
        except json.JSONDecodeError as e:
            st.error(f"The request is not valid JSON: {e}")
        except Exception as e:
            st.error(f"Run failed: {e}")
    if "dual_single" in st.session_state:
        run, notes = st.session_state["dual_single"]
        for n in notes:
            st.info(n)
        ui.inspector(run.results[0], "single")
        with st.expander("Run trace"):
            ui.trace_view(run)

# ------------------------------------------------------------------ bulk
with tab_bulk:
    c1, c2, _ = st.columns([1, 1, 2])
    n = c1.number_input("Requests", 10, 5000, 1000, step=100)
    seed = c2.number_input("Random seed", 1, 9999, 7)
    st.caption("Requests are generated with realistic edge cases mixed in (bad IBANs, long names, EUR bank holidays, "
               "half-cent fees, same-day payments, rejections). Every request is sent, unchanged, to both services.")
    if st.button("▶ Send all to both implementations", type="primary", key="go_bulk"):
        try:
            old_ad, new_ad, notes = build_adapters()
            reqs, _ = generate_requests(int(n), int(seed), proc_date)
            with st.status("Running both implementations…", expanded=False) as status:
                run = run_dual(reqs, old_ad, new_ad, load_spec(), progress=lambda m: status.update(label=m))
                status.update(label=f"Done — {run.counts['total']} payments compared", state="complete")
            st.session_state["dual_bulk"] = (run, notes)
        except Exception as e:
            st.error(f"Run failed: {e}")
    if "dual_bulk" in st.session_state:
        run, notes = st.session_state["dual_bulk"]
        for note in notes:
            st.info(note)
        ui.render_run(run, key="bulk", stem="dualrun-report")
    else:
        ui.flow([("Generate", "Realistic requests with edge cases mixed in."),
                 ("Send to both", "Identical request to old and new, same processing date."),
                 ("Compare", "14 mapping rules + 6 new-feature checks per payment."),
                 ("Diagnose", "Differences grouped into patterns with a suggested fix.")])
