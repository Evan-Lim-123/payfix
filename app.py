"""PayFix: AI-assisted resolution of failed loan and recurring payments.

Prototype for the OCBC Ignite Innovation Challenge (Problem 2). Uses synthetic
data only. Run with:  streamlit run app.py
"""

import base64
import random
import time
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

import agent
import data
import simulator as sim

AI_CASES_PER_BATCH = 5   # Gemini investigates this many failures per batch; the rest use rules (free-tier limits)

st.set_page_config(page_title="PayFix", page_icon="💳", layout="wide")

# ---------------------------------------------------------------------------
# Shared look
# ---------------------------------------------------------------------------
RISK_COLOURS = {
    "Low": ("#E3F4EA", "#1B5E36"),
    "Medium": ("#FCEFD7", "#7A4A05"),
    "High": ("#FBE3E1", "#8E1F17"),
    "Certain": ("#FBE3E1", "#8E1F17"),
    "Likely": ("#FCEFD7", "#7A4A05"),
    "Check needed": ("#E8EBF0", "#2E3644"),
}

st.markdown(
    """
    <style>
    /* Layout */
    .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px;}
    [data-testid="stHeader"] {background: transparent;}
    footer {visibility: hidden;}

    /* Page header */
    .pf-hero {display:flex; flex-wrap:wrap; justify-content:space-between; align-items:flex-end; gap:12px;
              margin: 0 0 1.4rem; padding-bottom: 1.1rem; border-bottom: 1px solid #E1E4EA;}
    .pf-eyebrow {font-size:12px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:#0B6E63;
                 margin-bottom:4px;}
    .pf-hero h1.pf-title {padding:0 !important;}
    .pf-title {font-family:"Space Grotesk", sans-serif; font-size:2.1rem; font-weight:700; line-height:1.15;
               color:#141922; margin:0;}
    .pf-sub {color:#5A6372; font-size:15px; margin:6px 0 0; max-width:760px; line-height:1.5;}
    .pf-chip {display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600; color:#2E3644;
              background:#FFFFFF; border:1px solid #E1E4EA; border-radius:999px; padding:5px 12px; white-space:nowrap;}
    .pf-dot {width:8px; height:8px; border-radius:50%; background:#0B6E63; display:inline-block;}

    /* Metric cards */
    [data-testid="stMetric"] {background:#FFFFFF; border:1px solid #E1E4EA; border-radius:12px; padding:14px 18px;
                              box-shadow: 0 1px 2px rgba(20,25,34,.04);}
    [data-testid="stMetricLabel"] p {font-size:13px !important; color:#5A6372 !important;}
    [data-testid="stMetricValue"] {font-family:"Space Grotesk", sans-serif; font-weight:600;}

    /* Bordered containers become cards */
    [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {background:#FFFFFF;}
    h3 {font-size:1.15rem !important;}

    /* Case header */
    .pf-case {background:#FFFFFF; border:1px solid #E1E4EA; border-radius:14px; padding:20px 24px; margin-bottom:1.2rem;}
    .pf-case-top {display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:14px;}
    .pf-case-id {font-family:"Space Grotesk", sans-serif; font-size:1.6rem; font-weight:700; color:#141922; margin-right:6px;}
    .pf-facts {display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:14px;}
    .pf-fact span {display:block; font-size:12px; font-weight:600; letter-spacing:.04em; text-transform:uppercase;
                   color:#5A6372; margin-bottom:2px;}
    .pf-fact b {font-size:15px; font-weight:600; color:#141922;}

    /* Small pieces */
    .pill {display:inline-block; padding:3px 10px; border-radius:999px; font-size:12px; font-weight:600;}
    .muted {color:#5A6372; font-size:14px;}
    .sms {background:#EEF6F5; border-radius:14px 14px 14px 4px; padding:14px 16px; color:#12332F; line-height:1.55;}
    .pf-brand {font-family:"Space Grotesk", sans-serif; font-size:1.6rem; font-weight:700; color:#FFFFFF; line-height:1;}
    .pf-brand em {font-style:normal; color:#5FD3C3;}
    .pf-tag {font-size:12px; color:#9AA3B2; margin:6px 0 2px;}

    /* Dark sidebar and teal accents, even if .streamlit/config.toml is missing */
    [data-testid="stSidebar"], [data-testid="stSidebarContent"] {background-color:#141922 !important;}
    [data-testid="stSidebar"] [data-testid="stNavSectionHeader"],
    [data-testid="stSidebar"] [data-testid="stNavSectionHeader"] * {color:#9AA3B2 !important;}
    [data-testid="stSidebarNavLink"] span, [data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"]
        {color:#C9CED8 !important;}
    [data-testid="stSidebarNavLink"]:hover {background-color:#232A36 !important;}
    [data-testid="stSidebarNavLink"][aria-current="page"] {background-color:#232A36 !important;}
    [data-testid="stSidebarNavLink"][aria-current="page"] span {color:#FFFFFF !important; font-weight:600;}
    [data-testid="stSidebarNavSeparator"], [data-testid="stSidebar"] hr {border-color:#2E3644 !important;}
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#9AA3B2 !important;}
    [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
    [data-testid="stSidebar"] .stCheckbox p {color:#E6E9EE !important;}
    [data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {color:#9AA3B2 !important;}
    [data-testid="stBaseButton-primary"] {background-color:#0B6E63 !important; border-color:#0B6E63 !important;
                                          color:#FFFFFF !important;}
    [data-testid="stBaseButton-primary"]:hover {background-color:#08524A !important; border-color:#08524A !important;}
    button[data-variant="segmented_control"][aria-checked="true"] {background-color:#E3F1EF !important;
        border-color:#0B6E63 !important; color:#0B6E63 !important;}
    button[data-variant="segmented_control"][aria-checked="true"] * {color:#0B6E63 !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


def pill(text, colour_key=None):
    bg, fg = RISK_COLOURS.get(colour_key or text, ("#E8EBF0", "#2E3644"))
    return f'<span class="pill" style="background:{bg};color:{fg}">{text}</span>'


def page_header(eyebrow, title, subtitle):
    st.markdown(
        f"""<div class="pf-hero"><div><div class="pf-eyebrow">{eyebrow}</div>
        <h1 class="pf-title">{title}</h1><p class="pf-sub">{subtitle}</p></div>
        <span class="pf-chip"><span class="pf-dot"></span>Synthetic data only</span></div>""",
        unsafe_allow_html=True,
    )


STATUS_COLOURS = {"auto": ("#E3F4EA", "#1B5E36"), "review": ("#FCEFD7", "#7A4A05"),
                  "escalated": ("#FBE3E1", "#8E1F17"), "resolved": ("#E3F4EA", "#1B5E36")}


def status_pill(case):
    bg, fg = STATUS_COLOURS.get(case["group"], ("#E8EBF0", "#2E3644"))
    return f'<span class="pill" style="background:{bg};color:{fg}">{current_status(case)}</span>'


# ---------------------------------------------------------------------------
# Session state: officer decisions, audit trails, reminders
# ---------------------------------------------------------------------------
def reset_state():
    st.session_state.cases = [dict(c, simulated=False) for c in data.CASES]
    st.session_state.audit = {c["id"]: data.initial_audit(c) for c in data.CASES}
    st.session_state.decisions = {}
    st.session_state.reminders = set()
    st.session_state.selected = data.CASES[0]["id"]
    st.session_state.next_case = 3001
    st.session_state.feed = []          # every simulated payment, newest first
    st.session_state.last_run = None    # step-by-step view of the last scenario
    st.session_state.rng = random.Random()


if "cases" not in st.session_state:
    reset_state()


def case_by_id(case_id):
    return next(c for c in st.session_state.cases if c["id"] == case_id)


def ai_investigator():
    """The Gemini agent as a function, or None if it's switched off or no key is set."""
    key = agent.get_setting("GEMINI_API_KEY", st.secrets)
    if not key or not st.session_state.get("use_ai", True):
        return None
    model = agent.get_setting("GEMINI_MODEL", st.secrets)
    return lambda p, code: agent.investigate(p, code, api_key=key, model=model)


def add_simulated(payment, use_ai=True):
    """Run one payment through the PayFix pipeline and store the results."""
    case_id = f"PF-{st.session_state.next_case}"
    feed, case, steps = sim.process(payment, case_id, ai_investigator() if use_ai else None)
    st.session_state.feed.insert(0, feed)
    if case is not None:
        st.session_state.next_case += 1
        st.session_state.cases.insert(0, case)
        st.session_state.audit[case_id] = list(case["audit"])
    return feed, case, steps


def current_status(case):
    return st.session_state.decisions.get(case["id"], case["status"])


def record_decision(case, decision, reason):
    """Apply an officer decision: move the case, simulate the action, log everything."""
    now = datetime.now(sim.SGT).strftime("%H:%M")
    log = st.session_state.audit[case["id"]]
    status = f"{decision} by {data.OFFICER}"
    log.append((now, data.OFFICER, f"{status}." + (f" Reason: {reason}" if reason else "")))

    if decision in ("Approved", "Edited"):
        case["group"] = "resolved"
        done = case["action"] if decision == "Approved" else f"{case['action']} (with officer's changes: {reason})"
        log.append((now, "PayFix", f"Action carried out (simulated): {done}"))
        if case.get("message"):
            log.append((now, "PayFix", "Customer SMS sent (simulated)."))
        status += " · action carried out"
    elif decision == "Rejected":
        case["group"] = "resolved"
        log.append((now, "PayFix", "No action taken. Case closed."))
        status += " · no action taken"
    else:  # Escalated
        case["group"] = "escalated"
        log.append((now, "PayFix", "Case sent to a senior officer. No action taken."))
        status += " · sent to senior officer"

    st.session_state.decisions[case["id"]] = status
    case["status"] = status
    st.session_state.toast = f"{case['id']}: {status}"


def open_case(case_id):
    st.session_state.selected = case_id
    st.switch_page(case_page)


# ---------------------------------------------------------------------------
# Page 1: failed payments queue
# ---------------------------------------------------------------------------
def queue():
    page_header("Operations · Case queue", "Failed payments",
                f"Loan repayments and recurring GIRO payments that failed today, {sim.now():%a %d %b %Y}.")

    cases = st.session_state.cases
    groups = [c["group"] for c in cases]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Failed payments", len(cases))
    c2.metric("Auto-resolved", groups.count("auto"))
    c3.metric("Waiting for an officer", groups.count("review"))
    c4.metric("Escalated (high risk)", groups.count("escalated"))
    c5.metric("Resolved by officer", groups.count("resolved"))
    if not any(c.get("simulated") for c in cases):
        st.info("Showing sample cases only. Go to **Live simulation** to generate fake payments.")

    choice = st.segmented_control(
        "Filter", ["All cases", "Needs an officer", "Auto-resolved", "Escalated", "Resolved by officer"],
        default="All cases", label_visibility="collapsed",
    )
    group = {"Needs an officer": "review", "Auto-resolved": "auto", "Escalated": "escalated",
             "Resolved by officer": "resolved"}.get(choice)
    shown = [c for c in cases if group is None or c["group"] == group]

    df = pd.DataFrame(
        {
            "Case": [c["id"] for c in shown],
            "Payment": [c["type"] for c in shown],
            "Customer": [c["customer"] for c in shown],
            "Amount (S$)": [c["amount"] for c in shown],
            "Failure": [c["failure"] for c in shown],
            "Risk": [c["risk"] for c in shown],
            "Status": [current_status(c) for c in shown],
            "AI confidence": [c["confidence"] * 100 if c["confidence"] else None for c in shown],
            "Source": ["Simulated" if c.get("simulated") else "Sample" for c in shown],
        }
    )

    def colour_risk(val):
        bg, fg = RISK_COLOURS[val]
        return f"background-color:{bg};color:{fg};font-weight:600"

    event = st.dataframe(
        df.style.map(colour_risk, subset=["Risk"]),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Amount (S$)": st.column_config.NumberColumn(format="%.2f"),
            "AI confidence": st.column_config.NumberColumn(format="%d%%"),
        },
    )
    if event.selection.rows:
        picked = shown[event.selection.rows[0]]
        if st.button(f"Open case {picked['id']} →", type="primary"):
            open_case(picked["id"])

    st.caption("Select a row, then open the case. PayFix only retries or reschedules low-risk payments by itself. "
               "It never changes who receives money or how much without an officer confirming.")


# ---------------------------------------------------------------------------
# Page 2: case detail and officer decision
# ---------------------------------------------------------------------------
def case_detail():
    page_header("Operations · Case detail", "Case investigation",
                "What the agent found, the rules it was checked against, and the officer's decision.")
    ids = [c["id"] for c in st.session_state.cases]
    if st.session_state.selected not in ids:
        st.session_state.selected = ids[0]
    pick_col, _ = st.columns([2, 3])
    case_id = pick_col.selectbox("Case", ids, index=ids.index(st.session_state.selected),
                                 format_func=lambda i: f"{i} · {case_by_id(i)['type']}")
    st.session_state.selected = case_id
    case = case_by_id(case_id)

    agent_name = case.get("engine") or "Investigation agent"
    st.markdown(
        f"""<div class="pf-case"><div class="pf-case-top">
        <span class="pf-case-id">{case['id']}</span>{pill(case['risk'] + ' risk', case['risk'])}{status_pill(case)}
        </div><div class="pf-facts">
        <div class="pf-fact"><span>Payment</span><b>{case['type']}</b></div>
        <div class="pf-fact"><span>Customer</span><b>{case['customer']}</b></div>
        <div class="pf-fact"><span>Amount</span><b>S${case['amount']:,.2f}</b></div>
        <div class="pf-fact"><span>Rejection code</span><b>{case['code']}</b></div>
        <div class="pf-fact"><span>Likely cause</span><b>{case['failure']}</b></div>
        <div class="pf-fact"><span>Investigated by</span><b>{agent_name}</b></div>
        </div></div>""",
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 2], gap="large")

    with left:
        with st.container(border=True):
            st.subheader("What happened")
            st.write(case["explanation"])
            if case.get("engine"):
                st.caption(f"Investigated by **{case['engine']}** · confidence {case['confidence']:.0%}. "
                           f"{case['engine_note']}")
            elif case["confidence"] is not None:
                st.caption(f"AI confidence {case['confidence']:.0%} · explanation generated by the investigation agent")

        with st.container(border=True):
            st.subheader("Evidence gathered")
            cols = st.columns(2)
            for i, (tool, found) in enumerate(case["evidence"]):
                with cols[i % 2]:
                    st.markdown(f"**{tool}**  \n{found}")
            if case["missing"]:
                st.warning("Missing information: " + "; ".join(case["missing"]) + ". PayFix will request it rather than guess.")
            else:
                st.info("Missing information: none. All required data was available.")

        with st.container(border=True):
            st.subheader("Audit trail")
            audit_df = pd.DataFrame(st.session_state.audit[case_id], columns=["Time", "Who", "What"])
            st.dataframe(audit_df, hide_index=True, width="stretch")

        if case.get("simulated"):
            with st.expander("Simulation ground truth (hidden from the agent)"):
                truth = sim.CAUSE_LABELS[case["true_cause"]]
                said = sim.CAUSE_LABELS[case["agent_cause"]]
                st.markdown(f"**Real cause:** {truth}  \n**Agent said:** {said}")
                if case["agent_correct"]:
                    st.success("The agent identified the correct cause.")
                elif case["blocked"]:
                    st.warning("The agent was wrong, and the policy rules blocked its proposal before any action.")
                elif case["agent_cause"] == "unclear":
                    st.info("The agent said it couldn't confirm the cause, so a person reviews it. No action was taken.")
                elif case["group"] != "auto":
                    st.info("The agent got the cause wrong, but no automatic action was taken: a person reviews it.")
                else:
                    st.error("The agent was wrong and PayFix acted automatically. This should never happen.")

    with right:
        with st.container(border=True):
            st.subheader("Suggested action")
            st.write(case["action"])
            st.markdown("**Policy checks (rules, not AI)**")
            for text, ok in case["checks"]:
                st.markdown(f"{'✅' if ok else '⛔'} {text}")
            decided = st.session_state.decisions.get(case_id)
            if case["group"] == "resolved":
                st.success(f"Resolved by an officer: {decided}.")
            elif case["group"] == "review":
                st.warning(f"{case['risk']} risk: PayFix has prepared the fix, but an officer must approve it.")
            elif case["group"] == "escalated":
                st.error("High risk: a person must decide. PayFix will not act on this case.")
            else:
                st.success("Low risk: PayFix resolved this automatically.")

        if case["group"] != "auto" and not decided:
            with st.container(border=True):
                st.subheader("Your decision")
                reason = st.text_area("Reason (required if you edit, reject or escalate)",
                                      placeholder="e.g. Customer called, salary delayed this month",
                                      key=f"reason_{case_id}")
                b1, b2 = st.columns(2)
                b3, b4 = st.columns(2)
                clicked = None
                if b1.button("Approve", type="primary", width="stretch", key=f"ap_{case_id}"):
                    clicked = "Approved"
                if b2.button("Edit action", width="stretch", key=f"ed_{case_id}"):
                    clicked = "Edited"
                if b3.button("Reject", width="stretch", key=f"rj_{case_id}"):
                    clicked = "Rejected"
                if b4.button("Escalate", width="stretch", key=f"es_{case_id}"):
                    clicked = "Escalated"

                if clicked:
                    if clicked != "Approved" and not reason.strip():
                        st.error("Please give a reason before you edit, reject or escalate.")
                    else:
                        record_decision(case, clicked, reason.strip())
                        st.rerun()
        elif decided:
            with st.container(border=True):
                st.subheader("Decision recorded")
                st.markdown(f"**{decided}**")
                st.caption("This case is locked. The decision and what PayFix did are in the audit trail.")

        if case["message"]:
            with st.container(border=True):
                st.subheader("Customer message preview (SMS)")
                st.markdown(f"<div class='sms'>{case['message']}</div>", unsafe_allow_html=True)
                if decided and decided.startswith(("Approved", "Edited")):
                    st.caption("✅ Sent to the customer (simulated). PayFix never asks customers for passwords or login links.")
                elif decided:
                    st.caption("Not sent: the officer did not approve this case.")
                else:
                    st.caption("Sent only after an officer approves. PayFix never asks customers for passwords or login links.")


# ---------------------------------------------------------------------------
# Live simulation
# ---------------------------------------------------------------------------
STEP_ICONS = {"ok": "✅", "warn": "🟡", "fail": "⛔"}


def step_line(stage, text, state):
    icon = "🔎" if stage == "Agent tool call" else ("❌" if stage == "Payment system" and state == "fail"
                                                    else STEP_ICONS[state])
    return f"{icon} **{stage}:** {text}"


def session_stats():
    feed = st.session_state.feed
    simc = [c for c in st.session_state.cases if c.get("simulated")]
    wrong = [c for c in simc if not c["agent_correct"]]
    return {
        "processed": len(feed),
        "paid": sum(1 for f in feed if f["Outcome"] == "Paid"),
        "failed": len(simc),
        "auto": sum(1 for c in simc if c["group"] == "auto"),
        "review": sum(1 for c in simc if c["group"] in ("review", "resolved")),
        "escalated": sum(1 for c in simc if c["group"] == "escalated"),
        "accuracy": (1 - len(wrong) / len(simc)) if simc else None,
        "mistakes": len(wrong),
        "caught": sum(1 for c in wrong if c["group"] != "auto"),
        "ai_cases": sum(1 for c in simc if c.get("engine", "").startswith("Gemini")),
        "wrong_auto": sum(1 for c in simc if c["group"] == "auto" and not c["agent_correct"]),
        "cases": simc,
    }


def show_session_results():
    s = session_stats()
    r1 = st.columns(4)
    r1[0].metric("Payments processed", s["processed"])
    r1[1].metric("Paid first time", s["paid"])
    r1[2].metric("Failed", s["failed"])
    r1[3].metric("Auto-resolved", s["auto"])
    r2 = st.columns(4)
    r2[0].metric("Sent to an officer", s["review"] + s["escalated"],
                 help=f"{s['review']} for review, {s['escalated']} escalated")
    r2[1].metric("Correct cause found", "—" if s["accuracy"] is None else f"{s['accuracy']:.0%}",
                 help="Compared with the simulation's ground truth, which the agent never sees")
    r2[2].metric("AI mistakes stopped", f"{s['caught']} of {s['mistakes']}",
                 help="Wrong causes that were blocked by the rules or sent to a person instead of acted on")
    r2[3].metric("Wrong auto-actions", s["wrong_auto"], help="Target: always zero")
    return s


def simulation():
    page_header("Demo · Live simulation", "Watch PayFix work",
                "Generate loan, GIRO and standing-instruction payments, then follow every failure through "
                "PayFix: detect → investigate → validate → resolve or escalate → notify.")

    # --- Batch run --------------------------------------------------------
    with st.container(border=True):
        st.subheader("Run a payment batch")
        c1, c2, c3 = st.columns([2, 2, 1], vertical_alignment="bottom")
        size = c1.slider("Payments in the batch", 10, 200, 50, step=10)
        rate = c2.slider("Share that fail", 5, 40, 20, step=5, format="%d%%") / 100
        live = c3.toggle("Animate", value=True)
        if st.button("▶ Run payment batch", type="primary"):
            bar = st.progress(0.0, text="Processing payments…")
            table = st.empty()
            before = len([c for c in st.session_state.cases if c.get("simulated")])
            ai_on = ai_investigator() is not None
            ai_left = AI_CASES_PER_BATCH if ai_on else 0
            gemini_error = None
            for i in range(size):
                was_left = ai_left
                _, case, _ = add_simulated(sim.random_payment(st.session_state.rng, rate), use_ai=ai_left > 0)
                if case is not None and ai_on and was_left == 0:
                    why = (f"Gemini skipped: it failed earlier in this batch ({gemini_error})" if gemini_error
                           else f"Gemini skipped: batch limit of {AI_CASES_PER_BATCH} reached")
                    case["engine"], case["engine_note"] = "Rule-based agent", why + "."
                if case is not None and was_left > 0:
                    if case["engine"].startswith("Gemini"):
                        ai_left -= 1
                    else:
                        # Stop calling Gemini for this batch if it failed (e.g. rate limit, bad key)
                        ai_left = 0
                        gemini_error = case["engine_note"].split("unavailable (", 1)[-1].rsplit(")", 1)[0]
                    bar.progress((i + 1) / size, text=f"Processed {i + 1} of {size} payments "
                                                      f"(Gemini investigating failures…)")
                if live and (i % 2 == 0 or i == size - 1):
                    bar.progress((i + 1) / size, text=f"Processed {i + 1} of {size} payments")
                    table.dataframe(pd.DataFrame(st.session_state.feed[:10]), hide_index=True, width="stretch")
                    time.sleep(0.05)
            bar.progress(1.0, text=f"Done: {size} payments processed")
            new_cases = [c for c in st.session_state.cases if c.get("simulated")][:max(
                0, len([c for c in st.session_state.cases if c.get("simulated")]) - before)]
            n_ai = sum(1 for c in new_cases if c["engine"].startswith("Gemini"))
            note = f"Batch done: {size} payments, {len(new_cases)} failed and went through PayFix."
            if ai_on and gemini_error:
                note += (f" ⚠️ Gemini failed on the first try ({gemini_error}), so this batch used the "
                         "rule-based agent. Click **Test Gemini** in the sidebar for details.")
            elif ai_on:
                note += (f" Gemini investigated {n_ai}; the rest used the rule-based agent "
                         f"(capped at {AI_CASES_PER_BATCH} per batch to stay within free-tier limits).")
            st.session_state.batch_note = note
            st.rerun()
        if st.session_state.get("batch_note"):
            st.success(st.session_state.batch_note + " New cases are in **Failed payments**.")

    # --- One-click scenarios ----------------------------------------------
    with st.container(border=True):
        st.subheader("Demo scenarios")
        st.caption("Each button creates one failed payment that shows a specific behaviour. "
                   "Hover a button to see what it demonstrates.")
        keys = list(sim.SCENARIOS)
        for row in (keys[:5], keys[5:]):
            cols = st.columns(5)
            for col, key in zip(cols, row):
                label, desc = sim.SCENARIOS[key]
                if col.button(label, key=f"sc_{key}", help=desc, width="stretch"):
                    p = sim.scenario_payment(st.session_state.rng, key)
                    if ai_investigator():
                        with st.spinner("Gemini agent is investigating…"):
                            _, case, steps = add_simulated(p)
                    else:
                        _, case, steps = add_simulated(p)
                    st.session_state.last_run = {"key": key, "case_id": case["id"], "steps": steps,
                                                 "animate": True}

        run = st.session_state.last_run
        if run:
            label, desc = sim.SCENARIOS[run["key"]]
            st.markdown(f"#### {label} · case {run['case_id']}")
            st.caption(desc)
            if run["animate"]:
                with st.status("PayFix is working on it…", expanded=True) as status:
                    for step in run["steps"]:
                        st.markdown(step_line(*step))
                        time.sleep(0.35 if step[0] != "Agent tool call" else 0.2)
                    status.update(label="Done: every step is also in the case's audit trail",
                                  state="complete", expanded=True)
                run["animate"] = False
            else:
                with st.expander("Pipeline steps", expanded=True):
                    for step in run["steps"]:
                        st.markdown(step_line(*step))
            if st.button(f"Open case {run['case_id']} →", type="primary"):
                open_case(run["case_id"])

    # --- Results ------------------------------------------------------------
    with st.container(border=True):
        st.subheader("This session's results")
        s = show_session_results()
        if s["mistakes"]:
            st.caption("The agent is sometimes fooled by a mislabelled rejection code, as real systems can be. "
                       "Independent policy checks or a human review stop those mistakes before anything happens.")
        if s["failed"]:
            st.caption(f"{s['ai_cases']} of {s['failed']} failed payments were investigated by Gemini; "
                       "the rest by the rule-based agent.")

    if st.session_state.feed:
        with st.container(border=True):
            st.subheader("Recent payments")
            feed = pd.DataFrame(st.session_state.feed[:100])
            st.dataframe(
                feed.style.map(lambda v: "color:#8E1F17;font-weight:600" if v == "Failed" else "color:#1B5E36",
                               subset=["Outcome"]),
                hide_index=True, width="stretch",
                column_config={"Amount (S$)": st.column_config.NumberColumn(format="%.2f")},
            )
            st.caption(f"Showing the latest {len(feed)} of {len(st.session_state.feed)} payments.")

    if st.button("Reset simulation", help="Clears simulated payments, cases and decisions"):
        reset_state()
        st.session_state.batch_note = None
        st.rerun()


# ---------------------------------------------------------------------------
# Page 3: upcoming payments at risk
# ---------------------------------------------------------------------------
def at_risk():
    page_header("Proactive · Next 7 days", "Upcoming payments at risk",
                "Scheduled loan and GIRO payments that PayFix expects to fail. Fix them before the due date. "
                "PayFix only sends reminders; it never moves money.")

    for item in data.AT_RISK:
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 5, 2], vertical_alignment="center")
            c1.markdown(f"<span class='muted'>DUE</span><br><b style='font-size:20px'>{item['due']}</b>",
                        unsafe_allow_html=True)
            c2.markdown(
                f"**{item['type']}** &nbsp; {pill(item['likelihood'])}<br>"
                f"<span class='muted'>{item['customer']} · S${item['amount']:,.2f}</span><br>"
                f"<b>Why:</b> {item['why']}",
                unsafe_allow_html=True,
            )
            sent = item["key"] in st.session_state.reminders
            if c3.button("✓ Reminder queued" if sent else "Send reminder", key=f"rem_{item['key']}",
                         disabled=sent, type="secondary" if sent else "primary", width="stretch"):
                st.session_state.reminders.add(item["key"])
                st.rerun()
            c3.caption(item["channel"])


# ---------------------------------------------------------------------------
# Page 4: process owner dashboard
# ---------------------------------------------------------------------------
def dashboard():
    page_header("Process owner · Dashboard", "How PayFix is performing",
                "Live results from this session's simulation, plus sample weekly figures.")

    if any(c.get("simulated") for c in st.session_state.cases):
        with st.container(border=True):
            st.subheader("Live: this session's simulation")
            s = show_session_results()
            by_cause = pd.Series([sim.CAUSE_LABELS[c["true_cause"]] for c in s["cases"]]).value_counts()
            mix = pd.DataFrame({"Failure": by_cause.index, "Cases": by_cause.values})
            st.altair_chart(
                alt.Chart(mix).mark_bar(color="#0B6E63", cornerRadiusEnd=4, size=20)
                .encode(x=alt.X("Cases:Q", title="Failed payments by real cause",
                                axis=alt.Axis(tickMinStep=1, format="d")),
                        y=alt.Y("Failure:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
                        tooltip=["Failure", "Cases"])
                .properties(height=40 * len(mix) + 50),
                width="stretch",
            )
        st.divider()

    st.subheader("Sample weekly figures")
    st.caption("Week of 10–16 Nov 2026 · sample results from a test run on synthetic cases with known causes")

    for start in range(0, len(data.KPIS), 3):
        cols = st.columns(3)
        for col, (label, value, note) in zip(cols, data.KPIS[start:start + 3]):
            col.metric(label, value)
            col.caption(note)

    left, right = st.columns([3, 2], gap="large")

    with left:
        with st.container(border=True):
            st.subheader("Failures by type")
            mix = pd.DataFrame({"Failure": list(data.FAILURE_MIX), "Share (%)": list(data.FAILURE_MIX.values())})
            chart = (
                alt.Chart(mix)
                .mark_bar(color="#0B6E63", cornerRadiusEnd=4)
                .encode(
                    x=alt.X("Share (%):Q", title="Share of failures (%)"),
                    y=alt.Y("Failure:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
                    tooltip=["Failure", "Share (%)"],
                )
                .properties(height=320)
            )
            st.altair_chart(chart, width="stretch")

    with right:
        with st.container(border=True):
            st.subheader("How cases were resolved")
            res = pd.DataFrame({"Route": list(data.RESOLUTION_MIX), "Share (%)": list(data.RESOLUTION_MIX.values())})
            donut = (
                alt.Chart(res)
                .mark_arc(innerRadius=58, outerRadius=100)
                .encode(
                    theta="Share (%):Q",
                    color=alt.Color("Route:N", scale=alt.Scale(domain=list(data.RESOLUTION_MIX),
                                                                range=["#0B6E63", "#6FB8AE", "#C9CED8"]),
                                    legend=alt.Legend(orient="bottom", title=None, columns=1, labelLimit=260)),
                    tooltip=["Route", "Share (%)"],
                )
                .properties(height=260)
            )
            st.altair_chart(donut, width="stretch")
            st.caption("Officers overrode the AI on 9% of reviewed cases. Most overrides were partial "
                       "payments the AI read as insufficient funds.")

    decided = len(st.session_state.decisions)
    if decided:
        st.info(f"This session: you have recorded {decided} officer decision(s). They appear in each case's audit trail.")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="150" height="40" viewBox="0 0 150 40">'
    '<rect x="0" y="6" width="28" height="28" rx="7" fill="#0B6E63"/>'
    '<path d="M8 20.5l4.5 4.5L21 15" fill="none" stroke="#FFFFFF" stroke-width="3" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<text x="38" y="28" font-family="Helvetica, Arial, sans-serif" font-size="22" font-weight="700" '
    'fill="#FFFFFF">Pay<tspan fill="#5FD3C3">Fix</tspan></text></svg>'
)
st.logo("data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode(), size="large")

sim_page = st.Page(simulation, title="Live simulation", icon=":material/play_circle:", default=True)
queue_page = st.Page(queue, title="Failed payments", icon=":material/inbox:")
case_page = st.Page(case_detail, title="Case detail", icon=":material/fact_check:")
risk_page = st.Page(at_risk, title="Upcoming at risk", icon=":material/event_upcoming:")
dash_page = st.Page(dashboard, title="Dashboard", icon=":material/monitoring:")

with st.sidebar:
    st.markdown('<div class="pf-tag">Investigate. Validate. Resolve.</div>', unsafe_allow_html=True)
    if agent.available(st.secrets):
        st.toggle("Use Gemini agent", value=True, key="use_ai",
                  help="Off = use the offline rule-based agent. Useful if you hit the free-tier limit.")
        key_end = agent.get_setting("GEMINI_API_KEY", st.secrets).strip()[-4:]
        st.caption(f"🟢 Gemini agent on (key …{key_end}). If a call fails, the case says so and uses rules."
                   if st.session_state.use_ai else "⚪ Rule-based agent (Gemini switched off)")
        if st.button("Test Gemini", help="Sends one tiny request to check the key and model"):
            if not hasattr(agent, "ping"):
                st.error("agent.py on GitHub is an older version. Upload the latest agent.py.")
            else:
                with st.spinner("Contacting Gemini…"):
                    ok, msg = agent.ping(agent.get_setting("GEMINI_API_KEY", st.secrets),
                                         agent.get_setting("GEMINI_MODEL", st.secrets))
                (st.success if ok else st.error)(msg)
    else:
        st.caption("⚪ Rule-based agent · add GEMINI_API_KEY in Secrets to use Gemini")

if st.session_state.get("toast"):
    st.toast(st.session_state.pop("toast"), icon="✅")

st.navigation({"Demo": [sim_page], "Operations": [risk_page, queue_page, case_page],
               "Insights": [dash_page]}).run()
