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
| Upcoming at risk | Officer | Payments due in the next 7 days that are likely to fail, with a "Send reminder" button |
| Failed payments | Officer | Today's failed payments, filterable, colour-coded by risk |
| Case detail | Officer / reviewer | AI explanation, evidence, policy checks, approve/edit/reject/escalate, SMS preview, audit trail |
| Dashboard | Process owner | KPIs, failures by type, how cases were resolved |

Officer decisions are saved for the session and added to the case's audit trail.
Edit, reject and escalate require a reason.

## Files

- `app.py`: the Streamlit app (Person 4, front-end)
- `data.py`: sample cases, at-risk payments and dashboard figures. Replace with the real
  synthetic-data generator later (Person 1), keeping the same field names.

## Next steps for the team

- Replace the hardcoded `CASES` with output from the data generator and the agent's `AgentResult`
- Move the policy checks into a `policy/` module that returns the checks list
- Store decisions and the audit trail in SQLite instead of session state
- Replace the sample dashboard numbers with figures computed against the ground truth
