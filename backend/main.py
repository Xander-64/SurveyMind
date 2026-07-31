"""SurveyMind REST API — a thin FastAPI layer over the existing src/ modules.

Every endpoint follows the same pattern: load the session's DataFrame, call one
existing analysis function from src/, serialize the result to JSON. No analysis
logic lives here.

Run from the project root:
    uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager, suppress
from dataclasses import asdict
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

from src.ai_report import AI_STATUS_NOT_CONFIGURED, AI_STATUS_OK, generate_ai_report
from src.analysis_suggestions import generate_analysis_suggestions
from src.chart_recommender import recommend_charts
from src.cross_analysis import analyze_cross_relationship
from src.data_loader import get_dataset_overview, load_uploaded_dataset
from src.dataset_mode import (
    DATASET_MODE_MIXED,
    DATASET_MODE_OPTIONS,
    DATASET_MODE_SURVEY,
    detect_dataset_mode,
)
from src.descriptive_analysis import generate_descriptive_results
from src.field_semantics import (
    FIELD_ROLE_NUMERIC,
    apply_role_overrides,
    detect_field_semantics,
    get_field_role_options,
)
from src.general_overview import build_overview_findings, generate_general_overview
from src.i18n import translate_question_type
from src.llm_client import LLMNotConfiguredError, ask_llm, is_llm_configured
from src.preprocessing import is_metadata_column, soft_clean_dataframe
from src.question_type_detector import (
    QUESTION_TYPE_EMPTY,
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
    detect_question_types,
    detect_scale_candidates,
)
from src.report import (
    build_dataset_summary,
    build_llm_prompt,
    generate_markdown_report,
    generate_report,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSIONS_DIR = PROJECT_ROOT / "uploads_tmp"
SESSION_MAX_AGE_SECONDS = 60 * 60
SESSION_CLEANUP_INTERVAL_SECONDS = 30
LOCAL_FRONTEND_ORIGINS = (
    "http://127.0.0.1:5500",
    "http://localhost:5500",
)

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

# Small in-process cache so repeated requests for one session skip the disk.
_session_cache: dict[str, tuple[pd.DataFrame, dict]] = {}
_session_expiry_handles: dict[str, asyncio.TimerHandle] = {}


def _allowed_origins() -> list[str]:
    """Return the explicit CORS allowlist for local or hosted frontends."""
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "")
    origins = [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    return origins or list(LOCAL_FRONTEND_ORIGINS)


def _delete_session(session_id: str) -> None:
    handle = _session_expiry_handles.pop(session_id, None)
    if handle is not None:
        handle.cancel()
    _session_cache.pop(session_id, None)
    shutil.rmtree(SESSIONS_DIR / session_id, ignore_errors=True)


def _schedule_session_expiry(session_id: str, created_at: float) -> None:
    """Schedule deletion at the one-hour deadline while this process is awake."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    previous = _session_expiry_handles.pop(session_id, None)
    if previous is not None:
        previous.cancel()
    delay = max(0.0, created_at + SESSION_MAX_AGE_SECONDS - time.time())
    _session_expiry_handles[session_id] = loop.call_later(delay, _delete_session, session_id)


def _cancel_session_expiry_handles() -> None:
    for handle in _session_expiry_handles.values():
        handle.cancel()
    _session_expiry_handles.clear()


def _session_created_at(session_dir: Path) -> float:
    meta_path = session_dir / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return float(meta["created_at"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return session_dir.stat().st_mtime


def _cleanup_old_sessions(*, now: float | None = None) -> None:
    if not SESSIONS_DIR.exists():
        return
    cutoff = (time.time() if now is None else now) - SESSION_MAX_AGE_SECONDS
    for session_dir in SESSIONS_DIR.iterdir():
        if session_dir.is_dir() and _session_created_at(session_dir) <= cutoff:
            _delete_session(session_dir.name)


async def _session_cleanup_loop() -> None:
    """Delete expired upload sessions even when no new upload arrives."""
    while True:
        _cleanup_old_sessions()
        await asyncio.sleep(SESSION_CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    _cleanup_old_sessions()
    if SESSIONS_DIR.exists():
        for session_dir in SESSIONS_DIR.iterdir():
            if session_dir.is_dir():
                _schedule_session_expiry(session_dir.name, _session_created_at(session_dir))
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        _cancel_session_expiry_handles()


app = FastAPI(title="SurveyMind API", version="0.1.0", lifespan=lifespan)

# The hosted frontend origin is supplied through CORS_ALLOWED_ORIGINS. Local
# development remains available by default on ports documented in README.md.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _write_meta(session_id: str, meta: dict) -> None:
    (SESSIONS_DIR / session_id / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )


def _store_meta(session_id: str, meta: dict) -> None:
    """Persist meta and refresh the cache entry without touching the stored df."""
    _write_meta(session_id, meta)
    cached = _session_cache.get(session_id)
    if cached is not None:
        _session_cache[session_id] = (cached[0], meta)


# Legacy strict-cleaning error, kept byte-identical for the upload endpoints.
NO_SURVEY_COLUMNS_ERROR = "No usable survey columns remain after preprocessing."


def _clean_for_storage(loaded: pd.DataFrame) -> pd.DataFrame:
    """Soft-clean an upload for session storage (metadata columns kept for the
    general platform), preserving the strict cleaner's error contract: a file
    with no survey columns is still rejected with the legacy message."""
    try:
        df = soft_clean_dataframe(loaded)
    except ValueError:
        raise ValueError(NO_SURVEY_COLUMNS_ERROR)
    if all(is_metadata_column(column) for column in df.columns):
        raise ValueError(NO_SURVEY_COLUMNS_ERROR)
    return df


def _save_session(df: pd.DataFrame, filename: str) -> tuple[str, dict]:
    """Store the soft-cleaned (full) df; question_types stays the five-screen
    contract by detecting on the metadata-free view (byte-identical to the old
    strict-cleaning pipeline)."""
    session_id = uuid.uuid4().hex
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    df.to_parquet(session_dir / "data.parquet")
    metadata_columns = [column for column in df.columns if is_metadata_column(column)]
    detected = detect_question_types(df.drop(columns=metadata_columns))
    semantics = detect_field_semantics(df)
    detected_roles = {column: profile.role for column, profile in semantics.items()}
    mode_detection = asdict(detect_dataset_mode(df, semantics))
    meta = {
        "filename": filename,
        "created_at": time.time(),
        "question_types": detected,
        # kept immutable so manual overrides can be reset to this baseline
        "detected_types": dict(detected),
        "metadata_columns": metadata_columns,
        "dataset_mode": mode_detection["mode"],
        "mode_detection": mode_detection,
        "field_roles": dict(detected_roles),
        # kept immutable so role overrides can be reset to this baseline
        "detected_roles": detected_roles,
    }
    _write_meta(session_id, meta)
    _session_cache[session_id] = (df, meta)
    _schedule_session_expiry(session_id, meta["created_at"])
    return session_id, meta


def _load_session_full(session_id: str) -> tuple[pd.DataFrame, dict]:
    """Load the stored df with every column, for the general-platform endpoints."""
    if session_id in _session_cache:
        df, meta = _session_cache[session_id]
        if float(meta.get("created_at", 0)) + SESSION_MAX_AGE_SECONDS <= time.time():
            _delete_session(session_id)
            raise HTTPException(status_code=404, detail="Session expired. Please upload the file again.")
        return df, meta

    session_dir = SESSIONS_DIR / session_id
    data_path = session_dir / "data.parquet"
    meta_path = session_dir / "meta.json"
    if not data_path.exists() or not meta_path.exists():
        raise HTTPException(status_code=404, detail="Session not found. Please upload the file again.")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if float(meta.get("created_at", 0)) + SESSION_MAX_AGE_SECONDS <= time.time():
        _delete_session(session_id)
        raise HTTPException(status_code=404, detail="Session expired. Please upload the file again.")

    df = pd.read_parquet(data_path)
    _session_cache[session_id] = (df, meta)
    return df, meta


def _survey_view(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    metadata_columns = [column for column in meta.get("metadata_columns", ()) if column in df.columns]
    return df.drop(columns=metadata_columns) if metadata_columns else df


def _load_session(session_id: str) -> tuple[pd.DataFrame, dict]:
    """Load the survey view (metadata columns dropped) — identical to what the
    strict cleaner used to store, so every legacy endpoint behaves unchanged."""
    df, meta = _load_session_full(session_id)
    return _survey_view(df, meta), meta


def df_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of records (NaN -> null, numpy -> native)."""
    return json.loads(df.to_json(orient="records", force_ascii=False))


def _numeric_histograms(df: pd.DataFrame, columns: list[str]) -> dict[str, dict]:
    """Bin counts for the frontend's histogram bars (8 bins matches the design
    mockup). Pure numpy on already-numeric columns — no new analysis."""
    histograms: dict[str, dict] = {}
    for column in columns:
        values = pd.to_numeric(df[column], errors="coerce").dropna()
        if len(values) >= 2 and values.nunique() > 1:
            counts, edges = np.histogram(values, bins=8)
            histograms[column] = {
                "counts": counts.tolist(),
                "min": float(edges[0]),
                "max": float(edges[-1]),
            }
    return histograms


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    _cleanup_old_sessions()
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    try:
        # Identical pipeline to the Streamlit app: tolerant load + shared cleaning.
        df = _clean_for_storage(load_uploaded_dataset(file_bytes, file.filename or ""))
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=400, detail="The file appears to be corrupted or unreadable.")

    session_id, meta = _save_session(df, file.filename or "uploaded")
    return {
        "session_id": session_id,
        "filename": file.filename,
        "rows": int(len(df)),
        # survey-view count: byte-identical to the strict-cleaning era
        "columns": int(df.shape[1] - len(meta["metadata_columns"])),
        "mode": meta["dataset_mode"],
    }


@app.post("/api/demo")
async def demo_session():
    """Create a session from the bundled sample dataset (same pipeline as upload)."""
    demo_path = PROJECT_ROOT / "data" / "sample_survey.csv"
    if not demo_path.exists():
        raise HTTPException(status_code=404, detail="Demo dataset not found.")
    df = _clean_for_storage(load_uploaded_dataset(demo_path.read_bytes(), demo_path.name))
    session_id, meta = _save_session(df, demo_path.name)
    return {
        "session_id": session_id,
        "filename": demo_path.name,
        "rows": int(len(df)),
        "columns": int(df.shape[1] - len(meta["metadata_columns"])),
        "mode": meta["dataset_mode"],
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


def _detect_payload(meta: dict, df: pd.DataFrame | None = None) -> dict:
    """Question types, plus a per-column scale hint.

    ``scale_candidate`` marks a numeric column that could be a 0-10 style scale
    the detector will not claim on its own. It never changes the type: a count
    of purchases and an NPS rating are identical in their values, so guessing
    risks narrating "3.2 purchases" as "a 3.2 rating" in the report. The hint
    surfaces the ambiguity for the one person who knows the answer, who
    resolves it through the existing POST /types override.
    """
    candidates = detect_scale_candidates(df) if df is not None else {}
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
                # Only offer the hint where it means something: a column the
                # active type still calls numeric. Once it has been overridden
                # the question is settled and repeating the hint is noise.
                "scale_candidate": bool(candidates.get(column, False))
                and q_type == QUESTION_TYPE_NUMERIC,
            }
        )
    return {"types": types, "counts": counts}


@app.get("/api/{session_id}/detect")
def detect(session_id: str):
    df, meta = _load_session(session_id)
    return _detect_payload(meta, df)


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
    _store_meta(session_id, meta)
    return _detect_payload(meta, df)


@app.delete("/api/{session_id}/types")
def reset_types(session_id: str):
    """Discard manual overrides, restoring the original auto-detected types."""
    df, meta = _load_session(session_id)
    meta["question_types"] = dict(meta.get("detected_types") or meta["question_types"])
    _store_meta(session_id, meta)
    return _detect_payload(meta, df)


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

    numeric_histograms = _numeric_histograms(
        df, [column for column, q_type in question_types.items() if q_type == QUESTION_TYPE_NUMERIC]
    )

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
    mode: str | None = None,
):
    if mode is not None and mode not in DATASET_MODE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown dataset mode: {mode}")

    if mode is None or mode == DATASET_MODE_SURVEY:
        # Legacy path — the five-screen export contract, byte-identical.
        df, meta = _load_session(session_id)
        question_types = meta["question_types"]
        results = generate_descriptive_results(df, question_types)

        cross_result = None
        if group_col and target_col and group_col in df.columns and target_col in df.columns:
            cross_result = analyze_cross_relationship(df, group_col, target_col, question_types, language=language)

        markdown = generate_markdown_report(df, question_types, results, cross_result, language)
    else:
        # general / mixed: full df + active field roles drive the mode report.
        df, meta = _load_session_full(session_id)
        meta = _ensure_platform_meta(session_id, df, meta)
        semantics = _active_semantics(df, meta)
        overview = generate_general_overview(df, semantics)
        question_types = meta["question_types"]
        descriptive_results = (
            generate_descriptive_results(df, question_types) if mode == DATASET_MODE_MIXED else None
        )

        cross_result = None
        if group_col and target_col and group_col in question_types and target_col in question_types:
            cross_result = analyze_cross_relationship(df, group_col, target_col, question_types, language=language)

        markdown = generate_report(
            df,
            mode,
            language,
            question_types=question_types,
            descriptive_results=descriptive_results,
            cross_analysis_result=cross_result,
            semantics=semantics,
            overview=overview,
        )

    if download:
        return PlainTextResponse(
            markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="surveymind_report.md"'},
        )
    return {"markdown": markdown}


@app.post("/api/{session_id}/ai-report")
def ai_report(session_id: str, body: dict | None = None):
    """LLM interpretation of the dataset. Without a body (or mode) this is the
    legacy survey prompt, unchanged; with a mode it runs the persona-based
    generator from src/ai_report. Degrades gracefully when no key is set."""
    body = body or {}
    mode = body.get("mode")

    if mode is None:
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

    if mode not in DATASET_MODE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown dataset mode: {mode}")

    language = body.get("language", "zh-CN")
    df, meta = _load_session_full(session_id)
    meta = _ensure_platform_meta(session_id, df, meta)
    semantics = _active_semantics(df, meta)
    overview = generate_general_overview(df, semantics)

    question_types = None
    descriptive_results = None
    if mode in {DATASET_MODE_SURVEY, DATASET_MODE_MIXED}:
        question_types = meta["question_types"]
        descriptive_results = generate_descriptive_results(df, question_types)

    result = generate_ai_report(df, mode, language, overview, descriptive_results, question_types)
    if result["status"] == AI_STATUS_OK:
        return {"ok": True, "mode": mode, "markdown": result["content"]}
    if result["status"] == AI_STATUS_NOT_CONFIGURED:
        return {"ok": False, "reason": "not_configured"}
    return {"ok": False, "reason": "api_error"}


# --- General data platform (mode / field roles / overview) -------------------


def _ensure_platform_meta(session_id: str, df: pd.DataFrame, meta: dict) -> dict:
    """Backfill sessions created before the general-platform upgrade so the new
    endpoints work on them too (their stored df is already the strict view)."""
    if "detected_roles" in meta and "mode_detection" in meta:
        return meta

    semantics = detect_field_semantics(df)
    detected_roles = {column: profile.role for column, profile in semantics.items()}
    mode_detection = asdict(detect_dataset_mode(df, semantics))
    meta.setdefault("metadata_columns", [])
    meta["detected_roles"] = detected_roles
    meta.setdefault("field_roles", dict(detected_roles))
    meta["mode_detection"] = mode_detection
    meta.setdefault("dataset_mode", mode_detection["mode"])
    _store_meta(session_id, meta)
    return meta


def _active_semantics(df: pd.DataFrame, meta: dict) -> dict:
    """Detected field profiles with the session's manual role overrides applied."""
    return apply_role_overrides(detect_field_semantics(df), meta.get("field_roles", {}))


def _mode_payload(meta: dict) -> dict:
    return {"detected": meta["mode_detection"], "active": meta["dataset_mode"]}


def _semantics_payload(df: pd.DataFrame, meta: dict) -> dict:
    fields = []
    for column, profile in _active_semantics(df, meta).items():
        data = asdict(profile)
        fields.append(
            {
                "column": data["column"],
                "role": data["role"],
                "confidence": data["confidence"],
                "evidence": data["evidence"],
                "non_null": data["non_null_count"],
                "unique": data["unique_count"],
                "missing_pct": round(float(df[column].isna().mean() * 100), 2),
            }
        )
    return {"fields": fields, "role_options": get_field_role_options()}


@app.get("/api/{session_id}/mode")
def get_mode(session_id: str):
    df, meta = _load_session_full(session_id)
    meta = _ensure_platform_meta(session_id, df, meta)
    return _mode_payload(meta)


@app.put("/api/{session_id}/mode")
def set_mode(session_id: str, body: dict):
    """Manually switch the active dataset mode; detection stays as the baseline."""
    df, meta = _load_session_full(session_id)
    meta = _ensure_platform_meta(session_id, df, meta)
    mode = body.get("mode")
    if mode not in DATASET_MODE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown dataset mode: {mode}")

    meta["dataset_mode"] = mode
    _store_meta(session_id, meta)
    return _mode_payload(meta)


@app.get("/api/{session_id}/semantics")
def semantics(session_id: str):
    df, meta = _load_session_full(session_id)
    meta = _ensure_platform_meta(session_id, df, meta)
    return _semantics_payload(df, meta)


@app.put("/api/{session_id}/semantics")
def override_role(session_id: str, body: dict):
    """Manually correct one column's field role; overview and reports follow."""
    df, meta = _load_session_full(session_id)
    meta = _ensure_platform_meta(session_id, df, meta)
    column = body.get("column")
    role = body.get("role")
    if column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Column not found: {column}")
    if role not in get_field_role_options():
        raise HTTPException(status_code=400, detail=f"Unknown field role: {role}")

    meta["field_roles"][column] = role
    _store_meta(session_id, meta)
    return _semantics_payload(df, meta)


@app.delete("/api/{session_id}/semantics")
def reset_roles(session_id: str):
    """Discard manual role overrides, restoring the original detected roles."""
    df, meta = _load_session_full(session_id)
    meta = _ensure_platform_meta(session_id, df, meta)
    meta["field_roles"] = dict(meta["detected_roles"])
    _store_meta(session_id, meta)
    return _semantics_payload(df, meta)


@app.get("/api/{session_id}/general-overview")
def general_overview(session_id: str):
    """Everything the Smart Insights screen needs in one response, with
    natural-language findings/suggestions returned in both languages."""
    df, meta = _load_session_full(session_id)
    meta = _ensure_platform_meta(session_id, df, meta)
    semantics = _active_semantics(df, meta)
    overview = generate_general_overview(df, semantics)

    quality = overview["quality"]
    numeric_summary = overview["numeric_summary"]
    numeric_columns = [column for column, profile in semantics.items() if profile.role == FIELD_ROLE_NUMERIC]
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "quality": {
            "duplicate_rows": quality["duplicate_rows"],
            "overall_missing_pct": quality["overall_missing_pct"],
            "high_missing": [
                {"column": str(column), "missing_pct": round(float(rate * 100), 2)}
                for column, rate in quality["high_missing"].items()
            ],
            "unusable_columns": quality["unusable_columns"],
        },
        "numeric_summary": df_records(numeric_summary.reset_index(names="column")) if not numeric_summary.empty else [],
        "categorical_summary": {column: df_records(freq) for column, freq in overview["categorical_summary"].items()},
        "datetime_summary": df_records(overview["datetime_summary"]) if not overview["datetime_summary"].empty else [],
        "time_trends": {column: df_records(trend) for column, trend in overview["time_trends"].items()},
        "correlations": df_records(overview["correlations"]) if not overview["correlations"].empty else [],
        "group_differences": df_records(overview["group_differences"]) if not overview["group_differences"].empty else [],
        "id_candidates": overview["id_candidates"],
        "findings": {
            "zh": build_overview_findings(df, overview, "zh-CN"),
            "en": build_overview_findings(df, overview, "en"),
        },
        "suggestions": {
            "zh": generate_analysis_suggestions(df, semantics, overview, "zh-CN"),
            "en": generate_analysis_suggestions(df, semantics, overview, "en"),
        },
        "chart_specs": recommend_charts(df, semantics, overview),
        "numeric_histograms": _numeric_histograms(df, numeric_columns),
    }
