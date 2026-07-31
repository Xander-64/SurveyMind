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
    # false positive: 0-10 scales (NPS, satisfaction ladders, trust batteries)
    "likert_points_invalid": 8,
    # false positive for interviewer-administered instruments
    "attention_check_present": 1,
    # artifact of our bilingual product requirement, not a methodology defect
    "bilingual_completeness": 59,
    # true positive: the instrument really does use 4-point forced choice
    "likert_points_forced_choice": 19,
    # true positive: three batteries carry no reverse-keyed item
    "reverse_coded_per_construct": 3,
    # true positive: an 11-item grid does invite straight-lining
    "matrix_rows_limit": 1,
    # false positive: residual codes (other / not applicable) inflate the count
    "option_count_too_many": 1,
}

# ---- wording-dependent findings, only visible with the local fixture ---------
EXPECTED_WORDING_EXTRA = {
    # false positive: 不太/比较 is a valid Chinese intensity pair
    "likert_intensity_mirror": 6,
    # false positive: 总是 is the standard phrasing of trait items
    "absolute_wording": 5,
    # false positive: 不好 is missing from the negative-polarity list
    "likert_endpoint_polarity": 1,
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


def test_structural_errors_are_the_two_known_false_positives(structure_counts):
    """These are the findings that would block a real questionnaire's export."""
    assert structure_counts["likert_points_invalid"] == 8
    assert structure_counts["attention_check_present"] == 1


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
def test_all_errors_on_a_real_instrument_are_false_positives(wording_issues):
    found = errors(wording_issues)
    assert len(found) == 9
    assert {issue.rule_id for issue in found} == {
        "likert_points_invalid",
        "attention_check_present",
    }
    assert all(issue.severity == SEVERITY_ERROR for issue in found)
