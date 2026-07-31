"""API tests for the general-data-platform endpoints (batch 1).

Covers /mode, /semantics, /general-overview, the mode-aware /report and
/ai-report extensions, and the storage change behind them: sessions now keep
metadata (ID/timestamp) columns on disk while every legacy endpoint still
sees the strict survey view (metadata columns dropped at read time).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import backend.main as api
from src.ai_report import AI_STATUS_OK
from src.i18n import t

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "SESSIONS_DIR", tmp_path / "sessions")
    api._session_cache.clear()
    api._cancel_session_expiry_handles()
    with TestClient(api.app) as test_client:
        yield test_client


def _upload(client, filename: str) -> dict:
    csv_bytes = (DATA_DIR / filename).read_bytes()
    resp = client.post("/api/upload", files={"file": (filename, csv_bytes, "text/csv")})
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- dataset mode -------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected_mode"),
    [
        ("sample_general.csv", "general"),
        ("sample_survey.csv", "survey"),
        ("sample_mixed.csv", "mixed"),
    ],
)
def test_upload_reports_detected_mode(client, filename, expected_mode):
    assert _upload(client, filename)["mode"] == expected_mode


def test_demo_reports_mode(client):
    assert client.post("/api/demo").json()["mode"] == "survey"


def test_mode_detection_payload(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    data = client.get(f"/api/{sid}/mode").json()
    assert data["active"] == "general"
    detected = data["detected"]
    assert detected["mode"] == "general"
    assert detected["general_score"] > detected["survey_score"]
    assert detected["signals"], "mode detection should expose its evidence"
    json.dumps(data)


def test_mode_override_persists_and_validates(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    resp = client.put(f"/api/{sid}/mode", json={"mode": "mixed"})
    assert resp.status_code == 200 and resp.json()["active"] == "mixed"

    # the override persists while the detection baseline stays untouched
    data = client.get(f"/api/{sid}/mode").json()
    assert data["active"] == "mixed" and data["detected"]["mode"] == "general"

    assert client.put(f"/api/{sid}/mode", json={"mode": "banana"}).status_code == 400


# --- field semantics ----------------------------------------------------------


def test_semantics_roles_and_payload(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    data = client.get(f"/api/{sid}/semantics").json()
    roles = {field["column"]: field["role"] for field in data["fields"]}
    assert roles["order_id"] == "identifier"
    assert roles["order_date"] == "datetime"
    assert roles["total_amount"] == "numeric_metric"
    assert roles["region"] == "categorical_dimension"
    assert len(data["role_options"]) == 8

    first = data["fields"][0]
    assert {"column", "role", "confidence", "evidence", "non_null", "unique", "missing_pct"} <= set(first)
    json.dumps(data)


def test_semantics_override_and_reset(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    resp = client.put(
        f"/api/{sid}/semantics", json={"column": "customer_age", "role": "categorical_dimension"}
    )
    assert resp.status_code == 200, resp.text
    overridden = {field["column"]: field for field in resp.json()["fields"]}["customer_age"]
    assert overridden["role"] == "categorical_dimension"
    assert overridden["confidence"] == 1.0
    assert overridden["evidence"] == ["manual override"]

    restored = {field["column"]: field for field in client.delete(f"/api/{sid}/semantics").json()["fields"]}
    assert restored["customer_age"]["role"] == "numeric_metric"

    assert client.put(f"/api/{sid}/semantics", json={"column": "nope", "role": "numeric_metric"}).status_code == 400
    assert client.put(f"/api/{sid}/semantics", json={"column": "region", "role": "banana"}).status_code == 400


def test_role_override_flows_into_overview(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    client.put(f"/api/{sid}/semantics", json={"column": "customer_age", "role": "categorical_dimension"})
    data = client.get(f"/api/{sid}/general-overview").json()
    assert "customer_age" not in {row["column"] for row in data["numeric_summary"]}


# --- general overview ---------------------------------------------------------


def test_general_overview_payload(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    data = client.get(f"/api/{sid}/general-overview").json()

    assert data["rows"] > 0 and data["columns"] == 9  # the full df keeps order_id
    assert data["id_candidates"] == ["order_id"]
    assert [entry["column_name"] for entry in data["datetime_summary"]] == ["order_date"]
    assert "order_date" in data["time_trends"] and len(data["time_trends"]["order_date"]) >= 2

    numeric_columns = {row["column"] for row in data["numeric_summary"]}
    assert "total_amount" in numeric_columns and "order_id" not in numeric_columns

    assert data["findings"]["zh"] and data["findings"]["en"]
    assert data["findings"]["zh"] != data["findings"]["en"]
    assert 3 <= len(data["suggestions"]["zh"]) <= 5
    assert 3 <= len(data["suggestions"]["en"]) <= 5

    kinds = {spec["kind"] for spec in data["chart_specs"]}
    assert "time_trend" in kinds
    assert data["numeric_histograms"]
    first_hist = next(iter(data["numeric_histograms"].values()))
    assert len(first_hist["counts"]) == 8

    json.dumps(data)


def test_general_overview_no_survey_vocabulary(client):
    # 批 2 验收线索的后端前提：通用数据的响应里不出现题型词汇。
    sid = _upload(client, "sample_general.csv")["session_id"]
    body = json.dumps(client.get(f"/api/{sid}/general-overview").json(), ensure_ascii=False)
    for survey_term in ("单选题", "多选题", "量表题", "开放题"):
        assert survey_term not in body


# --- soft storage vs the strict survey view -----------------------------------


def test_survey_view_matches_strict_cleaning(client):
    from pandas.testing import assert_frame_equal

    from src.data_loader import load_uploaded_dataset
    from src.preprocessing import preprocess_input_dataframe

    csv_bytes = (DATA_DIR / "sample_general.csv").read_bytes()
    expected = preprocess_input_dataframe(load_uploaded_dataset(csv_bytes, "sample_general.csv"))

    sid = _upload(client, "sample_general.csv")["session_id"]
    survey_df, meta = api._load_session(sid)
    assert meta["metadata_columns"] == ["order_id"]
    assert_frame_equal(survey_df.reset_index(drop=True), expected.reset_index(drop=True))

    full_df, _ = api._load_session_full(sid)
    assert "order_id" in full_df.columns


def test_metadata_columns_hidden_from_legacy_endpoints(client):
    sid = _upload(client, "sample_general.csv")["session_id"]

    overview = client.get(f"/api/{sid}/overview").json()
    assert "order_id" not in {entry["column_name"] for entry in overview["column_meta"]}
    assert all("order_id" not in row for row in overview["preview"])

    detect = client.get(f"/api/{sid}/detect").json()
    assert "order_id" not in {entry["column"] for entry in detect["types"]}

    # metadata columns are invisible to the legacy override endpoint too
    assert client.post(f"/api/{sid}/types", json={"column": "order_id", "type": "num"}).status_code == 400


def test_upload_with_only_metadata_columns_still_400(client):
    csv_bytes = "UserID,提交时间\n1,2026-01-01\n2,2026-01-02\n".encode("utf-8")
    resp = client.post("/api/upload", files={"file": ("meta_only.csv", csv_bytes, "text/csv")})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "No usable survey columns remain after preprocessing."


def test_upload_columns_count_keeps_survey_view(client):
    data = _upload(client, "sample_general.csv")
    assert data["columns"] == 8  # 9 stored columns minus order_id


def test_new_endpoints_backfill_pre_upgrade_sessions(client):
    sid = _upload(client, "sample_survey.csv")["session_id"]

    # simulate a session written by the previous deployment: platform keys absent
    meta_path = api.SESSIONS_DIR / sid / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in ("metadata_columns", "dataset_mode", "mode_detection", "field_roles", "detected_roles"):
        meta.pop(key, None)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    api._session_cache.clear()

    data = client.get(f"/api/{sid}/mode").json()
    assert data["active"] == data["detected"]["mode"] == "survey"
    assert client.get(f"/api/{sid}/semantics").status_code == 200
    assert client.get(f"/api/{sid}/general-overview").status_code == 200


# --- mode-aware reports ---------------------------------------------------------


def test_report_mode_general_structure(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    md = client.get(f"/api/{sid}/report", params={"mode": "general", "language": "zh-CN"}).json()["markdown"]
    assert md.startswith(f"# {t('zh-CN', 'report_title_general')}")
    for section_key in (
        "report_dataset_overview",
        "report_fields_distribution",
        "report_data_quality",
        "report_variable_relations",
        "report_key_findings",
        "report_next_steps",
        "report_analysis_limitations",
    ):
        assert f"## {t('zh-CN', section_key)}" in md

    assert client.get(f"/api/{sid}/report", params={"mode": "banana"}).status_code == 400


def test_report_mode_survey_equals_default(client):
    sid = _upload(client, "sample_survey.csv")["session_id"]
    default = client.get(f"/api/{sid}/report", params={"language": "zh-CN"}).json()["markdown"]
    explicit = client.get(f"/api/{sid}/report", params={"mode": "survey", "language": "zh-CN"}).json()["markdown"]
    assert explicit == default


def test_report_mode_mixed_structure(client):
    sid = _upload(client, "sample_mixed.csv")["session_id"]
    md = client.get(f"/api/{sid}/report", params={"mode": "mixed", "language": "zh-CN"}).json()["markdown"]
    assert md.startswith(f"# {t('zh-CN', 'report_title_mixed')}")
    assert f"## {t('zh-CN', 'report_fields_distribution')}" in md  # general half
    assert f"## {t('zh-CN', 'question_type_summary_title')}" in md  # survey half

    dl = client.get(f"/api/{sid}/report", params={"mode": "mixed", "download": "true"})
    assert dl.headers["content-disposition"].startswith("attachment")


# --- mode-aware AI report -------------------------------------------------------


def test_ai_report_without_body_stays_legacy(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sid = _upload(client, "sample_general.csv")["session_id"]
    assert client.post(f"/api/{sid}/ai-report").json() == {"ok": False, "reason": "not_configured"}


def test_ai_report_mode_not_configured(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sid = _upload(client, "sample_general.csv")["session_id"]
    data = client.post(f"/api/{sid}/ai-report", json={"mode": "general"}).json()
    assert data == {"ok": False, "reason": "not_configured"}


def test_ai_report_mode_mocked_success(client, monkeypatch):
    captured = {}

    def fake_generate(df, mode, language, overview, descriptive_results=None, question_types=None):
        captured["mode"], captured["language"] = mode, language
        return {"status": AI_STATUS_OK, "content": "# AI general report"}

    monkeypatch.setattr(api, "generate_ai_report", fake_generate)
    sid = _upload(client, "sample_general.csv")["session_id"]
    data = client.post(f"/api/{sid}/ai-report", json={"mode": "general", "language": "en"}).json()
    assert data == {"ok": True, "mode": "general", "markdown": "# AI general report"}
    assert captured == {"mode": "general", "language": "en"}


def test_ai_report_mode_llm_failure_degrades(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    monkeypatch.setattr("src.ai_report.call_llm", lambda *args, **kwargs: None)
    sid = _upload(client, "sample_mixed.csv")["session_id"]
    data = client.post(f"/api/{sid}/ai-report", json={"mode": "mixed"}).json()
    assert data == {"ok": False, "reason": "api_error"}
    assert "test-key-not-real" not in json.dumps(data)


def test_ai_report_mode_invalid_400(client):
    sid = _upload(client, "sample_general.csv")["session_id"]
    assert client.post(f"/api/{sid}/ai-report", json={"mode": "banana"}).status_code == 400


def test_detect_marks_zero_based_scale_candidates_without_changing_types(client):
    """The hint is advisory: the column stays a numeric question.

    A 0-10 rating and a 0-10 count are identical in their values, so the API
    surfaces the ambiguity rather than resolving it. Accepting the hint goes
    through the same POST /types override a user would use by hand.
    """
    csv = "nps_score,purchase_count,satisfaction\n" + "\n".join(
        "%d,%d,%d" % (i % 11, i % 11, (i % 5) + 1) for i in range(60)
    )
    session_id = client.post(
        "/api/upload", files={"file": ("scales.csv", csv, "text/csv")}
    ).json()["session_id"]

    by_column = {item["column"]: item for item in client.get(f"/api/{session_id}/detect").json()["types"]}

    # 0-10 rating: not claimed as a scale, but flagged for the user
    assert by_column["nps_score"]["short"] == "num"
    assert by_column["nps_score"]["scale_candidate"] is True

    # identical values, but the name says count — no hint, no noise
    assert by_column["purchase_count"]["short"] == "num"
    assert by_column["purchase_count"]["scale_candidate"] is False

    # already a scale: nothing to offer
    assert by_column["satisfaction"]["short"] == "scale"
    assert by_column["satisfaction"]["scale_candidate"] is False

    # accepting the hint uses the existing override endpoint
    accepted = client.post(
        f"/api/{session_id}/types", json={"column": "nps_score", "type": "scale"}
    ).json()
    accepted_by_column = {item["column"]: item for item in accepted["types"]}
    assert accepted_by_column["nps_score"]["short"] == "scale"
    assert accepted_by_column["nps_score"]["scale_candidate"] is False
