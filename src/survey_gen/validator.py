"""Methodology validator: pure rules over a Survey, no IO and no LLM.

Severity calibration (design section 7.0): until the benchmark in batch 3
measures their false-positive rate, every wording rule backed by a word list or
a regex is a warning. ``error`` is reserved for structural and formally
decidable problems — uniqueness, counts, field presence, regex shape. A rule
whose precision is unknown must not be able to block an export.

Rules 8 and 9 of the design are implemented as rule *families*: each tier is
its own rule_id because the guidance differs (a 4-point forced-choice scale is
a deliberate design with a cost to explain, a 0-point scale is a defect).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from src.i18n import translate_validator_rule
from src.preprocessing import is_metadata_column
from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)
from src.survey_gen import vocabulary as vocab
from src.survey_gen.schema import (
    POLARITY_BIPOLAR,
    SCALE_POINTS_COARSE,
    SCALE_POINTS_CONVENTIONAL,
    SCALE_POINTS_FORCED_CHOICE,
    SCALE_POINTS_MAX,
    SECTION_PURPOSE_DEMOGRAPHIC,
    SECTION_PURPOSE_RANK,
    SECTION_PURPOSE_SCREENING,
    Question,
    Survey,
    mode_policy,
    text_in,
)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

SCOPE_QUESTION = "question"
SCOPE_SECTION = "section"
SCOPE_CONSTRUCT = "construct"
SCOPE_SURVEY = "survey"

CODE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,30}$")

MAX_STEM_CHARS_ZH = 40
MAX_STEM_WORDS_EN = 25
MATRIX_ROWS_WARN = 8
MATRIX_ROWS_ERROR = 12
MIN_CONSTRUCT_ITEMS = 3
REVERSE_CODED_CONSTRUCT_THRESHOLD = 4
MIN_OPTIONS = 2
MAX_OPTIONS = 10
CHOICE_TYPES = (QUESTION_TYPE_SINGLE, QUESTION_TYPE_MULTIPLE)


@dataclass
class ValidationIssue:
    rule_id: str
    severity: str
    scope: str
    target_id: str | None
    message: dict[str, str]
    evidence: str = ""
    suggestion: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "scope": self.scope,
            "target_id": self.target_id,
            "message": self.message,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
        }


def _issue(
    rule_id: str,
    severity: str,
    scope: str,
    target_id: str | None,
    evidence: str = "",
    **params,
) -> ValidationIssue:
    """Build an issue with both languages rendered from the shared copy table."""
    return ValidationIssue(
        rule_id=rule_id,
        severity=severity,
        scope=scope,
        target_id=target_id,
        message={
            lang: translate_validator_rule(lang, rule_id, "message", **params)
            for lang in ("zh-CN", "en")
        },
        evidence=evidence,
        suggestion={
            lang: translate_validator_rule(lang, rule_id, "suggestion", **params)
            for lang in ("zh-CN", "en")
        },
    )


def _stems(question: Question) -> list[str]:
    """Every language version of the stem, for wording checks."""
    return [value for value in (question.text or {}).values() if value and value.strip()]


# =============================================================================
# 1-7  wording rules — all warnings, see module docstring
# =============================================================================


def _split_on_coordinator(stem: str) -> list[tuple[str, str, str]]:
    """Yield (left, coordinator, right) for each coordinator occurrence."""
    spans: list[tuple[str, str, str]] = []
    for coordinator in vocab.COORDINATORS_ZH:
        for match in re.finditer(re.escape(coordinator), stem):
            spans.append((stem[: match.start()], coordinator, stem[match.end() :]))
    for coordinator in vocab.COORDINATORS_EN:
        for match in re.finditer(r"\b%s\b" % coordinator, stem, flags=re.IGNORECASE):
            spans.append((stem[: match.start()], coordinator, stem[match.end() :]))
    return spans


def check_double_barreled(survey: Survey) -> list[ValidationIssue]:
    """A question is double-barreled when both coordinated items sit in the
    evaluation-object position, rather than describing the response context.

    Operational test (the actual criterion; what follows only approximates it):
    split the item in two — if one respondent could answer the halves
    differently, it is double-barreled.

    Three guards encode the "response context" side of that criterion:
    companions, compound concepts (a ratio is one idea, not two), and joint
    quantifiers ("have you used both X and Y" is a single conjoined claim).
    """
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        for stem in _stems(question):
            if vocab.contains_any(stem, vocab.JOINT_QUANTIFIERS):
                continue
            if vocab.contains_any(stem, vocab.COMPOUND_CONCEPT_MARKERS):
                continue
            flagged = False
            for left, _, right in _split_on_coordinator(stem):
                if vocab.contains_any(left, vocab.PERSON_NOUNS) or vocab.contains_any(
                    right, vocab.PERSON_NOUNS
                ):
                    continue
                left_object = vocab.contains_any(left, vocab.EVALUATION_OBJECTS)
                right_object = vocab.contains_any(right, vocab.EVALUATION_OBJECTS)
                if left_object and right_object:
                    issues.append(
                        _issue(
                            "double_barreled",
                            SEVERITY_WARNING,
                            SCOPE_QUESTION,
                            question.question_id,
                            evidence=stem,
                            qid=question.question_id,
                            left=left_object,
                            right=right_object,
                        )
                    )
                    flagged = True
                    break
            if flagged:
                break
    return issues


def check_leading_question(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        for stem in _stems(question):
            marker = vocab.contains_any(stem, vocab.LEADING_MARKERS)
            if marker:
                issues.append(
                    _issue(
                        "leading_question",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence=stem,
                        qid=question.question_id,
                        marker=marker,
                    )
                )
                break
    return issues


def check_double_negative(survey: Survey) -> list[ValidationIssue]:
    """Two negations only count inside one clause.

    Chinese "不" turns up constantly inside ordinary compounds (不错, 不同,
    不仅, 不过, 对不起), so a whole-sentence count plus a white-list is not
    reliable. Splitting on clause punctuation first is the cheaper guard.
    """
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        for stem in _stems(question):
            hit = None
            for clause in vocab.CLAUSE_SPLIT_PATTERN.split(stem):
                if not clause.strip():
                    continue
                count = sum(clause.count(marker) for marker in vocab.NEGATION_MARKERS_ZH)
                count += sum(
                    len(re.findall(r"\b%s\b" % marker, clause, flags=re.IGNORECASE))
                    for marker in vocab.NEGATION_MARKERS_EN
                )
                if count >= 2:
                    hit = clause.strip()
                    break
            if hit:
                issues.append(
                    _issue(
                        "double_negative",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence=hit,
                        qid=question.question_id,
                        clause=hit,
                    )
                )
                break
    return issues


def check_absolute_wording(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        for stem in _stems(question):
            marker = vocab.contains_any(stem, vocab.ABSOLUTE_MARKERS)
            if marker:
                issues.append(
                    _issue(
                        "absolute_wording",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence=stem,
                        qid=question.question_id,
                        marker=marker,
                    )
                )
                break
    return issues


def check_jargon(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        for stem in _stems(question):
            term = vocab.contains_any(stem, vocab.JARGON_TERMS)
            if not term:
                explained = set(vocab.ACRONYM_EXPLAINED_PATTERN.findall(stem))
                for acronym in vocab.ACRONYM_PATTERN.findall(stem):
                    if not any(acronym in item for item in explained):
                        term = acronym
                        break
            if term:
                issues.append(
                    _issue(
                        "jargon",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence=stem,
                        qid=question.question_id,
                        term=term,
                    )
                )
                break
    return issues


def check_question_length(survey: Survey) -> list[ValidationIssue]:
    """Limits come from MODE_POLICY: a stem read aloud can carry more than
    one the respondent has to read off a screen."""
    policy = mode_policy(survey)
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        for language, stem in (question.text or {}).items():
            if not stem:
                continue
            if language == "en":
                words = len(stem.split())
                if words > policy["max_stem_words_en"]:
                    issues.append(
                        _issue(
                            "question_length",
                            SEVERITY_WARNING,
                            SCOPE_QUESTION,
                            question.question_id,
                            evidence=stem,
                            qid=question.question_id,
                            length="%d words" % words,
                            limit="%d-word" % policy["max_stem_words_en"],
                        )
                    )
                    break
            elif len(stem) > policy["max_stem_chars_zh"]:
                issues.append(
                    _issue(
                        "question_length",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence=stem,
                        qid=question.question_id,
                        length="%d 字" % len(stem),
                        limit="%d 字" % MAX_STEM_CHARS_ZH,
                    )
                )
                break
    return issues


def check_fabricated_citation(survey: Survey) -> list[ValidationIssue]:
    """Belt to the schema's braces: Question.source has no "validated scale"
    value, so the model cannot record such a claim structurally. This catches
    the claim leaking into prose instead.
    """
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        for stem in _stems(question):
            evidence = None
            for pattern in vocab.CITATION_PATTERNS:
                match = pattern.search(stem)
                if match:
                    evidence = match.group(0)
                    break
            if not evidence:
                evidence = vocab.contains_any(stem, vocab.VALIDATED_SCALE_NAMES)
            if evidence:
                issues.append(
                    _issue(
                        "fabricated_citation",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence=stem,
                        qid=question.question_id,
                        evidence_text=evidence,
                    )
                )
                break
    return issues


# =============================================================================
# 8-10  scale rules
# =============================================================================


def check_likert_points(survey: Survey) -> list[ValidationIssue]:
    """Tiered, and deliberately decoupled from the detector.

    An earlier version justified the tiers by what src.question_type_detector
    recognises. That was both wrong on the facts (4- and 6-point scales are
    recognised; zero-based ones are not) and wrong in principle: our own
    detector's range check is an implementation detail and must not decide
    which instrument designs are allowed. The tiers below are a methodology
    judgement only. The detector's blind spot is handled separately, by a hint
    that asks the user rather than by a rule that forbids the design.
    """
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        spec = question.scale_spec
        if question.question_type != QUESTION_TYPE_SCALE or spec is None:
            continue
        points = spec.points
        if points < 2 or points > SCALE_POINTS_MAX:
            rule_id, severity = "likert_points_invalid", SEVERITY_ERROR
        elif points in SCALE_POINTS_FORCED_CHOICE:
            rule_id, severity = "likert_points_forced_choice", SEVERITY_WARNING
        elif points in SCALE_POINTS_COARSE:
            rule_id, severity = "likert_points_coarse", SEVERITY_WARNING
        elif points in SCALE_POINTS_CONVENTIONAL:
            continue
        else:
            # 8 or 9 points: unusual but not defective.
            continue
        issues.append(
            _issue(rule_id, severity, SCOPE_QUESTION, question.question_id,
                   evidence="points=%s" % points, qid=question.question_id, points=points)
        )
    return issues


def check_likert_zero_based(survey: Survey) -> list[ValidationIssue]:
    """A zero-based scale is standard practice; it just needs the schema.

    0-10 is one of the most widely used formats there is. The only cost is that
    a recovered CSV without this schema attached reads it as a numeric column,
    because the detector will not guess (see docs/detection-benchmark.md for
    why guessing is worse than asking).
    """
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        spec = question.scale_spec
        if question.question_type != QUESTION_TYPE_SCALE or spec is None:
            continue
        if spec.is_zero_based:
            issues.append(
                _issue("likert_points_zero_based", SEVERITY_WARNING, SCOPE_QUESTION,
                       question.question_id,
                       evidence="%d-%d" % (spec.min_value, spec.max_value),
                       qid=question.question_id, low=spec.min_value, high=spec.max_value)
            )
    return issues


def _intensity(label: str) -> int:
    for term, tier in vocab.INTENSIFIER_TIERS.items():
        if term.isascii():
            if re.search(r"\b%s\b" % term, label, flags=re.IGNORECASE):
                return tier
        elif term in label:
            return tier
    return 0


def check_likert_label_symmetry(survey: Survey) -> list[ValidationIssue]:
    """Label-count mismatch is an error (formally decidable); the polarity and
    intensity checks are heuristics over word lists, so they stay warnings.

    The neutral-midpoint check applies to bipolar scales only. A unipolar scale
    (never -> always, not at all important -> extremely important) has a
    midpoint meaning *moderate*, not *neutral*; demanding a neutral word there
    would be a guaranteed false positive.
    """
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        spec = question.scale_spec
        if question.question_type != QUESTION_TYPE_SCALE or spec is None or not spec.labels:
            continue
        labels = [text_in(item, "zh-CN") or text_in(item, "en") for item in spec.labels]

        if len(labels) != spec.points:
            issues.append(
                _issue(
                    "likert_label_count",
                    SEVERITY_ERROR,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence="; ".join(labels),
                    qid=question.question_id,
                    points=spec.points,
                    count=len(labels),
                )
            )
            continue

        if spec.polarity == POLARITY_BIPOLAR and spec.points % 2 == 1:
            middle = labels[spec.points // 2]
            if not vocab.contains_any(middle, vocab.NEUTRAL_MARKERS):
                issues.append(
                    _issue(
                        "likert_missing_neutral",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence=middle,
                        qid=question.question_id,
                        points=spec.points,
                        label=middle,
                    )
                )

        low, high = labels[0], labels[-1]
        low_negative = vocab.contains_any(low, vocab.NEGATIVE_POLARITY_MARKERS)
        high_positive = vocab.contains_any(high, vocab.POSITIVE_POLARITY_MARKERS)
        if not (low_negative and high_positive):
            issues.append(
                _issue(
                    "likert_endpoint_polarity",
                    SEVERITY_WARNING,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence="%s / %s" % (low, high),
                    qid=question.question_id,
                    low=low,
                    high=high,
                )
            )

        for index in range(spec.points // 2):
            mirror = spec.points - 1 - index
            if _intensity(labels[index]) != _intensity(labels[mirror]):
                issues.append(
                    _issue(
                        "likert_intensity_mirror",
                        SEVERITY_WARNING,
                        SCOPE_QUESTION,
                        question.question_id,
                        evidence="%s / %s" % (labels[index], labels[mirror]),
                        qid=question.question_id,
                        low_pos=index + 1,
                        high_pos=mirror + 1,
                    )
                )
                break
    return issues


def check_likert_polarity_consistency(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for construct in survey.constructs:
        formats = set()
        for question in survey.questions_for_construct(construct.construct_id):
            if question.question_type == QUESTION_TYPE_SCALE and question.scale_spec:
                formats.add((question.scale_spec.points, question.scale_spec.polarity))
        if len(formats) > 1:
            rendered = ", ".join(sorted("%d-point %s" % item for item in formats))
            issues.append(
                _issue(
                    "likert_polarity_consistency",
                    SEVERITY_ERROR,
                    SCOPE_CONSTRUCT,
                    construct.construct_id,
                    evidence=rendered,
                    cid=construct.construct_id,
                    formats=rendered,
                )
            )
    return issues


# =============================================================================
# 11-21  structural rules
# =============================================================================


def check_matrix_rows_limit(survey: Survey) -> list[ValidationIssue]:
    """Thresholds come from MODE_POLICY: showcards and a live interviewer
    hold attention through longer grids than a web form does."""
    policy = mode_policy(survey)
    issues: list[ValidationIssue] = []
    for section in survey.sections:
        groups: dict[tuple, int] = {}
        for question in section.questions:
            if question.question_type == QUESTION_TYPE_SCALE and question.scale_spec:
                key = (question.scale_spec.points, question.scale_spec.polarity)
                groups[key] = groups.get(key, 0) + 1
        for count in groups.values():
            if count > policy["matrix_rows_error"]:
                rule_id, severity = "matrix_rows_excessive", SEVERITY_ERROR
            elif count > policy["matrix_rows_warn"]:
                rule_id, severity = "matrix_rows_limit", SEVERITY_WARNING
            else:
                continue
            issues.append(
                _issue(
                    rule_id,
                    severity,
                    SCOPE_SECTION,
                    section.section_id,
                    evidence="%d items" % count,
                    sid=section.section_id,
                    count=count,
                )
            )
    return issues


def check_question_order(survey: Survey) -> list[ValidationIssue]:
    """Screening first, demographics last."""
    issues: list[ValidationIssue] = []
    ranks = [
        (section, SECTION_PURPOSE_RANK.get(section.purpose, 1))
        for section in survey.sections
        if section.questions
    ]
    for index, (section, rank) in enumerate(ranks):
        if section.purpose == SECTION_PURPOSE_SCREENING and any(
            earlier_rank > 0 for _, earlier_rank in ranks[:index]
        ):
            issues.append(
                _issue(
                    "question_order_screening",
                    SEVERITY_ERROR,
                    SCOPE_SECTION,
                    section.section_id,
                    evidence=section.purpose,
                    sid=section.section_id,
                )
            )
        if section.purpose == SECTION_PURPOSE_DEMOGRAPHIC and any(
            later_rank < 2 for _, later_rank in ranks[index + 1 :]
        ):
            issues.append(
                _issue(
                    "question_order_demographic",
                    SEVERITY_WARNING,
                    SCOPE_SECTION,
                    section.section_id,
                    evidence=section.purpose,
                    sid=section.section_id,
                )
            )
        _ = rank
    return issues


def check_construct_min_items(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for construct in survey.constructs:
        count = len(survey.questions_for_construct(construct.construct_id))
        if count < MIN_CONSTRUCT_ITEMS:
            issues.append(
                _issue(
                    "construct_min_items",
                    SEVERITY_ERROR,
                    SCOPE_CONSTRUCT,
                    construct.construct_id,
                    evidence="%d items" % count,
                    cid=construct.construct_id,
                    count=count,
                )
            )
    return issues


def check_construct_items_are_scale(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for construct in survey.constructs:
        for question in survey.questions_for_construct(construct.construct_id):
            if question.question_type != QUESTION_TYPE_SCALE:
                issues.append(
                    _issue(
                        "construct_items_are_scale",
                        SEVERITY_ERROR,
                        SCOPE_CONSTRUCT,
                        construct.construct_id,
                        evidence=question.question_type,
                        cid=construct.construct_id,
                        qid=question.question_id,
                        qtype=question.question_type,
                    )
                )
    return issues


def check_reverse_coded(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    questions = survey.all_questions()
    if questions and not any(question.reverse_coded for question in questions):
        issues.append(
            _issue("reverse_coded_present", SEVERITY_ERROR, SCOPE_SURVEY, None)
        )
    for construct in survey.constructs:
        items = survey.questions_for_construct(construct.construct_id)
        if len(items) >= REVERSE_CODED_CONSTRUCT_THRESHOLD and not any(
            question.reverse_coded for question in items
        ):
            issues.append(
                _issue(
                    "reverse_coded_per_construct",
                    SEVERITY_WARNING,
                    SCOPE_CONSTRUCT,
                    construct.construct_id,
                    evidence="%d items" % len(items),
                    cid=construct.construct_id,
                    count=len(items),
                )
            )
    return issues


def check_attention_check(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    questions = survey.all_questions()
    checks = [question for question in questions if question.attention_check]
    # Instructed-response items are a self-administered convention. Requiring
    # one of an interviewer-administered instrument applies the norms of one
    # mode to another.
    if questions and not checks and mode_policy(survey)["requires_attention_check"]:
        issues.append(
            _issue("attention_check_present", SEVERITY_ERROR, SCOPE_SURVEY, None)
        )
    for question in checks:
        expected = question.attention_expected_value
        values = {option.value for option in question.options}
        if not expected or (values and expected not in values):
            issues.append(
                _issue(
                    "attention_check_expected_value",
                    SEVERITY_ERROR,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence=str(expected),
                    qid=question.question_id,
                    value=expected if expected else "-",
                )
            )
    return issues


def check_attention_check_position(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    questions = survey.all_questions()
    if len(questions) < 3:
        return issues
    for position, label_zh, label_en in ((0, "开头", "start"), (len(questions) - 1, "结尾", "end")):
        question = questions[position]
        if question.attention_check:
            issues.append(
                ValidationIssue(
                    rule_id="attention_check_position",
                    severity=SEVERITY_WARNING,
                    scope=SCOPE_QUESTION,
                    target_id=question.question_id,
                    message={
                        "zh-CN": translate_validator_rule(
                            "zh-CN", "attention_check_position", "message",
                            qid=question.question_id, position=label_zh,
                        ),
                        "en": translate_validator_rule(
                            "en", "attention_check_position", "message",
                            qid=question.question_id, position=label_en,
                        ),
                    },
                    evidence="position %d/%d" % (position + 1, len(questions)),
                    suggestion={
                        lang: translate_validator_rule(lang, "attention_check_position", "suggestion")
                        for lang in ("zh-CN", "en")
                    },
                )
            )
    return issues


def check_option_count(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        if question.question_type not in CHOICE_TYPES:
            continue
        count = len(question.options)
        if count < MIN_OPTIONS:
            issues.append(
                _issue(
                    "option_count_too_few",
                    SEVERITY_ERROR,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence="%d options" % count,
                    qid=question.question_id,
                    count=count,
                )
            )
        elif count > MAX_OPTIONS:
            issues.append(
                _issue(
                    "option_count_too_many",
                    SEVERITY_WARNING,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence="%d options" % count,
                    qid=question.question_id,
                    count=count,
                )
            )
    return issues


def check_option_mutual_exclusivity(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        if question.question_type != QUESTION_TYPE_MULTIPLE or not question.options:
            continue
        exclusive_positions = [
            index for index, option in enumerate(question.options) if option.exclusive
        ]
        if not exclusive_positions:
            continue
        last = exclusive_positions[-1]
        if len(exclusive_positions) > 1 or last != len(question.options) - 1:
            issues.append(
                _issue(
                    "option_mutual_exclusivity",
                    SEVERITY_WARNING,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence="positions %s" % ", ".join(str(p + 1) for p in exclusive_positions),
                    qid=question.question_id,
                    count=len(exclusive_positions),
                    position=last + 1,
                )
            )
    return issues


def check_option_label_uniqueness(survey: Survey) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for _, question in survey.iter_questions():
        seen: set[str] = set()
        for option in question.options:
            for label in (option.label or {}).values():
                normalized = (label or "").strip()
                if not normalized:
                    continue
                if normalized in seen:
                    issues.append(
                        _issue(
                            "option_label_uniqueness",
                            SEVERITY_ERROR,
                            SCOPE_QUESTION,
                            question.question_id,
                            evidence=normalized,
                            qid=question.question_id,
                            label=normalized,
                        )
                    )
                    break
                seen.add(normalized)
            else:
                continue
            break
    return issues


def check_code_shape(survey: Survey) -> list[ValidationIssue]:
    """Codes become CSV column names, so they carry three hard requirements.

    The metadata check is the safety belt for the whole round trip: the upload
    path drops ID/timestamp-looking columns, so a question coded ``user_id``
    would silently disappear between export and analysis.
    """
    issues: list[ValidationIssue] = []
    seen: dict[str, str] = {}
    for _, question in survey.iter_questions():
        code = question.code or ""
        if code in seen:
            issues.append(
                _issue(
                    "code_uniqueness",
                    SEVERITY_ERROR,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence="also used by %s" % seen[code],
                    code=code,
                )
            )
        else:
            seen[code] = question.question_id

        if not CODE_PATTERN.match(code):
            issues.append(
                _issue(
                    "code_shape",
                    SEVERITY_ERROR,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence=code,
                    code=code,
                    qid=question.question_id,
                )
            )
        elif is_metadata_column(code):
            issues.append(
                _issue(
                    "code_is_metadata",
                    SEVERITY_ERROR,
                    SCOPE_QUESTION,
                    question.question_id,
                    evidence=code,
                    code=code,
                    qid=question.question_id,
                )
            )
    return issues


_SCOPE_LABELS = {
    SCOPE_SURVEY: ("问卷", "Survey"),
    SCOPE_SECTION: ("章节", "Section"),
    SCOPE_QUESTION: ("题目", "Question"),
}


def _bilingual_issue(scope: str, target_id: str | None, target: str, language: str) -> ValidationIssue:
    zh_label, en_label = _SCOPE_LABELS.get(scope, ("", ""))
    language_zh = "中文" if language == "zh-CN" else "英文"
    return ValidationIssue(
        rule_id="bilingual_completeness",
        severity=SEVERITY_WARNING,
        scope=scope,
        target_id=target_id,
        message={
            "zh-CN": translate_validator_rule(
                "zh-CN", "bilingual_completeness", "message",
                scope_label=zh_label, target=target, missing_language=language_zh,
            ),
            "en": translate_validator_rule(
                "en", "bilingual_completeness", "message",
                scope_label=en_label, target=target, missing_language=language,
            ),
        },
        evidence="missing %s" % language,
        suggestion={
            lang: translate_validator_rule(lang, "bilingual_completeness", "suggestion")
            for lang in ("zh-CN", "en")
        },
    )


def check_bilingual_completeness(survey: Survey) -> list[ValidationIssue]:
    """Only the languages the instrument claims to be offered in.

    Demanding two languages of a monolingual instrument is a product
    opinion, not a methodology finding, and on a real questionnaire it was
    over half of every issue raised — enough noise to make the rest
    unreadable.
    """
    issues: list[ValidationIssue] = []
    for language in survey.languages:
        if not (survey.title or {}).get(language):
            issues.append(_bilingual_issue(SCOPE_SURVEY, survey.survey_id, "title", language))
        for section in survey.sections:
            if not (section.title or {}).get(language):
                issues.append(
                    _bilingual_issue(SCOPE_SECTION, section.section_id, section.section_id, language)
                )
        for _, question in survey.iter_questions():
            if not (question.text or {}).get(language):
                issues.append(
                    _bilingual_issue(SCOPE_QUESTION, question.question_id, question.question_id, language)
                )
    return issues


# =============================================================================
# registry
# =============================================================================

RULES: tuple[Callable[[Survey], list[ValidationIssue]], ...] = (
    check_double_barreled,
    check_leading_question,
    check_double_negative,
    check_absolute_wording,
    check_jargon,
    check_question_length,
    check_fabricated_citation,
    check_likert_points,
    check_likert_zero_based,
    check_likert_label_symmetry,
    check_likert_polarity_consistency,
    check_matrix_rows_limit,
    check_question_order,
    check_construct_min_items,
    check_construct_items_are_scale,
    check_reverse_coded,
    check_attention_check,
    check_attention_check_position,
    check_option_count,
    check_option_mutual_exclusivity,
    check_option_label_uniqueness,
    check_code_shape,
    check_bilingual_completeness,
)


def validate_survey(survey: Survey) -> list[ValidationIssue]:
    """Run every rule. Errors first, then warnings; order is otherwise stable."""
    issues: list[ValidationIssue] = []
    for rule in RULES:
        issues.extend(rule(survey))
    return sorted(issues, key=lambda issue: 0 if issue.severity == SEVERITY_ERROR else 1)


def errors(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity == SEVERITY_ERROR]


def warnings(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity == SEVERITY_WARNING]
