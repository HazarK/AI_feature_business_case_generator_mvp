"""Deterministic financial calculator. No LLM calls, no randomness, no I/O.

One 12-month simulation covers every mechanism; the per-mechanism branch decides how
"adopters" turn into money. Definitions used throughout:

* monthly_revenue      recognized revenue in that month (GMV × take rate), NOT profit
* steady_state_monthly revenue in month 12 (after ramp; for accumulating mechanisms, the month-12 level)
* annualized_run_rate  steady_state_monthly × 12  -- a run-rate, NOT money earned in year one
* first_year_revenue   sum of the 12 simulated months -- what would actually be booked in year one
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .models import BOUNDED_EFFECT, MAX_UNBOUNDED_EFFECT, NEEDS_BASELINE_RATE, BusinessCase, Mechanism

MONTHS = 12


class CalcInputs(BaseModel):
    mechanism: Mechanism
    base_population: float = Field(..., ge=0)
    eligible_share: float = Field(..., ge=0, le=1)
    adoption_rate: float = Field(..., ge=0, le=1)
    effect: float = Field(..., ge=0, le=MAX_UNBOUNDED_EFFECT)
    incremental_share: float = Field(1.0, ge=0, le=1)
    value_per_unit: float = Field(..., ge=0)
    baseline_rate: float = Field(0.0, ge=0)
    monthly_churn: float = Field(0.0, ge=0, le=1)
    take_rate: float = Field(1.0, ge=0, le=1)
    cost_per_unit: float = Field(0.0, ge=0)
    gross_margin: float | None = Field(None, ge=0, le=1)
    ramp_months: int = Field(3, ge=0, le=MONTHS)

    @model_validator(mode="after")
    def _check(self):
        if self.mechanism in BOUNDED_EFFECT and self.effect > 1:
            raise ValueError(f"effect must be <= 1 for mechanism '{self.mechanism.value}'")
        if self.mechanism == Mechanism.RETENTION and self.baseline_rate > 1:
            raise ValueError("baseline_rate (monthly churn) must be <= 1 for retention")
        if self.mechanism in NEEDS_BASELINE_RATE and self.baseline_rate == 0:
            # legal, but yields zero; kept permissive so sliders can pass through 0
            pass
        return self


class CalcResult(BaseModel):
    eligible_users: float
    adopters: float                    # at full adoption (after ramp)
    incremental_units_monthly: float   # at full adoption; meaning depends on mechanism (see MECHANISM_INFO)
    monthly_gmv: list[float]           # gross customer spend; equals revenue when take_rate == 1
    monthly_revenue: list[float]
    monthly_cost: list[float]          # variable costs / incentives
    monthly_savings: list[float]       # cost_reduction only
    steady_state_monthly_gmv: float
    steady_state_monthly_revenue: float
    new_mrr_per_month: float | None    # accumulating mechanisms: recurring revenue ADDED each month at full adoption
    annualized_run_rate: float
    first_year_gmv: float
    first_year_revenue: float
    first_year_cost: float
    first_year_savings: float
    annualized_savings: float
    first_year_net_contribution: float  # revenue × gross margin (1 if unknown) + savings − variable costs


def _ramp(month: int, ramp_months: int) -> float:
    """Share of scenario-level adoption reached in a given month (linear ramp, month is 1-based)."""
    if ramp_months <= 0:
        return 1.0
    return min(1.0, month / ramp_months)


def calculate(i: CalcInputs) -> CalcResult:
    eligible = i.base_population * i.eligible_share
    adopters_full = eligible * i.adoption_rate
    mech = i.mechanism

    gmv, cost, savings = [], [], []
    active = 0.0       # accumulated incremental customers (acquisition / retention)
    prev_gross = 0.0   # for one-off costs on newly converted customers (stock mechanisms)

    for m in range(1, MONTHS + 1):
        adopters = adopters_full * _ramp(m, i.ramp_months)
        month_gmv = month_cost = month_savings = 0.0

        if mech in (Mechanism.PAID_CONVERSION, Mechanism.UPGRADE):
            # Stock: a share of adopters is converted and pays every month while adoption holds.
            gross = adopters * i.effect
            month_gmv = gross * i.incremental_share * i.value_per_unit
            month_cost = max(0.0, gross - prev_gross) * i.cost_per_unit  # one-off cost per new conversion
            prev_gross = gross

        elif mech == Mechanism.ACQUISITION:
            # Flow: new customers arrive every month and accumulate, net of churn.
            gross_new = adopters * i.effect
            active = active * (1 - i.monthly_churn) + gross_new * i.incremental_share
            month_gmv = active * i.value_per_unit
            month_cost = gross_new * i.cost_per_unit  # incentives are paid on non-incremental customers too

        elif mech == Mechanism.RETENTION:
            # Flow: customers who would have churned this month keep paying from next month on.
            active = active * (1 - i.baseline_rate)
            month_gmv = active * i.value_per_unit
            saved = adopters * i.baseline_rate * i.effect
            active += saved * i.incremental_share
            month_cost = saved * i.cost_per_unit

        elif mech == Mechanism.TRANSACTION_UPLIFT:
            gross = adopters * i.baseline_rate * i.effect
            month_gmv = gross * i.incremental_share * i.value_per_unit
            month_cost = gross * i.cost_per_unit

        elif mech == Mechanism.COST_REDUCTION:
            gross = adopters * i.baseline_rate * i.effect
            month_savings = gross * i.incremental_share * i.value_per_unit
            month_cost = gross * i.cost_per_unit

        gmv.append(month_gmv)
        cost.append(month_cost)
        savings.append(month_savings)

    revenue = [g * i.take_rate for g in gmv]

    if mech in (Mechanism.PAID_CONVERSION, Mechanism.UPGRADE):
        units = adopters_full * i.effect * i.incremental_share
        new_mrr = None
    elif mech == Mechanism.ACQUISITION:
        units = adopters_full * i.effect * i.incremental_share
        new_mrr = units * i.value_per_unit * i.take_rate
    elif mech == Mechanism.RETENTION:
        units = adopters_full * i.baseline_rate * i.effect * i.incremental_share
        new_mrr = units * i.value_per_unit * i.take_rate
    else:
        units = adopters_full * i.baseline_rate * i.effect * i.incremental_share
        new_mrr = None

    margin = 1.0 if i.gross_margin is None else i.gross_margin
    return CalcResult(
        eligible_users=eligible,
        adopters=adopters_full,
        incremental_units_monthly=units,
        monthly_gmv=gmv,
        monthly_revenue=revenue,
        monthly_cost=cost,
        monthly_savings=savings,
        steady_state_monthly_gmv=gmv[-1],
        steady_state_monthly_revenue=revenue[-1],
        new_mrr_per_month=new_mrr,
        annualized_run_rate=revenue[-1] * 12,
        first_year_gmv=sum(gmv),
        first_year_revenue=sum(revenue),
        first_year_cost=sum(cost),
        first_year_savings=sum(savings),
        annualized_savings=savings[-1] * 12,
        first_year_net_contribution=sum(revenue) * margin + sum(savings) - sum(cost),
    )


# --------------------------------------------------------------------------- glue to the business case
SHARED_FIELDS = ("base_population", "eligible_share", "value_per_unit")
SCENARIO_FIELDS = ("adoption_rate", "effect", "incremental_share")
SCENARIO_NAMES = ("conservative", "base", "optimistic")


def inputs_from_case(case: BusinessCase, scenario: str, overrides: dict | None = None) -> CalcInputs:
    """Build calculator inputs for one scenario. `overrides` keys: shared field names, or
    '<scenario>.<field>' for per-scenario fields (e.g. 'base.adoption_rate')."""
    a = case.assumptions
    s = getattr(case.scenarios, scenario)
    opt = lambda m, default: default if m is None else m.value  # noqa: E731
    data = dict(
        mechanism=case.mechanism,
        base_population=a.base_population.value,
        eligible_share=a.eligible_share.value,
        value_per_unit=a.value_per_unit.value,
        baseline_rate=opt(a.baseline_rate, 0.0),
        monthly_churn=opt(a.monthly_churn, 0.0),
        take_rate=opt(a.take_rate, 1.0),
        cost_per_unit=opt(a.cost_per_unit, 0.0),
        gross_margin=opt(a.gross_margin, None),
        ramp_months=a.ramp_months,
        adoption_rate=s.adoption_rate,
        effect=s.effect,
        incremental_share=s.incremental_share,
    )
    for key, value in (overrides or {}).items():
        if "." in key:
            scen, field = key.split(".", 1)
            if scen == scenario:
                data[field] = value
        else:
            data[key] = value
    return CalcInputs(**data)


def calculate_scenarios(case: BusinessCase, overrides: dict | None = None) -> dict[str, CalcResult]:
    return {name: calculate(inputs_from_case(case, name, overrides)) for name in SCENARIO_NAMES}


def headline(case: BusinessCase, r: CalcResult) -> float:
    """The first-year figure this case is about: cost savings for cost_reduction, else revenue."""
    return r.first_year_savings if case.mechanism == Mechanism.COST_REDUCTION else r.first_year_revenue


def change_attribution(case: BusinessCase, overrides: dict) -> list[dict]:
    """For every overridden assumption: old value, new value and the effect of that single change
    (applied alone to the original case) on each affected scenario's first-year headline figure."""
    original = calculate_scenarios(case)
    rows = []
    for key, new in overrides.items():
        if "." in key:
            scen, field = key.split(".", 1)
            old = getattr(getattr(case.scenarios, scen), field)
            affected = [scen]
        else:
            field = key
            old = getattr(case.assumptions, key).value
            affected = list(SCENARIO_NAMES)
        if old == new:
            continue
        alone = calculate_scenarios(case, {key: new})
        rows.append(
            {
                "key": key,
                "field": field,
                "old": old,
                "new": new,
                "impact": {s: headline(case, alone[s]) - headline(case, original[s]) for s in affected},
            }
        )
    return rows


def sensitivity(case: BusinessCase) -> list[dict]:
    """Swing in the base scenario's first-year headline figure when ONE scenario assumption moves
    from its conservative to its optimistic value. Shows which uncertainty matters most."""
    base = headline(case, calculate(inputs_from_case(case, "base")))
    rows = []
    for f in SCENARIO_FIELDS:
        lo_v = getattr(case.scenarios.conservative, f)
        hi_v = getattr(case.scenarios.optimistic, f)
        if lo_v == hi_v:
            continue
        lo = headline(case, calculate(inputs_from_case(case, "base", {f"base.{f}": lo_v})))
        hi = headline(case, calculate(inputs_from_case(case, "base", {f"base.{f}": hi_v})))
        rows.append({"field": f, "low_value": lo_v, "high_value": hi_v, "low": lo, "high": hi, "base": base})
    return sorted(rows, key=lambda r: r["high"] - r["low"], reverse=True)


def round_sig(x: float, sig: int = 2) -> float:
    """Round to significant figures so outputs do not suggest more precision than the inputs have."""
    if x == 0:
        return 0.0
    from math import floor, log10

    return round(x, -int(floor(log10(abs(x)))) + (sig - 1))


def fmt_money(x: float, currency: str = "EUR") -> str:
    symbol = {"EUR": "€", "USD": "$", "GBP": "£"}.get(currency.upper(), currency + " ")
    v = round_sig(x, 2)
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        body = f"{v / 1e9:.2g}B"
    elif v >= 1e6:
        body = f"{v / 1e6:.2g}M"
    elif v >= 1e3:
        body = f"{v / 1e3:.2g}k"
    else:
        body = f"{v:.2g}"
    return f"{sign}≈{symbol}{body}"


def fmt_count(x: float) -> str:
    v = round_sig(x, 2)
    return f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2g}"
