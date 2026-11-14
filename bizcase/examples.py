"""Three synthetic, hand-authored business cases used as fixtures/demos.

These are NOT AI output — they are illustrative examples built to exercise each
mechanism and to let the UI/tests run without calling the Claude CLI. Every one
sets `synthetic_example=True` and every company-level number is marked
HYPOTHETICAL or ESTIMATED; none describes a real company.
"""
from __future__ import annotations

from .models import (
    Assumptions,
    BusinessCase,
    DataStatus,
    Experiment,
    Mechanism,
    Metric,
    ScenarioAssumptions,
    Scenarios,
    Source,
    UserInputs,
)

H = DataStatus.HYPOTHETICAL
E = DataStatus.ESTIMATED


def _saas_premium_feature() -> BusinessCase:
    return BusinessCase(
        company_summary=(
            "SYNTHETIC EXAMPLE. A hypothetical mid-size B2B SaaS company selling project-management "
            "software to other businesses on monthly/annual subscriptions, illustrative of the small/"
            "medium tier (no real company)."
        ),
        business_model="B2B SaaS, tiered monthly subscriptions sold to business accounts.",
        customer_type="B2B",
        currency="EUR",
        size_basis="Illustrative 'small/medium B2B SaaS' tier: ~2,000 paying accounts (no real company named).",
        feature_summary="A premium analytics dashboard add-on for existing paying accounts.",
        expected_value="Give power users a reason to upgrade to the Pro plan, raising ARPU.",
        mechanism=Mechanism.UPGRADE,
        mechanism_chain=[
            "Existing paying accounts see the premium dashboard behind a Pro-plan gate",
            "A share of accounts try it during a trial window",
            "Some of those accounts upgrade their subscription to access it permanently",
            "Upgraded accounts pay a higher monthly price going forward",
        ],
        mechanism_rationale=(
            "The feature is a visible, business-value-adding capability gated behind a higher tier, which "
            "is a classic upgrade/expansion-revenue mechanism rather than new-customer acquisition or churn."
        ),
        effect_definition="effect = probability that an adopting account upgrades its plan because of the feature.",
        assumptions=Assumptions(
            base_population=Metric(
                name="Paying accounts", value=2000, unit="accounts", status=H, uncertainty="high",
                reasoning="Illustrative scale for a small/medium B2B SaaS company; no real company specified.",
            ),
            eligible_share=Metric(
                name="Accounts on a plan eligible to upgrade", value=0.6, unit="share", status=H,
                reasoning="Assumes top ~60% of accounts by usage are plausible upgrade candidates.",
            ),
            value_per_unit=Metric(
                name="Monthly price uplift (Standard -> Pro)", value=80, unit="EUR/month", status=H,
                reasoning="Illustrative €200 Standard -> €280 Pro step, a common SaaS tier gap.",
            ),
            ramp_months=3,
        ),
        scenarios=Scenarios(
            conservative=ScenarioAssumptions(adoption_rate=0.15, effect=0.05, incremental_share=0.8,
                rationale="Low feature discovery, cautious upgrade behavior."),
            base=ScenarioAssumptions(adoption_rate=0.30, effect=0.10, incremental_share=0.85,
                rationale="Typical try-then-upgrade funnel for a well-marketed add-on."),
            optimistic=ScenarioAssumptions(adoption_rate=0.45, effect=0.18, incremental_share=0.9,
                rationale="Strong in-app promotion and sales-assisted upsell."),
        ),
        scenario_rationale="Adoption and upgrade probability both scale with how aggressively the feature is marketed in-app and by sales.",
        beneficiaries="Power-user accounts that need deeper reporting for internal stakeholders.",
        adoption_rationale="B2B upgrade decisions are slower and need internal buy-in, so adoption is modest even among eligible accounts.",
        key_drivers=["eligible_share", "base.effect (upgrade probability)", "value_per_unit (price uplift)"],
        risks=["Cannibalization: some adopters might have upgraded anyway", "Feature could be undervalued at current price gap"],
        missing_evidence=["Actual Pro-plan trial-to-paid conversion history", "True price elasticity for this customer base"],
        data_to_collect=["Instrument feature usage and trial starts", "A/B test the upgrade prompt"],
        experiment=Experiment(
            design="Gate the dashboard behind a 14-day Pro trial for a random half of eligible accounts.",
            primary_metric="Upgrade rate within 30 days of trial start",
            success_criteria="Treatment upgrade rate exceeds control by >=5 percentage points",
            duration="8-10 weeks",
        ),
        confidence="low",
        confidence_rationale="All company metrics are hypothetical; only the mechanism and formula structure are solid.",
        sources=[],
        synthetic_example=True,
    )


def _ecommerce_one_click_checkout() -> BusinessCase:
    return BusinessCase(
        company_summary=(
            "SYNTHETIC EXAMPLE. A hypothetical mid-size D2C e-commerce retailer, illustrative of a "
            "medium-traffic online store (no real company)."
        ),
        business_model="E-commerce retailer selling direct to consumers online.",
        customer_type="B2C",
        currency="EUR",
        size_basis="Illustrative 'medium online retailer' tier: ~50,000 monthly shoppers.",
        feature_summary="One-click checkout for returning, logged-in shoppers.",
        expected_value="Reduce checkout abandonment and lift completed purchases.",
        mechanism=Mechanism.TRANSACTION_UPLIFT,
        mechanism_chain=[
            "Returning shoppers reach checkout with saved payment/address",
            "One-click checkout removes multi-step friction",
            "Fewer shoppers abandon at checkout",
            "More sessions convert into completed orders",
        ],
        mechanism_rationale="Checkout friction reduction is a transaction-uplift mechanism: more orders per shopper, not new customers or retention.",
        effect_definition="effect = relative uplift in monthly purchase conversion among adopters (e.g. 0.10 = +10% more orders).",
        assumptions=Assumptions(
            base_population=Metric(
                name="Monthly shoppers (sessions)", value=50000, unit="shoppers/month", status=H, uncertainty="high",
                reasoning="Illustrative scale for a medium online retailer.",
            ),
            eligible_share=Metric(
                name="Logged-in, returning shoppers with saved payment", value=0.35, unit="share", status=H,
                reasoning="One-click checkout only applies to shoppers with a saved account and payment method.",
            ),
            value_per_unit=Metric(
                name="Average order value", value=70, unit="EUR/order", status=H,
                reasoning="Illustrative AOV typical of a general D2C retailer.",
            ),
            baseline_rate=Metric(
                name="Baseline purchase conversion among eligible shoppers", value=0.03, unit="orders/shopper/month",
                status=H, reasoning="Illustrative 3% conversion rate for eligible returning shoppers.",
            ),
            ramp_months=2,
        ),
        scenarios=Scenarios(
            conservative=ScenarioAssumptions(adoption_rate=0.4, effect=0.05, incremental_share=0.7,
                rationale="Slow rollout, modest friction reduction, some orders would have completed anyway."),
            base=ScenarioAssumptions(adoption_rate=0.6, effect=0.10, incremental_share=0.75,
                rationale="Checkout-abandonment studies typically show high-single-digit to low-double-digit lifts."),
            optimistic=ScenarioAssumptions(adoption_rate=0.8, effect=0.18, incremental_share=0.85,
                rationale="Strong promotion of the feature plus mobile checkout being especially friction-sensitive."),
        ),
        scenario_rationale="Range reflects uncertainty in how much checkout friction was really driving abandonment versus other factors (price, shipping cost).",
        beneficiaries="Returning, logged-in shoppers who already trust the store with payment details.",
        adoption_rationale="Only a subset of traffic is logged-in returning shoppers; adoption is capped by that eligible pool, not by feature appeal.",
        key_drivers=["eligible_share", "base.effect (conversion uplift)", "baseline_rate"],
        risks=["Uplift may be mostly saved time, not incremental purchases", "One-click checkout has fraud/chargeback risk"],
        missing_evidence=["Actual cart-to-checkout abandonment funnel data", "Share of traffic that is logged-in returning shoppers"],
        data_to_collect=["Funnel analytics on checkout steps", "A/B test completion rate with vs without feature"],
        experiment=Experiment(
            design="A/B test: random half of eligible returning shoppers see one-click checkout.",
            primary_metric="Orders per eligible shopper per month",
            success_criteria="Treatment group shows a statistically significant uplift in order rate",
            duration="4-6 weeks to reach sample size",
        ),
        confidence="low",
        confidence_rationale="Company scale and conversion rate are illustrative; the uplift range is grounded in general checkout-UX literature, not this company's data.",
        sources=[
            Source(title="Baymard Institute checkout usability research (general benchmark, illustrative)", url="https://baymard.com/", date="n/a - general reference"),
        ],
        synthetic_example=True,
    )


def _consumer_app_referral_program() -> BusinessCase:
    return BusinessCase(
        company_summary=(
            "SYNTHETIC EXAMPLE. A hypothetical consumer subscription app (e.g. fitness/wellness), "
            "illustrative of a mid-scale freemium app (no real company)."
        ),
        business_model="Freemium consumer subscription app; free tier plus a paid monthly subscription.",
        customer_type="B2C",
        currency="EUR",
        size_basis="Illustrative 'mid-scale consumer app' tier: ~100,000 monthly active users.",
        feature_summary="A referral program rewarding existing users for inviting friends who subscribe.",
        expected_value="Acquire new paying subscribers at a lower cost than paid marketing.",
        mechanism=Mechanism.ACQUISITION,
        mechanism_chain=[
            "Existing active users (free or paid) are shown the referral offer",
            "A share of users send invites to friends",
            "Some invited friends install the app and some of those convert to paid",
            "Newly acquired paying subscribers add recurring revenue, net of referral rewards and churn",
        ],
        mechanism_rationale="A referral program's entire purpose is bringing in new paying customers, so acquisition is the correct mechanism, not retention or conversion of existing users.",
        effect_definition="effect = new paying subscribers generated per participating user per month (gross, before incremental-share and churn).",
        assumptions=Assumptions(
            base_population=Metric(
                name="Monthly active users", value=100000, unit="MAU", status=H, uncertainty="high",
                reasoning="Illustrative scale for a mid-size consumer subscription app.",
            ),
            eligible_share=Metric(
                name="Active users shown the referral offer", value=0.5, unit="share", status=H,
                reasoning="Assumes the program is surfaced to roughly half of MAU initially (e.g. engaged users only).",
            ),
            value_per_unit=Metric(
                name="Monthly subscription price", value=10, unit="EUR/month", status=H,
                reasoning="Illustrative price point for a consumer wellness/fitness subscription app.",
            ),
            monthly_churn=Metric(
                name="Monthly churn of acquired subscribers", value=0.08, unit="share/month", status=H,
                reasoning="Illustrative churn typical of consumer subscription apps acquired via referral.",
            ),
            cost_per_unit=Metric(
                name="Referral reward cost per converted referral", value=5, unit="EUR", status=H,
                reasoning="Illustrative one-off reward (e.g. one free month equivalent) per successful referral.",
            ),
            ramp_months=2,
        ),
        scenarios=Scenarios(
            conservative=ScenarioAssumptions(adoption_rate=0.05, effect=0.02, incremental_share=0.6,
                rationale="Few users participate; most invited friends who convert might have joined organically anyway."),
            base=ScenarioAssumptions(adoption_rate=0.12, effect=0.04, incremental_share=0.7,
                rationale="Typical referral participation and conversion for a moderately incentivized program."),
            optimistic=ScenarioAssumptions(adoption_rate=0.25, effect=0.07, incremental_share=0.8,
                rationale="Strong viral loop with prominent in-app placement and an attractive reward."),
        ),
        scenario_rationale="Referral programs have wide variance in viral participation; the range reflects typical consumer-app referral benchmarks, not this app's measured data.",
        beneficiaries="New users acquired through friends, and existing users earning rewards.",
        adoption_rationale="Only a minority of users typically engage with referral programs; adoption is capped by willingness to invite friends, not just feature visibility.",
        key_drivers=["base.effect (referrals converting to paying users)", "incremental_share (how many would have joined anyway)", "monthly_churn of acquired cohort"],
        risks=["Invited users may convert at lower retention than organic users", "Reward cost could exceed incremental revenue if incremental_share is overestimated"],
        missing_evidence=["Actual invite-to-install and install-to-paid conversion rates", "Retention curve of referred users vs organic"],
        data_to_collect=["Track referral funnel end to end (invite sent -> install -> trial -> paid)", "Cohort-retention comparison, referred vs organic"],
        experiment=Experiment(
            design="Launch to a random 50% of eligible users; track invites sent, conversions, and 90-day retention vs organic cohort.",
            primary_metric="Net new paying subscribers per month attributable to referrals",
            success_criteria="Referral-driven subscribers retain within 20% of organic subscriber retention and incremental_share holds up in a holdout test",
            duration="12 weeks (to observe early churn)",
        ),
        confidence="low",
        confidence_rationale="All figures are hypothetical benchmarks; the acquisition mechanism and net-of-churn accumulation logic are the reliable part of this example.",
        sources=[],
        synthetic_example=True,
    )


EXAMPLES: dict[str, BusinessCase] = {
    "B2B SaaS — premium analytics upgrade": _saas_premium_feature(),
    "E-commerce — one-click checkout": _ecommerce_one_click_checkout(),
    "Consumer app — referral program": _consumer_app_referral_program(),
}

EXAMPLE_INPUTS: dict[str, UserInputs] = {
    "B2B SaaS — premium analytics upgrade": UserInputs(
        company_name="(hypothetical) ProjectFlow",
        business_description="B2B SaaS project-management tool sold to small/medium businesses on monthly subscriptions.",
        company_size="medium", geography="EU", known_active_users=2000, known_value_per_unit=200,
        known_metrics_notes="2,000 paying accounts, ~€200/month average subscription (illustrative).",
        feature_description="A premium analytics dashboard gated behind the Pro plan.",
        feature_rationale="Give power users a reason to upgrade and raise ARPU.",
        expected_outcome="Increase plan-upgrade rate and average revenue per account.",
    ),
    "E-commerce — one-click checkout": UserInputs(
        company_name="(hypothetical) ShopLane",
        business_description="D2C e-commerce retailer selling general consumer goods online.",
        company_size="medium", geography="EU", known_active_users=50000, known_value_per_unit=70,
        known_metrics_notes="~50,000 monthly shoppers, ~€70 average order value (illustrative).",
        feature_description="One-click checkout for returning, logged-in shoppers.",
        feature_rationale="Reduce checkout abandonment at the payment step.",
        expected_outcome="More completed orders per shopper per month.",
    ),
    "Consumer app — referral program": UserInputs(
        company_name="(hypothetical) FitTrail",
        business_description="Freemium consumer fitness/wellness subscription app.",
        company_size="medium", geography="Global", known_active_users=100000, known_value_per_unit=10,
        known_metrics_notes="~100,000 MAU, €10/month subscription (illustrative).",
        feature_description="A referral program rewarding users who invite friends that subscribe.",
        feature_rationale="Acquire new paying subscribers at lower cost than paid ads.",
        expected_outcome="Increase net new paying subscribers per month.",
    ),
}
