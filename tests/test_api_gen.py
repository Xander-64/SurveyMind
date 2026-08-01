"""Generation endpoints.

The contract is fixed here, before the LLM author exists, on purpose: when that
lands it has to satisfy these shapes rather than the shapes being guessed around
whatever it happens to return.

Until then generation means "build a bundled template", and the API says so in
`generation_mode` rather than implying a model wrote it. A test below pins that,
because an interface that quietly suggests AI involvement where there is none is
the kind of thing that survives right up until someone asks.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import DRAFT_MAX_AGE_SECONDS, SESSION_MAX_AGE_SECONDS, app
from src.survey_gen.templates import TEMPLATES


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def draft(client):
    response = client.post(
        "/api/gen/drafts", json={"template": "service_satisfaction", "language": "zh-CN"}
    )
    assert response.status_code == 200
    return response.json()


# ---- catalogue ---------------------------------------------------------------


def test_templates_are_listed_without_a_key(client):
    body = client.get("/api/gen/templates").json()
    keys = {entry["key"] for entry in body["templates"]}
    assert keys == {spec.key for spec in TEMPLATES}
    for entry in body["templates"]:
        assert entry["name"]["zh-CN"] and entry["name"]["en"]


# ---- creating a draft --------------------------------------------------------


def test_a_draft_carries_survey_validation_and_plan_together(draft):
    """One response, three things. They are pure and cheap, and the builder
    screen shows all of them at once."""
    assert draft["draft_id"]
    assert draft["survey"]["sections"]
    assert draft["validation"]["counts"]["error"] == 0
    assert draft["analysis_plan"]["analyses"]


def test_the_response_says_no_model_was_involved(draft):
    """The LLM author is a later batch. Until then this must not read as AI
    output — the interface shows what this field says."""
    assert draft["generation_mode"] == "template"
    assert draft["generation"]["llm_used"] is False
    assert "no language model" in draft["generation"]["note"].lower()


def test_a_template_key_is_required_and_checked(client):
    assert client.post("/api/gen/drafts", json={}).status_code == 400
    assert client.post("/api/gen/drafts", json={"template": "nope"}).status_code == 400


@pytest.mark.parametrize("spec", TEMPLATES, ids=lambda s: s.key)
def test_every_template_creates_a_draft_with_no_errors(client, spec):
    body = client.post("/api/gen/drafts", json={"template": spec.key}).json()
    assert body["validation"]["counts"]["error"] == 0, [
        issue["rule_id"] for issue in body["validation"]["issues"]
        if issue["severity"] == "error"
    ]


# ---- reading, editing --------------------------------------------------------


def test_a_draft_can_be_read_back(client, draft):
    fetched = client.get("/api/gen/%s" % draft["draft_id"]).json()
    assert fetched["survey"] == draft["survey"]
    assert fetched["generation_mode"] == "template"


def test_a_missing_draft_is_404_not_500(client):
    response = client.get("/api/gen/deadbeef")
    assert response.status_code == 404
    assert "expired" in response.json()["detail"].lower()


def test_editing_revalidates_and_the_errors_come_back(client):
    """Break something on purpose: the response has to report it, not accept it."""
    created = client.post("/api/gen/drafts", json={"template": "course_evaluation"}).json()
    survey = created["survey"]
    # Two questions sharing a column code: codes become CSV headers.
    survey["sections"][1]["questions"][1]["code"] = survey["sections"][1]["questions"][0]["code"]

    updated = client.put(
        "/api/gen/%s" % created["draft_id"], json={"survey": survey}
    ).json()
    assert updated["validation"]["counts"]["error"] >= 1
    assert "code_uniqueness" in {
        issue["rule_id"] for issue in updated["validation"]["issues"]
    }

    # and the edit persisted
    assert client.get("/api/gen/%s" % created["draft_id"]).json()[
        "validation"]["counts"]["error"] >= 1


def test_a_malformed_edit_is_rejected(client, draft):
    assert client.put("/api/gen/%s" % draft["draft_id"], json={}).status_code == 400
    assert client.put(
        "/api/gen/%s" % draft["draft_id"], json={"survey": {"nonsense": True}}
    ).status_code == 400


# ---- validate and plan on their own ------------------------------------------


def test_validate_endpoint_matches_the_draft_payload(client, draft):
    standalone = client.post("/api/gen/%s/validate" % draft["draft_id"]).json()
    assert standalone["counts"] == draft["validation"]["counts"]


def test_analysis_plan_reports_the_exact_sample_sizes(client, draft):
    plan = client.get("/api/gen/%s/analysis-plan" % draft["draft_id"]).json()
    assert plan["sample_size_basis"]["two_group"]["min_n_per_group"] == 64
    assert plan["sample_size_basis"]["two_group"]["closed_form_n"] == 63
    assert plan["defaults"]["power"] == 0.80


# ---- exports -----------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt,check",
    [
        ("template_csv", lambda t: "\n" in t and "recommend_intent" in t),
        ("sample_csv", lambda t: len(t.strip().split("\n")) == 4),
        ("schema_json", lambda t: json.loads(t)["schema_version"] >= 1),
        ("questionnaire_md", lambda t: t.startswith("#")),
        ("codebook_md", lambda t: "schema.json" in t),
    ],
)
def test_every_export_format_returns_its_artifact(client, draft, fmt, check):
    response = client.get("/api/gen/%s/export?format=%s" % (draft["draft_id"], fmt))
    assert response.status_code == 200
    assert check(response.text), fmt


def test_exports_are_plain_files_not_json_envelopes(client, draft):
    """Each of these is saved to disk by the user; wrapping them in JSON would
    make the browser download an envelope."""
    response = client.get("/api/gen/%s/export?format=template_csv" % draft["draft_id"])
    assert response.headers["content-type"].startswith("text/csv")


def test_download_sets_a_filename(client, draft):
    response = client.get(
        "/api/gen/%s/export?format=codebook_md&download=true" % draft["draft_id"]
    )
    assert "attachment" in response.headers["content-disposition"]
    assert "codebook" in response.headers["content-disposition"]


def test_export_language_switches_the_document(client, draft):
    zh = client.get(
        "/api/gen/%s/export?format=questionnaire_md&language=zh-CN" % draft["draft_id"]
    ).text
    en = client.get(
        "/api/gen/%s/export?format=questionnaire_md&language=en" % draft["draft_id"]
    ).text
    assert zh != en
    assert "题型" in zh or "量表题" in zh
    assert "Scale" in en


def test_an_unknown_export_format_is_rejected(client, draft):
    assert client.get(
        "/api/gen/%s/export?format=pdf" % draft["draft_id"]
    ).status_code == 400


# ---- storage lifetime --------------------------------------------------------


def test_drafts_outlive_upload_sessions():
    """A draft is edited over a sitting; an upload is consumed in one go.

    Nothing persists past the day. A draft worth keeping is downloaded as
    schema.json, which is the whole persistence story for a tool with no
    database and no accounts.
    """
    assert DRAFT_MAX_AGE_SECONDS == 24 * 60 * 60
    assert DRAFT_MAX_AGE_SECONDS > SESSION_MAX_AGE_SECONDS
