"""Exports: the file bridge between generating a survey and analysing it.

Five artifacts, because they serve different readers:

    template.csv   header only, for the platform the survey is fielded on
    sample.csv     three synthetic rows, so the round trip can be checked
                   without waiting for real respondents
    questionnaire  markdown, one file per language, for humans
    schema.json    machine-readable, and the thing that has to travel with the
                   data for a 0-10 column to survive the round trip
    codebook.md    variable to stem to coding, the standard academic artifact

On the two CSVs
---------------
A header-only CSV cannot be re-uploaded: the cleaning step drops all-empty
columns, so a zero-row file loses every column and the upload is rejected. That
is correct behaviour for the cleaner and not worth bending. Hence two files —
the empty one is what a platform wants, the sampled one is what a person uses
to check the loop actually closes.
"""
from __future__ import annotations

import io
import json

import pandas as pd

from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)
from src.report.common import _bullet
from src.survey_gen.schema import Survey, text_in
from src.survey_gen.synthetic import generate_responses

TYPE_LABELS = {
    QUESTION_TYPE_SCALE: {"zh-CN": "量表题", "en": "Scale"},
    QUESTION_TYPE_SINGLE: {"zh-CN": "单选题", "en": "Single choice"},
    QUESTION_TYPE_MULTIPLE: {"zh-CN": "多选题", "en": "Multiple choice"},
    QUESTION_TYPE_NUMERIC: {"zh-CN": "数值题", "en": "Numeric"},
    QUESTION_TYPE_OPEN: {"zh-CN": "开放题", "en": "Open text"},
}

SECTION_PURPOSE_LABELS = {
    "screening": {"zh-CN": "甄别", "en": "Screening"},
    "construct": {"zh-CN": "主体", "en": "Main"},
    "attention": {"zh-CN": "作答确认", "en": "Response check"},
    "open_feedback": {"zh-CN": "开放反馈", "en": "Open feedback"},
    "demographic": {"zh-CN": "基本信息", "en": "About you"},
}


def column_codes(survey: Survey) -> list[str]:
    """CSV header order: section order, then question order."""
    return [question.code for _, question in survey.iter_questions()]


def export_template_csv(survey: Survey) -> str:
    """Header row only. Hand this to the platform the survey runs on."""
    buffer = io.StringIO()
    pd.DataFrame(columns=column_codes(survey)).to_csv(buffer, index=False)
    return buffer.getvalue()


def export_sample_csv(survey: Survey, rows: int = 3, seed: int = 7) -> str:
    """A few synthetic rows, so the export can be re-uploaded immediately."""
    frame, _ = generate_responses(survey, n_respondents=rows, seed=seed)
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


def export_schema_json(survey: Survey) -> str:
    return json.dumps(survey.to_dict(), ensure_ascii=False, indent=2)


def _scale_line(question, language: str) -> str:
    spec = question.scale_spec
    if spec is None:
        return ""
    low = text_in(spec.min_label, language) or str(spec.min_value)
    high = text_in(spec.max_label, language) or str(spec.max_value)
    if language == "zh-CN":
        return "%d-%d 点量表：%d = %s，%d = %s" % (
            spec.min_value, spec.max_value, spec.min_value, low, spec.max_value, high)
    return "%d-%d scale: %d = %s, %d = %s" % (
        spec.min_value, spec.max_value, spec.min_value, low, spec.max_value, high)


def export_questionnaire_markdown(survey: Survey, language: str = "zh-CN") -> str:
    zh = language == "zh-CN"
    lines: list[str] = ["# " + text_in(survey.title, language), ""]
    if survey.description:
        lines += [text_in(survey.description, language), ""]
    if survey.estimated_minutes:
        lines += ["*%s*" % (("预计用时约 %d 分钟。" % survey.estimated_minutes) if zh
                            else ("Takes about %d minutes." % survey.estimated_minutes)), ""]

    number = 0
    for section in survey.sections:
        purpose = SECTION_PURPOSE_LABELS.get(section.purpose, {}).get(language, section.purpose)
        lines += ["## %s（%s）" % (text_in(section.title, language), purpose) if zh
                  else "## %s (%s)" % (text_in(section.title, language), purpose), ""]
        if section.intro:
            lines += ["> " + text_in(section.intro, language), ""]
        for question in section.questions:
            number += 1
            tags = []
            if question.reverse_coded:
                tags.append("反向计分" if zh else "reverse-coded")
            if question.attention_check:
                tags.append("注意力检测" if zh else "attention check")
            if not question.required:
                tags.append("选填" if zh else "optional")
            suffix = "  `[%s]`" % " / ".join(tags) if tags else ""
            type_label = TYPE_LABELS.get(question.question_type, {}).get(language, question.question_type)
            lines.append("**%d. %s**  `%s`%s" % (
                number, text_in(question.text, language), type_label, suffix))
            lines.append("")
            if question.scale_spec is not None:
                lines += [_bullet(_scale_line(question, language)), ""]
            for option in question.options:
                mark = " *(%s)*" % ("其他/不适用" if zh else "residual") if option.residual else ""
                lines.append(_bullet("%s%s" % (text_in(option.label, language), mark)))
            if question.options:
                lines.append("")

    lines += ["---", ""]
    lines += ["## " + ("构念与题目对照" if zh else "Constructs and items"), ""]
    for construct in survey.constructs:
        items = survey.questions_for_construct(construct.construct_id)
        codes = ", ".join("`%s`" % question.code for question in items)
        reverse = [question.code for question in items if question.reverse_coded]
        line = "**%s** (`%s`): %s" % (
            text_in(construct.name, language), construct.construct_id, codes)
        if reverse:
            line += " — %s %s" % (
                "反向计分：" if zh else "reverse-coded:", ", ".join("`%s`" % c for c in reverse))
        lines += [_bullet(line)]
    lines.append("")
    return "\n".join(lines)


def export_codebook_markdown(survey: Survey, language: str = "zh-CN") -> str:
    """Variable, stem, type, coding. The artifact an analyst actually opens."""
    zh = language == "zh-CN"
    header = ("| 变量名 | 题干 | 题型 | 取值编码 | 构念 | 反向 |"
              if zh else "| Variable | Stem | Type | Coding | Construct | Reverse |")
    lines = ["# " + (("%s — 变量编码表" % text_in(survey.title, language)) if zh
                     else ("%s — codebook" % text_in(survey.title, language))), "",
             header, "| --- | --- | --- | --- | --- | --- |"]
    for _, question in survey.iter_questions():
        if question.scale_spec is not None:
            coding = "%d-%d" % (question.scale_spec.min_value, question.scale_spec.max_value)
        elif question.options:
            coding = "; ".join(
                "%s=%s" % (option.value, text_in(option.label, language))
                for option in question.options
            )
        elif question.numeric_spec is not None:
            spec = question.numeric_spec
            coding = "%s-%s" % (spec.min, spec.max)
        else:
            coding = "自由文本" if zh else "free text"
        stem = text_in(question.text, language).replace("|", "/")
        lines.append("| `%s` | %s | %s | %s | %s | %s |" % (
            question.code,
            stem,
            TYPE_LABELS.get(question.question_type, {}).get(language, question.question_type),
            coding,
            question.construct_id or "—",
            ("是" if zh else "yes") if question.reverse_coded else "—",
        ))
    lines.append("")
    lines.append("> " + (
        "分析时请与本表同时保留 schema.json：0-10 量表等编码在纯数据中无法与计数变量区分。"
        if zh else
        "Keep schema.json alongside this table: a 0-10 scale cannot be told from a "
        "count variable by its values alone."))
    lines.append("")
    return "\n".join(lines)


EXPORT_FORMATS = ("template_csv", "sample_csv", "schema_json", "questionnaire_md", "codebook_md")


def export_all(survey: Survey, language: str = "zh-CN") -> dict[str, str]:
    """Every artifact, keyed by filename."""
    survey_id = survey.survey_id[:12]
    return {
        "%s_template.csv" % survey_id: export_template_csv(survey),
        "%s_sample.csv" % survey_id: export_sample_csv(survey),
        "%s_schema.json" % survey_id: export_schema_json(survey),
        "%s.%s.md" % (survey_id, language): export_questionnaire_markdown(survey, language),
        "%s_codebook.%s.md" % (survey_id, language): export_codebook_markdown(survey, language),
    }
