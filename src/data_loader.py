from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEMO_PATH = PROJECT_ROOT / "data" / "sample_survey.csv"


def load_demo_dataset(path: str | Path = DEFAULT_DEMO_PATH) -> pd.DataFrame:
    """Load the bundled demo survey dataset."""
    return pd.read_csv(path)


def load_uploaded_dataset(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Load a CSV or Excel file from uploaded bytes.

    Malformed CSV rows fall back to the tolerant python engine so that messy
    real-world exports (extra delimiters, ragged rows) still load. Every entry
    point (Streamlit app, API layer) shares this fallback behaviour.
    """
    suffix = Path(filename).suffix.lower()

    if suffix == ".csv":
        try:
            return pd.read_csv(BytesIO(file_bytes))
        except pd.errors.ParserError:
            return pd.read_csv(BytesIO(file_bytes), engine="python", on_bad_lines="skip")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(BytesIO(file_bytes))

    raise ValueError("Unsupported file type. Please upload a CSV or Excel file.")


def load_dataset(file_source: Any | None = None, filename: str | None = None) -> pd.DataFrame:
    """Load either user-provided data or the default demo dataset."""
    if file_source is None:
        return load_demo_dataset()

    if isinstance(file_source, (str, Path)):
        path = Path(file_source)
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path)
        raise ValueError("Unsupported file type. Please use CSV or Excel.")

    if isinstance(file_source, bytes) and filename:
        return load_uploaded_dataset(file_source, filename)

    raise ValueError("Unable to read the provided dataset.")


def get_dataset_overview(df: pd.DataFrame) -> dict[str, Any]:
    """Return core metadata used by the Streamlit overview panel."""
    overview_table = pd.DataFrame(
        {
            "column_name": df.columns,
            "data_type": [str(dtype) for dtype in df.dtypes],
            "missing_ratio": df.isna().mean().round(3).values,
            "non_null_count": df.notna().sum().values,
            "unique_values": df.nunique(dropna=True).values,
        }
    )

    return {
        "shape": df.shape,
        "preview": df.head(),
        "columns": list(df.columns),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "overview_table": overview_table,
    }
