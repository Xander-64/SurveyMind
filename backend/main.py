"""SurveyMind REST API — a thin FastAPI layer over the existing src/ modules.

Every endpoint follows the same pattern: load the session's DataFrame, call one
existing analysis function from src/, serialize the result to JSON. No analysis
logic lives here.

Run from the project root:
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

# Load .env so LLM_API_KEY etc. are available (optional convenience dependency).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src.cross_analysis import analyze_cross_relationship
from src.data_loader import get_dataset_overview, load_uploaded_dataset
from src.descriptive_analysis import generate_descriptive_results
from src.i18n import translate_question_type
from src.llm_client import LLMNotConfiguredError, ask_llm, is_llm_configured
from src.preprocessing import preprocess_input_dataframe
from src.question_type_detector import (
    QUESTION_TYPE_EMPTY,
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
    detect_question_types,
)
from src.report_generator import build_dataset_summary, build_llm_prompt, generate_markdown_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = PROJECT_ROOT / "uploads_tmp"
SESSION_MAX_AGE_SECONDS = 24 * 60 * 60

# Short keys the frontend uses for badge classes / the "量表3 · 单选2" counters.
SHORT_TYPE_KEYS = {
    QUESTION_TYPE_NUMERIC: "num",
    QUESTION_TYPE_SCALE: "scale",
    QUESTION_TYPE_SINGLE: "single",
    QUESTION_TYPE_MULTIPLE: "multi",
    QUESTION_TYPE_OPEN: "open",
    QUESTION_TYPE_EMPTY: "empty",
}
FULL_TYPE_BY_SHORT = {short: full for full, short in SHORT_TYPE_KEYS.items()}

app = FastAPI(title="SurveyMind API", version="0.1.0")

# Local development: the static frontend is served from another port (or the
# filesystem), so allow any origin. No credentials are used.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Small in-process cache so repeated requests for one session skip the disk.
_session_cache: dict[str, tuple[pd.DataFrame, dict]] = {}


def _cleanup_old_sessions() -> None:
    if not SESSIONS_DIR.exists():
        return
    cutoff = time.time() - SESSION_MAX_AGE_SECONDS
    for session_dir in SESSIONS_DIR.iterdir():
        if session_dir.is_dir() and session_dir.stat().st_mtime < cutoff:
            shutil.rmtree(session_dir, ignore_errors=True)


def _write_meta(session_id: str, meta: dict) -> None:
    (SESSIONS_DIR / session_id / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


def _save_session(df: pd.DataFrame, filename: str) -> tuple[str, dict]:
    session_id = uuid.uuid4().hex
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    df.to_parquet(session_dir / "data.parquet")
    detected = detect_question_types(df)
    meta = {
        "filename": filename,
        "created_at": time.time(),
        "question_types": detected,
        # kept immutable so manual overrides can be reset to this baseline
        "detected_types": dict(detected),
    }
    _write_meta(session_id, meta)
    _session_cache[session_id] = (df, meta)
    return session_id, meta


def _load_session(session_id: str) -> tuple[pd.DataFrame, dict]:
    if session_id in _session_cache:
        return _session_cache[session_id]

    session_dir = SESSIONS_DIR / session_id
    data_path = session_dir / "data.parquet"
    meta_path = session_dir / "meta.json"
    if not data_path.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Session not found. Please upload the file again.")

    df = pd.read_parquet(data_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    _session_cache[session_id] = (df, meta)
    return df, meta


def df_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of records (NaN -> null, numpy -> native)."""
    return json.loads(df.to_json(orient="records", force_ascii=False))


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    _cleanup_old_sessions()
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        # Identical pipeline to the Streamlit app: tolerant load + shared cleaning.
        df = preprocess_input_dataframe(load_uploaded_dataset(file_bytes, file.filename or ""))
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=400, detail="The file appears to be corrupted or unreadable.")

    session_id, _ = _save_session(df, file.filename or "uploaded")
    return {
        "session_id": session_id,
        "filename": file.filename,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
    }


@app.post("/api/demo")
def demo_session():
    """Create a session from the bundled sample dataset (same pipeline as upload)."""
    demo_path = PROJECT_ROOT / "data" / "sample_survey.csv"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Demo dataset not found.")
    df = preprocess_input_dataframe(load_uploaded_dataset(demo_path.read_bytes(), demo_path.name))
    session_id, _ = _save_session(df, demo_path.name)
    return {
        "session_id": session_id,
        "filename": demo_path.name,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
    }


@app.get("/api/{session_id}/overview")
def overview(session_id: str):
    df, meta = _load_session(session_id)
    ov = get_dataset_overview(df)
    question_types = meta["question_types"]
    return {
        "filename": meta.get("filename"),
        "rows": int(ov["shape"][0]),
        "columns": int(ov["shape"][1]),
        "missing_ratio": round(float(df.isna().mean().mean()), 4),
        "question_count": sum(1 for t in question_types.values() if t != QUESTION_TYPE_EMPTY),
        "column_meta": df_records(ov["overview_table"]),
        "preview": df_records(df.head(10)),
    }


def _detect_payload(meta: dict) -> dict:
    counts: dict[str, int] = {}
    types = []
    for column, q_type in meta["question_types"].items():
        short = SHORT_TYPE_KEYS.get(q_type, "empty")
        counts[short] = counts.get(short, 0) + 1
        types.append(
            {
                "column": column,
                "type": q_type,
                "short": short,
                "type_zh": translate_question_type("zh-CN", q_type),
            }
        )
    return {"types": types, "counts": counts}


@app.get("/api/{session_id}/detect")
def detect(session_id: str):
    _, meta = _load_session(session_id)
    return _detect_payload(meta)


@app.post("/api/{session_id}/types")
def override_type(session_id: str, body: dict):
    """Manually correct one column's question type; stats/cross/report follow."""
    df, meta = _load_session(session_id)
    column = body.get("column")
    short = body.get("type")
    if column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column not found: {column}")
    full_type = FULL_TYPE_BY_SHORT.get(short)
    if full_type is None:
        raise HTTPException(status_code=400, detail=f"Unknown question type: {short}")

    meta["question_types"][column] = full_type
    _write_meta(session_id, meta)
    _session_cache[session_id] = (df, meta)
    return _detect_payload(meta)


@app.delete("/api/{session_id}/types")
def reset_types(session_id: str):
    """Discard manual overrides, restoring the original auto-detected types."""
    df, meta = _load_session(session_id)
    meta["question_types"] = dict(meta.get("detected_types") or meta["question_types"])
    _write_meta(session_id, meta)
    _session_cache[session_id] = (df, meta)
    return _detect_payload(meta)


@app.get("/api/{session_id}/stats")
def stats(session_id: str, open_text_limit: int = 200):
    df, meta = _load_session(session_id)
    question_types = meta["question_types"]
    results = generate_descriptive_results(df, question_types)

    numeric_summary = results["numeric_summary"]
    scale_summary = results["scale_summary"]

    open_text = {}
    for column, q_type in question_types.items():
        if q_type == QUESTION_TYPE_OPEN:
            answers = df[column].dropna().astype(str).tolist()
            open_text[column] = {"total": len(answers), "answers": answers[:open_text_limit]}

    # Bin counts for the frontend's numeric histogram bars (8 bins matches the
    # design mockup). Pure numpy on already-numeric columns — no new analysis.
    numeric_histograms = {}
    for column, q_type in question_types.items():
        if q_type == QUESTION_TYPE_NUMERIC:
            values = pd.to_numeric(df[column], errors="coerce").dropna()
            if len(values) >= 2 and values.nunique() > 1:
                counts, edges = np.histogram(values, bins=8)
                numeric_histograms[column] = {
                    "counts": counts.tolist(),
                    "min": float(edges[0]),
                    "max": float(edges[-1]),
                }

    return {
        "numeric_summary": df_records(numeric_summary.reset_index(names="column")) if not numeric_summary.empty else [],
        "scale_summary": df_records(scale_summary.reset_index(names="column")) if not scale_summary.empty else [],
        "scale_distributions": {col: df_records(dist) for col, dist in results["scale_distributions"].items()},
        "frequency_tables": {col: df_records(freq) for col, freq in results["categorical_summary"].items()},
        "open_text": open_text,
        "numeric_histograms": numeric_histograms,
    }


@app.post("/api/{session_id}/cross")
def cross(session_id: str, body: dict):
    df, meta = _load_session(session_id)
    question_types = meta["question_types"]

    group_col = body.get("group_col")
    target_col = body.get("target_col")
    language = body.get("language", "zh-CN")
    for col in (group_col, target_col):
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column not found: {col}")

    result = analyze_cross_relationship(df, group_col, target_col, question_types, language=language)
    payload = {"analysis_type": result["analysis_type"]}

    if result["analysis_type"] == "numeric_by_group":
        payload["summary_table"] = df_records(result["summary_table"].reset_index(names="group"))
        payload["interpretation"] = result["interpretation"]
    elif result["analysis_type"] == "categorical_crosstab":
        crosstab = result["crosstab_table"]
        row_pct = result["row_percentage_table"]
        payload["rows"] = [str(v) for v in crosstab.index]
        payload["cols"] = [str(v) for v in crosstab.columns]
        payload["counts"] = crosstab.values.tolist()
        payload["row_pct"] = row_pct.values.tolist()
        payload["interpretation"] = result["interpretation"]
    else:  # unsupported (open-ended involved)
        payload["message"] = result.get("message", "")

    return payload


@app.get("/api/{session_id}/report")
def report(
    session_id: str,
    language: str = "zh-CN",
    group_col: str | None = None,
    target_col: str | None = None,
    download: bool = False,
):
    df, meta = _load_session(session_id)
    question_types = meta["question_types"]
    results = generate_descriptive_results(df, question_types)

    cross_result = None
    if group_col and target_col and group_col in df.columns and target_col in df.columns:
        cross_result = analyze_cross_relationship(df, group_col, target_col, question_types, language=language)

    markdown = generate_markdown_report(df, question_types, results, cross_result, language)
    if download:
        return PlainTextResponse(
            markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="surveymind_report.md"'},
        )
    return {"markdown": markdown}


@app.post("/api/{session_id}/ai-report")
def ai_report(session_id: str):
    """LLM interpretation of the dataset. Reuses the existing structured-summary
    prompt builders; degrades gracefully when no API key is configured."""
    df, _ = _load_session(session_id)
    if not is_llm_configured():
        return {"ok": False, "reason": "not_configured"}

    try:
        prompt = build_llm_prompt(build_dataset_summary(df))
        markdown = ask_llm(prompt)
    except LLMNotConfiguredError:
        return {"ok": False, "reason": "not_configured"}
    except Exception as exc:
        # str(exc) never contains the key (it travels in a request header only)
        return {"ok": False, "reason": "api_error", "message": str(exc)[:300]}
    return {"ok": True, "markdown": markdown}
