"""Structured models for inputs, assumptions and the business case.

The LLM fills these in; the deterministic calculator (calculator.py) consumes them.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class DataStatus(str, Enum):
    USER_PROVIDED = "USER PROVIDED"
    PUBLICLY_VERIFIED = "PUBLICLY VERIFIED"
    ESTIMATED = "ESTIMATED"
    HYPOTHETICAL = "HYPOTHETICAL"


class Mechanism(str, Enum):
    """How the feature creates value. Each maps to its own formula in calculator.py."""

    PAID_CONVERSION = "paid_conversion"        # free/trial users become paying
    UPGRADE = "upgrade"                        # paying customers move to a pricier plan / add-on
    ACQUISITION = "acquisition"                # existing users bring in new customers
    RETENTION = "retention"                    # fewer customers churn
    TRANSACTION_UPLIFT = "transaction_uplift"  # more orders, higher frequency or higher order value
    COST_REDUCTION = "cost_reduction"          # fewer cost-driving events (savings, not revenue)


MECHANISM_INFO: dict[Mechanism, dict[str, str]] = {
    Mechanism.PAID_CONVERSION: {
        "label": "Paid conversion",
        "effect": "Absolute probability that an adopting user becomes a paying customer because of the feature",
        "unit": "incremental paying customers",
        "formula": "Eligible users × Adoption × Incremental conversion × Incremental share × Monthly revenue per customer × Take rate",
    },
    Mechanism.UPGRADE: {
        "label": "Plan upgrade / add-on",
        "effect": "Absolute probability that an adopting customer upgrades because of the feature",
        "unit": "incremental upgraded customers",
        "formula": "Eligible customers × Adoption × Upgrade probability × Incremental share × Monthly price uplift × Take rate",
    },
    Mechanism.ACQUISITION: {
        "label": "Customer acquisition",
        "effect": "New paying customers generated per participating user per month (gross)",
        "unit": "incremental new customers / month",
        "formula": "Participants × New customers per participant per month × Incremental share × Monthly revenue per customer, accumulating month over month net of churn; incentive cost is paid on ALL acquired customers",
    },
    Mechanism.RETENTION: {
        "label": "Retention / churn reduction",
        "effect": "Relative reduction of monthly churn among adopters (0.10 = churn falls by 10%)",
        "unit": "customers retained / month",
        "formula": "Adopting customers × Baseline monthly churn × Relative churn reduction × Monthly revenue per customer, accumulating month over month (retained customers keep churning at the baseline rate)",
    },
    Mechanism.TRANSACTION_UPLIFT: {
        "label": "Transaction uplift",
        "effect": "Relative uplift in orders or order value among adopters (0.05 = +5%)",
        "unit": "incremental orders / month (or order-equivalents)",
        "formula": "Adopting users × Baseline orders per user per month × Relative uplift × Order value = incremental GMV; × Take rate = recognized revenue",
    },
    Mechanism.COST_REDUCTION: {
        "label": "Cost reduction",
        "effect": "Relative reduction in cost-driving events among adopters (0.20 = -20%)",
        "unit": "cost events avoided / month",
        "formula": "Adopting users × Baseline cost events per user per month × Relative reduction × Cost per event (savings, not revenue)",
    },
}

# Mechanisms whose `effect` is a probability / share and so cannot exceed 1.
BOUNDED_EFFECT = {
    Mechanism.PAID_CONVERSION,
    Mechanism.UPGRADE,
    Mechanism.RETENTION,
    Mechanism.COST_REDUCTION,
}
NEEDS_BASELINE_RATE = {Mechanism.RETENTION, Mechanism.TRANSACTION_UPLIFT, Mechanism.COST_REDUCTION}
MAX_UNBOUNDED_EFFECT = 5.0


# --------------------------------------------------------------------------- inputs
class UserInputs(BaseModel):
    """What the PM types into the form. Only the two descriptions are required."""

    company_name: str = Field("", max_length=200)
    website: str = Field("", max_length=300)
    business_description: str = Field(..., min_length=10, max_length=4000)
    company_size: Literal["unknown", "startup", "small", "medium", "large"] = "unknown"
    geography: str = Field("", max_length=200)
    known_active_users: Optional[float] = Field(None, gt=0)
    known_value_per_unit: Optional[float] = Field(None, gt=0)
    known_metrics_notes: str = Field("", max_length=2000)
    feature_description: str = Field(..., min_length=10, max_length=4000)
    feature_rationale: str = Field("", max_length=4000)
    expected_outcome: str = Field("", max_length=2000)

    @field_validator("*", mode="before")
    @classmethod
    def _clean(cls, v):
        if isinstance(v, str):
            # strip control characters; keep newlines/tabs
            v = "".join(ch for ch in v if ch in "\n\t" or ord(ch) >= 32).strip()
        return v


# --------------------------------------------------------------------------- business case
class Metric(BaseModel):
    name: str
    value: float
    unit: str = ""
    status: DataStatus
    reasoning: str = ""
    source_url: Optional[str] = None
    source_date: Optional[str] = None
    uncertainty: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="after")
    def _verified_needs_source(self):
        # Never let a number be called "verified" without a link to check it against.
        if self.status == DataStatus.PUBLICLY_VERIFIED and not (self.source_url or "").startswith("http"):
            self.status = DataStatus.ESTIMATED
            self.reasoning = (self.reasoning + " [Downgraded from PUBLICLY VERIFIED: no source link supplied.]").strip()
        return self


class Assumptions(BaseModel):
    """Shared (non-scenario) numeric inputs of the calculation."""

    base_population: Metric   # active users / customers / accounts the feature starts from
    eligible_share: Metric    # 0..1 share of the base population that can use the feature
    value_per_unit: Metric    # monthly ARPU / price uplift / order value / cost per event
    baseline_rate: Optional[Metric] = None   # orders per user per month, monthly churn, cost events per user per month
    monthly_churn: Optional[Metric] = None   # acquisition: churn of acquired customers (1.0 = one-off purchase)
    take_rate: Optional[Metric] = None       # marketplaces: share of GMV recognized as revenue
    cost_per_unit: Optional[Metric] = None   # variable cost / incentive per gross unit
    gross_margin: Optional[Metric] = None    # 0..1, to translate revenue into gross profit
    ramp_months: int = Field(3, ge=0, le=12)  # months until adoption reaches its scenario level

    @model_validator(mode="after")
    def _ranges(self):
        if self.base_population.value < 0:
            raise ValueError("base_population cannot be negative")
        if self.value_per_unit.value < 0:
            raise ValueError("value_per_unit cannot be negative")
        for field in ("eligible_share", "monthly_churn", "take_rate", "gross_margin"):
            m = getattr(self, field)
            if m is not None and not 0 <= m.value <= 1:
                raise ValueError(f"{field} must be a share between 0 and 1, got {m.value}")
        if self.baseline_rate is not None and self.baseline_rate.value < 0:
            raise ValueError("baseline_rate cannot be negative")
        if self.cost_per_unit is not None and self.cost_per_unit.value < 0:
            raise ValueError("cost_per_unit cannot be negative")
        return self


class ScenarioAssumptions(BaseModel):
    adoption_rate: float = Field(..., ge=0, le=1)
    effect: float = Field(..., ge=0, le=MAX_UNBOUNDED_EFFECT)
    incremental_share: float = Field(1.0, ge=0, le=1)  # share of the effect that would NOT have happened anyway
    rationale: str = ""


class Scenarios(BaseModel):
    conservative: ScenarioAssumptions
    base: ScenarioAssumptions
    optimistic: ScenarioAssumptions

    def items(self):
        return [("conservative", self.conservative), ("base", self.base), ("optimistic", self.optimistic)]

    @model_validator(mode="after")
    def _ordered(self):
        for f in ("adoption_rate", "effect", "incremental_share"):
            c, b, o = (getattr(s, f) for _, s in self.items())
            if not c <= b <= o:
                raise ValueError(f"scenarios must satisfy conservative <= base <= optimistic for {f} (got {c}, {b}, {o})")
        return self


class Experiment(BaseModel):
    design: str
    primary_metric: str
    success_criteria: str = ""
    duration: str = ""


class Source(BaseModel):
    title: str
    url: str
    date: str = ""


class BusinessCase(BaseModel):
    # 1. company
    company_summary: str
    business_model: str
    customer_type: Literal["B2B", "B2C", "B2B2C", "mixed"] = "mixed"
    currency: str = Field("EUR", max_length=8)
    size_basis: str = ""                       # how the scale was determined (public data / stated tier / illustrative)
    context_metrics: list[Metric] = []         # other relevant metrics that are not calculator inputs
    # 3-4. feature and mechanism
    feature_summary: str
    expected_value: str
    mechanism: Mechanism
    mechanism_chain: list[str] = []            # causal steps, e.g. "customers invite friends" -> ...
    mechanism_rationale: str = ""
    effect_definition: str = ""                # what `effect` means for THIS case, in plain words
    # 5-6. numbers
    assumptions: Assumptions
    scenarios: Scenarios
    scenario_rationale: str = ""
    # reasoning and confidence
    beneficiaries: str = ""
    adoption_rationale: str = ""
    key_drivers: list[str] = []
    risks: list[str] = []
    missing_evidence: list[str] = []
    data_to_collect: list[str] = []
    experiment: Experiment
    confidence: Literal["low", "medium", "high"] = "low"
    confidence_rationale: str = ""
    sources: list[Source] = []
    synthetic_example: bool = False

    @model_validator(mode="after")
    def _mechanism_requirements(self):
        a = self.assumptions
        if self.mechanism in NEEDS_BASELINE_RATE and a.baseline_rate is None:
            raise ValueError(f"mechanism '{self.mechanism.value}' requires assumptions.baseline_rate")
        if self.mechanism == Mechanism.RETENTION and a.baseline_rate.value > 1:
            raise ValueError("for retention, baseline_rate is monthly churn and must be between 0 and 1")
        if self.mechanism == Mechanism.ACQUISITION and a.monthly_churn is None:
            raise ValueError("mechanism 'acquisition' requires assumptions.monthly_churn (1.0 for one-off purchases)")
        if self.mechanism in BOUNDED_EFFECT:
            for name, s in self.scenarios.items():
                if s.effect > 1:
                    raise ValueError(f"{name}.effect must be <= 1 for mechanism '{self.mechanism.value}' (got {s.effect})")
        return self


def apply_user_overrides(case: BusinessCase, inputs: UserInputs) -> tuple[BusinessCase, list[str]]:
    """Make user-supplied numbers authoritative. Returns the updated case and human-readable notes.

    * Active users/customers: always becomes the base population (the model narrows it with eligible_share).
    * Value per unit: enforced exactly when the model says it used the user's figure. If the model derived a
      different monetization quantity (e.g. a plan price *uplift* from a known plan price) it is left alone
      and flagged, so the user can see and adjust it.
    """
    case = case.model_copy(deep=True)
    notes: list[str] = []
    a = case.assumptions
    if inputs.known_active_users is not None:
        if a.base_population.value != inputs.known_active_users:
            notes.append(
                f"Base population set to your figure ({inputs.known_active_users:,.0f}) "
                f"instead of the model's {a.base_population.value:,.0f}."
            )
        a.base_population.value = float(inputs.known_active_users)
        a.base_population.status = DataStatus.USER_PROVIDED
        a.base_population.uncertainty = "low"
    elif a.base_population.status == DataStatus.USER_PROVIDED:
        a.base_population.status = DataStatus.ESTIMATED  # nothing was supplied, so it cannot be user-provided

    if inputs.known_value_per_unit is not None:
        if a.value_per_unit.status == DataStatus.USER_PROVIDED:
            a.value_per_unit.value = float(inputs.known_value_per_unit)
            a.value_per_unit.uncertainty = "low"
        elif a.value_per_unit.value != inputs.known_value_per_unit:
            notes.append(
                f"Your price/ARPU figure ({inputs.known_value_per_unit:,.2f}) was used as context, but the "
                f"monetization metric here is a derived quantity: {a.value_per_unit.name} = "
                f"{a.value_per_unit.value:,.2f} ({a.value_per_unit.status.value}). Adjust it below if needed."
            )
    elif a.value_per_unit.status == DataStatus.USER_PROVIDED and not inputs.known_metrics_notes:
        a.value_per_unit.status = DataStatus.ESTIMATED
    return case, notes
