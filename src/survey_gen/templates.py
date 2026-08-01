"""Local questionnaire templates. No LLM, no network, no API key.

This is not a fallback that exists to be embarrassing when the key is missing.
It is the path a first-time reader takes: clone, run, get a complete
questionnaire, export it, feed the result back through the analysis pipeline.
The LLM author (a later batch) rewrites the prose; the structure below is what
it rewrites, and the structure is what the methodology rules actually check.

Design note on the recommendation item
--------------------------------------
``service_satisfaction`` carries a 0-10 recommendation question. The detector
cannot recognise a zero-based scale from values alone (see
docs/detection-benchmark.md), so a recovered CSV without its schema reads that
column as numeric.

That is not a reason to avoid 0-10 here. 0-10 is the standard form for
recommendation intent, life-satisfaction ladders and much of the WHO
instrument family; a template library without one is missing a product
capability, not dodging a technical problem. Shaping the templates around what
the detector happens to recognise would be letting the rules decide what a good
questionnaire looks like.

The gap is handled where it belongs — the schema travels with the export, and
``src.survey_gen.roundtrip`` resolves the column from the declaration. The
end-to-end test asserts both paths separately so the difference between them
stays visible rather than papered over.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SINGLE,
    QUESTION_TYPE_SCALE,
)
from src.survey_gen.schema import (
    ADMIN_MODE_SELF,
    POLARITY_BIPOLAR,
    POLARITY_UNIPOLAR,
    SECTION_PURPOSE_ATTENTION,
    SECTION_PURPOSE_CONSTRUCT,
    SECTION_PURPOSE_DEMOGRAPHIC,
    SECTION_PURPOSE_OPEN_FEEDBACK,
    SECTION_PURPOSE_SCREENING,
    Construct,
    NumericSpec,
    OpenSpec,
    Option,
    Question,
    ScaleSpec,
    Section,
    Survey,
    localized,
    new_survey_id,
)

# ---- shared building blocks --------------------------------------------------

AGREE_LABELS = [
    localized("非常不同意", "Strongly disagree"),
    localized("比较不同意", "Disagree"),
    localized("一般", "Neutral"),
    localized("比较同意", "Agree"),
    localized("非常同意", "Strongly agree"),
]


def agree_scale() -> ScaleSpec:
    """The 5-point bipolar agreement scale most of these templates use."""
    return ScaleSpec(
        points=5,
        min_value=1,
        polarity=POLARITY_BIPOLAR,
        min_label=localized("非常不同意", "Strongly disagree"),
        max_label=localized("非常同意", "Strongly agree"),
        mid_label=localized("一般", "Neutral"),
        labels=[dict(item) for item in AGREE_LABELS],
    )


def recommendation_scale() -> ScaleSpec:
    """0-10 recommendation intent: eleven points, unipolar, anchored at both ends.

    Unipolar because the low end is an absence of intent, not its opposite; no
    per-point labels because the numbers carry the meaning, which is exactly how
    this format is fielded.
    """
    return ScaleSpec(
        points=11,
        min_value=0,
        polarity=POLARITY_UNIPOLAR,
        min_label=localized("完全不可能", "Not at all likely"),
        max_label=localized("极有可能", "Extremely likely"),
    )


def _options(pairs) -> list[Option]:
    return [
        Option(value=value, label=localized(zh, en), order=index, exclusive=exclusive,
               residual=residual)
        for index, (value, zh, en, exclusive, residual) in enumerate(pairs)
    ]


def _scale_item(qid, code, zh, en, construct_id=None, reverse=False, spec=None) -> Question:
    return Question(
        question_id=qid,
        code=code,
        text=localized(zh, en),
        question_type=QUESTION_TYPE_SCALE,
        construct_id=construct_id,
        reverse_coded=reverse,
        scale_spec=spec or agree_scale(),
    )


def _single(qid, code, zh, en, pairs) -> Question:
    return Question(
        question_id=qid,
        code=code,
        text=localized(zh, en),
        question_type=QUESTION_TYPE_SINGLE,
        options=_options(pairs),
    )


def _attention_check(qid, code) -> Question:
    """An instructed-response item. Self-administered questionnaires need one."""
    return Question(
        question_id=qid,
        code=code,
        text=localized(
            "本题请选择「比较同意」，以确认您在认真作答。",
            'For this item please choose "Agree" to confirm you are reading carefully.',
        ),
        question_type=QUESTION_TYPE_SINGLE,
        attention_check=True,
        attention_expected_value="a4",
        options=_options([
            ("a1", "非常不同意", "Strongly disagree", False, False),
            ("a2", "比较不同意", "Disagree", False, False),
            ("a3", "一般", "Neutral", False, False),
            ("a4", "比较同意", "Agree", False, False),
            ("a5", "非常同意", "Strongly agree", False, False),
        ]),
    )


def _open_feedback(qid, code, zh, en) -> Question:
    return Question(
        question_id=qid,
        code=code,
        text=localized(zh, en),
        question_type=QUESTION_TYPE_OPEN,
        required=False,
        open_spec=OpenSpec(max_length=500, placeholder=localized("选填", "Optional")),
    )


def _demographics(prefix: str) -> Section:
    """Demographics last, per the ordering rule: asking them first raises
    drop-off and primes the answers that follow."""
    return Section(
        section_id="%s_DEMO" % prefix,
        title=localized("基本信息", "About you"),
        purpose=SECTION_PURPOSE_DEMOGRAPHIC,
        questions=[
            _single("QD1", "gender", "您的性别是？", "What is your gender?", [
                ("f", "女", "Woman", False, False),
                ("m", "男", "Man", False, False),
                ("o", "其他或不愿透露", "Other or prefer not to say", False, True),
            ]),
            _single("QD2", "age_group", "您所在的年龄段是？", "Which age group are you in?", [
                ("u18", "18 岁以下", "Under 18", False, False),
                ("a1825", "18-25 岁", "18-25", False, False),
                ("a2635", "26-35 岁", "26-35", False, False),
                ("a3645", "36-45 岁", "36-45", False, False),
                ("o46", "46 岁及以上", "46 or older", False, False),
            ]),
        ],
    )


# ---- templates ---------------------------------------------------------------


def _service_satisfaction() -> Survey:
    return Survey(
        survey_id=new_survey_id(),
        title=localized("服务体验调查", "Service experience survey"),
        description=localized(
            "了解您对本次服务的真实感受，用于改进服务流程。",
            "How you experienced this service, so the process can be improved.",
        ),
        primary_language="zh-CN",
        created_at=time.time(),
        estimated_minutes=5,
        administration_mode=ADMIN_MODE_SELF,
        constructs=[
            Construct("c_service", localized("服务体验", "Service experience"),
                      localized("受访者对服务过程与人员的主观评价。",
                                "How the respondent judges the service process and staff.")),
            Construct("c_value", localized("价值感知", "Perceived value"),
                      localized("受访者对付出与所得是否相称的判断。",
                                "Whether what they paid matches what they got.")),
        ],
        sections=[
            Section("S1", localized("资格甄别", "Screening"), SECTION_PURPOSE_SCREENING,
                    intro=localized("请先回答下面这道题。", "Please answer the question below first."),
                    questions=[
                        _single("Q01", "used_recently",
                                "您最近三个月使用过本服务吗？",
                                "Have you used this service in the past three months?",
                                [("yes", "是", "Yes", False, False),
                                 ("no", "否", "No", False, False)]),
                    ]),
            Section("S2", localized("服务体验", "Service experience"), SECTION_PURPOSE_CONSTRUCT,
                    intro=localized("请根据您的实际感受作答。", "Please answer from your own experience."),
                    questions=[
                        _scale_item("Q02", "srv_response", "客服人员的响应速度让我满意。",
                                    "The support team replies quickly enough for me.", "c_service"),
                        _scale_item("Q03", "srv_resolve", "客服人员能够解决我提出的问题。",
                                    "The support team resolves the problems I raise.", "c_service"),
                        _scale_item("Q04", "srv_respect", "客服人员的态度让我感到被尊重。",
                                    "The support team treats me with respect.", "c_service"),
                        _scale_item("Q05", "srv_wait", "我要等很久才能收到回复。",
                                    "I wait a long time before I get a reply.", "c_service",
                                    reverse=True),
                    ]),
            Section("S3", localized("价值感知", "Perceived value"), SECTION_PURPOSE_CONSTRUCT,
                    questions=[
                        _scale_item("Q06", "val_worth", "这项服务的价格让我觉得物有所值。",
                                    "The price of this service feels worth it to me.", "c_value"),
                        _scale_item("Q07", "val_expect", "这项服务达到了我事先的预期。",
                                    "This service met the expectations I had beforehand.", "c_value"),
                        _scale_item("Q08", "val_again", "下次有需要时我还会选择它。",
                                    "I would choose it again next time I need one.", "c_value"),
                    ]),
            # A single-item measure, so no construct: reliability is not defined
            # over one item and the validator would rightly object.
            Section("S4", localized("推荐意愿", "Likelihood to recommend"),
                    SECTION_PURPOSE_CONSTRUCT,
                    intro=localized("0 表示完全不可能，10 表示极有可能。",
                                    "0 means not at all likely, 10 means extremely likely."),
                    questions=[
                        _scale_item("Q09", "recommend_intent",
                                    "您有多大可能把本服务推荐给别人？",
                                    "How likely are you to recommend this service to someone else?",
                                    spec=recommendation_scale()),
                    ]),
            Section("S5", localized("作答确认", "Response check"), SECTION_PURPOSE_ATTENTION,
                    questions=[_attention_check("Q10", "attn_check")]),
            Section("S6", localized("补充意见", "Further comments"), SECTION_PURPOSE_OPEN_FEEDBACK,
                    questions=[_open_feedback("Q11", "open_feedback",
                                              "如果有可以改进的地方，请写下您的想法。",
                                              "If anything could be improved, write your thoughts here.")]),
            _demographics("S7"),
        ],
        generation_provenance={
            "source": "built-in template",
            "template": "service_satisfaction",
            "llm_model": None,
            "fallback_used": False,
        },
    )


def _product_usage() -> Survey:
    return Survey(
        survey_id=new_survey_id(),
        title=localized("产品使用情况调查", "Product usage survey"),
        description=localized(
            "了解您使用本产品的方式与感受。",
            "How you use this product and how it feels to use it.",
        ),
        primary_language="zh-CN",
        created_at=time.time(),
        estimated_minutes=6,
        administration_mode=ADMIN_MODE_SELF,
        constructs=[
            Construct("c_ease", localized("易用性", "Ease of use"),
                      localized("受访者使用产品时感到的顺畅程度。",
                                "How smooth the respondent finds the product to use.")),
            Construct("c_useful", localized("有用性", "Usefulness"),
                      localized("产品是否帮助受访者完成其目标。",
                                "Whether the product helps the respondent get things done.")),
        ],
        sections=[
            Section("S1", localized("资格甄别", "Screening"), SECTION_PURPOSE_SCREENING,
                    questions=[
                        _single("Q01", "is_user", "您目前在使用本产品吗？",
                                "Are you currently using this product?",
                                [("yes", "是", "Yes", False, False),
                                 ("no", "否", "No", False, False)]),
                    ]),
            Section("S2", localized("使用情况", "Usage"), SECTION_PURPOSE_CONSTRUCT,
                    questions=[
                        Question(
                            question_id="Q02", code="use_days_per_week",
                            text=localized("最近一周里，您有几天用到本产品？",
                                           "On how many days in the past week did you use it?"),
                            question_type=QUESTION_TYPE_NUMERIC,
                            numeric_spec=NumericSpec(min=0, max=7, integer_only=True,
                                                     unit=localized("天", "days")),
                        ),
                        Question(
                            question_id="Q03", code="use_channels",
                            text=localized("您通过哪些方式使用本产品？",
                                           "Which ways do you use this product?"),
                            question_type=QUESTION_TYPE_MULTIPLE,
                            options=_options([
                                ("web", "网页版", "Web", False, False),
                                ("app", "手机应用", "Mobile app", False, False),
                                ("desktop", "桌面客户端", "Desktop client", False, False),
                                ("none", "以上都没有", "None of these", True, True),
                            ]),
                        ),
                    ]),
            Section("S3", localized("易用性", "Ease of use"), SECTION_PURPOSE_CONSTRUCT,
                    questions=[
                        _scale_item("Q04", "ease_learn", "我很快就学会了怎么用它。",
                                    "I learned how to use it quickly.", "c_ease"),
                        _scale_item("Q05", "ease_find", "我能轻松找到需要的功能。",
                                    "I can easily find the features I need.", "c_ease"),
                        _scale_item("Q06", "ease_confuse", "使用过程中我常常感到困惑。",
                                    "I often feel confused while using it.", "c_ease", reverse=True),
                    ]),
            Section("S4", localized("有用性", "Usefulness"), SECTION_PURPOSE_CONSTRUCT,
                    questions=[
                        _scale_item("Q07", "use_help", "它帮助我更快完成任务。",
                                    "It helps me finish tasks faster.", "c_useful"),
                        _scale_item("Q08", "use_fit", "它满足了我的主要需要。",
                                    "It meets my main needs.", "c_useful"),
                        _scale_item("Q09", "use_worth", "花时间使用它是值得的。",
                                    "The time I spend on it is worth it.", "c_useful"),
                    ]),
            Section("S5", localized("作答确认", "Response check"), SECTION_PURPOSE_ATTENTION,
                    questions=[_attention_check("Q10", "attn_check")]),
            Section("S6", localized("补充意见", "Further comments"), SECTION_PURPOSE_OPEN_FEEDBACK,
                    questions=[_open_feedback("Q11", "open_feedback",
                                              "您希望本产品增加或改进什么？",
                                              "What would you like added or improved?")]),
            _demographics("S7"),
        ],
        generation_provenance={
            "source": "built-in template",
            "template": "product_usage",
            "llm_model": None,
            "fallback_used": False,
        },
    )


def _course_evaluation() -> Survey:
    return Survey(
        survey_id=new_survey_id(),
        title=localized("课程评价问卷", "Course evaluation survey"),
        description=localized(
            "了解学生对课程内容与教学方式的评价。",
            "How students rate the course content and the way it is taught.",
        ),
        primary_language="zh-CN",
        created_at=time.time(),
        estimated_minutes=5,
        administration_mode=ADMIN_MODE_SELF,
        constructs=[
            Construct("c_content", localized("课程内容", "Course content"),
                      localized("学生对课程内容本身的评价。",
                                "How students judge the content itself.")),
            Construct("c_teaching", localized("教学方式", "Teaching approach"),
                      localized("学生对授课形式与节奏的评价。",
                                "How students judge the delivery and pacing.")),
        ],
        sections=[
            Section("S1", localized("资格甄别", "Screening"), SECTION_PURPOSE_SCREENING,
                    questions=[
                        _single("Q01", "attended", "本学期您上过这门课吗？",
                                "Did you take this course this term?",
                                [("yes", "是", "Yes", False, False),
                                 ("no", "否", "No", False, False)]),
                    ]),
            Section("S2", localized("课程内容", "Course content"), SECTION_PURPOSE_CONSTRUCT,
                    questions=[
                        # "clearly organised" tripped the leading-question rule:
                        # the adverb asserts the quality the item is asking about.
                        # The template changed, not the rule.
                        _scale_item("Q02", "content_clear", "课程内容的组织是有条理的。",
                                    "The course content is well organised.", "c_content"),
                        _scale_item("Q03", "content_level", "课程难度适合我的基础。",
                                    "The difficulty suits my background.", "c_content"),
                        _scale_item("Q04", "content_useful", "课程内容对我有实际帮助。",
                                    "The content is of practical use to me.", "c_content"),
                    ]),
            Section("S3", localized("教学方式", "Teaching approach"), SECTION_PURPOSE_CONSTRUCT,
                    questions=[
                        _scale_item("Q05", "teach_pace", "授课节奏让我跟得上。",
                                    "The pace lets me keep up.", "c_teaching"),
                        _scale_item("Q06", "teach_example", "课堂例子帮助我理解概念。",
                                    "The examples help me understand the concepts.", "c_teaching"),
                        _scale_item("Q07", "teach_lost", "我在课上经常跟不上讲解。",
                                    "I often lose the thread during class.", "c_teaching",
                                    reverse=True),
                    ]),
            Section("S4", localized("作答确认", "Response check"), SECTION_PURPOSE_ATTENTION,
                    questions=[_attention_check("Q08", "attn_check")]),
            Section("S5", localized("补充意见", "Further comments"), SECTION_PURPOSE_OPEN_FEEDBACK,
                    questions=[_open_feedback("Q09", "open_feedback",
                                              "对这门课，您还有什么想说的？",
                                              "Anything else you would like to say about the course?")]),
            _demographics("S6"),
        ],
        generation_provenance={
            "source": "built-in template",
            "template": "course_evaluation",
            "llm_model": None,
            "fallback_used": False,
        },
    )


@dataclass(frozen=True)
class TemplateSpec:
    key: str
    name: dict[str, str]
    description: dict[str, str]
    build: Callable[[], Survey]


TEMPLATES: tuple[TemplateSpec, ...] = (
    TemplateSpec(
        key="service_satisfaction",
        name=localized("服务体验调查", "Service experience"),
        description=localized(
            "两个构念加一道 0-10 推荐意愿题，适合服务后回访。",
            "Two constructs plus a 0-10 recommendation item; suits post-service follow-up.",
        ),
        build=_service_satisfaction,
    ),
    TemplateSpec(
        key="product_usage",
        name=localized("产品使用情况", "Product usage"),
        description=localized(
            "使用行为加易用性与有用性两个构念。",
            "Usage behaviour plus ease-of-use and usefulness constructs.",
        ),
        build=_product_usage,
    ),
    TemplateSpec(
        key="course_evaluation",
        name=localized("课程评价", "Course evaluation"),
        description=localized(
            "课程内容与教学方式两个构念，适合期末评教。",
            "Content and teaching constructs; suits end-of-term evaluation.",
        ),
        build=_course_evaluation,
    ),
)

TEMPLATES_BY_KEY = {spec.key: spec for spec in TEMPLATES}


def list_templates() -> list[dict]:
    """Template catalogue for the UI. Available with no API key configured."""
    return [
        {"key": spec.key, "name": spec.name, "description": spec.description}
        for spec in TEMPLATES
    ]


def build_template(key: str) -> Survey:
    spec = TEMPLATES_BY_KEY.get(key)
    if spec is None:
        raise KeyError("Unknown template: %s" % key)
    return spec.build()
