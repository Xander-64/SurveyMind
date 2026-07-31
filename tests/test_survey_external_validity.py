"""External validity: run the validator against a real professional instrument.

golden_survey.json was written by the same person as the rules, so its clean
result is circular and proves nothing about precision. This module checks the
validator against an instrument designed by survey methodologists who had no
knowledge of these rules.

The fixture is split in two for copyright reasons, and the split is not
incidental — it maps exactly onto which rules need what:

    external_structure.json   committed. Scale points, polarity, construct
                              grouping, reverse flags, option counts, matrix
                              block sizes, monolingual declaration. Every stem,
                              option label and scale anchor is a placeholder.
                              Guards the seven structural findings.

    external_wording.json     git-ignored, local only. The full transcription,
                              including the instrument's own prose. Guards the
                              three findings that depend on actual wording, and
                              supplies the real-world negatives that are the
                              strongest precision evidence available.

Tests over the wording fixture skip when the file is absent. That is the
designed state for a fresh clone, not a broken setup.

Counts are a characterization record, not a target. A professional instrument
tripping a rule is evidence about the rule, not about the instrument. When a
rule is adjusted, update the expectations here and the analysis in
docs/external-validity-check.md.
"""
import json
from collections import Counter
from pathlib import Path

import pytest

from src.survey_gen.schema import Survey
from src.survey_gen.validator import SEVERITY_ERROR, errors, validate_survey

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surveys"
STRUCTURE = FIXTURES / "external_structure.json"
WORDING = FIXTURES / "external_wording.json"

wording_only = pytest.mark.skipif(
    not WORDING.exists(),
    reason=(
        "external_wording.json is intentionally git-ignored: it holds a third-party "
        "questionnaire's own prose, which is not redistributed in this repository. "
        "The committed external_structure.json covers the structural findings. "
        "To run these checks, rebuild the wording fixture locally following "
        "docs/external-validity-check.md."
    ),
)

# ---- structural findings, guarded by the committed fixture -------------------
EXPECTED_STRUCTURE = {
    # true positive: the instrument really does use 4-point forced choice, and
    # the copy now comments on the resolution trade-off instead of repeating a
    # claim about the detector that turned out to be false
    "likert_points_forced_choice": 19,
    # informational: 0-10 batteries are standard. Was 8 errors before
    # ScaleSpec.min_value existed; now it just reminds the author to keep the
    # schema with the data, because 0-10 ratings and 0-10 counts are
    # indistinguishable by value alone
    "likert_points_zero_based": 8,
    # true positive: three batteries carry no reverse-keyed item
    "reverse_coded_per_construct": 3,
    # Gone since the previous run, all deliberately:
    #   likert_points_invalid   8 -> 0  0-10 is a valid design, not a defect
    #   attention_check_present 1 -> 0  interviewer mode does not require one
    #   bilingual_completeness 59 -> 0  the instrument declares one language
    #   matrix_rows_limit       1 -> 0  showcards raise the threshold to 12
}

# ---- wording-dependent findings, only visible with the local fixture ---------
EXPECTED_WORDING_EXTRA = {
    # Down from warning to info, and correctly so: all five are 总是 inside a
    # trait battery, where it is the standard phrasing rather than an absolutist
    # trap. The rule keeps its detection power for standalone items.
    "absolute_wording": 5,
    # Gone since the previous run:
    #   likert_intensity_mirror 6 -> 0  不太 added; 不太/比较 is a valid pair
    #   likert_endpoint_polarity 1 -> 0  不好 added to the negative markers
}

# Rules a professional instrument must not trip. Zero hits across 51 real items
# is the strongest precision evidence available for the wording rules.
MUST_NOT_FIRE_WORDING = (
    "double_barreled",
    "leading_question",
    "double_negative",
    "jargon",
    "question_length",
    "fabricated_citation",
)
MUST_NOT_FIRE_STRUCTURE = (
    "code_shape",
    "code_uniqueness",
    "code_is_metadata",
    "option_label_uniqueness",
    "construct_min_items",
    "construct_items_are_scale",
    "question_order_screening",
)


def load(path):
    return Survey.from_dict(json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def structure_counts():
    return Counter(issue.rule_id for issue in validate_survey(load(STRUCTURE)))


@pytest.fixture(scope="module")
def wording_issues():
    if not WORDING.exists():
        pytest.skip("wording fixture not present")
    return validate_survey(load(WORDING))


# ---- committed fixture -------------------------------------------------------


def test_structure_fixture_carries_no_original_prose():
    """The committed fixture must stay free of the instrument's own wording."""
    survey = load(STRUCTURE)
    assert len(survey.all_questions()) == 51
    for question in survey.all_questions():
        assert question.text["zh-CN"].startswith("[题干已移除")
        for option in question.options:
            assert option.label["zh-CN"].startswith("[选项")
        if question.scale_spec:
            assert question.scale_spec.labels is None
            assert question.scale_spec.min_label is None
            assert question.scale_spec.max_label is None
    assert "copyright" in survey.generation_provenance["reason"]


def test_structure_preserves_the_scale_shapes_that_drive_the_findings():
    survey = load(STRUCTURE)
    points = Counter(
        q.scale_spec.points for q in survey.all_questions() if q.scale_spec
    )
    assert points[11] == 8, "the 0-10 batteries must survive the strip"
    zero_based = [q for q in survey.all_questions()
                  if q.scale_spec and q.scale_spec.is_zero_based]
    assert len(zero_based) == 8, "min_value must survive too, not just points"
    assert points[4] == 19, "the 4-point forced-choice blocks must survive the strip"
    assert points[5] == 12, "6 job-satisfaction + 4 life-satisfaction + 2 healthcare items"


@pytest.mark.parametrize("rule_id", MUST_NOT_FIRE_STRUCTURE)
def test_structural_high_precision_rules_stay_silent(rule_id, structure_counts):
    assert structure_counts[rule_id] == 0, "%s fired %d times" % (
        rule_id, structure_counts[rule_id])


def test_structural_counts_have_not_drifted(structure_counts):
    assert dict(structure_counts) == EXPECTED_STRUCTURE, (
        "Structural external-validity counts changed. Not automatically a "
        "failure: if a rule was deliberately adjusted, update EXPECTED_STRUCTURE "
        "and docs/external-validity-check.md. Got %s" % dict(structure_counts)
    )


def test_a_real_instrument_now_raises_no_errors_at_all(structure_counts):
    """The point of the whole exercise.

    A professionally designed questionnaire used to trip nine errors, every one
    of them a false positive, and errors are what would block an export. After
    ScaleSpec.min_value, the administration-mode policy and the declared
    languages, it trips none. What remains are warnings: two true findings, one
    design comment, one informational note and one pending fix.
    """
    assert structure_counts["likert_points_invalid"] == 0
    assert structure_counts["attention_check_present"] == 0
    assert structure_counts["bilingual_completeness"] == 0
    assert structure_counts["option_count_too_many"] == 0


# ---- local-only fixture ------------------------------------------------------


@wording_only
@pytest.mark.parametrize("rule_id", MUST_NOT_FIRE_WORDING)
def test_wording_rules_stay_silent_on_a_real_instrument(rule_id, wording_issues):
    """51 professionally written items, zero hits: the precision evidence a
    self-authored fixture cannot provide."""
    counts = Counter(issue.rule_id for issue in wording_issues)
    assert counts[rule_id] == 0, "%s fired %d times on a real instrument" % (
        rule_id, counts[rule_id])


@wording_only
def test_wording_counts_have_not_drifted(wording_issues):
    counts = Counter(issue.rule_id for issue in wording_issues)
    expected = dict(EXPECTED_STRUCTURE)
    expected.update(EXPECTED_WORDING_EXTRA)
    assert dict(counts) == expected, (
        "Wording external-validity counts changed. Update EXPECTED_WORDING_EXTRA "
        "and docs/external-validity-check.md if the change was intended. "
        "Got %s" % dict(counts)
    )


@wording_only
def test_no_errors_survive_on_the_full_transcription_either(wording_issues):
    assert errors(wording_issues) == []
    assert all(issue.severity != SEVERITY_ERROR for issue in wording_issues)


@wording_only
def test_no_false_positives_remain_at_warning_level(wording_issues):
    """Every warning left standing is a true finding or a design comment.

    The four vocabulary and scope defects the real instrument exposed are all
    closed; what is left is the forced-choice comment, the zero-based note, the
    three batteries genuinely missing a reverse-keyed item, and five trait-item
    hits demoted to info.
    """
    from src.survey_gen.validator import warnings as warning_issues

    remaining = Counter(issue.rule_id for issue in warning_issues(wording_issues))
    assert dict(remaining) == {
        "likert_points_forced_choice": 19,
        "likert_points_zero_based": 8,
        "reverse_coded_per_construct": 3,
    }
