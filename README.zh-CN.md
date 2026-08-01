# SurveyMind

[![tests](https://github.com/XB-FakeItTillIPO/SurveyMind/actions/workflows/tests.yml/badge.svg)](https://github.com/XB-FakeItTillIPO/SurveyMind/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

[English README](README.md)

## 项目简介

SurveyMind 是一个同时支持问卷数据和普通表格数据的双语 AI 辅助数据分析平台（基于 Streamlit）。上传 CSV 或 Excel 文件后，系统会自动识别数据模式（普通数据集 / 问卷数据 / 混合数据集，可手动切换），分析每个字段的通用角色（数值指标、分类维度、日期时间、标识符 ID、布尔变量、自由文本、多值字段、空白字段），生成包含数据质量检查、相关性分析和分组差异的通用数据概览，推荐图表与分析方向，并输出结构化的中英文分析报告。

- **普通数据集模式**：字段按通用角色分析，界面不会出现"单选题 / 多选题 / 量表题"等问卷术语。
- **问卷模式**：保留原有完整问卷管线——题型识别、描述统计、交叉分析、报告导出。
- **混合模式**：通用概览 + 问卷专用分析同时呈现。
- **AI 智能解读（可选）**：在 `.env` 中配置 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL` 后，系统按数据模式切换"通用数据分析师 / 问卷分析师 / 混合数据分析师"角色。AI 只解释由 pandas/NumPy/SciPy 本地计算出的统计结果；AI 未配置或调用失败时，全部基础分析仍然可用。

这个项目特别适合中文场景下的学生问卷、校园组织调研、课程作业、市场研究基础训练，同时也保留了英文界面和英文文档，适合作为 GitHub 作品集项目展示。

## 功能特点

- 支持上传 CSV 和 Excel 问卷数据
- 未上传文件时自动加载内置示例数据集
- 支持中英文双语界面切换
- 自动识别数值题、量表题、单选题、多选题和开放题
- 支持手动修正题型识别结果
- 自动生成描述性统计结果
- 提供 Plotly 可视化，包括柱状图、直方图、箱线图和交叉分析图
- 支持分组变量与目标变量的基础交叉分析
- 支持生成中英文 Markdown 分析报告并下载

## 支持的题型

SurveyMind 当前支持五类常见问卷题型：

- `数值题`：例如年龄、支出、预算、时长等连续或离散数值
- `量表题`：例如 1-5、1-7、1-10 的满意度、认同度、评价类题目
- `单选题`：每位受访者只选择一个选项
- `多选题`：多个选项存储在同一个单元格中，通常由分隔符连接
- `开放题`：自由文本回答，适合意见、建议、原因说明等内容

题型识别结果会直接影响后续统计分析、图表展示、交叉分析方式以及自动报告生成。

## 技术栈

- Python
- pandas
- numpy
- Streamlit
- Plotly
- openpyxl
- scipy

## 项目结构

```text
surveymind/
├── app.py                     Streamlit 界面
├── backend/main.py            FastAPI 层，薄封装 src/（此处不写分析逻辑）
├── frontend/                  静态前端，无框架、无构建步骤
│   ├── index.html             全部屏幕与 design tokens
│   ├── data.js                分析五屏的数据层
│   └── assets/insight.js      智能分析屏的数据层
├── src/
│   ├── survey_gen/            问卷生成
│   │   ├── schema.py          Survey / Section / Question，JSON 无损往返
│   │   ├── validator.py       方法学校验器（23 条规则 / 34 个 rule_id）
│   │   ├── vocabulary.py      措辞规则背后的词表
│   │   ├── templates.py       内置问卷模板，零 API key 可用
│   │   ├── synthetic.py       按 schema 合成回收数据，附带 ground truth
│   │   ├── export.py          CSV 模板 / 示例 / Markdown / schema / 编码表
│   │   └── roundtrip.py       按 schema 解析回收数据，计算构念得分
│   ├── report/                报告层，每种输出结构一个模块
│   │   ├── survey.py          问卷报告
│   │   ├── general.py         通用数据报告
│   │   ├── mixed.py           混合报告
│   │   ├── dispatch.py        按当前模式分派
│   │   ├── common.py          共用格式化 helper
│   │   └── llm_prompt.py      数据摘要与 prompt 构造
│   ├── question_type_detector.py   五种题型、量表提示、识别依据
│   ├── field_semantics.py     八种通用字段角色
│   ├── dataset_mode.py        general / survey / mixed 模式识别
│   ├── general_overview.py    质量、相关性、分组差异
│   ├── analysis_suggestions.py / chart_recommender.py
│   ├── descriptive_analysis.py / cross_analysis.py / visualization.py
│   ├── preprocessing.py / data_loader.py / i18n.py
│   └── llm_client.py / ai_report.py    可选 AI 层，未配置时自动降级
├── tests/                     390 个测试
│   └── fixtures/              问卷与检测 fixture
├── docs/
│   ├── detection-benchmark.md        量表 vs 计数，以及端到端对照
│   ├── external-validity-check.md    校验器对真实专业问卷的检验
│   └── specs/                        设计文档
├── data/                      样例数据集
└── .github/workflows/tests.yml
```

## 本地运行方法

1. 克隆项目到本地
2. 进入项目目录
3. 安装依赖：

```bash
pip install -r requirements.txt
```

4. 启动 Streamlit：

```bash
streamlit run app.py
```

5. 打开终端中显示的本地地址，通常为 `http://localhost:8501`

### 前后端分离模式（FastAPI + 静态前端）

```bash
# 终端 1 —— 后端 API
uvicorn backend.main:app --reload --port 8000

# 终端 2 —— 静态前端
python -m http.server 5500 --directory frontend
```

然后访问 `http://localhost:5500`。

## AI 报告配置（云端 LLM API）

"AI 智能解读"功能调用云端大模型 API。**API key 只从环境变量读取——绝不硬编码、
绝不提交到 git**（`.env` 已被 git 忽略）。

克隆项目后需配置你自己的 key：

```bash
cp .env.example .env
# 然后编辑 .env，填入你自己的 LLM_API_KEY
```

默认供应商为 DeepSeek（`https://api.deepseek.com/v1`，模型 `deepseek-chat`）。
客户端使用 OpenAI 兼容格式，切换供应商（Anthropic Claude、Kimi、智谱 GLM 等）
只需修改 `.env` 里的 `LLM_BASE_URL` 与 `LLM_MODEL`，代码零改动——详见
`.env.example` 内的注释。未配置 key 时应用一切正常，AI 按钮会提示如何配置，
不会报错。

## 使用示例

假设你正在分析一份关于学生消费、学习行为、服务满意度或校园活动参与情况的问卷。你可以把原始导出的 Excel 或 CSV 文件直接上传到 SurveyMind，然后：

- 查看数据规模、字段类型和缺失值情况
- 自动识别哪些题目是单选、多选、量表或开放题
- 查看数值题和量表题的描述性统计结果
- 通过图表快速理解选项分布和群体差异
- 对重点变量进行交叉分析
- 自动生成中英文分析报告，用于课程汇报、简历作品集或项目展示

## 当前局限

- 当前题型识别仍然是规则驱动的，遇到格式很特殊的数据时可能需要手动修正
- 多选题拆分默认依赖较一致的分隔符格式
- 交叉分析目前以描述性分析为主，尚未加入显著性检验
- 开放题目前提供的是有效回答数量和后续分析建议，还没有完整接入自动文本主题归纳
- 双语报告已经可用，但更细腻的行业化措辞仍可以继续优化

## 后续计划

- 接入 LLM，对开放题做主题摘要、关键词提取和观点归纳
- 提升自动报告的叙述质量和建议质量
- 增加显著性检验与更系统的分组比较能力
- 支持导出 PDF、PPT 或更完整的项目汇报材料
- 增加更多适合真实问卷场景的数据清洗与编码功能

## 这个项目如何体现数据分析能力

SurveyMind 能体现的数据分析能力包括：

- 多源数据读取与基础数据质量检查
- 问卷题型识别与规则设计
- 描述性统计与交叉分析
- 数据可视化与结果表达
- 报告自动化生成
- 中英文双语产品思维
- 面向真实使用场景的模块化 Python 项目组织能力
