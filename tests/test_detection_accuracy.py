"""Detection accuracy against ground truth, across noise profiles.

The labels cost nothing: every column was generated from a schema that already
states its question type, so the truth is read off the schema rather than hand
annotated. That is the point of building the generator before the benchmark.

Data provenance
---------------
All figures here come from the generator **with the latent factor implemented**
(src/survey_gen/synthetic.py). An earlier version documented a latent factor it
did not implement and produced independent columns; any statistic computed on
that data is not comparable with these numbers. See section 10 of
docs/detection-benchmark.md.

What the thresholds are for
---------------------------
The asserted floors sit below the measured values, deliberately. They are
regression guards, not targets: a floor set at the current measurement turns
every ordinary fluctuation into a failure, and a floor set above it is a wish.

What these numbers are not
--------------------------
Synthetic accuracy runs high because the generator and the detector share my
assumptions about what a questionnaire column looks like. This measures
regression and relative difficulty between noise profiles. It is not a claim
about real-world accuracy.
"""
from collections import Counter

import pytest

from src.question_type_detector import detect_question_types
from src.survey_gen.synthetic import NoiseProfile, generate_responses
from src.survey_gen.templates import TEMPLATES

N_RESPONDENTS = 200

PROFILES = {
    "clean": NoiseProfile(),
    "missing_15pct": NoiseProfile(missing_rate=0.15),
    "scale_as_text": NoiseProfile(scale_as_text=True),
    "delimiter_mix": NoiseProfile(delimiter_mix=True),
    "platform_metadata": NoiseProfile(add_metadata_columns=True),
    "straightliners_20pct": NoiseProfile(straightliner_ratio=0.2),
    "all_combined": NoiseProfile(
        missing_rate=0.10,
        scale_as_text=True,
        delimiter_mix=True,
        add_metadata_columns=True,
        straightliner_ratio=0.15,
    ),
}


def evaluate(profile: NoiseProfile, seed: int = 2026) -> dict:
    """Run every template through one noise profile.

    Columns the platform added (timestamps, IP, duration, nickname) carry no
    ground truth because they are not questions. They are counted separately as
    intrusions rather than folded into accuracy, since typing them at all is a
    different failure from typing a question wrongly.
    """
    pairs: list[tuple[str, str]] = []
    intrusions: list[str] = []
    dropped: list[str] = []

    for index, spec in enumerate(TEMPLATES):
        survey = spec.build()
        frame, truth = generate_responses(
            survey, n_respondents=N_RESPONDENTS, noise=profile, seed=seed + index
        )
        detected = detect_question_types(frame)
        for code, declared in truth.items():
            if code in detected:
                pairs.append((declared, detected[code]))
            else:
                dropped.append(code)
        for column in detected:
            if column not in truth:
                intrusions.append(column)

    correct = sum(1 for declared, predicted in pairs if declared == predicted)
    return {
        "pairs": pairs,
        "total": len(pairs),
        "correct": correct,
        "accuracy": correct / len(pairs) if pairs else 0.0,
        "intrusions": intrusions,
        "dropped": dropped,
    }


def per_type_metrics(pairs) -> dict[str, dict[str, float]]:
    """Precision, recall and F1 for each declared type."""
    types = sorted({declared for declared, _ in pairs} | {p for _, p in pairs})
    metrics = {}
    for question_type in types:
        tp = sum(1 for d, p in pairs if d == question_type and p == question_type)
        fp = sum(1 for d, p in pairs if d != question_type and p == question_type)
        fn = sum(1 for d, p in pairs if d == question_type and p != question_type)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        metrics[question_type] = {
            "precision": precision, "recall": recall, "f1": f1, "support": tp + fn,
        }
    return metrics


def confusion(pairs) -> Counter:
    return Counter(pairs)


# Floors sit under the measured values. See the module docstring.
ACCURACY_FLOOR = {
    "clean": 0.85,
    "missing_15pct": 0.85,
    "scale_as_text": 0.80,
    "delimiter_mix": 0.85,
    "platform_metadata": 0.85,
    "straightliners_20pct": 0.80,
    "all_combined": 0.70,
}


@pytest.fixture(scope="module")
def results():
    return {name: evaluate(profile) for name, profile in PROFILES.items()}


@pytest.mark.parametrize("name", list(PROFILES))
def test_accuracy_stays_above_its_floor(name, results):
    result = results[name]
    assert result["accuracy"] >= ACCURACY_FLOOR[name], (
        "%s: %.3f fell below the %.2f regression floor. If this is a deliberate "
        "detector change, update the floor and the table in "
        "docs/detection-benchmark.md section 10."
        % (name, result["accuracy"], ACCURACY_FLOOR[name])
    )


def test_ground_truth_needs_no_hand_annotation(results):
    """Every label came off a schema, which is why this benchmark is cheap."""
    assert results["clean"]["total"] >= 30


def test_the_zero_based_scale_is_the_expected_systematic_miss(results):
    """Not noise: one column type is missed by construction, every run.

    A 0-10 scale is indistinguishable from a count by its values, so the
    detector declines to claim it. That decision is defended in sections 2, 4
    and 9; here it simply has to show up as a scale predicted numeric rather
    than as random error.
    """
    matrix = confusion(results["clean"]["pairs"])
    assert matrix[("scale question", "numeric question")] >= 1


def test_platform_columns_are_typed_but_never_confused_with_questions(results):
    """English timestamp and IP columns are not dropped by the upload path.

    A known gap, characterised rather than hidden: they appear as intrusions,
    and they must not disturb the accuracy on real questions.
    """
    metadata = results["platform_metadata"]
    assert metadata["intrusions"], "the profile is supposed to add columns"
    assert metadata["accuracy"] >= ACCURACY_FLOOR["platform_metadata"]


def test_no_question_column_disappears_entirely(results):
    """Dropped columns are worse than mistyped ones: the question vanishes."""
    for name, result in results.items():
        if name in ("missing_15pct", "all_combined"):
            continue  # heavy missingness legitimately makes a column unusable
        assert result["dropped"] == [], (name, result["dropped"])


def test_scale_recall_survives_the_text_form(results):
    """Some platforms export Likert values as "5分"; that must not lose them."""
    metrics = per_type_metrics(results["scale_as_text"]["pairs"])
    assert metrics["scale question"]["recall"] >= 0.75
