# AI Feature Business Case Generator (MVP)

Turn a product idea into a structured, numerical, financially reasonable business case —
even when you don't have all the business data. Built for Product Managers.

> **Important:** this is an estimation tool, not a forecast engine. Every number is labeled
> by how it was derived (user-provided / publicly verified / estimated / hypothetical), and
> every scenario is a judgment-based range, not a statistical prediction.

## How it works

1. You describe the company and the proposed feature in the sidebar.
2. Claude (via the authenticated **Claude Code CLI**, non-interactively) reasons about the
   business model, picks the right value-creation **mechanism** for the feature, and produces
   structured assumptions, scenarios and explanations as JSON — validated against a strict
   Pydantic schema (`bizcase/models.py`).
3. A **deterministic Python calculator** (`bizcase/calculator.py`) — no LLM involved — turns
   those assumptions into monthly projections, three scenarios, and a 12-month simulation.
4. You can drag sliders to change any assumption and see the financial projections update
   **instantly**, with no further AI call — the recalculation is pure, tested arithmetic.

## Install & run

```bash
pip install -r requirements.txt
```

The Analyze button needs the **Claude Code CLI**, authenticated once interactively:

```bash
claude  # log in once if you haven't already; then exit
```

Then start the app:

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

### If the Claude CLI isn't available

The app detects this and disables the Analyze button with an explanation. You can still:
- Load one of the three bundled **synthetic examples** from the sidebar to see the full UI,
  tables, charts and interactive sliders work end to end.
- Run the Claude-assisted workflow manually: open `bizcase/prompts.py`, call `build_prompt(...)`
  with a `UserInputs` object, paste the resulting prompt into any Claude conversation, and feed
  the JSON reply into `bizcase.ai_client.parse_case(...)` to get a validated `BusinessCase` you
  can load into the app's session state.

The app never fakes an AI response — if the CLI is missing or Claude's reply fails validation
twice, you get a clear error, not a hardcoded template.

## Project structure

```
app.py                     Streamlit UI (inputs, results, interactive sliders, charts)
bizcase/
  models.py                Pydantic schema: UserInputs, Metric, Assumptions, Scenarios, BusinessCase
  calculator.py            Deterministic financial engine (6 mechanisms, 3 scenarios, 12-month sim)
  prompts.py                Prompt construction for the AI analysis
  ai_client.py              Runs the Claude Code CLI (`claude -p --output-format json`), parses
                             and validates the reply, retries once on a validation failure
  examples.py               3 synthetic, hand-authored example business cases (not AI-generated)
tests/
  test_calculator.py         Financial-logic and validation tests
  test_ai_client.py          JSON-extraction / validation / retry tests (fake CLI runner, no network)
requirements.txt
```

## The six value-creation mechanisms

Not every feature makes money the same way. Claude picks one per case:

| Mechanism | Example feature | What "effect" means |
|---|---|---|
| `paid_conversion` | Free-to-paid trial gate | P(adopter becomes a payer) |
| `upgrade` | Premium analytics add-on | P(adopter upgrades plan) |
| `acquisition` | Referral program | New payers generated per participant/month |
| `retention` | Proactive churn-save flow | Relative reduction in monthly churn |
| `transaction_uplift` | One-click checkout | Relative uplift in orders or order value |
| `cost_reduction` | Self-serve support bot | Relative reduction in cost-driving events |

Each has its own formula in `calculator.py` — see `MECHANISM_INFO` in `models.py` for the exact
definitions and units shown in the UI.

## Data-status labels

Every metric is tagged:
- 🟢 **USER PROVIDED** — you typed it in; always wins over AI estimates.
- 🔵 **PUBLICLY VERIFIED** — Claude retrieved it via web search in this session; always carries
  a source link and date (a claim without a source link is automatically downgraded to ESTIMATED).
- 🟡 **ESTIMATED** — Claude's reasoned estimate for a real company or benchmark.
- ⚪ **HYPOTHETICAL** — an illustrative figure for an unknown/hypothetical company or size tier.

## Financial definitions (used consistently throughout)

- **GMV** — gross transaction value flowing through the feature (relevant for marketplaces).
- **Revenue** — GMV × take rate (1.0 outside marketplace/platform businesses) — what's recognized.
- **Cost savings** — for `cost_reduction` only; never summed into revenue.
- **Steady-state monthly** — month 12 of the simulation, after the adoption ramp completes.
- **Annualized run-rate** — steady-state monthly × 12. A *rate*, not money already earned.
- **First-year revenue/savings** — the sum of all 12 simulated months — what would actually be
  booked in year one, including the ramp-up period. This is normally lower than the run-rate.

## Testing

```bash
pytest -q
```

48 tests cover: each mechanism's arithmetic, monthly-vs-annual vs run-rate distinctions,
GMV vs. recognized revenue for take-rate businesses, user-provided values overriding estimates,
graceful handling of missing optional inputs, input/assumption validation (no negative counts,
no >100% bounded probabilities, scenario ordering), deterministic recalculation, and the three
bundled synthetic examples (B2B SaaS upgrade, e-commerce checkout, consumer-app referral).

## What's deliberately not built (per MVP scope)

No auth, no cloud deployment, no multi-agent orchestration, no paid analytics integrations, no
database, no web-scraping infrastructure, no slide generation. The AI call is a single, isolated
module (`ai_client.py`) with a timeout, structured-output validation, and one retry — everything
numeric is deterministic Python you can audit and unit test.
