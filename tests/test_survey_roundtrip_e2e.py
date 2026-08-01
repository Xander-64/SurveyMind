"""The loop, closed, with no API key configured.

    template -> validate (0 errors) -> export -> synthesise 200 responses
    -> POST /api/upload -> types come back

The last step is asserted twice, on purpose, and both must pass:

    (a) detection only, no schema. Asserts what the detector actually returns.
        The 0-10 recommendation column comes back as a numeric question, and
        that is the recorded, documented behaviour — not a failure. A 0-10
        rating and a 0-10 count are identical in their values, and the detector
        declining to guess is the correct call (docs/detection-benchmark.md).

    (b) schema present. Asserts the same column resolves to a scale and that
        construct scores become computable.

The gap between (a) and (b) is the point. It is not something to paper over by
restricting what the templates may generate: 0-10 is the standard form for
recommendation intent and life-satisfaction ladders, and a template library
without one would be missing a capability, not avoiding a bug. The two
assertions keep the difference measured and visible.
"""
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from src.question_type_detector import (
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_SCALE,
    detect_question_types,
)
from src.survey_gen.export import EXPORT_FORMATS, export_all, export_sample_csv
from src.survey_gen.roundtrip import (
    RESOLUTION_DECLARED,
    RESOLUTION_DETECTED,
    construct_scores,
    resolve_types,
)
from src.survey_gen.synthetic import NoiseProfile, generate_responses
from src.survey_gen.templates import TEMPLATES, build_template, list_templates
from src.survey_gen.validator import errors, validate_survey

RECOMMEND_CODE = "recommend_intent"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def survey():
    return build_template("service_satisfaction")


@pytest.fixture(scope="module")
def responses(survey):
    frame, truth = generate_responses(survey, n_respondents=200, seed=42)
    return frame, truth


# ---- the chain, step by step -------------------------------------------------


def test_templates_are_available_without_any_api_key():
    """The zero-configuration path. A reader who just cloned the repo has no
    key, and must still get a complete questionnaire."""
    catalogue = list_templates()
    assert len(catalogue) == len(TEMPLATES) >= 3
    for entry in catalogue:
        assert entry["name"]["zh-CN"] and entry["name"]["en"]


@pytest.mark.parametrize("spec", TEMPLATES, ids=lambda s: s.key)
def test_every_template_passes_the_validator_with_zero_errors(spec):
    survey = spec.build()
    found = errors(validate_survey(survey))
    assert found == [], [(i.rule_id, i.target_id, i.evidence) for i in found]


def test_the_recommendation_item_is_a_real_zero_based_scale(survey):
    """Kept in the library deliberately.

    The detector cannot recognise this shape, which is a reason to carry the
    schema, not a reason to drop the item from the templates.
    """
    question = next(q for q in survey.all_questions() if q.code == RECOMMEND_CODE)
    assert question.question_type == QUESTION_TYPE_SCALE
    assert question.scale_spec.min_value == 0
    assert question.scale_spec.points == 11
    assert question.scale_spec.max_value == 10


def test_export_produces_every_artifact(survey):
    files = export_all(survey)
    assert len(files) == len(EXPORT_FORMATS)
    names = sorted(files)
    assert any(name.endswith("_template.csv") for name in names)
    assert any(name.endswith("_sample.csv") for name in names)
    assert any(name.endswith("_schema.json") for name in names)
    assert any(name.endswith(".zh-CN.md") for name in names)
    assert any("codebook" in name for name in names)
    for name, content in files.items():
        assert content.strip(), name


def test_the_empty_template_has_the_codes_as_its_header(survey):
    files = export_all(survey)
    template = next(v for k, v in files.items() if k.endswith("_template.csv"))
    header = pd.read_csv(io.StringIO(template)).columns.tolist()
    assert header == [q.code for q in survey.all_questions()]
    assert RECOMMEND_CODE in header


def test_the_codebook_tells_the_analyst_to_keep_the_schema(survey):
    files = export_all(survey)
    codebook = next(v for k, v in files.items() if "codebook" in k)
    assert "schema.json" in codebook
    assert RECOMMEND_CODE in codebook
    assert "0-10" in codebook


def test_synthetic_responses_carry_ground_truth_from_the_schema(survey, responses):
    frame, truth = responses
    assert len(frame) == 200
    assert set(truth) == {q.code for q in survey.all_questions()}
    assert truth[RECOMMEND_CODE] == QUESTION_TYPE_SCALE
    values = pd.to_numeric(frame[RECOMMEND_CODE])
    assert values.min() >= 0 and values.max() <= 10


# ---- (a) detection only ------------------------------------------------------


def test_path_a_upload_and_detect_without_a_schema(client, survey, responses):
    """The whole chain end to end, through the real API."""
    frame, truth = responses
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    upload = client.post(
        "/api/upload", files={"file": ("responses.csv", buffer.getvalue(), "text/csv")}
    )
    assert upload.status_code == 200
    session_id = upload.json()["session_id"]

    detected = {
        item["column"]: item["type"]
        for item in client.get("/api/%s/detect" % session_id).json()["types"]
    }

    # Every 1-5 item in the survey is recognised without help.
    five_point = [
        q.code for q in survey.all_questions()
        if q.scale_spec is not None and q.scale_spec.min_value == 1
    ]
    assert five_point
    for code in five_point:
        assert detected[code] == QUESTION_TYPE_SCALE, code

    # The 0-10 item is not, and the API says so plainly rather than guessing.
    assert detected[RECOMMEND_CODE] == QUESTION_TYPE_NUMERIC
    basis = next(
        item["basis"] for item in client.get("/api/%s/detect" % session_id).json()["types"]
        if item["column"] == RECOMMEND_CODE
    )
    assert basis == {"level": "low", "code": "scale_candidate"}

    # Ground truth agrees with detection everywhere except that one column.
    disagreements = {
        code for code, declared in truth.items()
        if code in detected and detected[code] != declared
    }
    assert disagreements == {RECOMMEND_CODE}


def test_path_a_sample_csv_can_be_uploaded_immediately(client, survey):
    """The three-row export exists so this works; a header-only file cannot."""
    sample = export_sample_csv(survey)
    upload = client.post(
        "/api/upload", files={"file": ("sample.csv", sample, "text/csv")}
    )
    assert upload.status_code == 200

    files = export_all(survey)
    template = next(v for k, v in files.items() if k.endswith("_template.csv"))
    rejected = client.post(
        "/api/upload", files={"file": ("template.csv", template, "text/csv")}
    )
    assert rejected.status_code == 400


# ---- (b) schema present ------------------------------------------------------


def test_path_b_the_schema_resolves_what_detection_cannot(survey, responses):
    frame, truth = responses

    without = resolve_types(frame, survey=None)
    assert without[RECOMMEND_CODE]["type"] == QUESTION_TYPE_NUMERIC
    assert without[RECOMMEND_CODE]["resolution"] == RESOLUTION_DETECTED

    with_schema = resolve_types(frame, survey=survey)
    assert with_schema[RECOMMEND_CODE]["type"] == QUESTION_TYPE_SCALE
    assert with_schema[RECOMMEND_CODE]["resolution"] == RESOLUTION_DECLARED

    # With the schema, every column matches its ground truth. Without it, one
    # does not. That difference is the product argument, measured.
    assert all(with_schema[code]["type"] == declared for code, declared in truth.items())


def test_path_b_construct_scores_become_computable(survey, responses):
    frame, _ = responses
    scores = construct_scores(frame, survey)
    assert set(scores) == {"c_service", "c_value"}
    for construct_id, series in scores.items():
        assert len(series) == len(frame)
        assert series.between(1, 5).all(), construct_id


def test_path_b_reverse_keyed_items_are_flipped_using_the_declaration(survey, responses):
    """Which items are reverse-keyed is not recoverable from the CSV.

    srv_wait is worded negatively, so its raw values run against the rest of its
    construct. Recoding it is possible only because the schema says to.

    The item is compared against the other three directly rather than against
    the construct score. The construct score contains those same three items, so
    correlating the two would be high whatever the recoding did — an earlier
    version of this test made that mistake and was measuring component overlap.
    """
    frame, _ = responses
    spec = survey.question_by_id("Q05").scale_spec
    raw = pd.to_numeric(frame["srv_wait"])
    others = pd.DataFrame(
        {code: pd.to_numeric(frame[code]) for code in ("srv_response", "srv_resolve", "srv_respect")}
    ).mean(axis=1)

    # Raw, the item runs backwards against its own construct.
    assert raw.corr(others) < -0.3

    # Recoded from the declaration, it runs with it. Same magnitude, flipped.
    recoded = spec.min_value + spec.max_value - raw
    assert recoded.corr(others) > 0.3
    assert recoded.corr(others) == pytest.approx(-raw.corr(others), abs=1e-9)


def test_synthetic_construct_items_actually_share_a_factor(survey, responses):
    """Guards the generator, not the pipeline.

    Items in one construct have to correlate, or the data is independent columns
    wearing a construct label and every reliability number computed from it is
    meaningless. An earlier version of the generator documented a latent factor
    it did not implement, which produced an alpha near zero.
    """
    frame, _ = responses
    for construct_id in ("c_service", "c_value"):
        codes = [
            question.code
            for question in survey.questions_for_construct(construct_id)
            if question.question_type == QUESTION_TYPE_SCALE and not question.reverse_coded
        ]
        block = pd.DataFrame({code: pd.to_numeric(frame[code]) for code in codes})
        correlations = block.corr().values
        off_diagonal = [
            correlations[i][j]
            for i in range(len(codes))
            for j in range(len(codes))
            if i != j
        ]
        assert min(off_diagonal) > 0.15, (construct_id, off_diagonal)


def test_path_b_records_the_capability_gap_rather_than_hiding_it(survey, responses):
    """One assertion naming the difference, so a regression in either direction
    is visible: detection loses exactly the zero-based column, and the schema
    recovers exactly it."""
    frame, truth = responses
    detected = detect_question_types(frame)
    detection_misses = {
        code for code, declared in truth.items() if detected.get(code) != declared
    }
    schema_resolved = resolve_types(frame, survey=survey)
    schema_misses = {
        code for code, declared in truth.items() if schema_resolved[code]["type"] != declared
    }
    assert detection_misses == {RECOMMEND_CODE}
    assert schema_misses == set()


# ---- noise ------------------------------------------------------------------


def test_metadata_columns_from_a_platform_export_survive_upload(client, survey):
    """English timestamp and IP columns are a known gap, characterised here so
    the round trip does not quietly depend on them being absent."""
    frame, _ = generate_responses(
        survey, n_respondents=60, noise=NoiseProfile(add_metadata_columns=True), seed=3
    )
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    upload = client.post(
        "/api/upload", files={"file": ("messy.csv", buffer.getvalue(), "text/csv")}
    )
    assert upload.status_code == 200
    detected = {
        item["column"]: item["type"]
        for item in client.get("/api/%s/detect" % upload.json()["session_id"]).json()["types"]
    }
    assert "submit_time" in detected
    assert resolve_types(frame, survey=survey)["submit_time"]["resolution"] == RESOLUTION_DETECTED


def test_scale_values_exported_as_text_still_resolve(survey):
    """Some platforms write "5分" instead of 5."""
    frame, _ = generate_responses(
        survey, n_respondents=60, noise=NoiseProfile(scale_as_text=True), seed=5
    )
    assert frame["srv_response"].iloc[0].endswith("分")
    scores = construct_scores(frame, survey)
    assert scores["c_service"].between(1, 5).all()
