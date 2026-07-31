"""Methodology validator.

Layout mirrors the fixture split:

- wording rules are driven from edge_cases.json (positives) and
  hard_negatives.json (coordinator present, not double-barreled)
- structural rules are built here with make_survey, because their content is
  shape rather than prose
- ambiguous.json is a characterization record, not an assertion — see the
  test at the bottom and the _doc block inside the file
"""
import json
from pathlib import Path

import pytest

from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)
from src.survey_gen.schema import (
    POLARITY_BIPOLAR,
    POLARITY_UNIPOLAR,
    SECTION_PURPOSE_CONSTRUCT,
    SECTION_PURPOSE_DEMOGRAPHIC,
    SECTION_PURPOSE_SCREENING,
    Construct,
    Option,
    Question,
    ScaleSpec,
    Section,
    Survey,
    localized,
)
from src.survey_gen.validator import (
    RULES,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    check_double_barreled,
    errors,
    validate_survey,
    warnings,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surveys"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def golden():
    return Survey.from_dict(load("golden_survey.json"))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

AGREE_LABELS = [
    localized("非常不同意", "Strongly disagree"),
    localized("比较不同意", "Disagree"),
    localized("一般", "Neutral"),
    localized("比较同意", "Agree"),
    localized("非常同意", "Strongly agree"),
]


def agree_scale(points=5, polarity=POLARITY_BIPOLAR, labels=None):
    return ScaleSpec(
        points=points,
        polarity=polarity,
        min_label=localized("非常不同意", "Strongly disagree"),
        max_label=localized("非常同意", "Strongly agree"),
        labels=labels,
    )


def question(qid="Q01", code="item_01", zh="这项服务让我满意。", en="This service satisfies me.", **kwargs):
    kwargs.setdefault("question_type", QUESTION_TYPE_SCALE)
    if kwargs["question_type"] == QUESTION_TYPE_SCALE:
        kwargs.setdefault("scale_spec", agree_scale())
    return Question(question_id=qid, code=code, text=localized(zh, en), **kwargs)


def make_survey(sections=None, constructs=None, questions=None, purpose=SECTION_PURPOSE_CONSTRUCT):
    """Smallest survey that still satisfies the survey-level rules.

    Callers override just the piece under test; unrelated rules stay quiet so a
    test failure points at one rule.
    """
    if sections is None:
        base = questions if questions is not None else [question()]
        sections = [Section(section_id="S1", title=localized("章节", "Section"), purpose=purpose, questions=base)]
    return Survey(
        survey_id="test",
        title=localized("测试问卷", "Test survey"),
        constructs=constructs or [],
        sections=sections,
    )


def rule_ids(issues):
    return [issue.rule_id for issue in issues]


def run(survey, rule=None):
    return rule(survey) if rule else validate_survey(survey)


# --------------------------------------------------------------------------
# the golden survey: the single most important guard rail
# --------------------------------------------------------------------------


def test_golden_survey_has_no_errors(golden):
    found = errors(validate_survey(golden))
    assert found == [], [(i.rule_id, i.target_id, i.evidence) for i in found]


def test_golden_survey_has_no_warnings_either(golden):
    """Not required by the design, but a clean reference is worth keeping clean."""
    found = warnings(validate_survey(golden))
    assert found == [], [(i.rule_id, i.target_id, i.evidence) for i in found]


def test_every_issue_carries_both_languages(golden):
    survey = make_survey(questions=[question(zh="您对质量和价格是否满意？", en="Are you happy with quality and price?")])
    for issue in validate_survey(survey):
        assert issue.message["zh-CN"] and issue.message["en"]
        assert issue.message["zh-CN"] != issue.message["en"]


def test_validate_survey_puts_errors_first():
    survey = make_survey(questions=[question(code="user_id", zh="您总是满意吗？", en="Are you always satisfied?")])
    severities = [issue.severity for issue in validate_survey(survey)]
    assert severities == sorted(severities, key=lambda s: 0 if s == SEVERITY_ERROR else 1)


# --------------------------------------------------------------------------
# 1-7  wording rules, driven from the fixtures
# --------------------------------------------------------------------------

EDGE_CASES = load("edge_cases.json")["cases"]


@pytest.mark.parametrize(
    "rule_id,case",
    [(rule_id, case) for rule_id, cases in EDGE_CASES.items() for case in cases],
    ids=[
        "%s-%d" % (rule_id, index)
        for rule_id, cases in EDGE_CASES.items()
        for index, _ in enumerate(cases)
    ],
)
def test_wording_positives_trigger_their_rule(rule_id, case):
    survey = make_survey(questions=[question(zh=case["stem"]["zh-CN"], en=case["stem"]["en"])])
    assert rule_id in rule_ids(validate_survey(survey)), case["why"]


@pytest.mark.parametrize("case", load("hard_negatives.json")["cases"], ids=lambda c: c["id"])
def test_hard_negatives_do_not_trigger_double_barreled(case):
    """Coordinator present, but not double-barreled.

    Without these, an implementation that flags every coordinator would pass
    the positive cases and be useless in practice.
    """
    survey = make_survey(questions=[question(zh=case["stem"]["zh-CN"], en=case["stem"]["en"])])
    assert check_double_barreled(survey) == [], "%s (%s guard): %s" % (
        case["id"],
        case["guard"],
        case["why"],
    )


def test_all_wording_rules_are_warnings_for_now():
    """Design section 7.0: no word-list rule may block an export until batch 3
    measures its false-positive rate."""
    wording = {
        "double_barreled",
        "leading_question",
        "double_negative",
        "absolute_wording",
        "jargon",
        "question_length",
        "fabricated_citation",
    }
    for rule_id, cases in EDGE_CASES.items():
        survey = make_survey(
            questions=[question(zh=cases[0]["stem"]["zh-CN"], en=cases[0]["stem"]["en"])]
        )
        for issue in validate_survey(survey):
            if issue.rule_id in wording:
                assert issue.severity == SEVERITY_WARNING, issue.rule_id
        assert rule_id in wording


def test_double_negative_needs_both_negations_in_one_clause():
    """Chinese 不 turns up in ordinary compounds, so a sentence-wide count
    would fire constantly."""
    across_clauses = make_survey(
        questions=[question(zh="这个功能不错，价格也没有问题。", en="The feature is fine, and the price is no problem.")]
    )
    assert "double_negative" not in rule_ids(validate_survey(across_clauses))


def test_explained_acronym_is_not_jargon():
    explained = make_survey(
        questions=[question(zh="本产品的 API（应用程序接口）是否好用？", en="Is the interface easy to use?")]
    )
    assert "jargon" not in rule_ids(validate_survey(explained))


# --------------------------------------------------------------------------
# 8-10  scale rules
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "points,expected_rule,expected_severity",
    [
        (5, None, None),
        (7, None, None),
        (10, None, None),
        (4, "likert_points_forced_choice", SEVERITY_WARNING),
        (6, "likert_points_forced_choice", SEVERITY_WARNING),
        (3, "likert_points_coarse", SEVERITY_WARNING),
        (2, "likert_points_coarse", SEVERITY_WARNING),
        (0, "likert_points_invalid", SEVERITY_ERROR),
        (11, "likert_points_invalid", SEVERITY_ERROR),
    ],
)
def test_likert_points_are_tiered_not_pass_fail(points, expected_rule, expected_severity):
    """A 4- or 6-point forced-choice scale is a legitimate instrument, so it
    gets a warning explaining the cost, never an error."""
    survey = make_survey(questions=[question(scale_spec=agree_scale(points=points))])
    found = [i for i in validate_survey(survey) if i.rule_id.startswith("likert_points")]
    if expected_rule is None:
        assert found == []
    else:
        assert [i.rule_id for i in found] == [expected_rule]
        assert found[0].severity == expected_severity


def test_unipolar_scale_is_not_asked_for_a_neutral_midpoint():
    """A unipolar midpoint means moderate, not neutral: requiring a neutral
    word there is a guaranteed false positive."""
    labels = [
        localized("从不", "Never"),
        localized("很少", "Rarely"),
        localized("有时", "Sometimes"),
        localized("经常", "Often"),
        localized("总是如此", "Always"),
    ]
    survey = make_survey(
        questions=[question(scale_spec=agree_scale(polarity=POLARITY_UNIPOLAR, labels=labels))]
    )
    assert "likert_missing_neutral" not in rule_ids(validate_survey(survey))


def test_bipolar_odd_scale_without_a_neutral_midpoint_is_flagged():
    labels = list(AGREE_LABELS)
    labels[2] = localized("有点同意", "Slightly agree")
    survey = make_survey(questions=[question(scale_spec=agree_scale(labels=labels))])
    assert "likert_missing_neutral" in rule_ids(validate_survey(survey))


def test_label_count_mismatch_is_an_error():
    survey = make_survey(questions=[question(scale_spec=agree_scale(labels=AGREE_LABELS[:4]))])
    found = [i for i in validate_survey(survey) if i.rule_id == "likert_label_count"]
    assert found and found[0].severity == SEVERITY_ERROR


def test_symmetric_labels_pass_all_symmetry_checks():
    survey = make_survey(questions=[question(scale_spec=agree_scale(labels=AGREE_LABELS))])
    assert not [i for i in validate_survey(survey) if i.rule_id.startswith("likert_")]


def test_endpoints_on_the_same_side_are_flagged():
    """Both ends positive: the scale has no negative pole to disagree on."""
    labels = [
        localized("有点同意", "Slightly agree"),
        localized("比较同意", "Somewhat agree"),
        localized("一般", "Neutral"),
        localized("很同意", "Quite agree"),
        localized("非常同意", "Strongly agree"),
    ]
    survey = make_survey(questions=[question(scale_spec=agree_scale(labels=labels))])
    assert "likert_endpoint_polarity" in rule_ids(validate_survey(survey))


def test_asymmetric_intensity_is_flagged():
    labels = list(AGREE_LABELS)
    labels[1] = localized("非常不同意一点", "Strongly disagree a bit")
    survey = make_survey(questions=[question(scale_spec=agree_scale(labels=labels))])
    assert "likert_intensity_mirror" in rule_ids(validate_survey(survey))


def test_mixed_scale_formats_inside_a_construct_is_an_error():
    items = [
        question(qid="Q1", code="a1", construct_id="c", scale_spec=agree_scale(points=5)),
        question(qid="Q2", code="a2", construct_id="c", scale_spec=agree_scale(points=7)),
        question(qid="Q3", code="a3", construct_id="c", scale_spec=agree_scale(points=5)),
    ]
    survey = make_survey(questions=items, constructs=[Construct("c", localized("构念", "Construct"))])
    found = [i for i in validate_survey(survey) if i.rule_id == "likert_polarity_consistency"]
    assert found and found[0].severity == SEVERITY_ERROR


# --------------------------------------------------------------------------
# 11-21  structural rules
# --------------------------------------------------------------------------


def test_long_matrix_warns_and_very_long_matrix_errors():
    def matrix(count):
        return make_survey(
            questions=[question(qid="Q%d" % i, code="m_%d" % i) for i in range(count)]
        )

    assert "matrix_rows_limit" not in rule_ids(validate_survey(matrix(8)))
    assert "matrix_rows_limit" in rule_ids(validate_survey(matrix(9)))
    found = [i for i in validate_survey(matrix(13)) if i.rule_id == "matrix_rows_excessive"]
    assert found and found[0].severity == SEVERITY_ERROR


def test_screening_after_other_content_is_an_error():
    sections = [
        Section("S1", localized("主体", "Body"), SECTION_PURPOSE_CONSTRUCT, questions=[question()]),
        Section(
            "S2", localized("甄别", "Screening"), SECTION_PURPOSE_SCREENING,
            questions=[question(qid="Q2", code="s2")],
        ),
    ]
    found = [i for i in validate_survey(make_survey(sections)) if i.rule_id == "question_order_screening"]
    assert found and found[0].severity == SEVERITY_ERROR


def test_demographics_before_other_content_warns():
    sections = [
        Section(
            "S1", localized("基本信息", "About you"), SECTION_PURPOSE_DEMOGRAPHIC,
            questions=[question(qid="Q1", code="d1")],
        ),
        Section("S2", localized("主体", "Body"), SECTION_PURPOSE_CONSTRUCT, questions=[question(qid="Q2", code="b1")]),
    ]
    found = [i for i in validate_survey(make_survey(sections)) if i.rule_id == "question_order_demographic"]
    assert found and found[0].severity == SEVERITY_WARNING


def test_correct_order_is_quiet(golden):
    assert "question_order_screening" not in rule_ids(validate_survey(golden))
    assert "question_order_demographic" not in rule_ids(validate_survey(golden))


def test_construct_with_fewer_than_three_items_is_an_error():
    items = [question(qid="Q%d" % i, code="c_%d" % i, construct_id="c") for i in range(2)]
    survey = make_survey(questions=items, constructs=[Construct("c", localized("构念", "Construct"))])
    found = [i for i in validate_survey(survey) if i.rule_id == "construct_min_items"]
    assert found and found[0].severity == SEVERITY_ERROR


def test_construct_message_does_not_claim_alpha_is_undefined_below_three():
    """Alpha is defined at k=2; the wording must say unstable, not impossible."""
    items = [question(qid="Q%d" % i, code="c_%d" % i, construct_id="c") for i in range(2)]
    survey = make_survey(questions=items, constructs=[Construct("c", localized("构念", "Construct"))])
    issue = [i for i in validate_survey(survey) if i.rule_id == "construct_min_items"][0]
    assert "unstable" in issue.suggestion["en"]
    assert "不稳定" in issue.suggestion["zh-CN"]


def test_non_scale_item_inside_a_construct_is_an_error():
    items = [
        question(qid="Q1", code="c_1", construct_id="c"),
        question(qid="Q2", code="c_2", construct_id="c"),
        question(qid="Q3", code="c_3", construct_id="c", question_type=QUESTION_TYPE_OPEN, scale_spec=None),
    ]
    survey = make_survey(questions=items, constructs=[Construct("c", localized("构念", "Construct"))])
    found = [i for i in validate_survey(survey) if i.rule_id == "construct_items_are_scale"]
    assert found and found[0].severity == SEVERITY_ERROR


def test_missing_reverse_coded_item_is_an_error_and_present_one_is_quiet():
    without = make_survey(questions=[question()])
    assert "reverse_coded_present" in rule_ids(validate_survey(without))
    with_reverse = make_survey(questions=[question(reverse_coded=True)])
    assert "reverse_coded_present" not in rule_ids(validate_survey(with_reverse))


def test_large_construct_without_a_reverse_item_warns():
    items = [question(qid="Q%d" % i, code="c_%d" % i, construct_id="c") for i in range(4)]
    items[0].reverse_coded = False
    survey = make_survey(
        questions=items + [question(qid="QR", code="other", reverse_coded=True)],
        constructs=[Construct("c", localized("构念", "Construct"))],
    )
    found = [i for i in validate_survey(survey) if i.rule_id == "reverse_coded_per_construct"]
    assert found and found[0].severity == SEVERITY_WARNING


def test_attention_check_must_exist_and_have_a_reachable_expected_value():
    assert "attention_check_present" in rule_ids(validate_survey(make_survey()))

    unreachable = question(
        qid="Q1", code="attn", question_type=QUESTION_TYPE_SINGLE, scale_spec=None,
        attention_check=True, attention_expected_value="not_an_option",
        options=[Option("a", localized("甲", "A")), Option("b", localized("乙", "B"))],
    )
    found = [
        i for i in validate_survey(make_survey(questions=[unreachable]))
        if i.rule_id == "attention_check_expected_value"
    ]
    assert found and found[0].severity == SEVERITY_ERROR


def test_attention_check_at_the_edges_warns():
    attn = question(
        qid="Q1", code="attn", question_type=QUESTION_TYPE_SINGLE, scale_spec=None,
        attention_check=True, attention_expected_value="a",
        options=[Option("a", localized("甲", "A")), Option("b", localized("乙", "B"))],
    )
    survey = make_survey(questions=[attn, question(qid="Q2", code="x2"), question(qid="Q3", code="x3")])
    found = [i for i in validate_survey(survey) if i.rule_id == "attention_check_position"]
    assert found and found[0].severity == SEVERITY_WARNING


def test_option_counts():
    too_few = question(
        qid="Q1", code="c1", question_type=QUESTION_TYPE_SINGLE, scale_spec=None,
        options=[Option("a", localized("甲", "A"))],
    )
    found = [i for i in validate_survey(make_survey(questions=[too_few])) if i.rule_id == "option_count_too_few"]
    assert found and found[0].severity == SEVERITY_ERROR

    too_many = question(
        qid="Q1", code="c1", question_type=QUESTION_TYPE_SINGLE, scale_spec=None,
        options=[Option("o%d" % i, localized("选项%d" % i, "Option %d" % i)) for i in range(11)],
    )
    found = [i for i in validate_survey(make_survey(questions=[too_many])) if i.rule_id == "option_count_too_many"]
    assert found and found[0].severity == SEVERITY_WARNING


def test_exclusive_option_must_be_single_and_last():
    def multi(exclusive_flags):
        return question(
            qid="Q1", code="c1", question_type=QUESTION_TYPE_MULTIPLE, scale_spec=None,
            options=[
                Option("o%d" % i, localized("选项%d" % i, "Option %d" % i), order=i, exclusive=flag)
                for i, flag in enumerate(exclusive_flags)
            ],
        )

    assert "option_mutual_exclusivity" not in rule_ids(
        validate_survey(make_survey(questions=[multi([False, False, True])]))
    )
    assert "option_mutual_exclusivity" in rule_ids(
        validate_survey(make_survey(questions=[multi([False, True, False])]))
    )
    assert "option_mutual_exclusivity" in rule_ids(
        validate_survey(make_survey(questions=[multi([True, False, True])]))
    )


def test_duplicate_option_labels_are_an_error():
    duplicated = question(
        qid="Q1", code="c1", question_type=QUESTION_TYPE_SINGLE, scale_spec=None,
        options=[Option("a", localized("同一个", "Same")), Option("b", localized("同一个", "Same"))],
    )
    found = [
        i for i in validate_survey(make_survey(questions=[duplicated]))
        if i.rule_id == "option_label_uniqueness"
    ]
    assert found and found[0].severity == SEVERITY_ERROR


@pytest.mark.parametrize(
    "code,expected",
    [
        ("srv_response", None),
        ("2bad_start", "code_shape"),
        ("has space", "code_shape"),
        ("题目一", "code_shape"),
        ("user_id", "code_is_metadata"),
        ("UserID", "code_is_metadata"),
        ("RespondentID", "code_is_metadata"),
        # Documents a real gap rather than asserting it is correct:
        # is_metadata_column matches the Chinese keywords 时间 / 编号 and the
        # token "id", so English timestamp names slip through. Recorded in the
        # design doc as technical debt; see test_metadata_guard_is_asymmetric.
        ("submit_time", None),
    ],
)
def test_code_shape_and_metadata_collision(code, expected):
    """A code that reads as metadata is dropped by the upload path, so the
    question would silently vanish between export and analysis."""
    survey = make_survey(questions=[question(code=code)])
    found = [i for i in validate_survey(survey) if i.rule_id.startswith("code_")]
    if expected is None:
        assert found == []
    else:
        assert [i.rule_id for i in found] == [expected]
        assert found[0].severity == SEVERITY_ERROR


def test_metadata_guard_is_asymmetric_across_languages():
    """Characterizes a real gap in is_metadata_column, not an endorsement of it.

    It matches the Chinese keywords 时间 / 编号 plus the token "id", so Chinese
    timestamp columns are dropped by the upload path while the English ones a
    third-party export actually produces are not. That matters for the round
    trip: a recovered file with a `submit_time` column keeps it and analyses it
    as a question. Recorded so the behaviour is visible; fixing it belongs with
    the alignment layer, where the _meta_ prefix is handled too.
    """
    from src.preprocessing import is_metadata_column

    assert is_metadata_column("提交时间") is True
    assert is_metadata_column("问卷编号") is True
    assert is_metadata_column("UserID") is True
    # The gap:
    assert is_metadata_column("submit_time") is False
    assert is_metadata_column("timestamp") is False
    assert is_metadata_column("submitted_at") is False


def test_duplicate_codes_are_an_error():
    survey = make_survey(questions=[question(qid="Q1", code="same"), question(qid="Q2", code="same")])
    found = [i for i in validate_survey(survey) if i.rule_id == "code_uniqueness"]
    assert found and found[0].severity == SEVERITY_ERROR


def test_missing_translation_warns():
    incomplete = Question(
        question_id="Q1", code="c1", text={"zh-CN": "只有中文"},
        question_type=QUESTION_TYPE_SCALE, scale_spec=agree_scale(),
    )
    found = [
        i for i in validate_survey(make_survey(questions=[incomplete]))
        if i.rule_id == "bilingual_completeness"
    ]
    assert found and found[0].severity == SEVERITY_WARNING


# --------------------------------------------------------------------------
# registry sanity + the characterization record
# --------------------------------------------------------------------------


def test_every_registered_rule_returns_a_list(golden):
    for rule in RULES:
        assert isinstance(rule(golden), list)


def test_empty_survey_does_not_crash_any_rule():
    empty = Survey(survey_id="empty", title=localized("空", "Empty"))
    assert isinstance(validate_survey(empty), list)


@pytest.mark.parametrize("case", load("ambiguous.json")["cases"], ids=lambda c: c["id"])
def test_ambiguous_cases_match_the_recorded_behaviour(case):
    """Characterization record, not a correctness assertion.

    Human annotators disagree on these, so asserting a verdict would freeze one
    arbitrary reading into the spec. What is checked is only that behaviour has
    not drifted unnoticed: if this fails, decide whether the change was
    intended and update `current_behavior` in the fixture.
    """
    survey = make_survey(questions=[question(zh=case["stem"]["zh-CN"], en=case["stem"]["en"])])
    flagged = check_double_barreled(survey) != []
    recorded = case["current_behavior"] == "flagged"
    assert flagged is recorded, (
        "double_barreled behaviour on an ambiguous stem changed (%s). "
        "This is not necessarily a bug: confirm the change was intended, then "
        "update current_behavior in ambiguous.json. Contested because: %s"
        % (case["id"], case["why_contested"])
    )
