from __future__ import annotations

from src.field_semantics import (
    FIELD_ROLE_BOOLEAN,
    FIELD_ROLE_CATEGORICAL,
    FIELD_ROLE_DATETIME,
    FIELD_ROLE_EMPTY,
    FIELD_ROLE_FREE_TEXT,
    FIELD_ROLE_IDENTIFIER,
    FIELD_ROLE_MULTI_VALUE,
    FIELD_ROLE_NUMERIC,
)
from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_EMPTY,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
)


LANGUAGE_OPTIONS = ["en", "zh-CN"]
DEFAULT_LANGUAGE = "en"


TRANSLATIONS = {
    "en": {
        "language_name": "English",
        "page_title": "SurveyMind",
        "app_title": "SurveyMind",
        "app_subtitle": "AI-assisted analytics for surveys and general datasets",
        "app_intro": (
            "SurveyMind analyzes both survey responses and general tabular data. Upload a CSV or "
            "Excel file and it detects the dataset mode, profiles every field, builds a data "
            "overview with quality checks and relationships, recommends charts and analyses, and "
            "generates a structured markdown report."
        ),
        "sidebar_settings": "Settings",
        "sidebar_language": "Language",
        "sidebar_language_help": "Choose the language used in the interface and generated report.",
        "section_data_upload": "Data Upload",
        "upload_label": "Upload a CSV or Excel dataset",
        "upload_help": "SurveyMind accepts .csv, .xlsx, and .xls files — survey exports or any tabular data.",
        "using_demo_caption": "Using bundled demo dataset from `{filename}`.",
        "using_upload_caption": "Using uploaded file: `{filename}`",
        "section_mode_detection": "Dataset Mode",
        "mode_detected_caption": "Auto-detected mode: **{mode}** (survey score {survey_score}, general score {general_score})",
        "mode_override_label": "Analysis mode",
        "mode_signals_label": "Detection signals",
        "mode_general": "General dataset",
        "mode_survey": "Survey dataset",
        "mode_mixed": "Mixed dataset",
        "section_field_roles": "Field Type Detection",
        "field_roles_desc": (
            "Each column is classified into a generic field role (metric, dimension, date, ID, ...). "
            "You can override any role below if the detection is off."
        ),
        "reset_field_roles": "Reset Roles to Detected Values",
        "manual_role_override": "Manual Field Role Override",
        "detected_role_label": "Detected Role",
        "active_role_label": "Active Role",
        "evidence_label": "Evidence",
        "section_data_overview": "Data Overview",
        "metric_duplicates": "Duplicate Rows",
        "overview_tab_fields": "Fields",
        "overview_tab_numeric": "Numeric Fields",
        "overview_tab_categorical": "Categorical Fields",
        "overview_tab_datetime": "Date Fields",
        "overview_tab_relations": "Relationships",
        "overview_tab_quality": "Data Quality",
        "overview_findings_title": "Main findings",
        "no_numeric_fields": "No numeric fields were detected.",
        "no_categorical_fields": "No categorical fields were detected.",
        "no_datetime_fields": "No date or time fields were detected.",
        "no_relations": "No strong correlations or group differences were detected in the current data.",
        "correlations_title": "Correlations between numeric fields",
        "group_differences_title": "Notable group differences",
        "choose_categorical_field": "Choose a categorical field",
        "label_field": "Field",
        "section_suggestions": "Suggested Analyses",
        "suggestions_desc": "Based on the detected fields, these analyses look most promising:",
        "section_recommended_charts": "Recommended Charts",
        "no_recommended_charts": "No charts could be recommended for the current data.",
        "section_ai_insights": "AI Interpretation",
        "ai_persona_caption": "Persona in use: {persona}",
        "ai_persona_general": "general data analyst",
        "ai_persona_survey": "survey analyst",
        "ai_persona_mixed": "mixed-data analyst",
        "ai_not_configured": (
            "AI service is not configured (set LLM_API_KEY / LLM_BASE_URL / LLM_MODEL in .env). "
            "All rule-based analysis above remains fully available."
        ),
        "ai_generate_button": "Generate AI interpretation",
        "ai_generating": "Calling the AI service...",
        "ai_failed_notice": (
            "The AI service call failed. The rule-based analysis and report remain fully available."
        ),
        "ai_grounding_note": "AI conclusions are grounded in the locally computed statistics shown above.",
        "no_data_insufficient": "The current data is not sufficient to draw further conclusions.",
        "report_title_general": "Data Analysis Report",
        "report_title_mixed": "Mixed Dataset Analysis Report",
        "report_fields_distribution": "Fields and Distributions",
        "report_variable_relations": "Variable Relationships",
        "report_next_steps": "Suggested Next Analyses",
        "report_analysis_limitations": "Analysis Limitations",
        "plot_correlation_heatmap": "Correlation heatmap of numeric fields",
        "plot_time_trend": "Monthly record trend for {column}",
        "label_period": "Month",
        "label_record_count": "Records",
        "metric_rows": "Rows",
        "metric_columns": "Columns",
        "metric_missing_ratio": "Missing Value Ratio",
        "first_five_rows": "First 5 rows",
        "column_names": "Column Names",
        "column_metadata": "Column Metadata",
        "section_question_detection": "Question Type Detection (Survey Mode)",
        "question_detection_desc": (
            "SurveyMind detects question types automatically, but you can manually override any column "
            "below if the dataset uses unusual formatting."
        ),
        "reset_overrides": "Reset Overrides to Detected Types",
        "manual_override": "Manual Question Type Override",
        "detected_as_help": "Automatically detected as: {question_type}",
        "column_name_label": "Column Name",
        "detected_type_label": "Detected Type",
        "active_type_label": "Active Type",
        "section_descriptive_stats": "Descriptive Statistics",
        "tab_numeric": "Numeric Questions",
        "tab_scale": "Scale Questions",
        "tab_categorical": "Categorical Questions",
        "tab_profile": "Sample Profile",
        "no_numeric": "No numeric questions were detected.",
        "no_scale": "No scale questions were detected.",
        "no_categorical": "No categorical questions were detected.",
        "no_profile": "No standard profile fields were detected.",
        "choose_scale_question": "Choose a scale question",
        "scale_distribution": "Score distribution",
        "choose_categorical_question": "Choose a categorical question",
        "section_visualization": "Visualization Explorer",
        "chart_tab_categorical": "Categorical Bar Chart",
        "chart_tab_scale": "Scale Bar Chart",
        "chart_tab_numeric": "Numeric Histogram",
        "chart_tab_box": "Grouped Box Plot",
        "categorical_variable": "Categorical variable",
        "scale_variable": "Scale question",
        "numeric_variable": "Numeric variable",
        "numeric_or_scale_variable": "Numeric or scale variable for box plot",
        "grouping_variable": "Grouping variable",
        "display_mode": "Display mode",
        "display_percentage": "Percentage",
        "display_count": "Count",
        "no_categorical_chart": "No categorical variables are available for bar charts.",
        "no_scale_chart": "No scale questions are available for scale charts.",
        "no_numeric_chart": "No numeric variables are available for histograms.",
        "boxplot_requirement": "Box plots need at least one numeric or scale variable and one categorical variable.",
        "section_cross_analysis": "Cross-Analysis Explorer",
        "target_variable": "Target variable",
        "cross_analysis_requirement": (
            "At least one grouping variable and one additional analyzable target are required for cross-analysis."
        ),
        "grouped_summary_stats": "Grouped summary statistics",
        "cross_display_mode": "Cross-tab display mode",
        "cross_raw_count": "Raw Count",
        "cross_row_percentage": "Row Percentage",
        "cross_column_percentage": "Column Percentage",
        "cross_table_title": "{mode} table",
        "cross_chart_type": "Cross-tab chart type",
        "chart_type_stacked": "stacked",
        "chart_type_heatmap": "heatmap",
        "cross_open_ended_warning": "Open-ended text fields are not supported for cross-analysis in this MVP.",
        "section_report": "Auto-Generated Report",
        "download_report": "Download Report (.md)",
        "download_report_filename": "surveymind_report_en.md",
        "question_type_summary_title": "Question Type Summary",
        "report_title": "SurveyMind Analysis Report",
        "report_dataset_overview": "Dataset Overview",
        "report_data_quality": "Data Quality Summary",
        "report_key_findings": "Key Findings",
        "report_group_findings": "Group Comparison Findings",
        "report_recommendations": "Recommendations",
        "report_limitations": "Limitations",
        "report_no_findings": "No key findings were generated.",
        "report_no_cross_analysis": "No cross-analysis was selected when this report was generated.",
        "question_type_numeric": "numeric question",
        "question_type_scale": "scale question",
        "question_type_single": "single-choice question",
        "question_type_multiple": "multiple-choice question",
        "question_type_open": "open-ended text question",
        "plot_distribution_of": "Distribution of {column}",
        "plot_score_distribution": "Score distribution for {column}",
        "plot_histogram_of": "Histogram of {column}",
        "plot_boxplot_of": "{numeric_column} by {group_column}",
        "plot_heatmap_title": "Cross-tabulation Heatmap ({mode})",
        "plot_stacked_title": "Cross-tabulation Stacked Bar Chart ({mode})",
        "label_response": "Response",
        "label_score": "Score",
        "label_count": "Count",
        "label_percentage": "Percentage",
        "label_grouping_variable": "Grouping Variable",
        "label_target_variable": "Target Variable",
        "label_row_percentage": "Row Percentage",
        "label_column_percentage": "Column Percentage",
        "label_interpretation": "Interpretation",
        "scale_level_low": "relatively low",
        "scale_level_moderate": "moderate",
        "scale_level_high": "relatively high",
        "scale_level_Insufficient data": "Insufficient data",
    },
    "zh-CN": {
        "language_name": "中文",
        "page_title": "SurveyMind 数据分析助手",
        "app_title": "SurveyMind",
        "app_subtitle": "支持问卷与通用表格的 AI 数据分析助手",
        "app_intro": (
            "SurveyMind 既能分析问卷数据，也能分析普通表格数据。上传 CSV 或 Excel 文件后，"
            "系统会自动识别数据模式、分析每个字段的类型，生成包含数据质量检查和变量关系的概览，"
            "推荐图表与分析方向，并输出结构化的分析报告。"
        ),
        "sidebar_settings": "设置",
        "sidebar_language": "界面语言",
        "sidebar_language_help": "选择界面与自动报告使用的语言。",
        "section_data_upload": "数据上传",
        "upload_label": "上传 CSV 或 Excel 数据集",
        "upload_help": "支持 .csv、.xlsx 和 .xls 文件——问卷导出或任意表格数据均可。",
        "using_demo_caption": "当前使用内置示例数据集：`{filename}`。",
        "using_upload_caption": "当前使用上传文件：`{filename}`",
        "section_mode_detection": "数据模式识别",
        "mode_detected_caption": "系统自动识别为：**{mode}**（问卷特征得分 {survey_score}，通用表格得分 {general_score}）",
        "mode_override_label": "分析模式",
        "mode_signals_label": "识别依据",
        "mode_general": "普通数据集",
        "mode_survey": "问卷数据",
        "mode_mixed": "混合数据集",
        "section_field_roles": "字段类型识别",
        "field_roles_desc": (
            "系统会将每个字段识别为通用字段角色（数值指标、分类维度、日期、ID 等）。"
            "如果识别有偏差，可以在下方手动修改。"
        ),
        "reset_field_roles": "重置为自动识别结果",
        "manual_role_override": "手动修改字段角色",
        "detected_role_label": "自动识别角色",
        "active_role_label": "当前使用角色",
        "evidence_label": "识别依据",
        "section_data_overview": "数据概览",
        "metric_duplicates": "重复行数",
        "overview_tab_fields": "字段总览",
        "overview_tab_numeric": "数值字段",
        "overview_tab_categorical": "分类字段",
        "overview_tab_datetime": "日期字段",
        "overview_tab_relations": "变量关系",
        "overview_tab_quality": "数据质量",
        "overview_findings_title": "主要发现",
        "no_numeric_fields": "未识别到数值字段。",
        "no_categorical_fields": "未识别到分类字段。",
        "no_datetime_fields": "未识别到日期或时间字段。",
        "no_relations": "当前数据中未检测到明显的相关关系或分组差异。",
        "correlations_title": "数值字段相关性",
        "group_differences_title": "值得关注的分组差异",
        "choose_categorical_field": "选择一个分类字段",
        "label_field": "字段",
        "section_suggestions": "智能分析建议",
        "suggestions_desc": "根据识别出的字段，下面这些分析方向最值得优先尝试：",
        "section_recommended_charts": "推荐图表",
        "no_recommended_charts": "当前数据暂无可推荐的图表。",
        "section_ai_insights": "AI 智能解读",
        "ai_persona_caption": "当前使用的分析角色：{persona}",
        "ai_persona_general": "通用数据分析师",
        "ai_persona_survey": "问卷分析师",
        "ai_persona_mixed": "混合数据分析师",
        "ai_not_configured": (
            "尚未配置 AI 服务（请在 .env 中设置 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL）。"
            "上方所有基于规则的分析结果不受影响，仍然完整可用。"
        ),
        "ai_generate_button": "生成 AI 解读",
        "ai_generating": "正在调用 AI 服务……",
        "ai_failed_notice": "AI 服务调用失败。基础数据分析与报告不受影响，仍然完整可用。",
        "ai_grounding_note": "AI 结论完全基于上方由本地计算得出的统计结果。",
        "no_data_insufficient": "根据当前数据无法进一步判断。",
        "report_title_general": "数据分析报告",
        "report_title_mixed": "混合数据集分析报告",
        "report_fields_distribution": "字段与分布",
        "report_variable_relations": "变量关系",
        "report_next_steps": "后续分析建议",
        "report_analysis_limitations": "分析限制",
        "plot_correlation_heatmap": "数值字段相关性热力图",
        "plot_time_trend": "{column} 的按月记录趋势",
        "label_period": "月份",
        "label_record_count": "记录数",
        "metric_rows": "行数",
        "metric_columns": "列数",
        "metric_missing_ratio": "缺失值比例",
        "first_five_rows": "前 5 行数据",
        "column_names": "列名",
        "column_metadata": "字段信息",
        "section_question_detection": "题型识别（问卷模式）",
        "question_detection_desc": (
            "SurveyMind 会先自动识别题型。如果你的原始问卷格式比较特殊，也可以在下方手动修正。"
        ),
        "reset_overrides": "重置为自动识别结果",
        "manual_override": "手动修改题型",
        "detected_as_help": "系统自动识别为：{question_type}",
        "column_name_label": "字段名",
        "detected_type_label": "自动识别题型",
        "active_type_label": "当前使用题型",
        "section_descriptive_stats": "描述性统计",
        "tab_numeric": "数值题",
        "tab_scale": "量表题",
        "tab_categorical": "类别题",
        "tab_profile": "样本画像",
        "no_numeric": "未识别到数值题。",
        "no_scale": "未识别到量表题。",
        "no_categorical": "未识别到类别题。",
        "no_profile": "未自动识别出典型样本画像字段。",
        "choose_scale_question": "选择一个量表题",
        "scale_distribution": "各分值分布",
        "choose_categorical_question": "选择一个类别题",
        "section_visualization": "可视化探索",
        "chart_tab_categorical": "类别题柱状图",
        "chart_tab_scale": "量表题分值图",
        "chart_tab_numeric": "数值题直方图",
        "chart_tab_box": "分组箱线图",
        "categorical_variable": "类别变量",
        "scale_variable": "量表题变量",
        "numeric_variable": "数值变量",
        "numeric_or_scale_variable": "用于箱线图的数值或量表变量",
        "grouping_variable": "分组变量",
        "display_mode": "显示方式",
        "display_percentage": "百分比",
        "display_count": "数量",
        "no_categorical_chart": "当前没有可用于柱状图的类别变量。",
        "no_scale_chart": "当前没有可用于量表图的量表题。",
        "no_numeric_chart": "当前没有可用于直方图的数值变量。",
        "boxplot_requirement": "箱线图至少需要一个数值或量表变量，以及一个类别分组变量。",
        "section_cross_analysis": "分组交叉分析",
        "target_variable": "目标变量",
        "cross_analysis_requirement": "交叉分析至少需要一个分组变量，以及另一个可分析的目标变量。",
        "grouped_summary_stats": "分组汇总统计",
        "cross_display_mode": "交叉表显示方式",
        "cross_raw_count": "原始数量",
        "cross_row_percentage": "行百分比",
        "cross_column_percentage": "列百分比",
        "cross_table_title": "{mode}表",
        "cross_chart_type": "交叉图表类型",
        "chart_type_stacked": "堆叠柱状图",
        "chart_type_heatmap": "热力图",
        "cross_open_ended_warning": "当前 MVP 版本暂不支持将开放题文本直接用于交叉分析。",
        "section_report": "自动生成报告",
        "download_report": "下载报告（.md）",
        "download_report_filename": "surveymind_分析报告.md",
        "question_type_summary_title": "题型识别概况",
        "report_title": "SurveyMind 问卷分析报告",
        "report_dataset_overview": "数据集概览",
        "report_data_quality": "数据质量概况",
        "report_key_findings": "主要发现",
        "report_group_findings": "分组比较发现",
        "report_recommendations": "分析建议",
        "report_limitations": "局限性说明",
        "report_no_findings": "本次未生成明显的关键发现。",
        "report_no_cross_analysis": "本次生成报告时尚未选择分组交叉分析结果。",
        "question_type_numeric": "数值题",
        "question_type_scale": "量表题",
        "question_type_single": "单选题",
        "question_type_multiple": "多选题",
        "question_type_open": "开放题",
        "plot_distribution_of": "{column} 的分布",
        "plot_score_distribution": "{column} 的分值分布",
        "plot_histogram_of": "{column} 的直方图",
        "plot_boxplot_of": "{group_column} 下的 {numeric_column} 分布",
        "plot_heatmap_title": "交叉分析热力图（{mode}）",
        "plot_stacked_title": "交叉分析堆叠柱状图（{mode}）",
        "label_response": "选项",
        "label_score": "分值",
        "label_count": "数量",
        "label_percentage": "百分比",
        "label_grouping_variable": "分组变量",
        "label_target_variable": "目标变量",
        "label_row_percentage": "行百分比",
        "label_column_percentage": "列百分比",
        "label_interpretation": "解读",
        "scale_level_low": "相对较低",
        "scale_level_moderate": "中等",
        "scale_level_high": "相对较高",
        "scale_level_Insufficient data": "Insufficient data",
    },
}


QUESTION_TYPE_TRANSLATIONS = {
    QUESTION_TYPE_NUMERIC: {"en": "numeric question", "zh-CN": "数值题"},
    QUESTION_TYPE_SCALE: {"en": "scale question", "zh-CN": "量表题"},
    QUESTION_TYPE_SINGLE: {"en": "single-choice question", "zh-CN": "单选题"},
    QUESTION_TYPE_MULTIPLE: {"en": "multiple-choice question", "zh-CN": "多选题"},
    QUESTION_TYPE_OPEN: {"en": "open-ended text question", "zh-CN": "开放题"},
    QUESTION_TYPE_EMPTY: {"en": "empty question", "zh-CN": "空白列"},
}


FIELD_ROLE_TRANSLATIONS = {
    FIELD_ROLE_NUMERIC: {"en": "numeric metric", "zh-CN": "数值指标"},
    FIELD_ROLE_CATEGORICAL: {"en": "categorical dimension", "zh-CN": "分类维度"},
    FIELD_ROLE_DATETIME: {"en": "date or time", "zh-CN": "日期或时间"},
    FIELD_ROLE_IDENTIFIER: {"en": "identifier / ID", "zh-CN": "标识符或 ID"},
    FIELD_ROLE_BOOLEAN: {"en": "boolean variable", "zh-CN": "布尔变量"},
    FIELD_ROLE_FREE_TEXT: {"en": "free text", "zh-CN": "自由文本"},
    FIELD_ROLE_MULTI_VALUE: {"en": "multi-value field", "zh-CN": "多值字段"},
    FIELD_ROLE_EMPTY: {"en": "empty or unusable", "zh-CN": "空白或不可用字段"},
}


DATASET_MODE_LABEL_KEYS = {
    "general": "mode_general",
    "survey": "mode_survey",
    "mixed": "mode_mixed",
}


# Methodology validator copy, keyed by rule_id (plain strings, so this module
# stays free of any import from src.survey_gen). Mirrors the shape of
# FIELD_ROLE_TRANSLATIONS rather than living in TRANSLATIONS: the messages take
# parameters and there are enough of them to swamp the flat table.
VALIDATOR_RULE_TRANSLATIONS = {
    "double_barreled": {
        "en": {
            "message": "{qid} asks about two things at once ({left} / {right}).",
            "suggestion": "Split it into two questions: a respondent could answer them differently.",
        },
        "zh-CN": {
            "message": "{qid} 在一道题里同时问了两件事（{left} / {right}）。",
            "suggestion": "拆成两道题：受访者可能对两者给出不同答案。",
        },
    },
    "leading_question": {
        "en": {
            "message": "{qid} contains loaded wording: \"{marker}\".",
            "suggestion": "Remove the value-laden adjective and let the respondent judge.",
        },
        "zh-CN": {
            "message": "{qid} 含引导性措辞：「{marker}」。",
            "suggestion": "去掉带倾向的修饰语，把判断留给受访者。",
        },
    },
    "double_negative": {
        "en": {
            "message": "{qid} uses two negations in one clause: \"{clause}\".",
            "suggestion": "Rewrite positively; double negatives are read wrong under time pressure.",
        },
        "zh-CN": {
            "message": "{qid} 的同一分句内出现两个否定：「{clause}」。",
            "suggestion": "改写为肯定句式；双重否定在快速作答时极易被理解反。",
        },
    },
    "absolute_wording": {
        "en": {
            "message": "{qid} uses absolute wording: \"{marker}\".",
            "suggestion": "Absolutes push respondents to disagree. Keep it only if the item really asks about frequency.",
        },
        "zh-CN": {
            "message": "{qid} 使用了绝对化措辞：「{marker}」。",
            "suggestion": "绝对化措辞会把受访者推向否定。除非本题确实在问频率，否则请改写。",
        },
    },
    "jargon": {
        "en": {
            "message": "{qid} uses jargon or an unexplained acronym: \"{term}\".",
            "suggestion": "Explain it in plain words, or gloss it in brackets on first use.",
        },
        "zh-CN": {
            "message": "{qid} 含专业术语或未解释的缩写：「{term}」。",
            "suggestion": "改用通俗表述，或首次出现时用括号解释。",
        },
    },
    "question_length": {
        "en": {
            "message": "{qid} is long ({length} vs a {limit} guideline).",
            "suggestion": "Shorten the stem; long items lose attention and raise drop-off.",
        },
        "zh-CN": {
            "message": "{qid} 题干偏长（{length}，建议上限 {limit}）。",
            "suggestion": "精简题干；过长的题目会降低注意力、抬高中途退出率。",
        },
    },
    "fabricated_citation": {
        "en": {
            "message": "{qid} looks like it claims an external source: \"{evidence}\".",
            "suggestion": "Generated items may not cite literature or claim to reproduce a published scale.",
        },
        "zh-CN": {
            "message": "{qid} 疑似声称引用了外部来源：「{evidence}」。",
            "suggestion": "生成的题目不得引用文献，也不得声称复制了已发表量表。",
        },
    },
    "likert_points_forced_choice": {
        "en": {
            "message": "{qid} uses a {points}-point scale with no midpoint.",
            "suggestion": (
                "A forced-choice scale is a legitimate design against midpoint and acquiescence "
                "bias. The trade-off is resolution: respondents with a genuinely neutral view "
                "have to pick a side."
            ),
        },
        "zh-CN": {
            "message": "{qid} 使用 {points} 点量表（无中点）。",
            "suggestion": (
                "强迫选择是对抗中庸倾向与默许偏差的正当设计。"
                "代价在分辨率：真正持中立态度的受访者被迫选边。"
            ),
        },
    },
    "likert_points_coarse": {
        "en": {
            "message": "{qid} uses only {points} scale points.",
            "suggestion": "Few points limit variance and discrimination. Consider 5 or 7.",
        },
        "zh-CN": {
            "message": "{qid} 只有 {points} 个量表点。",
            "suggestion": "点数过少会限制方差与区分度，建议改为 5 点或 7 点。",
        },
    },
    "likert_points_invalid": {
        "en": {
            "message": "{qid} declares an unusable number of scale points: {points}.",
            "suggestion": "A Likert item needs at least 2 points and at most 10.",
        },
        "zh-CN": {
            "message": "{qid} 声明的量表点数不可用：{points}。",
            "suggestion": "李克特题的点数至少为 2、至多为 10。",
        },
    },
    "likert_points_zero_based": {
        "en": {
            "message": "{qid} is coded {low}-{high}, starting at zero.",
            "suggestion": (
                "Zero-based scales such as 0-10 are standard practice and nothing needs changing "
                "here. Keep the schema with the exported data: a recovered CSV on its own reads "
                "this as a numeric column, because 0-10 ratings and 0-10 counts are "
                "indistinguishable by value alone."
            ),
        },
        "zh-CN": {
            "message": "{qid} 的编码为 {low}-{high}，从 0 起。",
            "suggestion": (
                "0 起量表（如 0-10）是通行做法，本身无需修改。"
                "请把 schema 与导出数据一并保留：单看回收的 CSV 会把它读成数值列，"
                "因为 0-10 的评分与 0-10 的计数在取值上无法区分。"
            ),
        },
    },
    "likert_label_count": {
        "en": {
            "message": "{qid} declares {points} points but {count} labels.",
            "suggestion": "Give one label per point, or leave labels empty and rely on the endpoints.",
        },
        "zh-CN": {
            "message": "{qid} 声明 {points} 点，却给了 {count} 个标签。",
            "suggestion": "每个点一个标签，或干脆不给全表标签、只保留两端锚点。",
        },
    },
    "likert_missing_neutral": {
        "en": {
            "message": "{qid} is a bipolar {points}-point scale whose middle label is not neutral: \"{label}\".",
            "suggestion": "On a bipolar scale the midpoint should read as neutral (neither agree nor disagree).",
        },
        "zh-CN": {
            "message": "{qid} 是 {points} 点双极量表，但中间项不是中性词：「{label}」。",
            "suggestion": "双极量表的中点应当读作中立（既不同意也不反对）。",
        },
    },
    "likert_endpoint_polarity": {
        "en": {
            "message": "{qid} endpoints are not opposite in polarity: \"{low}\" / \"{high}\".",
            "suggestion": "The two ends of a scale should sit on opposite sides of the construct.",
        },
        "zh-CN": {
            "message": "{qid} 两端标签极性不相反：「{low}」/「{high}」。",
            "suggestion": "量表两端应位于该构念的相反两侧。",
        },
    },
    "likert_intensity_mirror": {
        "en": {
            "message": "{qid} labels are not mirrored in intensity at positions {low_pos} and {high_pos}.",
            "suggestion": "Mirrored positions should carry matching intensity, e.g. strongly / somewhat vs somewhat / strongly.",
        },
        "zh-CN": {
            "message": "{qid} 的第 {low_pos} 与第 {high_pos} 个标签强度不对称。",
            "suggestion": "镜像位置的强度应当对应，例如「非常/比较」对「比较/非常」。",
        },
    },
    "likert_polarity_consistency": {
        "en": {
            "message": "Construct {cid} mixes scale formats: {formats}.",
            "suggestion": "Items in one construct must share point count and polarity, or the composite score is meaningless.",
        },
        "zh-CN": {
            "message": "构念 {cid} 内混用了不同的量表格式：{formats}。",
            "suggestion": "同一构念的题项必须共用点数与极性，否则构念得分无意义。",
        },
    },
    "matrix_rows_limit": {
        "en": {
            "message": "Section {sid} puts {count} items on one scale format.",
            "suggestion": "Long matrices invite straight-lining. Split them or break the block up.",
        },
        "zh-CN": {
            "message": "章节 {sid} 有 {count} 道题共用同一量表格式。",
            "suggestion": "过长的矩阵题会诱发直线作答，建议拆分或打断。",
        },
    },
    "matrix_rows_excessive": {
        "en": {
            "message": "Section {sid} puts {count} items on one scale format.",
            "suggestion": "This is long enough that straight-lining is near certain. Split the matrix.",
        },
        "zh-CN": {
            "message": "章节 {sid} 有 {count} 道题共用同一量表格式。",
            "suggestion": "这个长度几乎必然产生直线作答，必须拆分。",
        },
    },
    "question_order_screening": {
        "en": {
            "message": "Screening section {sid} appears after non-screening questions.",
            "suggestion": "Screening questions must come first, or ineligible respondents answer the whole survey.",
        },
        "zh-CN": {
            "message": "甄别章节 {sid} 排在了非甄别题之后。",
            "suggestion": "甄别题必须放在最前，否则不合格的受访者会答完整份问卷。",
        },
    },
    "question_order_demographic": {
        "en": {
            "message": "Demographic section {sid} is followed by other content.",
            "suggestion": "Demographics belong at the end; asking them first raises drop-off and priming.",
        },
        "zh-CN": {
            "message": "人口统计章节 {sid} 之后还有其他内容。",
            "suggestion": "人口统计题应放在最后；放在前面会抬高中途退出率并造成启动效应。",
        },
    },
    "construct_min_items": {
        "en": {
            "message": "Construct {cid} has only {count} item(s).",
            "suggestion": (
                "With fewer than 3 items the internal-consistency estimate is unstable "
                "and the construct is under-represented."
            ),
        },
        "zh-CN": {
            "message": "构念 {cid} 只有 {count} 个题项。",
            "suggestion": "少于 3 个题项时内部一致性估计不稳定，且构念内容覆盖不足。",
        },
    },
    "construct_items_are_scale": {
        "en": {
            "message": "Construct {cid} contains a non-scale item {qid} ({qtype}).",
            "suggestion": "Reliability and composite scores are only defined over scale items.",
        },
        "zh-CN": {
            "message": "构念 {cid} 内含非量表题 {qid}（{qtype}）。",
            "suggestion": "信度与构念得分只对量表题有定义。",
        },
    },
    "reverse_coded_present": {
        "en": {
            "message": "The survey has no reverse-coded item.",
            "suggestion": "At least one reverse-coded item is needed to detect acquiescence and straight-lining.",
        },
        "zh-CN": {
            "message": "整份问卷没有任何反向计分题。",
            "suggestion": "至少需要一道反向计分题，用于识别默许偏差与直线作答。",
        },
    },
    "reverse_coded_per_construct": {
        "en": {
            "message": "Construct {cid} has {count} items but none reverse-coded.",
            "suggestion": "Constructs of four or more items should carry a reverse-coded item.",
        },
        "zh-CN": {
            "message": "构念 {cid} 有 {count} 个题项，但没有反向计分题。",
            "suggestion": "题项数达到 4 个的构念应当包含一道反向计分题。",
        },
    },
    "attention_check_present": {
        "en": {
            "message": "The survey has no attention-check item.",
            "suggestion": "Add one instructed-response item so inattentive responses can be screened out.",
        },
        "zh-CN": {
            "message": "整份问卷没有注意力检测题。",
            "suggestion": "增加一道指令式题目，用于筛除不认真作答的样本。",
        },
    },
    "attention_check_expected_value": {
        "en": {
            "message": "Attention check {qid} has no usable expected answer ({value}).",
            "suggestion": "The expected value must match one of the item's option values.",
        },
        "zh-CN": {
            "message": "注意力检测题 {qid} 没有可用的预期答案（{value}）。",
            "suggestion": "预期答案必须与该题的某个选项值一致。",
        },
    },
    "attention_check_position": {
        "en": {
            "message": "Attention check {qid} sits at the {position} of the survey.",
            "suggestion": "Place it mid-survey, where attention actually decays.",
        },
        "zh-CN": {
            "message": "注意力检测题 {qid} 位于问卷的{position}。",
            "suggestion": "应放在问卷中段，那里才是注意力真正下降的位置。",
        },
    },
    "option_count_too_few": {
        "en": {
            "message": "{qid} offers only {count} option(s).",
            "suggestion": "A choice question needs at least two options.",
        },
        "zh-CN": {
            "message": "{qid} 只有 {count} 个选项。",
            "suggestion": "选择题至少需要两个选项。",
        },
    },
    "option_count_too_many": {
        "en": {
            "message": "{qid} offers {count} options.",
            "suggestion": "Long option lists cause position bias. Group them or drop rare ones.",
        },
        "zh-CN": {
            "message": "{qid} 有 {count} 个选项。",
            "suggestion": "过长的选项表会产生位置偏差，建议归并或删去罕见项。",
        },
    },
    "option_mutual_exclusivity": {
        "en": {
            "message": "{qid} has {count} exclusive option(s), last one at position {position}.",
            "suggestion": "Keep at most one exclusive option and put it last.",
        },
        "zh-CN": {
            "message": "{qid} 有 {count} 个互斥选项，最后一个在第 {position} 位。",
            "suggestion": "互斥选项最多保留一个，且应排在最后。",
        },
    },
    "option_label_uniqueness": {
        "en": {
            "message": "{qid} repeats an option label: \"{label}\".",
            "suggestion": "Duplicate labels make the answer ambiguous in the recovered data.",
        },
        "zh-CN": {
            "message": "{qid} 的选项标签重复：「{label}」。",
            "suggestion": "重复标签会让回收数据中的作答无法区分。",
        },
    },
    "code_uniqueness": {
        "en": {
            "message": "Column code \"{code}\" is used by more than one question.",
            "suggestion": "Codes become CSV column names, so they must be unique.",
        },
        "zh-CN": {
            "message": "列名 code「{code}」被多道题重复使用。",
            "suggestion": "code 会成为 CSV 列名，必须全局唯一。",
        },
    },
    "code_shape": {
        "en": {
            "message": "Column code \"{code}\" ({qid}) is not a safe column name.",
            "suggestion": "Use ASCII: a letter first, then letters, digits or underscores, 31 characters max.",
        },
        "zh-CN": {
            "message": "列名 code「{code}」（{qid}）不是安全的列名。",
            "suggestion": "请使用 ASCII：字母开头，其后为字母、数字或下划线，最长 31 个字符。",
        },
    },
    "code_is_metadata": {
        "en": {
            "message": "Column code \"{code}\" ({qid}) reads as a metadata column.",
            "suggestion": "The upload path drops ID/timestamp-looking columns, so this question would vanish.",
        },
        "zh-CN": {
            "message": "列名 code「{code}」（{qid}）会被判定为元数据列。",
            "suggestion": "上传管线会剔除形似 ID/时间戳的列，这道题会因此整列消失。",
        },
    },
    "bilingual_completeness": {
        "en": {
            "message": "{scope_label} {target} is missing its {missing_language} text.",
            "suggestion": "The frontend switches language without refetching, so both versions must exist.",
        },
        "zh-CN": {
            "message": "{scope_label} {target} 缺少{missing_language}文案。",
            "suggestion": "前端切换语言时不会重新请求，因此两种语言都必须存在。",
        },
    },
}


def t(language: str, key: str, **kwargs) -> str:
    language_map = TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE])
    template = language_map.get(key, TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key))
    return template.format(**kwargs)


def get_language_label(language: str) -> str:
    return t(language, "language_name")


def translate_question_type(language: str, question_type: str) -> str:
    return QUESTION_TYPE_TRANSLATIONS.get(question_type, {}).get(language, question_type)


def translate_field_role(language: str, role: str) -> str:
    return FIELD_ROLE_TRANSLATIONS.get(role, {}).get(language, role)


def translate_dataset_mode(language: str, mode: str) -> str:
    key = DATASET_MODE_LABEL_KEYS.get(mode)
    return t(language, key) if key else mode


def translate_scale_level(language: str, level: str) -> str:
    return t(language, f"scale_level_{level}")


def translate_validator_rule(language: str, rule_id: str, part: str = "message", **kwargs) -> str:
    """Render one validator message or suggestion in the requested language.

    Falls back the same way ``t`` does: unknown language -> English, unknown
    rule -> the rule id itself, so a missing entry degrades to something
    readable instead of raising mid-validation.
    """
    rule = VALIDATOR_RULE_TRANSLATIONS.get(rule_id)
    if not rule:
        return rule_id
    template = rule.get(language, rule[DEFAULT_LANGUAGE]).get(part, "")
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        # A missing parameter must not take the whole validation run down.
        return template
