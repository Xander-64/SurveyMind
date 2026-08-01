"""Word lists backing the wording rules.

Kept apart from validator.py so the lists can be reviewed and extended as
false positives show up, without touching rule logic. Every list is lower-cased
at match time; Chinese entries are matched as substrings, English ones on word
boundaries.
"""
from __future__ import annotations

import re

# ---- rule 1: double-barreled -------------------------------------------------

# Coordinators that can join two barrels. "、" is the Chinese enumeration comma.
COORDINATORS_ZH = ("和", "与", "以及", "并且", "、")
COORDINATORS_EN = ("and", "or")

# Attributes a respondent can be asked to evaluate. Both sides of a coordinator
# must hit this list before the rule fires.
EVALUATION_OBJECTS = (
    "质量", "速度", "价格", "服务", "态度", "界面", "功能", "性能", "外观",
    "售后", "物流", "包装", "环境", "效率", "内容", "方式", "设计", "体验",
    "响应", "专业性", "可靠性", "易用性", "安排", "流程", "氛围", "口味",
    "quality", "speed", "price", "cost", "service", "attitude", "interface",
    "design", "performance", "packaging", "delivery", "support", "content",
    "usability", "reliability", "experience", "responsiveness", "atmosphere",
)

# Guard 1: the coordinator joins companions, i.e. it describes who the
# respondent was with, not what is being judged.
PERSON_NOUNS = (
    "家人", "家属", "朋友", "同事", "同学", "父母", "孩子", "同伴", "伴侣",
    "配偶", "亲戚", "室友", "老师", "领导",
    "family", "friends", "colleagues", "classmates", "parents", "partner",
    "spouse", "roommate", "coworkers",
)

# Guard 2: the two items form one compound concept (a ratio, a relationship).
COMPOUND_CONCEPT_MARKERS = (
    "比值", "比例", "之比", "比率", "关系", "差异", "对比", "之间", "性价比",
    "ratio", "relationship", "difference", "comparison", "between", "trade-off",
)

# Guard 3: a joint quantifier turns the pair into a single conjoined claim
# ("have you used both X and Y?").
JOINT_QUANTIFIERS = ("都", "均", "同时", "both", "either", "neither")

# ---- rule 2: leading questions ------------------------------------------------

LEADING_MARKERS = (
    "优秀的", "出色的", "卓越的", "糟糕的", "恶劣的", "难道不", "不觉得",
    "众所周知", "显而易见", "毫无疑问", "理所当然", "自然而然",
    "excellent", "outstanding", "superb", "terrible", "awful", "obviously",
    "clearly", "undoubtedly", "everyone knows", "don't you agree",
    "wouldn't you say", "isn't it true",
)

# ---- rule 3: double negatives -------------------------------------------------

NEGATION_MARKERS_ZH = ("不", "没有", "无", "非", "未", "别", "莫")
NEGATION_MARKERS_EN = ("not", "no", "never", "none", "cannot", "without", "nor")

# Clause boundaries. Two negations only count when they share a clause.
CLAUSE_SPLIT_PATTERN = re.compile(r"[，,；;。.！!？?、\n]")

# ---- rule 4: absolute wording -------------------------------------------------

ABSOLUTE_MARKERS = (
    "总是", "从不", "从来不", "所有", "全部", "每次", "任何时候", "绝对",
    "一定", "必然", "无一例外",
    "always", "never", "all", "every", "none", "absolutely", "certainly",
    "without exception",
)

# ---- rule 5: jargon -----------------------------------------------------------

JARGON_TERMS = (
    "留存率", "转化率", "客单价", "渗透率", "复购率", "漏斗", "归因",
    "触点", "私域", "颗粒度", "对齐", "抓手", "闭环", "赋能",
    "churn", "retention", "conversion rate", "attribution", "funnel",
    "onboarding", "engagement rate", "stickiness",
)

# Uppercase acronyms of 2-5 letters, e.g. KPI, ROI, SaaS, API.
ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,5}\b")
# An acronym followed by a parenthesised gloss counts as explained.
ACRONYM_EXPLAINED_PATTERN = re.compile(r"\b[A-Z]{2,5}\b\s*[（(][^）)]{2,}[）)]")

# ---- rule 7: fabricated citations ---------------------------------------------

CITATION_PATTERNS = (
    re.compile(r"[（(]\s*[A-Z][a-z]+[^）)]{0,40}(?:19|20)\d{2}\s*[）)]"),
    re.compile(r"\bdoi\s*:", re.IGNORECASE),
    re.compile(r"\bet\s+al\.?", re.IGNORECASE),
    re.compile(r"改编自"),
    re.compile(r"引自"),
    re.compile(r"\badapted from\b", re.IGNORECASE),
)

# Named instruments the generator must never claim to reproduce.
VALIDATED_SCALE_NAMES = (
    "SERVQUAL", "SERVPERF", "TAM", "UTAUT", "SUS", "NPS", "PANAS",
    "Big Five", "NEO-PI", "MBTI", "Maslach", "Likert 原始量表",
)

# ---- rule 9: Likert label symmetry --------------------------------------------

NEUTRAL_MARKERS = (
    "一般", "中立", "中等", "说不清", "不确定",
    "neutral", "neither", "undecided", "no opinion",
)

NEGATIVE_POLARITY_MARKERS = (
    "不同意", "不满意", "不重要", "不愿意", "不符合", "很差", "较差", "差",
    # A real instrument anchored a scale "很不好 / 很好"; 不好 was missing, so the
    # low end read as un-negative and the pair looked broken.
    "不好", "不佳", "不行", "不高", "不足",
    "disagree", "dissatisfied", "unimportant", "unlikely", "poor", "bad",
)

POSITIVE_POLARITY_MARKERS = (
    "同意", "满意", "重要", "愿意", "符合", "很好", "较好", "好",
    "agree", "satisfied", "important", "likely", "good", "excellent",
)

# Intensifier tiers used for the mirror check: labels at mirrored positions
# should carry mirrored intensity.
INTENSIFIER_TIERS = {
    "非常": 2, "极其": 2, "十分": 2, "极为": 2, "完全": 2,
    "比较": 1, "有些": 1, "稍微": 1, "略": 1,
    # 不太 mirrors 比较 in the standard Chinese satisfaction anchor set
    # ("非常不满意 / 不太满意 / 一般 / 比较满意 / 非常满意"). Without it the
    # mirror check called that symmetric scale asymmetric.
    "不太": 1, "不很": 1, "还算": 1, "有点": 1, "略微": 1,
    "strongly": 2, "extremely": 2, "very": 2, "completely": 2,
    "somewhat": 1, "slightly": 1, "moderately": 1, "fairly": 1,
}


def contains_any(text: str, terms: tuple[str, ...]) -> str | None:
    """Return the first matching term, or None.

    ASCII terms match on word boundaries so "all" does not fire inside
    "generally"; CJK terms match as plain substrings.
    """
    lowered = text.lower()
    for term in terms:
        lowered_term = term.lower()
        if term.isascii():
            if re.search(r"\b%s\b" % re.escape(lowered_term), lowered):
                return term
        elif lowered_term in lowered:
            return term
    return None
