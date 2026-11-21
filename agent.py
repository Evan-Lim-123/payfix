"""Gemini investigation agent for PayFix.

The agent gets a failed payment, decides which evidence to look up by calling tools,
then returns a structured answer: likely cause, explanation, missing information,
confidence. PayFix's policy rules (simulator.decide) then check that answer before
anything happens. The agent never acts on its own.

If no API key is set, the call fails, or the free-tier limit is hit, PayFix falls back
to the rule-based stand-in in simulator.investigate() and labels the case accordingly.

Setup:
  - Get a free key at https://aistudio.google.com/apikey
  - Streamlit Cloud: app → Settings → Secrets, add   GEMINI_API_KEY = "your-key"
  - Locally: put the same line in .streamlit/secrets.toml (never upload that file)
  - Optional: GEMINI_MODEL = "gemini-3-flash-preview" to choose the model
"""

import json
import os

import simulator as sim

DEFAULT_MODELS = ["gemini-3-flash-preview", "gemini-3.1-flash-lite"]   # free-tier models, tried in order
MAX_TOOL_ROUNDS = 5
TIMEOUT_MS = 45_000

CAUSES = list(sim.CODES) + ["unclear"]

SYSTEM = """You are the investigation agent in PayFix, a bank operations tool. A scheduled payment
(loan instalment, GIRO debit or standing instruction) has failed. Your job is to work out WHY,
using only evidence from the tools.

Rules:
- Always gather evidence with the tools before concluding. Call every tool that could be relevant.
- The rejection code from the payment system can be wrong. Check it against the evidence.
- Never guess. If evidence needed to confirm the cause is missing, say what is missing.
- If the evidence does not clearly support one cause, answer "unclear".
- You do not take actions. PayFix's rules and a human officer decide what happens next.

Possible causes: insufficient_funds, exceeds_giro_limit, authorisation_expired, account_closed,
recipient_changed, system_timeout, missed_cutoff, unclear."""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {"type": "string", "enum": CAUSES},
        "explanation": {"type": "string",
                        "description": "2-3 plain-English sentences for a bank officer, citing the evidence and numbers."},
        "missing_information": {"type": "array", "items": {"type": "string"},
                                "description": "Evidence you needed but could not get. Empty if none."},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["cause", "explanation", "missing_information", "confidence"],
}


# ---------------------------------------------------------------------------
# Tools: each reads the (simulated) bank data for the case. No ground truth.
# ---------------------------------------------------------------------------
def _tool_results(p):
    """name -> (description, label, function returning a short finding)."""
    m = sim.money

    def balance():
        if not p["balance_available"]:
            return "ERROR: balance service returned no data."
        return f"Balance at 06:00 on the debit date: {m(p['balance'])}."

    def mandate():
        if p["channel"] != "giro":
            return "Not a GIRO payment; no mandate."
        status = "EXPIRED" if p["auth_expiry"] < p["due"] else "active"
        return f"GIRO authorisation {status}. Limit {m(p['giro_limit'])}. Expiry {p['auth_expiry']:%d %b %Y}."

    def billing():
        if p["previous_amount"] != p["amount"]:
            return f"Amount changed: previously {m(p['previous_amount'])}, now {m(p['amount'])}."
        return "Amount unchanged from previous payments."

    def account():
        if p["account_status"] == "closed":
            return f"Debit account CLOSED on {p['closed_on']:%d %b %Y}."
        return "Debit account active."

    def recipient():
        if p["channel"] != "standing":
            return "Not a standing instruction; recipient is fixed."
        if p["recipient_changed_on"]:
            return f"Recipient account details were CHANGED on {p['recipient_changed_on']:%d %b %Y}."
        return "No recent change to recipient details."

    def submission():
        if p["channel"] != "standing":
            return "Scheduled batch debit at 06:00; cutoff does not apply."
        return f"Instruction submitted at {p['submitted_time']}. Daily cutoff is {sim.CUTOFF}."

    def log():
        if not p["log_available"]:
            return "ERROR: payment system log not returned."
        return "Timeout: no response from debit service." if p["system_log"] == "timeout" else "No errors logged."

    def history():
        return (f"{p['past_misses']} missed payment(s) in the last 12 months. Salary of about "
                f"{m(p['salary_amount'])} usually arrives in {p['days_to_salary']} day(s).")

    return {
        "check_balance": ("Account balance on the debit date.", "Balance on debit date", balance),
        "check_giro_mandate": ("GIRO authorisation status, limit and expiry.", "GIRO authorisation", mandate),
        "billing_history": ("Whether the payment amount changed recently.", "Billing history", billing),
        "check_account_status": ("Whether the debit account is active or closed.", "Debit account", account),
        "check_recipient": ("Recent changes to the recipient's account details.", "Recipient", recipient),
        "check_submission_time": ("When the instruction was submitted vs the daily cutoff.", "Submission time", submission),
        "read_system_log": ("Payment system log for this debit attempt.", "System log", log),
        "payment_history": ("Past missed payments and expected salary timing.", "Payment history", history),
    }


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------
def get_setting(name, secrets=None):
    """Read a setting from Streamlit secrets (if given) or environment variables."""
    if secrets is not None:
        try:
            if name in secrets:
                return str(secrets[name])
        except Exception:
            pass
    return os.environ.get(name)


def available(secrets=None):
    return bool(get_setting("GEMINI_API_KEY", secrets))


class AgentUnavailable(Exception):
    pass


# ---------------------------------------------------------------------------
# The agent
# ---------------------------------------------------------------------------
def investigate(p, code, api_key, model=None, client=None):
    """Run the Gemini agent. Returns an AgentResult dict (same shape as
    simulator.investigate) or raises AgentUnavailable."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError as e:
        raise AgentUnavailable("google-genai package not installed") from e

    client = client or genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    tools = _tool_results(p)
    decls = [types.FunctionDeclaration(name=name, description=desc,
                                       parameters_json_schema={"type": "object", "properties": {}})
             for name, (desc, _, _) in tools.items()]
    tool_config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        tools=[types.Tool(function_declarations=decls)],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        temperature=0.2,
    )
    case_text = (f"Failed payment {p['tx_id']}: {p['type']} for {p['customer']} ({p['segment']}), "
                 f"amount {sim.money(p['amount'])}, due today {p['due']:%d %b %Y}. "
                 f"Payment system rejection code: {code}. Investigate the cause.")
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=case_text)])]

    models = [model] if model else []
    models += [m for m in DEFAULT_MODELS if m not in models]
    calls_made = []

    def generate(cfg):
        last = None
        for m in list(models):
            try:
                resp = client.models.generate_content(model=m, contents=contents, config=cfg)
                models[:] = [m]           # stick with the model that worked
                return resp, m
            except errors.ClientError as e:
                last = e
                if getattr(e, "code", None) == 404:      # model retired or not available: try next
                    continue
                raise AgentUnavailable(_short_error(e)) from e
            except errors.APIError as e:
                raise AgentUnavailable(_short_error(e)) from e
            except Exception as e:  # network errors, timeouts
                raise AgentUnavailable(f"{type(e).__name__}: {str(e)[:90]}") from e
        raise AgentUnavailable(_short_error(last) if last else "no model available")

    # 1. Tool-calling loop: Gemini decides which evidence to fetch
    used_model = None
    for _ in range(MAX_TOOL_ROUNDS):
        resp, used_model = generate(tool_config)
        fcs = resp.function_calls or []
        if not fcs:
            break
        contents.append(resp.candidates[0].content)      # keeps Gemini's thought signatures
        parts = []
        for fc in fcs:
            if fc.name in tools:
                desc, label, fn = tools[fc.name]
                finding = fn()
            else:
                label, finding = fc.name, "ERROR: unknown tool."
            calls_made.append((fc.name, label, finding))
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": finding}))
        contents.append(types.Content(role="user", parts=parts))
    else:
        contents.append(types.Content(role="user", parts=[types.Part.from_text(
            text="You have used all tool rounds. Conclude with the evidence you have.")]))

    # 2. Final structured answer. If the loop already ended with valid JSON, use it
    #    (saves a request on the free tier); otherwise ask once more in JSON mode, no tools.
    answer = None
    if not (resp.function_calls or []):
        try:
            answer = _parse(resp.text)
        except (ValueError, TypeError):
            answer = None
    if answer is None:
        if resp.candidates and resp.candidates[0].content and not (resp.function_calls or []):
            contents.append(resp.candidates[0].content)
        contents.append(types.Content(role="user", parts=[types.Part.from_text(
            text="Give your final answer as JSON matching the schema. Use only the evidence above.")]))
        json_cfg = types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.1,
                                               response_mime_type="application/json",
                                               response_json_schema=RESULT_SCHEMA)
        try:
            final, used_model = generate(json_cfg)
        except AgentUnavailable:
            # Some models reject a schema: retry with plain JSON mode
            final, used_model = generate(types.GenerateContentConfig(
                system_instruction=SYSTEM, temperature=0.1, response_mime_type="application/json"))
        answer = _parse(final.text)

    # 3. Confidence: never trust the model's own number alone
    cause = answer["cause"]
    llm_conf = answer["confidence"]
    if cause == "unclear":
        checklist, check_conf = [], 0.4
    else:
        plain = dict(p, agent_trusts_code=False)
        checklist = sim._agent_checks(plain, cause, code)
        check_conf = round(0.4 + 0.59 * sum(1 for _, ok in checklist if ok) / len(checklist), 2)
    confidence = round(min(llm_conf, check_conf), 2)

    missing = [m for m in answer["missing_information"] if m.strip()]
    return {
        "cause": cause,
        "explanation": answer["explanation"].strip(),
        "evidence": [(label, finding) for _, label, finding in calls_made],
        "tool_calls": calls_made,
        "missing": missing,
        "checklist": checklist,
        "confidence": confidence,
        "engine": f"Gemini agent ({used_model})",
        "engine_note": (f"Confidence {confidence:.0%} is the lower of Gemini's own estimate ({llm_conf:.0%}) "
                        f"and the evidence checklist ({check_conf:.0%})."),
    }


def ping(api_key, model=None, client=None):
    """Send one tiny request to check the key and model. Returns (ok, message)."""
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError:
        return False, ("The google-genai package isn't installed. Make sure requirements.txt on GitHub "
                       "includes the line: google-genai>=3.0")
    client = client or genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=20_000))
    models = ([model] if model else []) + [m for m in DEFAULT_MODELS if m != model]
    tried = []
    for m in models:
        try:
            resp = client.models.generate_content(model=m, contents="Reply with the single word OK.")
            return True, f"Gemini is working. Model: {m}. Reply: {(resp.text or '').strip()[:40]}"
        except errors.ClientError as e:
            if getattr(e, "code", None) == 404:
                tried.append(m)
                continue
            return False, f"{_short_error(e)} (model {m})"
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:150]}"
    return False, "None of these models are available to your key: " + ", ".join(tried)


def _parse(text):
    """Parse Gemini's JSON answer. Raises ValueError if there is no usable JSON."""
    text = (text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    data = json.loads(text[start: end + 1])
    if not isinstance(data, dict) or "cause" not in data:
        raise ValueError("JSON has no cause")
    cause = data.get("cause", "unclear")
    if cause not in CAUSES:
        cause = "unclear"
    try:
        conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    missing = data.get("missing_information") or []
    if isinstance(missing, str):
        missing = [missing]
    return {"cause": cause, "explanation": str(data.get("explanation", "")) or "No explanation given.",
            "missing_information": [str(m) for m in missing], "confidence": conf}


def _short_error(e):
    code = getattr(e, "code", None)
    if code == 429:
        return "free-tier rate limit reached (429)"
    msg = str(getattr(e, "message", "") or e)
    if code in (401, 403) or "API key not valid" in msg or "API_KEY_INVALID" in msg:
        return "API key rejected (check it was copied fully, with no spaces)"
    return f"{code or ''} {msg[:120]}".strip()
