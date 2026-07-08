# SurveyMind 代码审查报告

> 自动生成于 2026-06-06 | 审查范围：全项目 10 个 Python 文件 + 测试数据

---

## 一、严重 Bug（会导致崩溃或错误结果）

### 1. `cross_analysis.py:15-28` — 量表题含非数值字符串时交叉分析崩溃

**文件**：`src/cross_analysis.py:15`

**问题**：`analyze_numeric_by_group()` 直接对目标列做 `groupby().agg(["mean", "median", "std"])`，但如果量表列包含 `"5分"`、`"4 points"` 这类带后缀的字符串值，pandas 会抛出 `TypeError`。

`descriptive_analysis.py` 中有 `coerce_scale_scores()` 专门处理这种情况，但 `cross_analysis.py` 没有调用它。

**复现**：
```python
df = pd.DataFrame({
    'group': ['A', 'A', 'B', 'B'],
    'score': ['5分', '4分', '3分', '5分']
})
# 崩溃: TypeError: agg function failed [how->mean,dtype->object]
analyze_numeric_by_group(df, 'group', 'score')
```

**修复建议**：在 `analyze_numeric_by_group` 中，当 `target_type == QUESTION_TYPE_SCALE` 时，先用 `coerce_scale_scores()` 将目标列转为数值。

---

### 2. `report_generator.py:243-266` — 所有数值列标准差为 NaN 时报告错误信息

**文件**：`src/report_generator.py:248`

**问题**：`_build_numeric_findings` 中：
```python
top_std_column = numeric_summary["std"].fillna(0).sort_values(ascending=False).index[0]
```
当所有数值列的标准差都是 NaN（例如每列只有一个唯一值），`fillna(0)` 让所有值变为 0，排序后随机挑一个，但报告文案仍然写"`{top_std_column}` 的离散程度最大，标准差为 nan"——这显然是错误信息。

**修复建议**：检查 `top_std` 实际值，如果为 0 或 NaN，跳过该条发现或改用不同措辞。

---

## 二、中等 Bug（功能异常但不崩溃）

### 3. `app.py:52-56` — 元数据列识别遗漏 `UserID` 等驼峰命名

**文件**：`app.py:48-56`

**问题**：`is_metadata_column` 使用正则 `(?<![A-Z])ID(?![A-Z])` 加 `re.IGNORECASE` 来检测 ID 列。因为 Python 的 `re.IGNORECASE` 会让 `[A-Z]` 也匹配小写字母，导致：

| 列名 | 预期 | 实际 | 原因 |
|------|------|------|------|
| `UserID` | 移除 | **保留** | `r` 在 `[A-Za-z]` 范围内，lookbehind 失败 |
| `StudentID` | 移除 | **保留** | 同上 |
| `RespondentID` | 移除 | **保留** | 同上 |
| `student_id` | 视情况 | **移除** | 下划线不在字母范围内，匹配成功 |

这导致最常见的驼峰式 ID 列名无法被识别。

**修复建议**：改用更明确的正则，例如 `\bID\b` 或 `(?:^|_)ID(?:$|_)`，或直接增加 `"ID"` 到关键词列表中做精确匹配。

---

### 4. `question_type_detector.py:69-70` — 全空列被归类为"单选题"

**文件**：`src/question_type_detector.py:69-70`

**问题**：当列的所有值都是 null 时，`detect_question_type` 返回 `QUESTION_TYPE_SINGLE`。这会把完全无用的列当作有效列参与后续分析。

**修复建议**：返回一个特殊标记（如 `"unknown"` 或 `"empty"`），让下游模块可以跳过或提示用户。

---

### 5. `question_type_detector.py:36-58` — 量表检测不支持小数分值

**文件**：`src/question_type_detector.py:48`

**问题**：`_is_scale_question` 要求 `>=80%` 的值为整数。但实际问卷数据中（如 `sample_survey.csv` 的 `satisfaction_score`），量表分值经常包含小数（1.1, 2.3...），此时整数比仅 11%，量表被错误归类为数值题。

**影响**：`satisfaction_score` 列有 40 个唯一值（1.0-5.0 之间的各种小数），语义上明显是满意度量表，但被归类为 `numeric question`。

**修复建议**：对于值域在 1-10 范围内的列，放宽整数比要求到 50%，或增加基于列名关键词（`satisfaction`、`score`、`rating`）的启发式规则。

---

### 6. `report_generator.py:249` — `_build_numeric_findings` 访问可能不存在的 DataFrame 列

**文件**：`src/report_generator.py:249`

**问题**：
```python
numeric_missing = df[numeric_summary.index].isna().mean().sort_values(ascending=False)
```
`numeric_summary.index` 来自 `summarize_numeric_questions()` 的输出，该函数通过 `df[numeric_columns]` 选取列。如果 `df` 和 `numeric_summary` 的列名不完全一致（例如列名被重命名过），这里会 `KeyError`。

**修复建议**：使用集合交集过滤：`[c for c in numeric_summary.index if c in df.columns]`。

---

## 三、改进建议

### 架构与可靠性

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 7 | **零测试覆盖** | 整个项目 | 项目无任何 `.py` 测试文件。建议至少为核心模块添加 pytest 单元测试：`question_type_detector`、`descriptive_analysis`、`report_generator` |
| 8 | `ollama` 是强制依赖 | `requirements.txt:8` | `ollama` 仅用于 AI 报告功能，不应阻塞基础安装。建议移到 `requirements-optional.txt` 或在代码中做懒加载 |
| 9 | 死代码 | `report_generator.py:753-755` | `generate_llm_enhanced_report()` 只抛出 `NotImplementedError`，建议删除或在明确计划后再保留 |
| 10 | `render_ai_report` 无国际化 | `app.py:650-696` | AI 报告部分的 UI 文本全部硬编码为中文，与项目的双语架构不一致 |
| 11 | 测试数据文件格式不规范 | `data/test_extreme_edge_cases.csv` | 该文件行 7 有 9 个字段而非 8 个，默认 CSV 解析器报错。虽然上传流程有 python engine 兜底，但作为测试数据，格式应该规范 |
| 12 | 无 Streamlit 页面级错误边界 | `app.py:699-751` | 各 UI section 有 try/except，但如果 `load_active_dataset` 在外部抛出未预期的异常，整个页面会白屏 |

### 数据处理

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 13 | 交叉分析多选展开产生笛卡尔积 | `cross_analysis.py:67-72` | 当分组列和目标列都是多选题时，一行 `A,B` × `X,Y` 会展开成 4 行，人工放大样本量。应添加去重逻辑或标注此限制 |
| 14 | 多选题百分比基于选项数而非受访者数 | `descriptive_analysis.py:112` | `total = max(len(values), 1)` 的分母是展开后的总选项数，导致百分比解读为"选项被选中的比例"而非"受访者选择的比例"。需在报告中明确标注 |
| 15 | `build_sample_profile` 硬编码列名 | `descriptive_analysis.py:135-139` | `gender`、`grade`、`major_type` 等写死在代码中，对其他问卷数据集无意义。建议改为基于题型自动选择，或作为可配置项 |
| 16 | 常量数值列（如 `[5,5,5,5]`）被归类为数值题 | `question_type_detector.py:63-66` | 无方差的列在分析中无价值，建议标记为 `"constant"` 并在 UI 中跳过 |

### UI/UX

| # | 问题 | 位置 | 建议 |
|---|------|------|------|
| 17 | 无数据验证提示 | `app.py:713` | 用户上传数据后没有对列数、行数、缺失率的预检，直接进入分析。建议在上传后展示快速健康检查卡片 |
| 18 | 长操作无进度提示 | `app.py` 多处 | `generate_descriptive_results` 在大型数据集上可能需要几秒，建议添加 `st.spinner` |
| 19 | 文件上传限制未明确 | `app.py:219-223` | 没有文件大小限制提示，大文件可能导致内存溢出 |

---

## 四、已验证正常的部分

以下模块在测试中表现正常，未发现明显问题：

- `data_loader.py` — 数据加载逻辑正确，多种格式支持完善
- `i18n.py` — 翻译字典完整，`t()` 函数 `**kwargs` 格式化正确
- `visualization.py` — 图表构建函数正确，错误处理恰当
- `descriptive_analysis.py` — `coerce_scale_scores` 对 `"5分"` 等中文后缀提取正确
- `report_generator.py` — 中英文报告生成逻辑完整，结构清晰
- `llm_client.py` — Ollama 客户端错误处理全面，连接/模型未找到/空响应等场景都有覆盖

---

## 五、修复优先级建议

| 优先级 | Bug # | 理由 |
|--------|-------|------|
| P0 | #1 | 用户上传真实问卷（量表带文字后缀）时交叉分析直接崩溃 |
| P1 | #2 | 报告输出明显错误信息，影响用户信任 |
| P1 | #4 | 全空列被当单选题参与分析，影响所有下游结果 |
| P2 | #3 | 最常见的 ID 列名格式无法识别 |
| P2 | #5 | 小数满意度分值被错误归类 |
| P3 | #6 | 需要列名不一致的极端场景才会触发 |
