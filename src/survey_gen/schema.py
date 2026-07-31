"""Survey schema: the data model shared by generation, export and alignment.

Design rules baked in here:

- Question types come from ``src.question_type_detector`` constants. The
  generator may only emit the five real types; ``empty question`` and
  ``unknown`` are detector-side outcomes and are deliberately absent from
  ``GENERATABLE_QUESTION_TYPES``. Writing the strings by hand is what breaks
  the generate -> analyse loop, so nothing in this package does.
- A matrix question is *not* a type. It is a group of scale questions sharing
  one ScaleSpec inside a section; recovered data shows it as N scale columns.
- ``Question.source`` has exactly one legal value. There is no schema slot for
  "this came from a published validated scale", so the model cannot claim one.
- Construct membership lives only on ``Question.construct_id``. ``Construct``
  does not carry a question list; it would be a second source of truth.
- Every human-readable field is a LocalizedText mapping with both languages,
  because the frontend switches language without refetching.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterator

from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)

SCHEMA_VERSION = 1

LANGUAGES = ("zh-CN", "en")

# The generator may only produce these. QUESTION_TYPE_EMPTY / _UNKNOWN are
# detector outcomes for unusable columns and are never authored.
GENERATABLE_QUESTION_TYPES = (
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_OPEN,
)

SECTION_PURPOSE_SCREENING = "screening"
SECTION_PURPOSE_CONSTRUCT = "construct"
SECTION_PURPOSE_ATTENTION = "attention"
SECTION_PURPOSE_OPEN_FEEDBACK = "open_feedback"
SECTION_PURPOSE_DEMOGRAPHIC = "demographic"

SECTION_PURPOSES = (
    SECTION_PURPOSE_SCREENING,
    SECTION_PURPOSE_CONSTRUCT,
    SECTION_PURPOSE_ATTENTION,
    SECTION_PURPOSE_OPEN_FEEDBACK,
    SECTION_PURPOSE_DEMOGRAPHIC,
)

# Ordering contract used by the question_order rule: screening first,
# demographic last, everything else in between.
SECTION_PURPOSE_RANK = {
    SECTION_PURPOSE_SCREENING: 0,
    SECTION_PURPOSE_CONSTRUCT: 1,
    SECTION_PURPOSE_ATTENTION: 1,
    SECTION_PURPOSE_OPEN_FEEDBACK: 1,
    SECTION_PURPOSE_DEMOGRAPHIC: 2,
}

POLARITY_UNIPOLAR = "unipolar"
POLARITY_BIPOLAR = "bipolar"
POLARITIES = (POLARITY_UNIPOLAR, POLARITY_BIPOLAR)

# Conventional point counts. This is a methodology judgement and is deliberately
# independent of what src.question_type_detector happens to recognise: the
# detector's range check is an implementation detail of our own code and must
# not be allowed to outlaw a valid instrument design.
SCALE_POINTS_CONVENTIONAL = (5, 7, 10, 11)
# Legitimate forced-choice designs; flagged only to comment on the trade-off.
SCALE_POINTS_FORCED_CHOICE = (4, 6)
SCALE_POINTS_COARSE = (2, 3)
SCALE_POINTS_MAX = 11

# Administration mode. Several rules only make sense under one of these, so it
# is a general precondition carried in MODE_POLICY rather than a special case
# bolted onto any single rule.
ADMIN_MODE_SELF = "self_administered"
ADMIN_MODE_INTERVIEWER = "interviewer_administered"
ADMIN_MODES = (ADMIN_MODE_SELF, ADMIN_MODE_INTERVIEWER)

# One table, read by every mode-dependent rule. Adding a mode-sensitive rule
# later means adding a key here, not adding another branch to the rule.
MODE_POLICY = {
    ADMIN_MODE_SELF: {
        # Nobody is watching the respondent, so inattention has to be measured.
        "requires_attention_check": True,
        # The respondent reads the stem themselves off a screen.
        "max_stem_chars_zh": 40,
        "max_stem_words_en": 25,
        # Long grids invite straight-lining when self-completed.
        "matrix_rows_warn": 8,
        "matrix_rows_error": 12,
        # Reserved for a future rule: an explicit "don't know" is a courtesy
        # online but a convention in interviewing. No rule reads this yet.
        "expects_dont_know_option": False,
    },
    ADMIN_MODE_INTERVIEWER: {
        # An interviewer is present; instructed-response items are a
        # self-administered convention and misfire here.
        "requires_attention_check": False,
        # The stem is read aloud, so it can carry more.
        "max_stem_chars_zh": 60,
        "max_stem_words_en": 40,
        # Showcards and a live interviewer hold attention through longer grids.
        "matrix_rows_warn": 12,
        "matrix_rows_error": 16,
        "expects_dont_know_option": True,
    },
}

QUESTION_SOURCE_GENERATED = "generated"

DEFAULT_METADATA_PREFIX = "_meta_"

LocalizedText = dict[str, str]


def localized(zh: str, en: str) -> LocalizedText:
    """Build a bilingual text field."""
    return {"zh-CN": zh, "en": en}


def text_in(value: LocalizedText | None, language: str) -> str:
    """Read one language out of a LocalizedText, falling back to English."""
    if not value:
        return ""
    return value.get(language) or value.get("en") or ""


@dataclass
class Option:
    value: str
    label: LocalizedText
    order: int = 0
    # "None of the above" / "Prefer not to say": may not be combined with others.
    exclusive: bool = False


@dataclass
class ScaleSpec:
    # Number of response points. Kept separate from the value range: a 0-10
    # scale is 11 points starting at 0, and conflating the two is what made
    # "points" ambiguous in the first place.
    points: int
    # Lowest coded value. 1 for the usual 1-5 / 1-7, 0 for NPS-style 0-10.
    min_value: int = 1
    polarity: str = POLARITY_BIPOLAR
    min_label: LocalizedText | None = None
    max_label: LocalizedText | None = None
    mid_label: LocalizedText | None = None
    # Full per-point labels. Optional, but the symmetry checks need them.
    labels: list[LocalizedText] | None = None

    @property
    def max_value(self) -> int:
        return self.min_value + self.points - 1

    @property
    def is_zero_based(self) -> bool:
        return self.min_value < 1


@dataclass
class NumericSpec:
    min: float | None = None
    max: float | None = None
    unit: LocalizedText | None = None
    integer_only: bool = False


@dataclass
class OpenSpec:
    max_length: int = 500
    placeholder: LocalizedText | None = None


@dataclass
class MultiSelectLimits:
    min: int = 1
    max: int | None = None


@dataclass
class Question:
    question_id: str
    code: str
    text: LocalizedText
    question_type: str
    construct_id: str | None = None
    reverse_coded: bool = False
    attention_check: bool = False
    attention_expected_value: str | None = None
    required: bool = True
    source: str = QUESTION_SOURCE_GENERATED
    options: list[Option] = field(default_factory=list)
    scale_spec: ScaleSpec | None = None
    multi_select_limits: MultiSelectLimits | None = None
    numeric_spec: NumericSpec | None = None
    open_spec: OpenSpec | None = None
    physical_encoding_hint: str = "delimited_single_column"
    display_logic: dict[str, Any] | None = None


@dataclass
class Section:
    section_id: str
    title: LocalizedText
    purpose: str
    intro: LocalizedText | None = None
    randomize_questions: bool = False
    questions: list[Question] = field(default_factory=list)


@dataclass
class Construct:
    construct_id: str
    name: LocalizedText
    definition: LocalizedText | None = None
    expected_direction: str | None = None


@dataclass
class ResponseMetadataSpec:
    """Reserved slots for response metadata. Nothing collects these yet.

    ``enabled`` stays False until a collection layer exists. When one arrives,
    a self-hosted collector writes the columns named here, and a third-party
    platform is adapted by filling ``source_mappings`` with
    {platform column name: canonical name} — no downstream change required.
    """

    schema_version: int = 1
    enabled: bool = False
    column_prefix: str = DEFAULT_METADATA_PREFIX
    fields: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "duration_total_seconds": {"column": "_meta_duration_total", "dtype": "numeric"},
            "per_question_dwell": {"column_pattern": "_meta_dwell_{question_id}", "dtype": "numeric"},
            "dropout_position": {"column": "_meta_dropout_at", "dtype": "question_id"},
            "option_order_seed": {"column": "_meta_option_seed", "dtype": "string"},
            "per_question_option_order": {
                "column_pattern": "_meta_order_{question_id}",
                "dtype": "string(csv of option values)",
            },
        }
    )
    source_mappings: dict[str, str] = field(default_factory=dict)
    collected_by: str | None = None


@dataclass
class Survey:
    survey_id: str
    title: LocalizedText
    primary_language: str = "zh-CN"
    # Languages this instrument is actually offered in. bilingual_completeness
    # checks only these: demanding two languages of a monolingual instrument
    # is a product opinion, not a methodology finding, and it drowns the
    # signal (it was over half of all issues on a real questionnaire).
    languages: list[str] = field(default_factory=lambda: ["zh-CN", "en"])
    # Drives MODE_POLICY. Defaults to self-administered because that is what
    # this tool generates; a transcribed interviewer instrument declares it.
    administration_mode: str = ADMIN_MODE_SELF
    description: LocalizedText | None = None
    created_at: float = 0.0
    estimated_minutes: int = 0
    constructs: list[Construct] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    response_metadata_spec: ResponseMetadataSpec = field(default_factory=ResponseMetadataSpec)
    generation_provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    # ---- navigation helpers -------------------------------------------------

    def iter_questions(self) -> Iterator[tuple[Section, Question]]:
        for section in self.sections:
            for question in section.questions:
                yield section, question

    def all_questions(self) -> list[Question]:
        return [question for _, question in self.iter_questions()]

    def question_by_id(self, question_id: str) -> Question | None:
        for question in self.all_questions():
            if question.question_id == question_id:
                return question
        return None

    def questions_for_construct(self, construct_id: str) -> list[Question]:
        """Construct membership is derived, never stored on Construct."""
        return [q for q in self.all_questions() if q.construct_id == construct_id]

    # ---- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Survey":
        return _survey_from_dict(payload)


def new_survey_id() -> str:
    return uuid.uuid4().hex


# ---- deserialization ---------------------------------------------------------
# asdict() flattens nested dataclasses, so rebuilding is explicit. Unknown keys
# are dropped rather than raising: a schema written by a newer version should
# still load, just without the fields this version does not know about.


def _pick(payload: dict[str, Any], *names: str) -> dict[str, Any]:
    return {name: payload[name] for name in names if name in payload and payload[name] is not None}


def _option_from_dict(payload: dict[str, Any]) -> Option:
    return Option(
        value=payload["value"],
        label=payload.get("label") or {},
        order=int(payload.get("order", 0)),
        exclusive=bool(payload.get("exclusive", False)),
    )


def _scale_from_dict(payload: dict[str, Any] | None) -> ScaleSpec | None:
    if not payload:
        return None
    return ScaleSpec(
        points=int(payload.get("points", 0)),
        min_value=int(payload.get("min_value", 1)),
        polarity=payload.get("polarity", POLARITY_BIPOLAR),
        min_label=payload.get("min_label"),
        max_label=payload.get("max_label"),
        mid_label=payload.get("mid_label"),
        labels=payload.get("labels"),
    )


def _question_from_dict(payload: dict[str, Any]) -> Question:
    limits = payload.get("multi_select_limits")
    numeric = payload.get("numeric_spec")
    open_spec = payload.get("open_spec")
    return Question(
        question_id=payload["question_id"],
        code=payload["code"],
        text=payload.get("text") or {},
        question_type=payload["question_type"],
        construct_id=payload.get("construct_id"),
        reverse_coded=bool(payload.get("reverse_coded", False)),
        attention_check=bool(payload.get("attention_check", False)),
        attention_expected_value=payload.get("attention_expected_value"),
        required=bool(payload.get("required", True)),
        source=payload.get("source", QUESTION_SOURCE_GENERATED),
        options=[_option_from_dict(o) for o in payload.get("options") or []],
        scale_spec=_scale_from_dict(payload.get("scale_spec")),
        multi_select_limits=MultiSelectLimits(**_pick(limits, "min", "max")) if limits else None,
        numeric_spec=NumericSpec(**_pick(numeric, "min", "max", "unit", "integer_only")) if numeric else None,
        open_spec=OpenSpec(**_pick(open_spec, "max_length", "placeholder")) if open_spec else None,
        physical_encoding_hint=payload.get("physical_encoding_hint", "delimited_single_column"),
        display_logic=payload.get("display_logic"),
    )


def _section_from_dict(payload: dict[str, Any]) -> Section:
    return Section(
        section_id=payload["section_id"],
        title=payload.get("title") or {},
        purpose=payload["purpose"],
        intro=payload.get("intro"),
        randomize_questions=bool(payload.get("randomize_questions", False)),
        questions=[_question_from_dict(q) for q in payload.get("questions") or []],
    )


def _survey_from_dict(payload: dict[str, Any]) -> Survey:
    metadata = payload.get("response_metadata_spec")
    return Survey(
        survey_id=payload["survey_id"],
        title=payload.get("title") or {},
        primary_language=payload.get("primary_language", "zh-CN"),
        languages=list(payload.get("languages") or ["zh-CN", "en"]),
        administration_mode=payload.get("administration_mode", ADMIN_MODE_SELF),
        description=payload.get("description"),
        created_at=float(payload.get("created_at", 0.0)),
        estimated_minutes=int(payload.get("estimated_minutes", 0)),
        constructs=[
            Construct(
                construct_id=c["construct_id"],
                name=c.get("name") or {},
                definition=c.get("definition"),
                expected_direction=c.get("expected_direction"),
            )
            for c in payload.get("constructs") or []
        ],
        sections=[_section_from_dict(s) for s in payload.get("sections") or []],
        response_metadata_spec=(
            ResponseMetadataSpec(
                **_pick(
                    metadata,
                    "schema_version",
                    "enabled",
                    "column_prefix",
                    "fields",
                    "source_mappings",
                    "collected_by",
                )
            )
            if metadata
            else ResponseMetadataSpec()
        ),
        generation_provenance=payload.get("generation_provenance") or {},
        schema_version=int(payload.get("schema_version", SCHEMA_VERSION)),
    )


def mode_policy(survey: "Survey") -> dict[str, Any]:
    """Rule parameters for this survey's administration mode."""
    return MODE_POLICY.get(survey.administration_mode, MODE_POLICY[ADMIN_MODE_SELF])
