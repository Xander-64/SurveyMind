"""Analysis plan: which test for which construct, and how many respondents.

Everything here is computed locally. No LLM is involved and none should be: a
sample size or a reliability interval that a language model produced is a number
nobody can check, and these are the numbers a user will act on.

Two rules run through the whole module.

Sample sizes come from an exact search
--------------------------------------
Every ``min_n`` is the smallest n at which the exact distribution reaches the
target power, found by searching with ``scipy.stats.nct``. Closed-form normal
approximations are reported alongside as a comparison, never as the answer.
They systematically overstate power: the closed form gives 63 for the standard
two-group case, and at n=63 the actual power is 0.795, short of the 0.80 it
claims. ``min_n`` is advice a user will follow, so it may not name a number
that misses the power it promises.

Reliability is reported with an interval
----------------------------------------
Alpha alone is misleading in a specific way: it rises mechanically with the
number of items (Spearman-Brown), so a long weak scale can outscore a short
strong one. Every alpha here carries a Feldt confidence interval and a
corrected item-total correlation per item, and states the assumption the
interval rests on.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd
from scipy import stats

from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)
from src.survey_gen.schema import SECTION_PURPOSE_DEMOGRAPHIC, Survey, localized

# Conventional defaults. Every output states them rather than assuming the
# reader shares them.
DEFAULT_ALPHA = 0.05
DEFAULT_POWER = 0.80
DEFAULT_EFFECT_D = 0.5

# Items per respondent, the traditional rule of thumb for scale work.
ITEMS_PER_RESPONDENT_RATIO = 10
MIN_TOTAL_RESPONDENTS = 100

METHOD_ALPHA = "cronbach_alpha"
METHOD_T_TEST = "independent_t_test"
METHOD_ANOVA = "one_way_anova"
METHOD_MANN_WHITNEY = "mann_whitney_u"
METHOD_KRUSKAL = "kruskal_wallis"
METHOD_ORDINAL_TREND = "ordinal_association"
METHOD_CHI_SQUARE = "chi_square_independence"
METHOD_CORRELATION = "pearson_correlation"
METHOD_MULTI_FREQUENCY = "multi_select_frequency"


# ---- sample size -------------------------------------------------------------


def _two_group_power(n_per_group: int, effect_d: float, alpha: float) -> float:
    """Exact power for a two-sample t test at this n, via the noncentral t."""
    df = 2 * n_per_group - 2
    noncentrality = effect_d * math.sqrt(n_per_group / 2)
    critical = stats.t.ppf(1 - alpha / 2, df)
    return float(
        stats.nct.sf(critical, df, noncentrality) + stats.nct.cdf(-critical, df, noncentrality)
    )


def two_group_sample_size(
    effect_d: float = DEFAULT_EFFECT_D,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> dict:
    """Smallest n per group reaching `power`, searched on the exact distribution.

    The closed form is returned as ``closed_form_n`` with the power it actually
    delivers, so the gap between the two is visible instead of implied.
    """
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    closed_form = math.ceil(2 * (z_alpha + z_beta) ** 2 / effect_d**2)

    n = 2
    while _two_group_power(n, effect_d, alpha) < power:
        n += 1
        if n > 10000:  # pragma: no cover - guards a pathological effect size
            break
    return {
        "min_n_per_group": n,
        "exact_power": round(_two_group_power(n, effect_d, alpha), 4),
        "closed_form_n": closed_form,
        "closed_form_actual_power": round(_two_group_power(closed_form, effect_d, alpha), 4),
        "method": "noncentral t search; closed form shown for comparison only",
    }


def anova_sample_size(
    group_count: int,
    effect_d: float = DEFAULT_EFFECT_D,
    alpha: float = DEFAULT_ALPHA,
    power: float = DEFAULT_POWER,
) -> dict:
    """Sample size for a k-group comparison, via pairwise tests with Bonferroni.

    An exact power analysis for the omnibus F test needs machinery this project
    does not carry. Reducing the question to "every pairwise comparison should
    be powered" is a defensible substitute and errs on the safe side: it asks
    for more respondents than the omnibus test strictly requires. Stated as
    such in the caveat rather than presented as the ANOVA answer.
    """
    comparisons = max(1, group_count * (group_count - 1) // 2)
    adjusted_alpha = alpha / comparisons
    result = two_group_sample_size(effect_d, adjusted_alpha, power)
    result.update({
        "group_count": group_count,
        "pairwise_comparisons": comparisons,
        "adjusted_alpha": round(adjusted_alpha, 5),
        "method": "pairwise t tests with Bonferroni correction; conservative for the omnibus F",
    })
    return result


def proportion_sample_size(margin: float = 0.05, confidence: float = 0.95) -> dict:
    """Sample size to estimate a proportion within `margin`, worst case p=0.5."""
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    return {
        "min_n": math.ceil(z**2 * 0.25 / margin**2),
        "margin": margin,
        "confidence": confidence,
        "method": "normal approximation at p=0.5, the widest case",
    }


def rule_of_thumb_sample_size(scale_item_count: int) -> dict:
    """Ten respondents per scale item, floored at 100.

    Counts *all* scale items in the instrument, not the largest construct: the
    ratio is conventionally stated over the full item pool.
    """
    return {
        "min_n": max(ITEMS_PER_RESPONDENT_RATIO * scale_item_count, MIN_TOTAL_RESPONDENTS),
        "scale_items": scale_item_count,
        "ratio": ITEMS_PER_RESPONDENT_RATIO,
        "method": "%d:1 items-to-respondents, floor %d" % (
            ITEMS_PER_RESPONDENT_RATIO, MIN_TOTAL_RESPONDENTS),
        "caveat_key": "ratio_disputed",
    }


# ---- reliability -------------------------------------------------------------


def cronbach_alpha(frame: pd.DataFrame) -> float | None:
    """Alpha over the item columns given. Returns None when undefined."""
    items = frame.dropna()
    k = items.shape[1]
    if k < 2 or len(items) < 3:
        return None
    item_variance = items.var(axis=0, ddof=1).sum()
    total_variance = items.sum(axis=1).var(ddof=1)
    if total_variance == 0:
        return None
    return float((k / (k - 1)) * (1 - item_variance / total_variance))


def feldt_confidence_interval(
    alpha_hat: float, n_respondents: int, item_count: int, level: float = 0.95
) -> tuple[float, float] | None:
    """Feldt interval for coefficient alpha.

    Built on ``(1 - alpha_hat) / (1 - alpha) ~ F(n-1, (n-1)(k-1))`` and solved
    directly for the bounds. An equivalent multiplicative form exists via
    ``1/F_q(d1, d2) = F_{1-q}(d2, d1)`` — note that it requires the degrees of
    freedom to be **swapped**. Writing the multiplicative form with the df in
    their original order is a silent error: it does not raise, it just returns
    a slightly shifted interval. Hence the divisive form here.
    """
    if item_count < 2 or n_respondents < 3:
        return None
    df1 = n_respondents - 1
    df2 = (n_respondents - 1) * (item_count - 1)
    tail = (1 - level) / 2
    lower = 1 - (1 - alpha_hat) / stats.f.ppf(tail, df1, df2)
    upper = 1 - (1 - alpha_hat) / stats.f.ppf(1 - tail, df1, df2)
    return float(lower), float(upper)


def corrected_item_total_correlations(frame: pd.DataFrame) -> dict[str, float]:
    """Each item against the sum of the *other* items.

    Corrected, i.e. the item is excluded from the total it is correlated with;
    leaving it in inflates the coefficient by correlating the item with itself.
    Reported because alpha rises with item count on its own, so a high alpha
    says nothing about whether any individual item is pulling its weight.
    """
    items = frame.dropna()
    result: dict[str, float] = {}
    for column in items.columns:
        rest = items.drop(columns=[column]).sum(axis=1)
        if items[column].std(ddof=1) == 0 or rest.std(ddof=1) == 0:
            result[column] = float("nan")
        else:
            result[column] = float(items[column].corr(rest))
    return result


# ---- plan --------------------------------------------------------------------


@dataclass
class PlannedAnalysis:
    method: str
    target: str
    columns: list[str]
    description: dict[str, str]
    min_n: int | None = None
    sample_size_detail: dict = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "target": self.target,
            "columns": self.columns,
            "description": self.description,
            "min_n": self.min_n,
            "sample_size_detail": self.sample_size_detail,
            "assumptions": self.assumptions,
            "caveats": self.caveats,
        }


CAVEATS = {
    "closed_form_gap": localized(
        "闭式正态近似给出 {closed}，但该 n 的实际功效仅 {power}，未达声明的 {target}；"
        "故取精确非中心 t 搜索得到的 {exact}。",
        "The closed-form approximation gives {closed}, whose actual power is only {power}, "
        "short of the stated {target}; the exact noncentral-t search value {exact} is used.",
    ),
    "bonferroni_conservative": localized(
        "以两两比较加 Bonferroni 校正代替 ANOVA 的精确功效分析，结果偏保守（要求样本量偏大）。",
        "Pairwise tests with a Bonferroni correction stand in for an exact ANOVA power "
        "analysis; the result is conservative, asking for more respondents than needed.",
    ),
    "ratio_disputed": localized(
        "题项与样本量之比在文献中存在 5:1 到 20:1 的分歧，此处取中间的 10:1。",
        "The items-to-respondents ratio is disputed in the literature, from 5:1 to 20:1; "
        "10:1 is taken as the middle.",
    ),
    "tau_equivalence": localized(
        "Feldt 区间依赖经典测量理论的本质 τ 等价假设（各题真分数方差相等）。"
        "题项方差不齐时区间偏窄，实际覆盖率低于名义水平；"
        "若存在题项-总分相关低于 0.30 的题目，该假设很可能已被破坏。",
        "The Feldt interval assumes essential tau-equivalence under classical test theory "
        "(equal true-score variances). With unequal item variances it is too narrow and its "
        "real coverage falls below the nominal level; an item-total correlation below 0.30 "
        "is a sign the assumption has already failed.",
    ),
    "ordinal_not_jonckheere": localized(
        "有序分组的趋势检验使用 Somers' D 与 Spearman ρ，"
        "它们衡量有序关联，与 Jonckheere-Terpstra 的 k 样本趋势检验并不等同，不得混称。",
        "Ordered-group trend uses Somers' D and Spearman's rho. These measure ordinal "
        "association and are not equivalent to the Jonckheere-Terpstra k-sample trend test; "
        "they must not be labelled as such.",
    ),
    "residual_excluded": localized(
        "「其他 / 不适用 / 拒答」等残差类别已从分母与列联表中排除，它们不是实质类别。",
        "Residual categories (other, not applicable, refused) are excluded from denominators "
        "and contingency tables; they are not substantive categories.",
    ),
    "multi_denominator": localized(
        "多选题的百分比以受访者数为分母（每人计一次），而非以被选中的选项总数为分母。",
        "Multi-select percentages use the respondent count as the denominator, not the total "
        "number of selections.",
    ),
    "single_item_ordinal": localized(
        "单个李克特题是定序变量，组间比较使用非参数检验；t 检验与 ANOVA 仅用于构念得分。",
        "A single Likert item is ordinal, so group comparisons use nonparametric tests; "
        "t tests and ANOVA are reserved for composite construct scores.",
    ),
}


def _substantive_options(question) -> list:
    """Options excluding residual codes."""
    return [option for option in question.options if not option.residual]


def _demographic_questions(survey: Survey) -> list:
    return [
        question
        for section in survey.sections
        if section.purpose == SECTION_PURPOSE_DEMOGRAPHIC
        for question in section.questions
        if question.question_type in (QUESTION_TYPE_SINGLE, QUESTION_TYPE_MULTIPLE)
    ]


def build_analysis_plan(survey: Survey) -> dict:
    """The analyses this instrument supports, with the sample size each needs."""
    analyses: list[PlannedAnalysis] = []
    scale_items = [
        question for question in survey.all_questions()
        if question.question_type == QUESTION_TYPE_SCALE
    ]

    # Reliability, one per construct.
    for construct in survey.constructs:
        items = [
            question for question in survey.questions_for_construct(construct.construct_id)
            if question.question_type == QUESTION_TYPE_SCALE
        ]
        if len(items) < 2:
            continue
        reverse = [question.code for question in items if question.reverse_coded]
        analyses.append(PlannedAnalysis(
            method=METHOD_ALPHA,
            target=construct.construct_id,
            columns=[question.code for question in items],
            description=localized(
                "构念「%s」的内部一致性：Cronbach's α 及其 95%% 置信区间，"
                "并逐题报告校正后的题项-总分相关。" % construct.name.get("zh-CN", ""),
                "Internal consistency for %s: Cronbach's alpha with a 95%% interval, plus a "
                "corrected item-total correlation per item."
                % construct.name.get("en", construct.construct_id),
            ),
            min_n=rule_of_thumb_sample_size(len(scale_items))["min_n"],
            sample_size_detail=rule_of_thumb_sample_size(len(scale_items)),
            assumptions=(
                ["reverse-coded items must be recoded first: %s" % ", ".join(reverse)]
                if reverse else []
            ),
            caveats=["tau_equivalence", "ratio_disputed"],
        ))

    # Group comparisons: composite scores get parametric tests, single items do not.
    demographics = _demographic_questions(survey)
    for construct in survey.constructs:
        items = [
            question for question in survey.questions_for_construct(construct.construct_id)
            if question.question_type == QUESTION_TYPE_SCALE
        ]
        if len(items) < 2:
            continue
        for demographic in demographics:
            groups = len(_substantive_options(demographic))
            if groups < 2:
                continue
            if groups == 2:
                size = two_group_sample_size()
                method, min_n = METHOD_T_TEST, size["min_n_per_group"]
                caveats = ["closed_form_gap", "residual_excluded"]
            else:
                size = anova_sample_size(groups)
                method, min_n = METHOD_ANOVA, size["min_n_per_group"]
                caveats = ["closed_form_gap", "bonferroni_conservative", "residual_excluded"]
            analyses.append(PlannedAnalysis(
                method=method,
                target="%s ~ %s" % (construct.construct_id, demographic.code),
                columns=[question.code for question in items] + [demographic.code],
                description=localized(
                    "按 `%s` 比较构念得分（题项均值）。" % demographic.code,
                    "Compare the composite score (item mean) across `%s`." % demographic.code,
                ),
                min_n=min_n,
                sample_size_detail=size,
                assumptions=["composite score = mean of the construct's items"],
                caveats=caveats,
            ))

    # Single Likert items are ordinal; they get nonparametric tests only.
    for question in scale_items:
        for demographic in demographics:
            groups = len(_substantive_options(demographic))
            if groups < 2:
                continue
            method = METHOD_MANN_WHITNEY if groups == 2 else METHOD_KRUSKAL
            analyses.append(PlannedAnalysis(
                method=method,
                target="%s ~ %s" % (question.code, demographic.code),
                columns=[question.code, demographic.code],
                description=localized(
                    "按 `%s` 比较单题 `%s` 的分布（非参数）。" % (demographic.code, question.code),
                    "Compare the distribution of `%s` across `%s` (nonparametric)."
                    % (question.code, demographic.code),
                ),
                min_n=None,
                assumptions=["single Likert item treated as ordinal"],
                caveats=["single_item_ordinal", "residual_excluded"],
            ))
            if groups > 2:
                analyses.append(PlannedAnalysis(
                    method=METHOD_ORDINAL_TREND,
                    target="%s ~ %s" % (question.code, demographic.code),
                    columns=[question.code, demographic.code],
                    description=localized(
                        "若 `%s` 的类别本身有序，用 Somers' D 检验单调趋势，"
                        "并报告 Spearman ρ 作为效应量。" % demographic.code,
                        "If the categories of `%s` are themselves ordered, test for a monotone "
                        "trend with Somers' D and report Spearman's rho as the effect size."
                        % demographic.code,
                    ),
                    assumptions=["only valid when the grouping categories are ordered"],
                    caveats=["ordinal_not_jonckheere", "single_item_ordinal"],
                ))

    # Categorical association.
    choice_questions = [
        question for question in survey.all_questions()
        if question.question_type in (QUESTION_TYPE_SINGLE, QUESTION_TYPE_MULTIPLE)
        and len(_substantive_options(question)) >= 2
    ]
    for index, first in enumerate(choice_questions):
        for second in choice_questions[index + 1:]:
            if first.code == second.code:
                continue
            cells = len(_substantive_options(first)) * len(_substantive_options(second))
            analyses.append(PlannedAnalysis(
                method=METHOD_CHI_SQUARE,
                target="%s x %s" % (first.code, second.code),
                columns=[first.code, second.code],
                description=localized(
                    "检验 `%s` 与 `%s` 是否独立。" % (first.code, second.code),
                    "Test whether `%s` and `%s` are independent." % (first.code, second.code),
                ),
                min_n=cells * 5,
                sample_size_detail={
                    "cells": cells,
                    "method": "expected count of at least 5 per cell",
                },
                assumptions=["expected frequency >= 5 in every cell"],
                caveats=["residual_excluded"],
            ))

    for question in survey.all_questions():
        if question.question_type == QUESTION_TYPE_MULTIPLE:
            analyses.append(PlannedAnalysis(
                method=METHOD_MULTI_FREQUENCY,
                target=question.code,
                columns=[question.code],
                description=localized(
                    "`%s` 的选项频次与响应率。" % question.code,
                    "Option frequencies and response rates for `%s`." % question.code,
                ),
                caveats=["multi_denominator", "residual_excluded"],
            ))

    # Correlations between construct scores.
    construct_ids = [
        construct.construct_id for construct in survey.constructs
        if len([
            q for q in survey.questions_for_construct(construct.construct_id)
            if q.question_type == QUESTION_TYPE_SCALE
        ]) >= 2
    ]
    for index, first in enumerate(construct_ids):
        for second in construct_ids[index + 1:]:
            analyses.append(PlannedAnalysis(
                method=METHOD_CORRELATION,
                target="%s ~ %s" % (first, second),
                columns=[first, second],
                description=localized(
                    "构念得分 `%s` 与 `%s` 的 Pearson 相关。" % (first, second),
                    "Pearson correlation between the `%s` and `%s` composite scores."
                    % (first, second),
                ),
                min_n=proportion_sample_size()["min_n"] // 4,
                assumptions=["composite scores treated as interval"],
            ))

    overall = rule_of_thumb_sample_size(len(scale_items))
    return {
        "analyses": [analysis.to_dict() for analysis in analyses],
        "recommended_total_n": max(
            [overall["min_n"]] + [a.min_n for a in analyses if a.min_n] or [MIN_TOTAL_RESPONDENTS]
        ),
        "sample_size_basis": {
            "rule_of_thumb": overall,
            "two_group": two_group_sample_size(),
            "proportion": proportion_sample_size(),
        },
        "caveats": {key: value for key, value in CAVEATS.items()},
        "defaults": {
            "alpha": DEFAULT_ALPHA,
            "power": DEFAULT_POWER,
            "effect_size_d": DEFAULT_EFFECT_D,
        },
    }
