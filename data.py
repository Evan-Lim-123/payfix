"""Sample (synthetic) data for the PayFix prototype.

Everything here is invented for the demo. Person 1 (Data) can later replace
these lists with the real synthetic-data generator and ground truth, as long
as the field names stay the same.
"""

from datetime import date

TODAY = date(2026, 11, 17)
OFFICER = "J. Tan"

# Policy constants (owned by Person 3, Policy & audit)
AUTO_ACTION_LIMIT = 5_000      # S$, above this a person must always decide
MIN_CONFIDENCE = 0.85          # below this, always route to an officer

# ---------------------------------------------------------------------------
# Failed payment cases
# group: "auto" (PayFix fixed it), "review" (needs an officer), "escalated"
# ---------------------------------------------------------------------------
CASES = [
    {
        "id": "PF-1042",
        "type": "Home loan instalment",
        "customer": "Tan Wei Ming",
        "amount": 2310.00,
        "code": "AM04",
        "failure": "Insufficient funds",
        "risk": "Medium",
        "group": "review",
        "status": "Awaiting officer",
        "confidence": 0.92,
        "explanation": (
            "The monthly instalment could not be debited because the account held "
            "S$1,180.40, which is S$1,129.60 short. In each of the last 6 months a salary "
            "credit of about S$4,200 arrived on the 18th, so this looks like a one-day "
            "timing gap rather than a lasting problem. This is the first missed "
            "instalment in 12 months."
        ),
        "evidence": [
            ("Loan account", "Instalment S$2,310.00 on the 17th. 0 missed in last 12 months."),
            ("Balance on debit date", "S$1,180.40 at 06:00. Shortfall S$1,129.60."),
            ("Credit pattern", "Salary ~S$4,200 on the 18th, 6 of 6 months."),
            ("Other failures", "No other failed payments this month."),
        ],
        "missing": [],
        "action": "Notify the customer now, then retry the debit once on Thu 19 Nov after the expected salary credit. Waive the late fee if the retry succeeds.",
        "checks": [
            ("Retry + notify is allowed for insufficient funds", True),
            ("Amount below S$5,000 action limit", True),
            ("Evidence supports the cause: balance < instalment", True),
            ("First missed instalment in 12 months", True),
            ("Confidence 92% meets the 85% minimum", True),
        ],
        "message": (
            "Hi Tan Wei Ming, your home loan instalment of S$2,310.00 due 17 Nov could not be "
            "debited due to insufficient funds. We will retry on 19 Nov. Please ensure your "
            "account has enough funds. No late fee applies if the retry succeeds."
        ),
    },
    {
        "id": "PF-1041",
        "type": "Insurance premium (GIRO)",
        "customer": "Siti Nur Aisyah",
        "amount": 230.00,
        "code": "AM02",
        "failure": "Exceeds GIRO limit",
        "risk": "Medium",
        "group": "review",
        "status": "Customer notified",
        "confidence": 0.97,
        "explanation": (
            "The premium rose from S$195 to S$230 this month, but the customer's GIRO "
            "authorisation has a S$200 limit, so the debit was rejected."
        ),
        "evidence": [
            ("GIRO authorisation", "Active, limit S$200."),
            ("Billing history", "Premium S$195 for 11 months, S$230 from Nov."),
            ("Balance", "Sufficient funds on debit date."),
        ],
        "missing": [],
        "action": "Ask the customer to raise the GIRO limit, then retry once the limit is updated.",
        "checks": [
            ("Notify is allowed for limit breaches", True),
            ("Amount below S$5,000 action limit", True),
            ("Evidence supports the cause: amount > limit", True),
            ("Confidence 97% meets the 85% minimum", True),
        ],
        "message": (
            "Hi Siti, your insurance premium of S$230.00 could not be paid because it is above "
            "your GIRO limit of S$200. Please raise the limit in the app so we can retry."
        ),
    },
    {
        "id": "PF-1040",
        "type": "Rent (standing instruction)",
        "customer": "Rajesh Kumar",
        "amount": 2800.00,
        "code": "AC01",
        "failure": "Recipient account changed",
        "risk": "High",
        "group": "escalated",
        "status": "Escalated",
        "confidence": None,
        "explanation": (
            "The landlord's account number on the standing instruction no longer matches the "
            "account the payment went to last month, and a change request arrived by email "
            "two days ago. Changed recipient details are a common scam pattern, so PayFix "
            "does not suggest a fix."
        ),
        "evidence": [
            ("Standing instruction", "Monthly S$2,800 to the same recipient for 14 months."),
            ("Recent change", "Recipient account edited 15 Nov."),
        ],
        "missing": ["Confirmation from the customer through an official channel"],
        "action": "Always escalate. An officer must verify the change with the customer by phone.",
        "checks": [
            ("Recipient changes are never auto-resolved", False),
        ],
        "message": "",
    },
    {
        "id": "PF-1039",
        "type": "Car loan instalment",
        "customer": "Lim Jia Hui",
        "amount": 1045.50,
        "code": "SYS",
        "failure": "System timeout",
        "risk": "Low",
        "group": "auto",
        "status": "Auto-resolved · retried",
        "confidence": 0.99,
        "explanation": "The debit request timed out on the payment system. Funds and authorisation were fine.",
        "evidence": [("System log", "Timeout at 06:00:14, no response from debit service.")],
        "missing": [],
        "action": "Retried once at 06:15. Retry succeeded.",
        "checks": [
            ("Retry allowed for timeouts", True),
            ("Amount below S$5,000 action limit", True),
            ("Confidence 99% meets the 85% minimum", True),
        ],
        "message": "",
    },
    {
        "id": "PF-1038",
        "type": "Supplier payment (GIRO)",
        "customer": "Harbour Print Pte Ltd",
        "amount": 4600.00,
        "code": "CUT",
        "failure": "Missed cutoff time",
        "risk": "Low",
        "group": "auto",
        "status": "Auto-resolved · rescheduled",
        "confidence": 0.99,
        "explanation": "The payment was submitted at 16:42, after the 16:00 cutoff.",
        "evidence": [("Submission time", "16:42, cutoff 16:00.")],
        "missing": [],
        "action": "Rescheduled to the next window, Wed 18 Nov 09:00.",
        "checks": [
            ("Reschedule allowed for missed cutoff", True),
            ("Timestamp really is after cutoff", True),
            ("Amount below S$5,000 action limit", True),
        ],
        "message": "",
    },
    {
        "id": "PF-1037",
        "type": "Business loan facility",
        "customer": "Kopi Lane F&B Pte Ltd",
        "amount": 18750.00,
        "code": "AM04",
        "failure": "Insufficient funds · 2nd miss",
        "risk": "High",
        "group": "escalated",
        "status": "Escalated to loans team",
        "confidence": 0.88,
        "explanation": "Second missed instalment in a row on a business facility. Balance has trended down for 3 months.",
        "evidence": [
            ("Loan facility", "Missed instalment in October as well."),
            ("Balance trend", "Average balance down 46% over 3 months."),
        ],
        "missing": [],
        "action": "Escalate to the loans team. Repeated misses may breach the facility terms.",
        "checks": [
            ("Amount above S$5,000 action limit", False),
            ("Repeated misses are never auto-resolved", False),
        ],
        "message": "",
    },
    {
        "id": "PF-1036",
        "type": "School fees (GIRO)",
        "customer": "Ong Mei Ling",
        "amount": 640.00,
        "code": "MD01",
        "failure": "GIRO authorisation expired",
        "risk": "High",
        "group": "review",
        "status": "Awaiting officer",
        "confidence": 0.95,
        "explanation": "The GIRO authorisation for school fees expired on 15 Nov.",
        "evidence": [("GIRO authorisation", "Expired 15 Nov 2026.")],
        "missing": [],
        "action": "Ask the customer to renew the authorisation. Officer tracks the case until renewed.",
        "checks": [
            ("Notify allowed for expired authorisation", True),
            ("Confidence 95% meets the 85% minimum", True),
        ],
        "message": "Hi Ong Mei Ling, your GIRO authorisation for school fees has expired. Please renew it so the S$640.00 payment can go through.",
    },
    {
        "id": "PF-1035",
        "type": "Insurance premium (GIRO)",
        "customer": "Muhammad Hafiz",
        "amount": 185.00,
        "code": "AC04",
        "failure": "Debit account closed",
        "risk": "High",
        "group": "review",
        "status": "Waiting for customer",
        "confidence": 0.94,
        "explanation": "The debit account linked to this GIRO arrangement was closed on 10 Nov.",
        "evidence": [("Account status", "Closed 10 Nov 2026 at the customer's request.")],
        "missing": ["New debit account details"],
        "action": "Contact the customer for a new debit account. Do not guess.",
        "checks": [
            ("Account changes need customer confirmation", True),
        ],
        "message": "Hi Muhammad Hafiz, your insurance premium could not be paid because the linked account is closed. Please set up GIRO with your new account.",
    },
]

# ---------------------------------------------------------------------------
# Upcoming payments that PayFix expects to fail
# ---------------------------------------------------------------------------
AT_RISK = [
    {"key": "a", "due": "19 Nov", "type": "School fees (GIRO)", "customer": "Goh Kai Wen", "amount": 640.00,
     "likelihood": "Certain", "why": "GIRO authorisation expires on 18 Nov, one day before the payment.",
     "channel": "Reminder: renew authorisation in app"},
    {"key": "b", "due": "20 Nov", "type": "Home loan instalment", "customer": "Chua Boon Keat", "amount": 1980.00,
     "likelihood": "Likely", "why": "Balance was below the instalment 3 days before the due date in 4 of the last 6 months.",
     "channel": "Reminder: top up account by 19 Nov"},
    {"key": "c", "due": "21 Nov", "type": "Insurance premium (GIRO)", "customer": "Nur Farhana", "amount": 312.00,
     "likelihood": "Certain", "why": "New premium S$312 is above the S$300 GIRO limit.",
     "channel": "Reminder: raise GIRO limit"},
    {"key": "d", "due": "22 Nov", "type": "Personal loan instalment", "customer": "Aaron Teo", "amount": 860.00,
     "likelihood": "Certain", "why": "Debit account is scheduled to close on 21 Nov at the customer's request.",
     "channel": "Officer follow-up: new debit account"},
    {"key": "e", "due": "22 Nov", "type": "Supplier payment (standing instruction)", "customer": "Bright Leaf Trading Pte Ltd",
     "amount": 7200.00, "likelihood": "Check needed",
     "why": "Due date is a Sunday, so it will move to Mon 23 Nov. Check whether the contract allows a late payment.",
     "channel": "Reminder: confirm date with customer"},
]

# ---------------------------------------------------------------------------
# Dashboard figures (sample test-run results)
# ---------------------------------------------------------------------------
KPIS = [
    ("Cases handled", "612", "failed payments this week"),
    ("Failures prevented", "47", "fixed after a reminder"),
    ("Correct root cause", "89%", "AI vs ground truth"),
    ("Wrong auto-actions", "0", "target: always zero"),
    ("Avg time to resolve", "14 min", "from failure to decision"),
    ("Officer agreement", "91%", "accepted AI suggestion"),
]

FAILURE_MIX = {
    "Insufficient funds": 41,
    "Exceeds GIRO limit": 14,
    "Authorisation expired": 12,
    "System timeout": 11,
    "Holiday or missed cutoff": 9,
    "Debit account closed": 7,
    "Recipient account changed": 4,
    "Repeated loan misses": 2,
}

RESOLUTION_MIX = {
    "Auto-resolved": 38,
    "Officer one-click approval": 41,
    "Full review or escalated": 21,
}


def initial_audit(case):
    """Starting audit trail for a case, before any officer action."""
    trail = [
        ("06:00", "Payment system", f"Debit rejected with code {case['code']}. Case {case['id']} created."),
        ("06:00", "Agent", "Gathered evidence: " + "; ".join(t for t, _ in case["evidence"]) + "."),
    ]
    if case["confidence"] is not None:
        trail.append(("06:01", "Agent", f"Proposed action ({case['confidence']:.0%} confidence)."))
    route = {"auto": "Low risk, all checks passed. Auto-resolved.",
             "review": f"{case['risk']} risk. Routed to officer queue.",
             "escalated": "High risk. Escalated to a person."}[case["group"]]
    trail.append(("06:01", "Policy rules", route))
    return trail
