"""PayFix: AI-assisted resolution of failed loan and recurring payments.

Prototype for the OCBC Ignite Innovation Challenge (Problem 2). Uses synthetic
data only. Run with:  streamlit run app.py
"""

import random
import time
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

import data
import simulator as sim

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
    .pill {display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:600}
    .card {background:#FFFFFF;border:1px solid #E1E4EA;border-radius:12px;padding:18px 20px;margin-bottom:12px}
    .muted {color:#5A6372;font-size:14px}
    .sms {background:#EEF6F5;border-radius:12px 12px 12px 4px;padding:14px 16px;color:#12332F;line-height:1.55}
    </style>
    """,
    unsafe_allow_html=True,
)


def pill(text):
    bg, fg = RISK_COLOURS.get(text, ("#E8EBF0", "#2E3644"))
    return f'<span class="pill" style="background:{bg};color:{fg}">{text}</span>'


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


def add_simulated(payment):
    """Run one payment through the PayFix pipeline and store the results."""
    case_id = f"PF-{st.session_state.next_case}"
    feed, case, steps = sim.process(payment, case_id)
    st.session_state.feed.insert(0, feed)
    if case is not None:
        st.session_state.next_case += 1
        st.session_state.cases.insert(0, case)
        st.session_state.audit[case_id] = list(case["audit"])
    return feed, case, steps


def current_status(case):
    return st.session_state.decisions.get(case["id"], case["status"])


def open_case(case_id):
    st.session_state.selected = case_id
    st.switch_page(case_page)


# ---------------------------------------------------------------------------
# Page 1: failed payments queue
# ---------------------------------------------------------------------------
def queue():
    st.title("Failed payments")
    st.caption(f"Loan repayments and recurring GIRO payments that failed today, {sim.now():%a %d %b %Y}")

    cases = st.session_state.cases
    groups = [c["group"] for c in cases]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Failed payments in queue", len(cases))
    c2.metric("Auto-resolved by PayFix", groups.count("auto"))
    c3.metric("Waiting for an officer", groups.count("review"))
    c4.metric("Escalated (high risk)", groups.count("escalated"))
    if not any(c.get("simulated") for c in cases):
        st.info("Showing sample cases only. Go to **Live simulation** to generate fake payments.")

    choice = st.segmented_control(
        "Filter", ["All cases", "Needs an officer", "Auto-resolved", "Escalated"],
        default="All cases", label_visibility="collapsed",
    )
    group = {"Needs an officer": "review", "Auto-resolved": "auto", "Escalated": "escalated"}.get(choice)
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
    ids = [c["id"] for c in st.session_state.cases]
    if st.session_state.selected not in ids:
        st.session_state.selected = ids[0]
    case_id = st.selectbox("Case", ids, index=ids.index(st.session_state.selected),
                           format_func=lambda i: f"{i} · {case_by_id(i)['type']}")
    st.session_state.selected = case_id
    case = case_by_id(case_id)

    st.markdown(f"## {case['id']} · {case['type']} &nbsp; {pill(case['risk'] + ' risk')}", unsafe_allow_html=True)
    st.markdown(
        f"<p class='muted'>{case['customer']} · S${case['amount']:,.2f} · rejection code {case['code']} "
        f"({case['failure']}) · <b>Status: {current_status(case)}</b></p>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 2], gap="large")

    with left:
        with st.container(border=True):
            st.subheader("What happened")
            st.write(case["explanation"])
            if case["confidence"] is not None:
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
                    st.warning("The agent was wrong, and the policy rules caught it before any action was taken.")
                else:
                    st.error("The agent was wrong and the rules did not catch it.")

    with right:
        with st.container(border=True):
            st.subheader("Suggested action")
            st.write(case["action"])
            st.markdown("**Policy checks (rules, not AI)**")
            for text, ok in case["checks"]:
                st.markdown(f"{'✅' if ok else '⛔'} {text}")
            if case["group"] == "review":
                st.warning(f"{case['risk']} risk: PayFix has prepared the fix, but an officer must approve it.")
            elif case["group"] == "escalated":
                st.error("High risk: a person must decide. PayFix will not act on this case.")
            else:
                st.success("Low risk: PayFix resolved this automatically.")

        if case["group"] != "auto":
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
                        status = f"{clicked} by {data.OFFICER}"
                        st.session_state.decisions[case_id] = status
                        note = f"{status}." + (f" Reason: {reason.strip()}" if reason.strip() else "")
                        st.session_state.audit[case_id].append((datetime.now().strftime("%H:%M"), data.OFFICER, note))
                        st.rerun()

        if case["message"]:
            with st.container(border=True):
                st.subheader("Customer message preview (SMS)")
                st.markdown(f"<div class='sms'>{case['message']}</div>", unsafe_allow_html=True)
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
        "review": sum(1 for c in simc if c["group"] == "review"),
        "escalated": sum(1 for c in simc if c["group"] == "escalated"),
        "accuracy": (1 - len(wrong) / len(simc)) if simc else None,
        "mistakes": len(wrong),
        "caught": sum(1 for c in wrong if c["blocked"]),
        "wrong_auto": sum(1 for c in simc if c["group"] == "auto" and not c["agent_correct"]),
        "cases": simc,
    }


def show_session_results():
    s = session_stats()
    r1 = st.columns(4)
    r1[0].metric("Payments processed", s["processed"])
    r1[1].metric("Paid first time", s["paid"])
    r1[2].metric("Failed", s["failed"])
    r1[3].metric("Auto-resolved by PayFix", s["auto"])
    r2 = st.columns(4)
    r2[0].metric("Sent to an officer", s["review"] + s["escalated"],
                 help=f"{s['review']} for review, {s['escalated']} escalated")
    r2[1].metric("Agent found the right cause", "—" if s["accuracy"] is None else f"{s['accuracy']:.0%}",
                 help="Compared with the simulation's ground truth, which the agent never sees")
    r2[2].metric("AI mistakes caught by rules", f"{s['caught']} of {s['mistakes']}")
    r2[3].metric("Wrong auto-actions", s["wrong_auto"], help="Target: always zero")
    return s


def simulation():
    st.title("Live simulation")
    st.caption("Generate fake loan, GIRO and standing-instruction payments and watch PayFix handle the failures: "
               "detect → agent investigates → policy rules check → auto-resolve or send to an officer. "
               "All data is invented.")

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
            for i in range(size):
                add_simulated(sim.random_payment(st.session_state.rng, rate))
                if live and (i % 2 == 0 or i == size - 1):
                    bar.progress((i + 1) / size, text=f"Processed {i + 1} of {size} payments")
                    table.dataframe(pd.DataFrame(st.session_state.feed[:10]), hide_index=True, width="stretch")
                    time.sleep(0.05)
            bar.progress(1.0, text=f"Done: {size} payments processed")
            new = len([c for c in st.session_state.cases if c.get("simulated")]) - before
            st.session_state.batch_note = f"Batch done: {size} payments, {new} failed and went through PayFix."
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
            st.caption("The agent is occasionally fooled by a mislabelled rejection code, as real systems can be. "
                       "Every time, the independent policy checks blocked its proposal before anything happened.")

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
    st.title("Upcoming payments at risk")
    st.caption("Scheduled loan and GIRO payments in the next 7 days that PayFix expects to fail. "
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
    st.title("How PayFix is performing")

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

    cols = st.columns(len(data.KPIS))
    for col, (label, value, note) in zip(cols, data.KPIS):
        col.metric(label, value, help=note)
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
                    y=alt.Y("Failure:N", sort="-x", title=None),
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
                .mark_arc(innerRadius=60)
                .encode(
                    theta="Share (%):Q",
                    color=alt.Color("Route:N", scale=alt.Scale(range=["#0B6E63", "#6FB8AE", "#C9CED8"]),
                                    legend=alt.Legend(orient="bottom", title=None)),
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
sim_page = st.Page(simulation, title="Live simulation", icon="▶️", default=True)
queue_page = st.Page(queue, title="Failed payments", icon="📥")
case_page = st.Page(case_detail, title="Case detail", icon="🔎")
risk_page = st.Page(at_risk, title="Upcoming at risk", icon="🔮")
dash_page = st.Page(dashboard, title="Dashboard", icon="📊")

with st.sidebar:
    st.markdown("### Pay**Fix**")

st.navigation([sim_page, risk_page, queue_page, case_page, dash_page]).run()
