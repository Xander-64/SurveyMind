"""API tests: every endpoint is a thin wrapper over src/, so these focus on
wiring, serialization safety (NaN -> null), and session lifecycle."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import backend.main as api

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "SESSIONS_DIR", tmp_path / "sessions")
    api._session_cache.clear()
    api._cancel_session_expiry_handles()
    with TestClient(api.app) as test_client:
        yield test_client


def _upload_demo(client) -> str:
    csv_bytes = (DATA_DIR / "sample_survey.csv").read_bytes()
    resp = client.post("/api/upload", files={"file": ("sample_survey.csv", csv_bytes, "text/csv")})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


def test_upload_returns_session(client):
    session_id = _upload_demo(client)
    assert len(session_id) == 32


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_cors_allows_local_frontend_and_rejects_unknown_origin(client):
    allowed = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5500"

    rejected = client.options(
        "/health",
        headers={
            "Origin": "https://not-allowed.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_expired_session_is_deleted_on_access(client):
    sid = _upload_demo(client)
    _, meta = api._session_cache[sid]
    meta["created_at"] = time.time() - api.SESSION_MAX_AGE_SECONDS - 1
    api._write_meta(sid, meta)

    response = client.get(f"/api/{sid}/overview")

    assert response.status_code == 404
    assert sid not in api._session_cache
    assert not (api.SESSIONS_DIR / sid).exists()


def test_cleanup_loop_runs_without_new_upload(monkeypatch):
    calls = 0

    def record_cleanup(*, now=None):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(api, "_cleanup_old_sessions", record_cleanup)
    monkeypatch.setattr(api, "SESSION_CLEANUP_INTERVAL_SECONDS", 0.005)

    async def exercise_loop():
        task = asyncio.create_task(api._session_cleanup_loop())
        await asyncio.sleep(0.025)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise_loop())
    assert calls >= 2


def test_upload_empty_file_400(client):
    resp = client.post("/api/upload", files={"file": ("x.csv", b"", "text/csv")})
    assert resp.status_code == 400


def test_unknown_session_404(client):
    assert client.get("/api/nope/overview").status_code == 404


def test_overview_shape(client):
    sid = _upload_demo(client)
    data = client.get(f"/api/{sid}/overview").json()
    assert data["rows"] > 0 and data["columns"] > 0
    assert data["question_count"] > 0
    assert isinstance(data["column_meta"], list) and isinstance(data["preview"], list)
    # JSON must round-trip (no NaN leaked through serialization)
    json.dumps(data)


def test_detect_types_and_counts(client):
    sid = _upload_demo(client)
    data = client.get(f"/api/{sid}/detect").json()
    columns = {t["column"]: t["short"] for t in data["types"]}
    assert columns["satisfaction_score"] == "scale"
    assert columns["preferred_activities"] == "multi"
    assert columns["fitness_frequency"] == "single"
    assert columns["open_feedback"] == "open"
    assert sum(data["counts"].values()) == len(data["types"])


def test_stats_sections(client):
    sid = _upload_demo(client)
    data = client.get(f"/api/{sid}/stats").json()
    assert data["scale_summary"], "demo data has a scale question"
    assert data["frequency_tables"], "demo data has categorical questions"
    assert data["open_text"], "demo data has an open-ended question"
    first_open = next(iter(data["open_text"].values()))
    assert first_open["total"] >= len(first_open["answers"]) > 0
    assert data["numeric_histograms"], "demo data has numeric questions"
    first_hist = next(iter(data["numeric_histograms"].values()))
    assert len(first_hist["counts"]) == 8 and first_hist["min"] < first_hist["max"]
    json.dumps(data)


def test_demo_session_endpoint(client):
    resp = client.post("/api/demo")
    assert resp.status_code == 200, resp.text
    sid = resp.json()["session_id"]
    assert resp.json()["rows"] > 0
    assert client.get(f"/api/{sid}/overview").status_code == 200


def test_override_and_reset_types(client):
    sid = _upload_demo(client)
    resp = client.post(f"/api/{sid}/types", json={"column": "open_feedback", "type": "single"})
    assert resp.status_code == 200, resp.text
    types = {t["column"]: t["short"] for t in resp.json()["types"]}
    assert types["open_feedback"] == "single"

    # downstream stats must follow the corrected type
    stats = client.get(f"/api/{sid}/stats").json()
    assert "open_feedback" in stats["frequency_tables"]
    assert "open_feedback" not in stats["open_text"]

    # reset restores the original detection
    resp = client.delete(f"/api/{sid}/types")
    types = {t["column"]: t["short"] for t in resp.json()["types"]}
    assert types["open_feedback"] == "open"
    stats = client.get(f"/api/{sid}/stats").json()
    assert "open_feedback" in stats["open_text"]


def test_override_bad_input_400(client):
    sid = _upload_demo(client)
    assert client.post(f"/api/{sid}/types", json={"column": "nope", "type": "single"}).status_code == 400
    assert client.post(f"/api/{sid}/types", json={"column": "gender", "type": "banana"}).status_code == 400


def test_ai_report_not_configured(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    sid = _upload_demo(client)
    data = client.post(f"/api/{sid}/ai-report").json()
    assert data == {"ok": False, "reason": "not_configured"}


def test_ai_report_mocked_success(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    monkeypatch.setattr(api, "ask_llm", lambda prompt: "# AI 问卷分析报告\n\n测试解读内容")
    sid = _upload_demo(client)
    data = client.post(f"/api/{sid}/ai-report").json()
    assert data["ok"] is True
    assert data["markdown"].startswith("# AI 问卷分析报告")


def test_ai_report_api_error_hides_key(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")

    def boom(prompt):
        raise RuntimeError("upstream returned 500")

    monkeypatch.setattr(api, "ask_llm", boom)
    sid = _upload_demo(client)
    data = client.post(f"/api/{sid}/ai-report").json()
    assert data["ok"] is False and data["reason"] == "api_error"
    assert "test-key-not-real" not in json.dumps(data)


def test_cross_numeric_by_group(client):
    sid = _upload_demo(client)
    resp = client.post(
        f"/api/{sid}/cross",
        json={"group_col": "gender", "target_col": "satisfaction_score", "language": "zh-CN"},
    )
    data = resp.json()
    assert data["analysis_type"] == "numeric_by_group"
    assert data["summary_table"] and "interpretation" in data


def test_cross_categorical(client):
    sid = _upload_demo(client)
    resp = client.post(
        f"/api/{sid}/cross",
        json={"group_col": "gender", "target_col": "fitness_goal", "language": "zh-CN"},
    )
    data = resp.json()
    assert data["analysis_type"] == "categorical_crosstab"
    assert len(data["rows"]) == len(data["counts"])
    assert len(data["cols"]) == len(data["counts"][0])


def test_cross_bad_column_400(client):
    sid = _upload_demo(client)
    resp = client.post(f"/api/{sid}/cross", json={"group_col": "nope", "target_col": "gender"})
    assert resp.status_code == 400


def test_report_markdown(client):
    sid = _upload_demo(client)
    data = client.get(f"/api/{sid}/report", params={"language": "zh-CN"}).json()
    assert data["markdown"].startswith("#")
    dl = client.get(f"/api/{sid}/report", params={"download": "true"})
    assert dl.headers["content-disposition"].startswith("attachment")


def test_messy_dataset_serializes(client):
    csv_bytes = (DATA_DIR / "test_messy_real_world.csv").read_bytes()
    resp = client.post("/api/upload", files={"file": ("messy.csv", csv_bytes, "text/csv")})
    assert resp.status_code == 200, resp.text
    sid = resp.json()["session_id"]
    for path in ("overview", "detect", "stats"):
        r = client.get(f"/api/{sid}/{path}")
        assert r.status_code == 200
        json.dumps(r.json())


def test_api_cleaning_matches_streamlit_pipeline(client):
    # The API's upload pipeline must equal src loading + shared preprocessing.
    from pandas.testing import assert_frame_equal
    from src.data_loader import load_uploaded_dataset
    from src.preprocessing import preprocess_input_dataframe

    csv_bytes = (DATA_DIR / "sample_survey.csv").read_bytes()
    expected = preprocess_input_dataframe(load_uploaded_dataset(csv_bytes, "sample_survey.csv"))

    sid = _upload_demo(client)
    stored, _ = api._load_session(sid)
    assert_frame_equal(stored.reset_index(drop=True), expected.reset_index(drop=True))
