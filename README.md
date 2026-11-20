# PayFix

AI-assisted resolution of failed loan repayments and recurring GIRO payments.
Prototype for the OCBC Ignite Innovation Challenge, Problem 2 (Intelligent Operations).
Uses synthetic data only.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

It opens in your browser at http://localhost:8501.

## Screens

| Page | Who uses it | What it shows |
|---|---|---|
| Live simulation | Demo | Generate fake payments in batches, or one-click demo scenarios, and watch each failure go through PayFix step by step |
| Upcoming at risk | Officer | Payments due in the next 7 days that are likely to fail, with a "Send reminder" button |
| Failed payments | Officer | Today's failed payments, filterable, colour-coded by risk |
| Case detail | Officer / reviewer | AI explanation, evidence, policy checks, approve/edit/reject/escalate, SMS preview, audit trail |
| Dashboard | Process owner | KPIs, failures by type, how cases were resolved |

Officer decisions are saved for the session and added to the case's audit trail.
Edit, reject and escalate require a reason.

## Files

- `app.py`: the Streamlit app (Person 4, front-end)
- `agent.py`: the Gemini investigation agent. It calls evidence tools, then returns cause, explanation,
  missing information and confidence. Falls back to the rule-based agent if Gemini is unavailable.
- `simulator.py`: fake payment generator, simulated payment system, rule-based agent (offline fallback)
  and the policy rules that check every agent answer.
- `data.py`: sample cases, at-risk payments and dashboard figures. Replace with the real
  synthetic-data generator later (Person 1), keeping the same field names.

## Next steps for the team

- Replace the hardcoded `CASES` with output from the data generator and the agent's `AgentResult`
- Move the policy checks into a `policy/` module that returns the checks list
- Store decisions and the audit trail in SQLite instead of session state
- Replace the sample dashboard numbers with figures computed against the ground truth

## Demo tips

- **Live simulation** is the start page. Run a batch of 50 payments, then click a few demo scenarios.
- Best demo order: *System timeout* (auto-fixed) → *Short of funds* (officer approves) → *Recipient changed*
  (always escalated) → *Misleading code* (shows whether the agent is fooled; if it is, the rules block it). Open each case to show evidence, checks and the audit trail.
- Each simulated case has a **Simulation ground truth** box showing the real cause versus what the agent said.
- **Reset simulation** at the bottom of the page clears everything. Each visitor to the shared link gets their own session.

## Gemini agent setup

1. Get a free key at https://aistudio.google.com/apikey (sign in with a Google account, click **Create API key**).
2. **Streamlit Cloud:** your app → **Settings → Secrets**, paste:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```
   **Locally:** create `.streamlit/secrets.toml` with the same line. Never upload this file or put the key in code.
3. Optional: choose the model with `GEMINI_MODEL = "gemini-3-flash-preview"`. If it's unavailable, the app tries
   `gemini-3.1-flash-lite`.

How it works:
- Gemini decides which evidence tools to call (balance, GIRO mandate, account status, system log and so on),
  then returns its answer as JSON.
- Confidence is the **lower** of Gemini's own estimate and an evidence checklist, so an overconfident AI can't push a case through.
- The policy rules check every answer before anything happens. Gemini never acts on its own.
- Demo scenarios always use Gemini. Batches use Gemini for the first 5 failures, then the rule-based agent,
  to stay within free-tier limits.
- If Gemini fails (no key, rate limit, network), the case uses the rule-based agent and says why. Turn Gemini off
  with the sidebar switch if you hit the limit during a demo.
