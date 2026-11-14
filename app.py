"""AI Feature Business Case Generator — Streamlit MVP.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st
from pydantic import ValidationError

from bizcase.ai_client import DEFAULT_TIMEOUT_S, AnalysisError, analyze, cli_available
from bizcase.calculator import SCENARIO_NAMES, calculate_scenarios, change_attribution, fmt_count, fmt_money, headline, sensitivity
from bizcase.examples import EXAMPLE_INPUTS, EXAMPLES
from bizcase.models import Mechanism, UserInputs

# Reference categorical palette (dataviz skill, light mode)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SCENARIO_COLOR = {"conservative": "#86b6ef", "base": BLUE, "optimistic": "#184f95"}

st.set_page_config(page_title="AI Feature Business Case Generator", layout="wide")


def _init_state():
    st.session_state.setdefault("case", None)
    st.session_state.setdefault("inputs", None)
    st.session_state.setdefault("notes", [])
    st.session_state.setdefault("overrides", {})
    st.session_state.setdefault("error", None)


_init_state()

st.title("AI Feature Business Case Generator")
st.caption(
    "Turn a product idea into a structured, numerical business case. "
    "Estimates are reasoned, not guaranteed — every number below is labeled by how it was derived."
)

# --------------------------------------------------------------------------- sidebar: inputs
with st.sidebar:
    st.header("1. Describe the company & feature")

    example_choice = st.selectbox("Load a synthetic example (optional)", ["—"] + list(EXAMPLES.keys()))
    if st.button("Load example", disabled=example_choice == "—"):
        st.session_state.case = EXAMPLES[example_choice].model_copy(deep=True)
        st.session_state.inputs = EXAMPLE_INPUTS[example_choice]
        st.session_state.notes = ["Loaded a bundled synthetic example — not AI-generated, not a real company."]
        st.session_state.overrides = {}
        st.session_state.error = None
        st.rerun()

    st.divider()

    company_name = st.text_input("Company name (optional)", help="Leave blank for a hypothetical company.")
    website = st.text_input("Company website (optional)")
    business_description = st.text_area(
        "Business description & industry *", height=90,
        placeholder="e.g. B2B SaaS tool for restaurant inventory management, sold to independent restaurants.",
    )
    company_size = st.selectbox("Company size", ["unknown", "startup", "small", "medium", "large"])
    geography = st.text_input("Country / market (optional)", placeholder="e.g. Germany, or 'EU', or 'Global'")

    st.markdown("**Known business metrics (optional)**")
    known_active_users = st.number_input("Active users / customers / accounts", min_value=0.0, value=0.0, step=1.0)
    known_value_per_unit = st.number_input("Price / ARPU / order value", min_value=0.0, value=0.0, step=1.0)
    known_metrics_notes = st.text_area("Other known metrics (free text, optional)", height=60)

    st.markdown("**The feature**")
    feature_description = st.text_area("Proposed product feature *", height=90)
    feature_rationale = st.text_area("Why build it? (optional)", height=70)
    expected_outcome = st.text_area("Expected business outcome (optional)", height=70)

    st.divider()
    web_research = st.checkbox(
        "Allow web research for public company facts", value=True,
        help="Lets Claude use WebSearch/WebFetch for publicly verifiable facts. Turn off for fully offline/hypothetical runs.",
    )

    cli_ok = cli_available()
    if not cli_ok:
        st.warning(
            "Claude Code CLI not found on PATH. The Analyze button needs the authenticated `claude` CLI "
            "installed and logged in. See the README for the manual fallback workflow."
        )

    analyze_clicked = st.button("🔍 Analyze", type="primary", use_container_width=True, disabled=not cli_ok)

# --------------------------------------------------------------------------- run analysis
if analyze_clicked:
    try:
        inputs = UserInputs(
            company_name=company_name,
            website=website,
            business_description=business_description,
            company_size=company_size,
            geography=geography,
            known_active_users=known_active_users or None,
            known_value_per_unit=known_value_per_unit or None,
            known_metrics_notes=known_metrics_notes,
            feature_description=feature_description,
            feature_rationale=feature_rationale,
            expected_outcome=expected_outcome,
        )
    except ValidationError as e:
        st.session_state.error = f"Please check your inputs: {e}"
    else:
        st.session_state.error = None
        with st.spinner("Calling Claude for business reasoning (this can take 1-3 minutes, longer with web research)…"):
            try:
                case, notes = analyze(inputs, web_research=web_research, timeout_s=DEFAULT_TIMEOUT_S)
                st.session_state.case = case
                st.session_state.inputs = inputs
                st.session_state.notes = notes
                st.session_state.overrides = {}
            except AnalysisError as e:
                st.session_state.error = str(e)

if st.session_state.error:
    st.error(st.session_state.error)

case = st.session_state.case
if case is None:
    st.info("Fill in the sidebar (or load a synthetic example) and click **Analyze** to generate a business case.")
    st.stop()

if case.synthetic_example:
    st.warning("**Synthetic example** — illustrative figures only, not AI-generated and not a real company.")
for note in st.session_state.notes:
    st.info(note)

overrides = st.session_state.overrides


def status_badge(status) -> str:
    return {"USER PROVIDED": "🟢", "PUBLICLY VERIFIED": "🔵", "ESTIMATED": "🟡", "HYPOTHETICAL": "⚪"}.get(status.value, "")


# --------------------------------------------------------------------------- 1-2. company & metrics
st.header("1. Company & business model")
c1, c2 = st.columns([2, 1])
with c1:
    st.write(case.company_summary)
    st.write(f"**Business model:** {case.business_model}")
    st.write(f"**Customer type:** {case.customer_type} · **Currency:** {case.currency}")
    st.caption(f"Scale basis: {case.size_basis}")
with c2:
    st.metric("Confidence", case.confidence.upper())
    st.caption(case.confidence_rationale)

st.subheader("2. Known vs. estimated metrics")
rows = []
a = case.assumptions
for m in [a.base_population, a.eligible_share, a.value_per_unit, a.baseline_rate, a.monthly_churn, a.take_rate, a.cost_per_unit, a.gross_margin, *case.context_metrics]:
    if m is None:
        continue
    rows.append(
        {
            "Metric": m.name, "Value": f"{m.value:,.4g} {m.unit}".strip(),
            "Status": f"{status_badge(m.status)} {m.status.value}", "Uncertainty": m.uncertainty,
            "Reasoning": m.reasoning, "Source": m.source_url or "",
        }
    )
st.dataframe(rows, use_container_width=True, hide_index=True)
st.caption("🟢 User provided · 🔵 Publicly verified (source linked) · 🟡 Estimated · ⚪ Hypothetical / illustrative")

# --------------------------------------------------------------------------- 3-4. feature & mechanism
st.header("3. Proposed feature & expected value")
st.write(f"**Feature:** {case.feature_summary}")
st.write(f"**Expected value:** {case.expected_value}")

st.header("4. Business impact mechanism")
from bizcase.models import MECHANISM_INFO  # noqa: E402

info = MECHANISM_INFO[case.mechanism]
st.write(f"**Mechanism:** {info['label']}")
st.write(" → ".join(case.mechanism_chain) if case.mechanism_chain else "")
st.caption(case.mechanism_rationale)
st.caption(f"Definition of 'effect' here: {case.effect_definition}")

# --------------------------------------------------------------------------- 5. assumptions & interactive adjustment
st.header("5. Assumptions & interactive adjustments")
st.caption("Adjust any assumption below — projections recalculate instantly with deterministic Python, no AI call.")

col1, col2, col3 = st.columns(3)
with col1:
    base_population = st.number_input(
        "Base population (users/customers/accounts)", min_value=0.0,
        value=float(a.base_population.value), step=max(1.0, a.base_population.value * 0.01),
    )
    eligible_share = st.slider("Eligible share", 0.0, 1.0, float(a.eligible_share.value), 0.01)
with col2:
    value_per_unit = st.number_input(
        f"Value per unit ({case.currency}) — {a.value_per_unit.name}", min_value=0.0,
        value=float(a.value_per_unit.value), step=max(0.1, a.value_per_unit.value * 0.01),
    )
    scen_pick = st.selectbox("Scenario to tune adoption/effect", SCENARIO_NAMES, index=1)
with col3:
    scen_obj = getattr(case.scenarios, scen_pick)
    adoption_rate = st.slider(f"[{scen_pick}] Feature adoption rate", 0.0, 1.0, float(scen_obj.adoption_rate), 0.01)
    max_effect = 1.0 if case.mechanism in {Mechanism.PAID_CONVERSION, Mechanism.UPGRADE, Mechanism.RETENTION, Mechanism.COST_REDUCTION} else 2.0
    effect = st.slider(f"[{scen_pick}] Effect ({info['effect'].split(' because')[0][:40]}…)", 0.0, max_effect, float(scen_obj.effect), 0.005)

new_overrides = {}
if base_population != a.base_population.value:
    new_overrides["base_population"] = base_population
if eligible_share != a.eligible_share.value:
    new_overrides["eligible_share"] = eligible_share
if value_per_unit != a.value_per_unit.value:
    new_overrides["value_per_unit"] = value_per_unit
if adoption_rate != scen_obj.adoption_rate:
    new_overrides[f"{scen_pick}.adoption_rate"] = adoption_rate
if effect != scen_obj.effect:
    new_overrides[f"{scen_pick}.effect"] = effect
st.session_state.overrides = new_overrides
overrides = new_overrides

with st.expander("Why these numbers (adoption & calculation reasoning)"):
    st.write(case.adoption_rationale)
    st.write(f"**Formula:** {info['formula']}")
    if case.scenario_rationale:
        st.write(f"**Why scenarios differ:** {case.scenario_rationale}")

if new_overrides:
    changes = change_attribution(case, new_overrides)
    st.markdown("**What changed, and its effect on first-year headline value:**")
    for row in changes:
        impacts = ", ".join(f"{s}: {fmt_money(v, case.currency)}" for s, v in row["impact"].items())
        st.write(f"- `{row['key']}`: {row['old']:,.4g} → {row['new']:,.4g}  (Δ first-year: {impacts})")

# --------------------------------------------------------------------------- 6-7. scenarios & revenue
st.header("6. Scenarios")
results = calculate_scenarios(case, overrides)
headline_label = "cost savings" if case.mechanism == Mechanism.COST_REDUCTION else "revenue"

table_rows = []
for name in SCENARIO_NAMES:
    s = getattr(case.scenarios, name)
    r = results[name]
    table_rows.append(
        {
            "Scenario": name.capitalize(),
            "Eligible users": fmt_count(r.eligible_users),
            "Adoption rate": f"{s.adoption_rate:.0%}",
            "Effect": f"{s.effect:.1%}" if case.mechanism in {Mechanism.PAID_CONVERSION, Mechanism.UPGRADE, Mechanism.RETENTION, Mechanism.COST_REDUCTION} else f"{s.effect:.3g}",
            f"Monthly {headline_label} (steady-state)": fmt_money(r.steady_state_monthly_revenue if headline_label == "revenue" else r.monthly_savings[-1], case.currency),
            "Annualized run-rate": fmt_money(r.annualized_run_rate if headline_label == "revenue" else r.annualized_savings, case.currency),
            f"First-year {headline_label}": fmt_money(headline(case, r), case.currency),
        }
    )
st.dataframe(table_rows, use_container_width=True, hide_index=True)
st.caption(case.scenario_rationale)

st.header("7. Expected incremental revenue")
fig = go.Figure()
months = list(range(1, 13))
for name in SCENARIO_NAMES:
    r = results[name]
    series = r.monthly_revenue if headline_label == "revenue" else r.monthly_savings
    fig.add_trace(go.Scatter(
        x=months, y=series, mode="lines", name=name.capitalize(),
        line=dict(color=SCENARIO_COLOR[name], width=2),
    ))
fig.update_layout(
    title=f"Monthly incremental {headline_label} over the first year ({case.currency})",
    xaxis_title="Month", yaxis_title=case.currency, template="plotly_white",
    legend_title_text="Scenario", height=400,
)
st.plotly_chart(fig, use_container_width=True)

bar = go.Figure(go.Bar(
    x=[n.capitalize() for n in SCENARIO_NAMES],
    y=[headline(case, results[n]) for n in SCENARIO_NAMES],
    marker_color=[SCENARIO_COLOR[n] for n in SCENARIO_NAMES],
))
bar.update_layout(title=f"First-year {headline_label} by scenario", yaxis_title=case.currency, template="plotly_white", height=320)
st.plotly_chart(bar, use_container_width=True)

sens = sensitivity(case)
if sens:
    st.subheader("Which assumption matters most (base scenario, conservative↔optimistic swing)")
    tornado = go.Figure()
    for row in sens:
        tornado.add_trace(go.Bar(
            y=[row["field"]], x=[row["high"] - row["base"]], base=[row["base"]],
            orientation="h", marker_color=AQUA, showlegend=False,
        ))
        tornado.add_trace(go.Bar(
            y=[row["field"]], x=[row["low"] - row["base"]], base=[row["base"]],
            orientation="h", marker_color=ORANGE, showlegend=False,
        ))
    tornado.update_layout(title="Tornado chart — first-year headline sensitivity", template="plotly_white", height=250, barmode="overlay")
    st.plotly_chart(tornado, use_container_width=True)

st.caption(
    "These are judgment-based scenarios, not statistically validated forecasts, unless stated otherwise above. "
    "First-year figures sum 12 simulated months; annualized run-rate is steady-state × 12, not money already earned."
)

# --------------------------------------------------------------------------- 8-9. risks & experiment
st.header("8. Key risks & uncertainties")
colr1, colr2 = st.columns(2)
with colr1:
    st.markdown("**Risks**")
    for r in case.risks:
        st.write(f"- {r}")
    st.markdown("**Key drivers of the result**")
    for k in case.key_drivers:
        st.write(f"- {k}")
with colr2:
    st.markdown("**Missing evidence**")
    for m in case.missing_evidence:
        st.write(f"- {m}")
    st.markdown("**Data the PM should collect**")
    for d in case.data_to_collect:
        st.write(f"- {d}")

st.header("9. Recommended experiment")
st.write(f"**Design:** {case.experiment.design}")
st.write(f"**Primary metric:** {case.experiment.primary_metric}")
if case.experiment.success_criteria:
    st.write(f"**Success criteria:** {case.experiment.success_criteria}")
if case.experiment.duration:
    st.write(f"**Duration:** {case.experiment.duration}")

if case.sources:
    st.header("Sources")
    for s in case.sources:
        st.write(f"- [{s.title}]({s.url}) ({s.date})" if s.url else f"- {s.title} ({s.date})")
