"""Tests for the deterministic financial calculator and model validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bizcase.calculator import (
    CalcInputs,
    calculate,
    calculate_scenarios,
    change_attribution,
    headline,
    inputs_from_case,
    sensitivity,
)
from bizcase.examples import EXAMPLE_INPUTS, EXAMPLES
from bizcase.models import (
    Assumptions,
    BusinessCase,
    DataStatus,
    Experiment,
    Mechanism,
    Metric,
    ScenarioAssumptions,
    Scenarios,
    UserInputs,
    apply_user_overrides,
)

H = DataStatus.HYPOTHETICAL


def metric(value, status=H, **kw):
    return Metric(name="x", value=value, status=status, **kw)


def make_case(mechanism, **assumption_kwargs) -> BusinessCase:
    defaults = dict(
        base_population=metric(1000),
        eligible_share=metric(0.5),
        value_per_unit=metric(100),
    )
    defaults.update(assumption_kwargs)
    return BusinessCase(
        company_summary="s", business_model="m", feature_summary="f", expected_value="v",
        mechanism=mechanism, assumptions=Assumptions(**defaults),
        scenarios=Scenarios(
            conservative=ScenarioAssumptions(adoption_rate=0.1, effect=0.05, incremental_share=0.8),
            base=ScenarioAssumptions(adoption_rate=0.2, effect=0.1, incremental_share=0.8),
            optimistic=ScenarioAssumptions(adoption_rate=0.3, effect=0.2, incremental_share=0.8),
        ),
        experiment=Experiment(design="d", primary_metric="m"),
    )


# --------------------------------------------------------------------------- basic arithmetic
class TestPaidConversion:
    def test_steady_state_formula(self):
        inp = CalcInputs(
            mechanism=Mechanism.PAID_CONVERSION, base_population=10000, eligible_share=0.5,
            adoption_rate=0.2, effect=0.1, incremental_share=1.0, value_per_unit=50, ramp_months=0,
        )
        r = calculate(inp)
        # eligible=5000, adopters=1000, converted=100, monthly revenue=100*50=5000
        assert r.eligible_users == 5000
        assert r.adopters == 1000
        assert r.steady_state_monthly_revenue == pytest.approx(5000)
        assert r.annualized_run_rate == pytest.approx(5000 * 12)

    def test_ramp_reaches_full_only_at_ramp_month(self):
        inp = CalcInputs(
            mechanism=Mechanism.PAID_CONVERSION, base_population=1000, eligible_share=1.0,
            adoption_rate=1.0, effect=1.0, value_per_unit=10, ramp_months=4,
        )
        r = calculate(inp)
        assert r.monthly_revenue[0] == pytest.approx(10000 * 0.25)
        assert r.monthly_revenue[3] == pytest.approx(10000)
        assert r.monthly_revenue[-1] == pytest.approx(10000)

    def test_one_off_cost_only_on_new_conversions(self):
        inp = CalcInputs(
            mechanism=Mechanism.PAID_CONVERSION, base_population=1000, eligible_share=1.0,
            adoption_rate=1.0, effect=0.5, value_per_unit=10, cost_per_unit=2, ramp_months=2,
        )
        r = calculate(inp)
        # month1: gross=250*0.5=125 (ramp .5)... cost should be >0 month1, then decreasing/zero once stable
        assert r.monthly_cost[0] > 0
        assert r.monthly_cost[-1] == pytest.approx(0, abs=1e-6)


class TestRetention:
    def test_accumulates_month_over_month(self):
        inp = CalcInputs(
            mechanism=Mechanism.RETENTION, base_population=1000, eligible_share=1.0,
            adoption_rate=1.0, effect=0.5, value_per_unit=20, baseline_rate=0.1, ramp_months=0,
        )
        r = calculate(inp)
        # revenue should grow monotonically (fewer net churners -> compounding retained base)
        assert all(b >= a - 1e-9 for a, b in zip(r.monthly_revenue, r.monthly_revenue[1:]))
        assert r.monthly_revenue[-1] > r.monthly_revenue[0]

    def test_zero_effect_means_zero_retained_revenue(self):
        inp = CalcInputs(
            mechanism=Mechanism.RETENTION, base_population=1000, eligible_share=1.0,
            adoption_rate=1.0, effect=0.0, value_per_unit=20, baseline_rate=0.1,
        )
        r = calculate(inp)
        assert r.first_year_revenue == pytest.approx(0)


class TestAcquisition:
    def test_incentive_cost_paid_on_all_new_customers(self):
        inp = CalcInputs(
            mechanism=Mechanism.ACQUISITION, base_population=1000, eligible_share=1.0,
            adoption_rate=1.0, effect=0.1, incremental_share=0.5, value_per_unit=10,
            monthly_churn=1.0, cost_per_unit=3, ramp_months=0,
        )
        r = calculate(inp)
        gross_new = 1000 * 0.1  # =100
        assert r.monthly_cost[0] == pytest.approx(gross_new * 3)
        # churn=1.0 -> no accumulation, revenue = incremental active * value
        assert r.monthly_revenue[0] == pytest.approx(gross_new * 0.5 * 10)

    def test_low_churn_accumulates(self):
        inp = CalcInputs(
            mechanism=Mechanism.ACQUISITION, base_population=1000, eligible_share=1.0,
            adoption_rate=1.0, effect=0.1, incremental_share=1.0, value_per_unit=10,
            monthly_churn=0.0, ramp_months=0,
        )
        r = calculate(inp)
        assert r.monthly_revenue[1] == pytest.approx(r.monthly_revenue[0] * 2, rel=1e-6)


class TestTransactionUplift:
    def test_gmv_vs_recognized_revenue_marketplace(self):
        inp = CalcInputs(
            mechanism=Mechanism.TRANSACTION_UPLIFT, base_population=10000, eligible_share=1.0,
            adoption_rate=1.0, effect=0.1, value_per_unit=50, baseline_rate=1.0, take_rate=0.15, ramp_months=0,
        )
        r = calculate(inp)
        gmv = 10000 * 1.0 * 0.1 * 50
        assert r.steady_state_monthly_gmv == pytest.approx(gmv)
        assert r.steady_state_monthly_revenue == pytest.approx(gmv * 0.15)
        assert r.steady_state_monthly_revenue < r.steady_state_monthly_gmv


class TestCostReduction:
    def test_produces_savings_not_revenue(self):
        inp = CalcInputs(
            mechanism=Mechanism.COST_REDUCTION, base_population=1000, eligible_share=1.0,
            adoption_rate=1.0, effect=0.2, value_per_unit=5, baseline_rate=2.0, ramp_months=0,
        )
        r = calculate(inp)
        assert r.monthly_revenue[-1] == pytest.approx(0)
        assert r.monthly_savings[-1] > 0
        assert r.first_year_net_contribution == pytest.approx(r.first_year_savings - r.first_year_cost)


# --------------------------------------------------------------------------- validation
class TestValidation:
    def test_negative_base_population_rejected(self):
        with pytest.raises(ValidationError):
            CalcInputs(mechanism=Mechanism.PAID_CONVERSION, base_population=-1, eligible_share=0.5,
                       adoption_rate=0.1, effect=0.1, value_per_unit=10)

    def test_eligible_share_over_one_rejected(self):
        with pytest.raises(ValidationError):
            CalcInputs(mechanism=Mechanism.PAID_CONVERSION, base_population=100, eligible_share=1.5,
                       adoption_rate=0.1, effect=0.1, value_per_unit=10)

    def test_bounded_effect_over_one_rejected_for_conversion(self):
        with pytest.raises(ValidationError):
            CalcInputs(mechanism=Mechanism.PAID_CONVERSION, base_population=100, eligible_share=0.5,
                       adoption_rate=0.1, effect=1.5, value_per_unit=10)

    def test_unbounded_effect_allowed_above_one_for_acquisition(self):
        inp = CalcInputs(mechanism=Mechanism.ACQUISITION, base_population=100, eligible_share=0.5,
                          adoption_rate=0.1, effect=1.5, value_per_unit=10, monthly_churn=0.1)
        assert inp.effect == 1.5

    def test_scenarios_must_be_ordered(self):
        with pytest.raises(ValidationError):
            Scenarios(
                conservative=ScenarioAssumptions(adoption_rate=0.5, effect=0.1),
                base=ScenarioAssumptions(adoption_rate=0.2, effect=0.1),
                optimistic=ScenarioAssumptions(adoption_rate=0.3, effect=0.1),
            )

    def test_retention_requires_baseline_rate(self):
        with pytest.raises(ValidationError):
            make_case(Mechanism.RETENTION)

    def test_acquisition_requires_monthly_churn(self):
        with pytest.raises(ValidationError):
            make_case(Mechanism.ACQUISITION)

    def test_metric_claimed_verified_without_source_is_downgraded(self):
        m = Metric(name="x", value=1, status=DataStatus.PUBLICLY_VERIFIED, source_url=None)
        assert m.status == DataStatus.ESTIMATED
        assert "Downgraded" in m.reasoning

    def test_verified_with_source_kept(self):
        m = Metric(name="x", value=1, status=DataStatus.PUBLICLY_VERIFIED, source_url="https://example.com")
        assert m.status == DataStatus.PUBLICLY_VERIFIED


# --------------------------------------------------------------------------- user overrides
class TestUserOverrides:
    def test_known_active_users_overrides_estimate(self):
        case = make_case(Mechanism.UPGRADE, base_population=metric(999, status=DataStatus.HYPOTHETICAL))
        inputs = UserInputs(business_description="x" * 15, feature_description="y" * 15, known_active_users=5000)
        updated, notes = apply_user_overrides(case, inputs)
        assert updated.assumptions.base_population.value == 5000
        assert updated.assumptions.base_population.status == DataStatus.USER_PROVIDED
        assert notes  # a note should flag the override

    def test_no_user_value_keeps_model_estimate(self):
        case = make_case(Mechanism.UPGRADE, base_population=metric(777))
        inputs = UserInputs(business_description="x" * 15, feature_description="y" * 15)
        updated, notes = apply_user_overrides(case, inputs)
        assert updated.assumptions.base_population.value == 777
        assert notes == []

    def test_missing_optional_inputs_handled_gracefully(self):
        inputs = UserInputs(business_description="a minimal description here", feature_description="a minimal feature here")
        assert inputs.known_active_users is None
        assert inputs.company_name == ""


# --------------------------------------------------------------------------- scenario consistency / examples
class TestExamples:
    @pytest.mark.parametrize("name", list(EXAMPLES.keys()))
    def test_example_is_marked_synthetic(self, name):
        assert EXAMPLES[name].synthetic_example is True

    @pytest.mark.parametrize("name", list(EXAMPLES.keys()))
    def test_example_scenarios_monotonic_in_revenue(self, name):
        case = EXAMPLES[name]
        results = calculate_scenarios(case)
        vals = [headline(case, results[s]) for s in ("conservative", "base", "optimistic")]
        assert vals[0] <= vals[1] <= vals[2]

    @pytest.mark.parametrize("name", list(EXAMPLES.keys()))
    def test_example_known_inputs_present(self, name):
        inputs = EXAMPLE_INPUTS[name]
        case, notes = apply_user_overrides(EXAMPLES[name], inputs)
        assert case.assumptions.base_population.value == inputs.known_active_users

    def test_saas_example_is_upgrade_mechanism(self):
        assert EXAMPLES["B2B SaaS — premium analytics upgrade"].mechanism == Mechanism.UPGRADE

    def test_ecommerce_example_is_transaction_uplift(self):
        assert EXAMPLES["E-commerce — one-click checkout"].mechanism == Mechanism.TRANSACTION_UPLIFT

    def test_referral_example_is_acquisition(self):
        assert EXAMPLES["Consumer app — referral program"].mechanism == Mechanism.ACQUISITION


# --------------------------------------------------------------------------- change attribution / sensitivity
class TestInteractiveRecalculation:
    def test_change_attribution_reports_per_scenario_delta(self):
        case = make_case(Mechanism.UPGRADE)
        rows = change_attribution(case, {"base.adoption_rate": 0.9})
        assert len(rows) == 1
        assert "base" in rows[0]["impact"]
        assert "conservative" not in rows[0]["impact"]
        assert rows[0]["impact"]["base"] > 0  # more adoption -> more revenue

    def test_shared_field_change_affects_all_scenarios(self):
        case = make_case(Mechanism.UPGRADE)
        rows = change_attribution(case, {"value_per_unit": 999})
        assert set(rows[0]["impact"]) == {"conservative", "base", "optimistic"}

    def test_no_change_produces_no_rows(self):
        case = make_case(Mechanism.UPGRADE)
        rows = change_attribution(case, {"value_per_unit": case.assumptions.value_per_unit.value})
        assert rows == []

    def test_sensitivity_sorted_by_swing(self):
        case = make_case(Mechanism.UPGRADE)
        rows = sensitivity(case)
        swings = [r["high"] - r["low"] for r in rows]
        assert swings == sorted(swings, reverse=True)

    def test_recalculation_is_deterministic_no_randomness(self):
        case = make_case(Mechanism.UPGRADE)
        r1 = calculate_scenarios(case, {"value_per_unit": 150})
        r2 = calculate_scenarios(case, {"value_per_unit": 150})
        assert r1["base"].first_year_revenue == r2["base"].first_year_revenue


# --------------------------------------------------------------------------- inputs_from_case glue
def test_inputs_from_case_respects_scenario():
    case = make_case(Mechanism.UPGRADE)
    ci = inputs_from_case(case, "optimistic")
    assert ci.adoption_rate == case.scenarios.optimistic.adoption_rate
    assert ci.effect == case.scenarios.optimistic.effect
