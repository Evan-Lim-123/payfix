"""Payment simulator for the PayFix demo.

Generates fake recurring payments (loans, GIRO, standing instructions), runs them
through a simulated payment system, and sends every failure through the PayFix
pipeline:

    payment system  ->  agent investigates  ->  policy rules  ->  auto-resolve or officer

Everything is invented. The "agent" here is a rule-based stand-in so the demo works
offline with no API key. Swap `investigate()` for an LLM call later; keep the same
return shape and nothing else needs to change.
"""

import math
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SGT = ZoneInfo("Asia/Singapore")
AUTO_ACTION_LIMIT = 5000          # S$: above this a person must always decide
MIN_CONFIDENCE = 0.85             # below this, always route to an officer
CUTOFF = "16:00"                  # standing instructions submitted after this go next day

FIRST = ["Wei Ming", "Jia Hui", "Mei Ling", "Kai Wen", "Boon Keat", "Siew Lan", "Jun Jie", "Hui Min",
         "Aaron", "Rachel", "Daniel", "Priya", "Arjun", "Kavitha", "Nur Aisyah", "Muhammad Hafiz",
         "Siti", "Farhana", "Ravi", "Grace", "Marcus", "Shu Fen", "Zhi Hao", "Nadia", "Imran"]
LAST = ["Tan", "Lim", "Lee", "Ng", "Ong", "Wong", "Goh", "Chua", "Koh", "Teo", "Kumar", "Rahman",
        "Abdullah", "Singh", "Pillai", "Nair", "Ismail", "Hassan", "Fernandez", "Chen", "Yeo", "Ho"]
BIZ_A = ["Harbour", "Kopi Lane", "Bright Leaf", "Lion City", "Merlion", "Bukit", "Orchid", "Straits",
         "Marina", "Sunrise", "Evergreen", "Red Dot", "Jade", "Pioneer", "Rivervale"]
BIZ_B = ["Print", "F&B", "Trading", "Logistics", "Engineering", "Bakery", "Interiors", "Tech", "Motors"]

# name, channel, amount range (S$), customer segment, how common
PAYMENT_TYPES = [
    ("Home loan instalment", "loan", (1500, 4200), "individual", 0.20),
    ("Car loan instalment", "loan", (600, 1600), "individual", 0.14),
    ("Personal loan instalment", "loan", (300, 1200), "individual", 0.10),
    ("Business loan facility", "loan", (6000, 25000), "business", 0.04),
    ("Insurance premium (GIRO)", "giro", (90, 520), "either", 0.18),
    ("School fees (GIRO)", "giro", (220, 880), "individual", 0.08),
    ("Utilities (GIRO)", "giro", (60, 320), "either", 0.12),
    ("Rent (standing instruction)", "standing", (1600, 4200), "individual", 0.08),
    ("Supplier payment (standing instruction)", "standing", (2500, 12000), "business", 0.06),
]

CODES = {
    "insufficient_funds": "AM04",
    "exceeds_giro_limit": "AM02",
    "authorisation_expired": "MD01",
    "account_closed": "AC04",
    "recipient_changed": "BE01",
    "system_timeout": "SYS",
    "missed_cutoff": "CUT",
}
CODE_TO_CAUSE = {v: k for k, v in CODES.items()}

CAUSE_LABELS = {
    "insufficient_funds": "Insufficient funds",
    "exceeds_giro_limit": "Exceeds GIRO limit",
    "authorisation_expired": "GIRO authorisation expired",
    "account_closed": "Debit account closed",
    "recipient_changed": "Recipient account changed",
    "system_timeout": "System timeout",
    "missed_cutoff": "Missed cutoff time",
}

# Which channels each cause can happen on, and how common it is among failures
CAUSE_CHANNELS = {
    "insufficient_funds": ({"loan", "giro", "standing"}, 0.55),
    "exceeds_giro_limit": ({"giro"}, 0.10),
    "authorisation_expired": ({"giro"}, 0.08),
    "account_closed": ({"loan", "giro"}, 0.05),
    "recipient_changed": ({"standing"}, 0.03),
    "system_timeout": ({"loan", "giro", "standing"}, 0.12),
    "missed_cutoff": ({"standing"}, 0.07),
}


def now():
    return datetime.now(SGT)


def money(v):
    return f"S${v:,.2f}"


# ---------------------------------------------------------------------------
# 1. Generate payments
# ---------------------------------------------------------------------------
def _customer(rng, segment):
    if segment == "business" or (segment == "either" and rng.random() < 0.2):
        return f"{rng.choice(BIZ_A)} {rng.choice(BIZ_B)} Pte Ltd", "business"
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}", "individual"


def make_payment(rng, type_name=None, channel=None):
    """A healthy scheduled payment due today. Failures are injected afterwards."""
    options = [t for t in PAYMENT_TYPES if (type_name is None or t[0] == type_name)
               and (channel is None or t[1] in channel)]
    t = rng.choices(options, weights=[o[4] for o in options])[0]
    name, ch, (lo, hi), seg, _ = t
    customer, segment = _customer(rng, seg)
    amount = round(rng.uniform(lo, hi), 2)
    today = now().date()
    p = {
        "tx_id": f"TX-{rng.randint(100000, 999999)}",
        "type": name,
        "channel": ch,
        "segment": segment,
        "customer": customer,
        "amount": amount,
        "due": today,
        "is_loan": ch == "loan",
        # Data sources the agent and the rules can look up
        "balance": round(amount * rng.uniform(1.3, 6.0), 2),
        "balance_available": True,
        "salary_amount": round(rng.uniform(3500, 9000) if segment == "individual" else rng.uniform(30000, 120000), -2),
        "days_to_salary": rng.randint(3, 20),
        "past_misses": 0 if rng.random() < 0.9 else 1,
        "account_status": "active",
        "closed_on": None,
        "giro_limit": None,
        "previous_amount": amount,
        "auth_expiry": None,
        "recipient_changed_on": None,
        "submitted_time": "05:30" if ch != "standing" else f"{rng.randint(8, 15):02d}:{rng.randint(0, 59):02d}",
        "system_log": "ok",
        "log_available": True,
        # Demo-only flags
        "reported_code_override": None,
        "agent_trusts_code": False,
        "scenario": "random",
    }
    if ch == "giro":
        p["giro_limit"] = float(math.ceil(amount * rng.uniform(1.15, 1.6) / 50) * 50)
        p["auth_expiry"] = today + timedelta(days=rng.randint(30, 400))
    return p


def inject(p, cause, rng):
    """Change the payment's underlying data so that it fails for `cause`."""
    today = p["due"]
    if cause == "insufficient_funds":
        p["balance"] = round(p["amount"] * rng.uniform(0.2, 0.85), 2)
        p["days_to_salary"] = rng.choice([1, 1, 2, 4, 9, 14])
    elif cause == "exceeds_giro_limit":
        p["previous_amount"] = p["amount"]
        p["amount"] = round(p["amount"] * rng.uniform(1.12, 1.4), 2)
        p["giro_limit"] = float(math.ceil(p["previous_amount"] * 1.02 / 50) * 50)
        if p["giro_limit"] >= p["amount"]:
            p["giro_limit"] = float(math.floor((p["amount"] - 1) / 50) * 50)
        p["balance"] = max(p["balance"], p["amount"] * 2)
    elif cause == "authorisation_expired":
        p["auth_expiry"] = today - timedelta(days=rng.randint(1, 20))
    elif cause == "account_closed":
        p["account_status"] = "closed"
        p["closed_on"] = today - timedelta(days=rng.randint(2, 15))
    elif cause == "recipient_changed":
        p["recipient_changed_on"] = today - timedelta(days=rng.randint(1, 3))
    elif cause == "system_timeout":
        p["system_log"] = "timeout"
    elif cause == "missed_cutoff":
        p["submitted_time"] = f"16:{rng.randint(5, 59):02d}"
    return p


def random_payment(rng, fail_rate):
    """Random payment: usually succeeds, sometimes fails with a realistic cause."""
    if rng.random() >= fail_rate:
        return make_payment(rng)
    causes = list(CAUSE_CHANNELS)
    cause = rng.choices(causes, weights=[CAUSE_CHANNELS[c][1] for c in causes])[0]
    p = make_payment(rng, channel=CAUSE_CHANNELS[cause][0])
    p = inject(p, cause, rng)
    if cause == "system_timeout" and rng.random() < 0.3:
        # Realistic noise: the payment system mislabels a timeout as AM04 and the log
        # is unavailable, so the agent is fooled. The policy rules should catch it.
        p["reported_code_override"] = "AM04"
        p["log_available"] = False
        p["agent_trusts_code"] = True
        p["scenario"] = "misleading_code"
    return p


# ---------------------------------------------------------------------------
# 2. Simulated payment system: tries the debit, returns the true outcome
# ---------------------------------------------------------------------------
def attempt(p):
    """Returns (true_cause or None, reported rejection code or None)."""
    cause = None
    if p["account_status"] == "closed":
        cause = "account_closed"
    elif p["channel"] == "giro" and p["auth_expiry"] < p["due"]:
        cause = "authorisation_expired"
    elif p["recipient_changed_on"] is not None:
        cause = "recipient_changed"
    elif p["channel"] == "giro" and p["amount"] > p["giro_limit"]:
        cause = "exceeds_giro_limit"
    elif p["system_log"] == "timeout":
        cause = "system_timeout"
    elif p["channel"] == "standing" and p["submitted_time"] >= CUTOFF:
        cause = "missed_cutoff"
    elif p["balance"] < p["amount"]:
        cause = "insufficient_funds"
    if cause is None:
        return None, None
    return cause, p["reported_code_override"] or CODES[cause]


# ---------------------------------------------------------------------------
# 3. Investigation agent (rule-based stand-in for an LLM agent)
# ---------------------------------------------------------------------------
def _tools(p):
    """Evidence lookups the agent performs. Each: (tool call, label, finding)."""
    calls = [("lookup_payment", "Payment", f"{p['type']}, {money(p['amount'])} due today.")]
    if p["balance_available"]:
        calls.append(("check_balance", "Balance on debit date", f"{money(p['balance'])} at 06:00."))
    else:
        calls.append(("check_balance", "Balance on debit date", "No data returned (balance service unavailable)."))
    if p["channel"] == "giro":
        exp = p["auth_expiry"]
        state = "expired" if exp < p["due"] else "active"
        calls.append(("check_giro_mandate", "GIRO authorisation",
                      f"{state.capitalize()}, limit {money(p['giro_limit'])}, expires {exp:%d %b %Y}."))
        if p["previous_amount"] != p["amount"]:
            calls.append(("billing_history", "Billing history",
                          f"Was {money(p['previous_amount'])}, now {money(p['amount'])}."))
    status = f"Closed on {p['closed_on']:%d %b %Y}." if p["account_status"] == "closed" else "Active."
    calls.append(("check_account_status", "Debit account", status))
    if p["channel"] == "standing":
        changed = (f"Recipient details changed on {p['recipient_changed_on']:%d %b}."
                   if p["recipient_changed_on"] else "No recent change.")
        calls.append(("check_recipient", "Recipient", changed))
        calls.append(("check_submission_time", "Submission time", f"{p['submitted_time']}, cutoff {CUTOFF}."))
    if p["log_available"]:
        log = "Timeout: no response from debit service." if p["system_log"] == "timeout" else "No errors."
    else:
        log = "Log not returned."
    calls.append(("read_system_log", "System log", log))
    hist = f"Salary ~{money(p['salary_amount'])} usually arrives in {p['days_to_salary']} day(s). "
    hist += f"{p['past_misses']} missed payment(s) in last 12 months."
    calls.append(("payment_history", "Payment history", hist))
    return calls


def _agent_checks(p, cause, code):
    """The agent's own evidence checklist for a cause. None = could not check."""
    bal = p["balance"] if p["balance_available"] else None
    log_ok = (p["system_log"] != "timeout") if p["log_available"] else None
    if p.get("agent_trusts_code"):
        # The agent's mistake in the "AI is wrong" scenario: it trusts the code and
        # never checks the submission time, so it feels very sure of itself.
        return [("Rejection code matches the cause", True), ("Payment type can fail this way", True),
                ("No conflicting signal found", True)]
    table = {
        "insufficient_funds": [("Rejection code is AM04", code == "AM04"),
                               ("Balance below amount", None if bal is None else bal < p["amount"]),
                               ("No technical error in log", log_ok),
                               ("Debit account active", p["account_status"] == "active")],
        "exceeds_giro_limit": [("Rejection code is AM02", code == "AM02"),
                               ("Amount above GIRO limit", p["amount"] > (p["giro_limit"] or 1e12)),
                               ("Enough balance", None if bal is None else bal >= p["amount"])],
        "authorisation_expired": [("Rejection code is MD01", code == "MD01"),
                                  ("Mandate expired before due date",
                                   p["auth_expiry"] is not None and p["auth_expiry"] < p["due"])],
        "account_closed": [("Rejection code is AC04", code == "AC04"),
                           ("Account status is closed", p["account_status"] == "closed")],
        "recipient_changed": [("Rejection code is BE01", code == "BE01"),
                              ("Recipient changed recently", p["recipient_changed_on"] is not None)],
        "system_timeout": [("Rejection code is SYS", code == "SYS"),
                           ("Log shows a timeout", None if log_ok is None else not log_ok),
                           ("Enough balance", None if bal is None else bal >= p["amount"])],
        "missed_cutoff": [("Rejection code is CUT", code == "CUT"),
                          ("Submitted after cutoff", p["submitted_time"] >= CUTOFF)],
    }
    return table[cause]


def investigate(p, code):
    """Look up evidence, decide the likely cause, propose an action.

    Returns a dict (the AgentResult): cause, explanation, evidence, missing,
    confidence, checklist, tool_calls.
    """
    calls = _tools(p)
    missing = []
    if not p["balance_available"]:
        missing.append("Account balance on the debit date")
    if not p["log_available"]:
        missing.append("Payment system log")

    # Work out the cause from evidence; fall back to the code when evidence is missing.
    if p.get("agent_trusts_code"):
        cause = CODE_TO_CAUSE[code]
    elif p["account_status"] == "closed":
        cause = "account_closed"
    elif p["channel"] == "giro" and p["auth_expiry"] < p["due"]:
        cause = "authorisation_expired"
    elif p["recipient_changed_on"] is not None:
        cause = "recipient_changed"
    elif p["channel"] == "giro" and p["amount"] > p["giro_limit"]:
        cause = "exceeds_giro_limit"
    elif p["log_available"] and p["system_log"] == "timeout":
        cause = "system_timeout"
    elif p["channel"] == "standing" and p["submitted_time"] >= CUTOFF:
        cause = "missed_cutoff"
    else:
        cause = CODE_TO_CAUSE.get(code, "insufficient_funds")

    checklist = _agent_checks(p, cause, code)
    confirmed = sum(1 for _, ok in checklist if ok)
    confidence = round(0.4 + 0.59 * confirmed / len(checklist), 2)

    return {
        "cause": cause,
        "explanation": _explain(p, cause),
        "evidence": [(label, finding) for _, label, finding in calls],
        "tool_calls": calls,
        "missing": missing,
        "checklist": checklist,
        "confidence": confidence,
    }


def _explain(p, cause):
    a = money(p["amount"])
    if cause == "insufficient_funds":
        if p.get("agent_trusts_code"):
            return ("The payment system returned code AM04 (insufficient funds), so the customer is likely "
                    "short of funds. The customer should be notified and the debit retried.")
        if not p["balance_available"]:
            return (f"The {p['type'].lower()} of {a} was rejected with an insufficient-funds code, but the "
                    "balance service returned no data, so PayFix cannot confirm the shortfall or how big it is.")
        gap = money(p["amount"] - p["balance"])
        text = f"The account held {money(p['balance'])}, which is {gap} short of the {a} payment. "
        if p["past_misses"]:
            return text + "This customer has missed before in the last 12 months, so this may be a lasting problem."
        if p["days_to_salary"] <= 3:
            return text + (f"A salary credit of about {money(p['salary_amount'])} usually arrives in "
                           f"{p['days_to_salary']} day(s), so this looks like a short timing gap.")
        return text + "No salary credit is expected in the next few days."
    if cause == "exceeds_giro_limit":
        return (f"The bill rose from {money(p['previous_amount'])} to {a}, above the customer's GIRO limit of "
                f"{money(p['giro_limit'])}, so the debit was rejected. Funds were sufficient.")
    if cause == "authorisation_expired":
        return f"The GIRO authorisation expired on {p['auth_expiry']:%d %b %Y}, before today's {a} payment."
    if cause == "account_closed":
        return f"The linked debit account was closed on {p['closed_on']:%d %b %Y}, so the {a} payment could not be debited."
    if cause == "recipient_changed":
        return (f"The recipient's account details on this standing instruction were changed on "
                f"{p['recipient_changed_on']:%d %b}. Changed recipient details are a common scam pattern, "
                "so PayFix will not suggest a fix.")
    if cause == "system_timeout":
        return "The debit request timed out on the payment system. Funds, mandate and account were all fine."
    if cause == "missed_cutoff":
        if p.get("agent_trusts_code"):
            return ("The payment system returned code CUT, which means the instruction missed the 16:00 cutoff. "
                    "The payment should be rescheduled to the next business day.")
        return f"The instruction was submitted at {p['submitted_time']}, after the {CUTOFF} cutoff."
    return "Cause unclear."


# ---------------------------------------------------------------------------
# 4. Policy rules: decide what is allowed (rules, not AI)
# ---------------------------------------------------------------------------
ACTIONS = {
    # cause: (action text, base risk, auto-resolvable)
    "system_timeout": ("Retry the debit once now.", "Low", True),
    "missed_cutoff": ("Reschedule to the next business day at 09:00.", "Low", True),
    "insufficient_funds": ("Notify the customer and retry once after funds arrive.", "Medium", False),
    "exceeds_giro_limit": ("Ask the customer to raise the GIRO limit, then retry.", "Medium", False),
    "authorisation_expired": ("Ask the customer to renew the GIRO authorisation.", "High", False),
    "account_closed": ("Contact the customer for a new debit account. Do not guess.", "High", False),
    "recipient_changed": ("Always escalate. Verify the change with the customer by phone.", "High", False),
}


def _validate(p, cause):
    """Independent check, straight from the source data, that the claimed cause is real.
    Returns (passed: bool or None if data missing, description)."""
    if cause == "insufficient_funds":
        if not p["balance_available"]:
            return None, "Balance below amount (balance data missing)"
        return p["balance"] < p["amount"], f"Balance {money(p['balance'])} below amount {money(p['amount'])}"
    if cause == "exceeds_giro_limit":
        return p["amount"] > p["giro_limit"], f"Amount above GIRO limit {money(p['giro_limit'])}"
    if cause == "authorisation_expired":
        return p["auth_expiry"] < p["due"], f"Mandate expiry {p['auth_expiry']:%d %b} is before due date"
    if cause == "account_closed":
        return p["account_status"] == "closed", "Account status is closed"
    if cause == "recipient_changed":
        return p["recipient_changed_on"] is not None, "Recipient change found on record"
    if cause == "system_timeout":
        if not p["log_available"]:
            return None, "Log shows a timeout (log missing)"
        return p["system_log"] == "timeout", "System log shows a timeout"
    if cause == "missed_cutoff":
        return p["submitted_time"] >= CUTOFF, f"Submission time {p['submitted_time']} is after {CUTOFF}"
    return False, "Unknown cause"


def decide(p, result):
    """Returns the Decision: group (auto/review/escalated), risk, status, action, checks."""
    cause = result["cause"]
    action, risk, can_auto = ACTIONS[cause]
    repeat_loan_miss = cause == "insufficient_funds" and p["is_loan"] and p["past_misses"] >= 1
    if cause == "insufficient_funds" and not repeat_loan_miss and p["balance_available"]:
        days = 1 + p["days_to_salary"] if p["days_to_salary"] <= 3 else 3
        retry_on = p["due"] + timedelta(days=days)
        action = f"Notify the customer now, then retry once on {retry_on:%a %d %b}."
    if repeat_loan_miss:
        action, risk = "Escalate to the loans team. Repeated misses may breach the loan terms.", "High"

    valid, vtext = _validate(p, cause)
    conf = result["confidence"]
    checks = [
        (f"Evidence supports the cause: {vtext}", bool(valid)),
        (f"Amount {money(p['amount'])} within {money(AUTO_ACTION_LIMIT)} action limit", p["amount"] <= AUTO_ACTION_LIMIT),
        (f"Confidence {conf:.0%} meets the {MIN_CONFIDENCE:.0%} minimum", conf >= MIN_CONFIDENCE),
        ("All required data available", not result["missing"]),
    ]
    if cause == "recipient_changed":
        checks.append(("Recipient changes are never auto-resolved", False))
    if repeat_loan_miss:
        checks.append(("Repeated loan misses are never auto-resolved", False))

    # Routing, in priority order
    if valid is False:
        return {"group": "escalated", "risk": "High", "checks": checks, "blocked": True,
                "status": "Escalated · AI claim failed validation",
                "action": f"Blocked. The agent proposed: \"{action}\" but the evidence does not support "
                          "the claimed cause. An officer must investigate."}
    if result["missing"]:
        return {"group": "review", "risk": "High" if risk == "High" else "Medium", "checks": checks,
                "blocked": False, "status": "Waiting for information",
                "action": "Request the missing information before acting: " + "; ".join(result["missing"]) + "."}
    if cause == "recipient_changed" or repeat_loan_miss:
        status = "Escalated to loans team" if repeat_loan_miss else "Escalated"
        return {"group": "escalated", "risk": "High", "checks": checks, "blocked": False,
                "status": status, "action": action}
    if p["amount"] > AUTO_ACTION_LIMIT:
        return {"group": "review", "risk": "High", "checks": checks, "blocked": False,
                "status": "Awaiting officer (high value)",
                "action": action + f" Above {money(AUTO_ACTION_LIMIT)}, so an officer must approve."}
    if conf < MIN_CONFIDENCE:
        return {"group": "review", "risk": risk, "checks": checks, "blocked": False,
                "status": "Awaiting officer (low confidence)", "action": action}
    if can_auto:
        done = "retried" if cause == "system_timeout" else "rescheduled"
        return {"group": "auto", "risk": "Low", "checks": checks, "blocked": False,
                "status": f"Auto-resolved · {done}", "action": action}
    return {"group": "review", "risk": risk, "checks": checks, "blocked": False,
            "status": "Awaiting officer", "action": action}


def _message(p, cause, group):
    if group == "auto" or cause in ("recipient_changed", "system_timeout", "missed_cutoff"):
        return ""
    first = p["customer"].split()[0] if p["segment"] == "individual" else p["customer"]
    a = money(p["amount"])
    if cause == "insufficient_funds":
        return (f"Hi {first}, your {p['type'].lower()} of {a} due today could not be debited due to "
                "insufficient funds. Please ensure your account has enough funds; we will retry once.")
    if cause == "exceeds_giro_limit":
        return (f"Hi {first}, your payment of {a} is above your GIRO limit of {money(p['giro_limit'])}. "
                "Please raise the limit in the app so we can retry.")
    if cause == "authorisation_expired":
        return f"Hi {first}, your GIRO authorisation has expired. Please renew it so the {a} payment can go through."
    if cause == "account_closed":
        return (f"Hi {first}, your payment of {a} could not be made because the linked account is closed. "
                "Please set up the arrangement with your new account.")
    return ""


# ---------------------------------------------------------------------------
# 5. Run the whole pipeline for one payment
# ---------------------------------------------------------------------------
def process(p, case_id):
    """Runs one payment end to end.

    Returns (feed_row, case or None, steps). `case` has the same shape as data.CASES,
    plus ground-truth fields. `steps` is a list of (stage, text, state) for the live view.
    """
    t = now()
    stamp = lambda s: (t + timedelta(seconds=s)).strftime("%H:%M:%S")
    true_cause, code = attempt(p)
    feed = {"Time": stamp(0), "Payment": p["tx_id"], "Customer": p["customer"], "Type": p["type"],
            "Amount (S$)": p["amount"], "Outcome": "Paid", "Code": "", "PayFix route": "", "Case": ""}
    if true_cause is None:
        return feed, None, [("Payment system", f"{p['tx_id']} debited successfully.", "ok")]

    result = investigate(p, code)
    decision = decide(p, result)
    agent_cause = result["cause"]

    audit = [(stamp(0), "Payment system", f"Debit rejected with code {code}. Case {case_id} created.")]
    steps = [("Payment system", f"{p['tx_id']} rejected with code {code}. Case {case_id} created.", "fail")]
    for i, (tool, label, finding) in enumerate(result["tool_calls"], start=1):
        audit.append((stamp(i), "Agent", f"{tool}() → {finding}"))
        steps.append(("Agent tool call", f"`{tool}()` → {finding}", "ok"))
    n = len(result["tool_calls"]) + 1
    audit.append((stamp(n), "Agent",
                   f"Likely cause: {CAUSE_LABELS[agent_cause]} ({result['confidence']:.0%} confidence)."))
    steps.append(("Agent conclusion", f"{CAUSE_LABELS[agent_cause]} · confidence {result['confidence']:.0%}. "
                  + result["explanation"], "ok"))
    for text, ok in decision["checks"]:
        steps.append(("Policy check", text, "ok" if ok else "fail"))
    route = {"auto": "Low risk, all checks passed. Auto-resolved.",
             "review": f"{decision['risk']} risk. Routed to officer queue ({decision['status']}).",
             "escalated": f"High risk. {decision['status']}."}[decision["group"]]
    audit.append((stamp(n + 1), "Policy rules", route))
    steps.append(("Decision", route, {"auto": "ok", "review": "warn", "escalated": "fail"}[decision["group"]]))
    if decision["group"] == "auto":
        audit.append((stamp(n + 2), "PayFix", decision["action"] + " Done."))
        steps.append(("Action", decision["action"] + " Done.", "ok"))

    case = {
        "id": case_id,
        "type": p["type"],
        "customer": p["customer"],
        "amount": p["amount"],
        "code": code,
        "failure": CAUSE_LABELS[agent_cause],
        "risk": decision["risk"],
        "group": decision["group"],
        "status": decision["status"],
        "confidence": result["confidence"],
        "explanation": result["explanation"],
        "evidence": result["evidence"],
        "missing": result["missing"],
        "action": decision["action"],
        "checks": decision["checks"],
        "message": "" if decision["blocked"] else _message(p, agent_cause, decision["group"]),
        # Extra fields for the simulation and scoring
        "simulated": True,
        "scenario": p["scenario"],
        "true_cause": true_cause,
        "agent_cause": agent_cause,
        "agent_correct": agent_cause == true_cause,
        "blocked": decision["blocked"],
        "audit": audit,
    }
    feed.update({"Outcome": "Failed", "Code": code, "PayFix route": decision["status"], "Case": case_id})
    return feed, case, steps


# ---------------------------------------------------------------------------
# 6. Demo scenarios (one click each)
# ---------------------------------------------------------------------------
def _scenario(rng, key):
    if key == "salary_tomorrow":
        p = inject(make_payment(rng, "Home loan instalment"), "insufficient_funds", rng)
        p["days_to_salary"], p["past_misses"] = 1, 0
    elif key == "giro_limit":
        p = inject(make_payment(rng, "Insurance premium (GIRO)"), "exceeds_giro_limit", rng)
    elif key == "timeout":
        p = inject(make_payment(rng, "Car loan instalment"), "system_timeout", rng)
    elif key == "cutoff":
        p = inject(make_payment(rng, "Rent (standing instruction)"), "missed_cutoff", rng)
    elif key == "recipient":
        p = inject(make_payment(rng, "Rent (standing instruction)"), "recipient_changed", rng)
    elif key == "auth_expired":
        p = inject(make_payment(rng, "School fees (GIRO)"), "authorisation_expired", rng)
    elif key == "repeat_miss":
        p = inject(make_payment(rng, "Car loan instalment"), "insufficient_funds", rng)
        p["past_misses"] = 2
    elif key == "high_value":
        p = inject(make_payment(rng, "Supplier payment (standing instruction)"), "system_timeout", rng)
        p["amount"] = round(rng.uniform(40000, 60000), 2)
        p["balance"] = p["amount"] * 3
    elif key == "missing_data":
        p = inject(make_payment(rng, "Home loan instalment"), "insufficient_funds", rng)
        p["balance_available"] = False
        p["past_misses"] = 0
    elif key == "agent_wrong":
        # Truth: a system timeout. The payment system wrongly reports CUT, the log is
        # unavailable, and the agent trusts the code. The rules must catch it.
        p = inject(make_payment(rng, "Rent (standing instruction)"), "system_timeout", rng)
        p["submitted_time"] = f"{rng.randint(9, 11):02d}:{rng.randint(0, 59):02d}"
        p["reported_code_override"] = "CUT"
        p["log_available"] = False
        p["agent_trusts_code"] = True
    else:
        raise ValueError(key)
    p["scenario"] = key
    return p


SCENARIOS = {
    # key: (button label, what it demonstrates)
    "timeout": ("System timeout", "Low risk: PayFix retries automatically."),
    "cutoff": ("Missed cutoff", "Low risk: PayFix reschedules automatically."),
    "salary_tomorrow": ("Short of funds", "Medium risk: salary arrives tomorrow, so PayFix prepares a "
                                          "retry and an officer approves."),
    "giro_limit": ("Over GIRO limit", "Medium risk: the premium went up, so the customer is asked to "
                                      "raise their GIRO limit."),
    "auth_expired": ("GIRO expired", "High risk: the GIRO authorisation expired, so the customer must renew."),
    "repeat_miss": ("Repeat loan miss", "Second missed loan instalment: escalated to the loans team."),
    "recipient": ("Recipient changed", "Possible scam pattern: always escalated, never auto-fixed."),
    "high_value": ("High value", "Easy fix, but above S$5,000, so a person must decide."),
    "missing_data": ("Missing data", "The balance service returns nothing, so PayFix asks for the data "
                                     "instead of guessing."),
    "agent_wrong": ("AI is wrong", "The agent is confidently wrong, and the policy rules block it."),
}


def scenario_payment(rng, key):
    return _scenario(rng, key)
