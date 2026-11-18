"""PayFix: AI-assisted resolution of failed loan and recurring payments.

Prototype for the OCBC Ignite Innovation Challenge (Problem 2). Uses synthetic
data only. Run with:  streamlit run app.py
"""

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

import data

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
if "audit" not in st.session_state:
    st.session_state.audit = {c["id"]: data.initial_audit(c) for c in data.CASES}
    st.session_state.decisions = {}
    st.session_state.reminders = set()
    st.session_state.selected = data.CASES[0]["id"]


def case_by_id(case_id):
    return next(c for c in data.CASES if c["id"] == case_id)


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
    st.caption(f"Loan repayments and recurring GIRO payments that failed today, {data.TODAY:%a %d %b %Y}")

    cases = data.CASES
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Failed today", 148)
    c2.metric("Auto-resolved by PayFix", 57)
    c3.metric("Waiting for an officer", 63)
    c4.metric("Escalated (high risk)", 28)

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
    ids = [c["id"] for c in data.CASES]
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
queue_page = st.Page(queue, title="Failed payments", icon="📥", default=True)
case_page = st.Page(case_detail, title="Case detail", icon="🔎")
risk_page = st.Page(at_risk, title="Upcoming at risk", icon="🔮")
dash_page = st.Page(dashboard, title="Dashboard", icon="📊")

with st.sidebar:
    st.markdown("### Pay**Fix**")
    st.caption(f"Officer: {data.OFFICER}")
    st.caption("Synthetic data only. Prototype for the OCBC Ignite Innovation Challenge.")

st.navigation([risk_page, queue_page, case_page, dash_page]).run()
