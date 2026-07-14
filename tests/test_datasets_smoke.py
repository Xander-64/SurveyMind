"""End-to-end smoke test over every bundled dataset.

Guards the "handles messy real questionnaire data" promise: each CSV in data/
must flow through preprocess -> detect -> describe -> report without crashing.
"""
from __future__ import annotations

import warnings
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

warnings.filterwarnings("ignore")
app = pytest.importorskip("app")

from src.cross_analysis import analyze_cross_relationship
from src.descriptive_analysis import generate_descriptive_results
from src.question_type_detector import detect_question_types
from src.report_generator import generate_markdown_report

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATASETS = sorted(DATA_DIR.glob("*.csv"))


def _robust_read_csv(path: Path) -> pd.DataFrame:
    """Mirror app.get_uploaded_data: fall back to the tolerant python engine."""
    try:
        return pd.read_csv(path)
    except pd.errors.ParserError:
        return pd.read_csv(BytesIO(path.read_bytes()), engine="python", on_bad_lines="skip")


@pytest.mark.parametrize("path", DATASETS, ids=lambda p: p.name)
def test_full_pipeline_runs_on_dataset(path):
    df = app.preprocess_input_dataframe(_robust_read_csv(path))
    assert df.shape[1] > 0

    question_types = detect_question_types(df)
    results = generate_descriptive_results(df, question_types)

    for language in ("en", "zh-CN"):
        report = generate_markdown_report(df, question_types, results, None, language)
        assert isinstance(report, str) and report.strip()


def test_at_least_one_dataset_present():
    assert DATASETS, "No bundled datasets found in data/"
