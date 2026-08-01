"""Headless end-to-end tests: run the real Streamlit app via AppTest."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(scope="module")
def demo_app():
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.run()
    return at


def test_app_renders_demo_without_exceptions(demo_app):
    assert not demo_app.exception, [str(e.value) for e in demo_app.exception]


def test_demo_survey_mode_detected(demo_app):
    mode_radio = demo_app.radio(key="dataset_mode_override::demo")
    assert mode_radio.value == "survey"


def test_manual_mode_switch_to_general_does_not_crash(demo_app):
    demo_app.radio(key="dataset_mode_override::demo").set_value("general").run()
    assert not demo_app.exception, [str(e.value) for e in demo_app.exception]


def test_language_switch_to_chinese_does_not_crash():
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.session_state["language"] = "zh-CN"
    at.run()
    assert not at.exception, [str(e.value) for e in at.exception]
