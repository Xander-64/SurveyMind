"""Synthetic response data for a survey schema.

Two jobs:

1. Give exports something to demonstrate with, and give the end-to-end test a
   recovered CSV to feed back through /api/upload.
2. Produce ``(frame, ground_truth)`` where the truth comes straight from the
   schema. Question types are known at generation time, so the accuracy work in
   a later batch needs no hand labelling at all.

The noise switches exist because clean data proves very little. Each one
reproduces something a real platform export actually does to the data.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import pandas as pd

from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)
from src.survey_gen.schema import Question, Survey, text_in

# Free-text answers are near-unique and longer than a choice label. Drawing
# from a small fixed list produced a low-cardinality column that the detector
# reasonably read as single-choice — realistic-looking data matters, because a
# generator that quietly produces unrealistic columns turns the end-to-end test
# into a check on the generator rather than on the pipeline.
OPEN_TEXT_FRAGMENTS = (
    "整体还不错，希望能保持现在的水准",
    "希望响应速度可以再快一些",
    "流程有点繁琐，建议适当简化",
    "服务态度很好，让人觉得舒服",
    "价格偏高，感觉性价比一般",
    "界面用起来比较顺手，没什么障碍",
    "希望能增加更多可选的方式",
    "遇到问题时找不到合适的入口",
    "整体体验超出了我的预期",
    "有几次等待时间明显偏长",
    "客服解释得很清楚，问题当场就解决了",
    "预约环节的提示不太明显，差点错过",
    "希望周末也能有人值班",
    "退换流程比想象中顺利",
    "通知消息有点多，可以让我自己选",
    "网点位置不太好找，建议加个指引",
    "工作人员很耐心，讲解也仔细",
    "系统偶尔会卡住，需要重新进入",
    "整体流程比去年简化了不少",
    "希望能提供更详细的收费说明",
)
OPEN_TEXT_DETAILS = (
    "上个月我大概用了{n}次",
    "第{n}次使用时印象比较深",
    "等了差不多{n}分钟才有回应",
    "前后联系过{n}位工作人员",
    "最近{n}周都是这样",
    "大约{n}天前刚办理过一次",
    "同事里有{n}个人也遇到过",
)


def _open_text(rng: random.Random) -> str:
    """One opinion clause plus one concrete detail.

    The detail carries a number so the clause differs from row to row. Without
    it, comma-joined reusable fragments have exactly the statistical signature
    of a multi-select column — a small token vocabulary reused across many rows
    — and the detector reads them as one, correctly. Real open text does not
    reuse whole clauses; a generator that does is producing a multi-select
    column and mislabelling it.
    """
    opinion = rng.choice(OPEN_TEXT_FRAGMENTS)
    detail = rng.choice(OPEN_TEXT_DETAILS).format(n=rng.randint(2, 40))
    if rng.random() < 0.5:
        return "%s。%s。" % (opinion, detail)
    return "%s。%s。" % (detail, opinion)


@dataclass
class NoiseProfile:
    """Each switch mirrors something a real export does.

    Defaults are all off: the baseline is clean data, and every test that wants
    mess has to ask for it by name, so it is obvious from the test what is being
    exercised.
    """

    missing_rate: float = 0.0
    # Likert values written as text ("5分") the way some platforms export them.
    scale_as_text: bool = False
    # Multi-select joined with whatever delimiter the platform happened to use.
    delimiter_mix: bool = False
    # Submission timestamps, IP, duration, nickname appended by the platform.
    add_metadata_columns: bool = False
    # A share of respondents who pick the same option all the way down.
    straightliner_ratio: float = 0.0


def _scale_values(question: Question, n: int, rng: random.Random) -> list:
    spec = question.scale_spec
    low = spec.min_value
    high = spec.max_value
    # A latent tendency per respondent so items in one construct correlate,
    # which is what makes reliability meaningful rather than noise.
    values = []
    for _ in range(n):
        centre = (low + high) / 2
        drawn = rng.gauss(centre, (high - low) / 4 or 1)
        values.append(int(min(high, max(low, round(drawn)))))
    if question.reverse_coded:
        values = [low + high - value for value in values]
    return values


def _choice_values(question: Question, n: int, rng: random.Random) -> list:
    labels = [text_in(option.label, "zh-CN") for option in question.options] or ["A", "B"]
    weights = [rng.random() + 0.2 for _ in labels]
    return rng.choices(labels, weights=weights, k=n)


def _multi_values(question: Question, n: int, rng: random.Random, delimiters) -> list:
    labels = [text_in(option.label, "zh-CN") for option in question.options] or ["A", "B"]
    exclusive = {
        text_in(option.label, "zh-CN") for option in question.options if option.exclusive
    }
    rows = []
    for _ in range(n):
        picked = [label for label in labels if label not in exclusive and rng.random() < 0.4]
        if not picked:
            picked = [rng.choice(labels)]
        rows.append(rng.choice(delimiters).join(picked))
    return rows


def _numeric_values(question: Question, n: int, rng: random.Random) -> list:
    spec = question.numeric_spec
    low = int(spec.min) if spec and spec.min is not None else 0
    high = int(spec.max) if spec and spec.max is not None else 100
    return [rng.randint(low, high) for _ in range(n)]


def generate_responses(
    survey: Survey,
    n_respondents: int = 200,
    noise: NoiseProfile | None = None,
    seed: int = 20260801,
) -> tuple[pd.DataFrame, dict[str, str]]:
    """Return (responses, ground_truth).

    ``ground_truth`` maps column code to the declared question type. It is read
    off the schema, not inferred, which is the entire point: the labels cost
    nothing and cannot drift from what was actually generated.
    """
    noise = noise or NoiseProfile()
    rng = random.Random(seed)
    delimiters = [";", "，", "、", "/"] if noise.delimiter_mix else [";"]

    columns: dict[str, list] = {}
    ground_truth: dict[str, str] = {}

    for _, question in survey.iter_questions():
        if question.question_type == QUESTION_TYPE_SCALE:
            values = _scale_values(question, n_respondents, rng)
            if noise.scale_as_text:
                values = ["%d分" % value for value in values]
        elif question.question_type == QUESTION_TYPE_SINGLE:
            values = _choice_values(question, n_respondents, rng)
        elif question.question_type == QUESTION_TYPE_MULTIPLE:
            values = _multi_values(question, n_respondents, rng, delimiters)
        elif question.question_type == QUESTION_TYPE_NUMERIC:
            values = _numeric_values(question, n_respondents, rng)
        elif question.question_type == QUESTION_TYPE_OPEN:
            values = [_open_text(rng) for _ in range(n_respondents)]
        else:
            continue
        columns[question.code] = values
        ground_truth[question.code] = question.question_type

    frame = pd.DataFrame(columns)

    if noise.straightliner_ratio > 0:
        scale_codes = [
            question.code
            for _, question in survey.iter_questions()
            if question.question_type == QUESTION_TYPE_SCALE and question.scale_spec
        ]
        count = int(n_respondents * noise.straightliner_ratio)
        for row in rng.sample(range(n_respondents), min(count, n_respondents)):
            for code in scale_codes:
                frame.loc[row, code] = frame.loc[row, scale_codes[0]]

    if noise.missing_rate > 0:
        for code in frame.columns:
            mask = [rng.random() < noise.missing_rate for _ in range(n_respondents)]
            frame.loc[mask, code] = None

    if noise.add_metadata_columns:
        # English names on purpose: this is what a third-party export produces,
        # and is_metadata_column does not catch them (see the design doc).
        stamps = pd.date_range("2026-03-01", periods=n_respondents, freq="37min")
        frame["submit_time"] = stamps.strftime("%Y-%m-%d %H:%M:%S")
        frame["ip_address"] = [
            "10.%d.%d.%d" % (rng.randint(0, 9), rng.randint(0, 255), rng.randint(1, 254))
            for _ in range(n_respondents)
        ]
        frame["duration_sec"] = [rng.randint(60, 900) for _ in range(n_respondents)]
        frame["nickname"] = [
            rng.choice(["小明", "阿华", "Lee", "匿名", "用户%d" % rng.randint(1000, 9999)])
            for _ in range(n_respondents)
        ]

    return frame, ground_truth
