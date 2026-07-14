# SurveyMind 通用数据分析平台升级设计（2026-07-13）

## 背景

用户反馈：上传普通建模数据、表格后，系统仍然把所有字段强制解释成"单选题 / 多选题 / 量表题"，
无法自然地分析普通表格。目标是把 SurveyMind 从"仅支持问卷分析的工具"升级为
"同时支持问卷数据和普通表格数据的 AI 辅助数据分析平台"，并保留已有问卷分析能力。

## 一、当前问题的技术原因

1. **字段语义层缺失**：`src/question_type_detector.py` 是唯一的字段理解入口，输出只有
   5 种问卷题型（数值题 / 量表题 / 单选题 / 多选题 / 开放题）。任何低基数分类字段
   （如 `region`、`product_category`）都会落进"单选题"分支，任何含逗号的文本
   （地址、备注）只要分隔符比例 ≥ 0.15 就会被判成"多选题"——阈值判断没有
   "词表复用"等证据支撑。
2. **没有数据集模式概念**：`app.py` 的 `main()` 是一条固定的问卷流水线
   （题型识别 → 问卷描述统计 → 问卷可视化 → 问卷报告），上传什么数据都走同一条路。
3. **预处理主动破坏通用数据**：`preprocess_input_dataframe()` 直接**删除**列名含
   `ID / 时间 / 编号` 的列。问卷场景下这是去噪，但普通数据集的主键和日期列被删掉后，
   时间趋势、去重检查、建模准备度都无从谈起。
4. **报告与提示词固定为问卷口径**：`report_generator.py` 的报告标题、章节、措辞全部
   围绕"题型 / 量表 / 多选题"，`i18n.py` 的界面文案也是问卷术语。
5. **LLM 完全未接入**：`generate_llm_enhanced_report()` 只是 `NotImplementedError`
   占位；`.env` 中的 `LLM_API_KEY / LLM_BASE_URL / LLM_MODEL` 没有任何代码读取。
   "向数据提问"没有落点。
6. **缺少通用统计能力**：没有日期解析、相关性分析、分组差异检验、异常值汇总、
   ID 字段识别，`scipy` 虽在依赖里但没被使用。

## 二、推荐的新架构

分层原则：**字段语义层是地基，问卷题型只是它在问卷模式下的一种投影**。

```
数据加载 (data_loader)
   ↓
字段语义识别 field_semantics.py        ← 新增，8 种通用字段角色
   ↓
数据集模式识别 dataset_mode.py         ← 新增，general / survey / mixed + 手动切换
   ↓                                      问卷题型 = 字段角色在 survey/mixed 模式下的派生
通用数据概览 general_overview.py       ← 新增，所有模式都生成
   ├─ 智能分析建议 analysis_suggestions.py   ← 新增，按实际字段动态生成
   ├─ 自动图表推荐 chart_recommender.py      ← 新增
   └─ 问卷专用管线（保留：question_type_detector / descriptive_analysis / cross_analysis）
   ↓
报告层 report_generator.py             ← 改造，按模式分派三种报告结构
   └─ AI 解读 ai_report.py + llm_client.py  ← 新增，三种分析师人设，
        只解释本地 pandas/scipy 算出的数字，未配置/失败时自动降级
```

### 字段角色体系（通用模式）

| 角色 | 常量 | 判定证据 |
| --- | --- | --- |
| 数值指标 | `numeric_metric` | 数值 dtype，非 ID、非布尔 |
| 分类维度 | `categorical_dimension` | 低/中基数离散取值 |
| 日期或时间 | `datetime` | datetime dtype，或字符串可解析率 ≥ 90% + 长度/列名佐证 |
| 标识符或 ID | `identifier` | 唯一率 ≈ 1 且（列名含 id/编号 或 连续整数 或 均匀短字符串） |
| 布尔变量 | `boolean` | 取值 ⊆ {是/否, yes/no, true/false, 0/1, …} |
| 自由文本 | `free_text` | 平均长度长、唯一率高、含句子标点 |
| 多值字段 | `multi_value` | 含分隔符 **且** 拆分后 token 词表小、token 跨行复用、token 短 |
| 空白或不可用 | `empty_or_constant` | 全空或只有一个取值 |

多选题误判修复的关键：不再只看"分隔符比例"，必须同时满足
①分隔符出现率 ≥ 10%；②拆分后 token 词表远小于行数；③token 平均长度短（标签而非句子）；
④token 跨行重复出现。含逗号的句子/地址会因 token 词表爆炸、token 过长而被否决。

### 数据集模式识别

对每列打分：量表特征 + 问卷类列名（满意/意愿/评分/nps/feedback…）、多值字段、
反馈类自由文本 → survey 分；标识符、日期列、带业务量纲列名（price/金额/销量…）的
连续数值 → general 分。双方都 ≥ 3 → `mixed`；survey ≥ 2 且占优 → `survey`；否则 `general`。
识别结果连同证据展示给用户，并提供手动三态切换（radio）。

### 问卷模式派生

`derive_question_types(df, semantics)`：identifier / datetime / empty 列被排除出题型体系；
numeric → 量表(满足 Likert 特征)或数值题；categorical/boolean → 单选题；
multi_value → 多选题；free_text → 开放题。原有问卷描述统计、交叉分析、报告导出
继续消费这份 `question_types` 字典，接口不变。

### AI 报告

- `llm_client.py`：读取 `.env` / 环境变量（`LLM_API_KEY / LLM_BASE_URL / LLM_MODEL`），
  OpenAI 兼容 `chat/completions`，任何异常返回 `None`，绝不让 UI 崩溃。
- `ai_report.py`：三种人设（通用数据分析师 / 问卷分析师 / 混合数据分析师）；
  提示词只包含 **本地已计算** 的统计摘要（digest），系统提示明确要求：
  只引用给定数字、不得编造、数据不足时输出"根据当前数据无法进一步判断"。
- 未配置或调用失败 → 界面仅显示规则报告 + 降级提示，基础分析全部可用。

## 三、需要修改或新增的文件

| 文件 | 动作 | 内容 |
| --- | --- | --- |
| `src/field_semantics.py` | 新增 | 8 种字段角色识别 + 证据 |
| `src/dataset_mode.py` | 新增 | 模式识别、题型派生 |
| `src/general_overview.py` | 新增 | 通用概览：质量/数值/分类/日期/相关性/分组差异/异常值/发现 |
| `src/analysis_suggestions.py` | 新增 | 动态分析建议（3-5 条） |
| `src/chart_recommender.py` | 新增 | 按字段角色推荐图表 |
| `src/llm_client.py` | 新增 | LLM 配置与调用（可降级） |
| `src/ai_report.py` | 新增 | 三种人设 + 统计摘要 + 提示词 |
| `src/report_generator.py` | 修改 | `generate_report()` 按模式分派；通用/混合报告结构 |
| `src/visualization.py` | 修改 | 新增相关性热力图、时间趋势图 |
| `src/i18n.py` | 修改 | 中性术语、模式/角色翻译、新界面键 |
| `app.py` | 修改 | 新流程：模式识别 → 字段角色 → 通用概览 → 建议/图表 → 按模式分派 |
| `data/sample_general.csv` | 新增 | 普通建模数据（订单/客户/日期/金额/是否退货） |
| `data/sample_mixed.csv` | 新增 | 混合数据（客户属性 + 满意度量表 + 多选 + 反馈文本） |
| `tests/test_*.py` | 新增 | 字段语义 / 模式 / 概览 / 报告 / 建议 / 问卷兼容 六组测试 |

## 四、分阶段实施计划

- **第一阶段（本次实施）**：中性术语；`field_semantics` + `dataset_mode` + 手动切换；
  修正分类字段和多选题误判；预处理不再删除 ID/日期列。
- **第二阶段（本次实施）**：`general_overview` 全量概览；`chart_recommender` 自动图表；
  `analysis_suggestions`；报告按模式分派三种结构；`llm_client`/`ai_report` 三种人设
  接入与降级。
- **第三阶段（后续）**：向数据提问——自然语言 → LLM 生成受控 JSON 分析计划
  （白名单操作：describe/groupby/corr/crosstab/trend/topk）→ 本地执行 → LLM 解释结果。
  计划校验器拒绝不存在的字段与不支持的操作。
- **第四阶段（后续）**：文本主题分析（分词+关键词聚类，LLM 摘要可选）；时间序列分析
  （重采样、同环比、简单分解）；建模准备度报告（目标变量建议、类别不平衡、
  特征关联、泄漏字段启发式、清洗/编码清单）。

## 五、每阶段测试与验收标准

- **阶段一**：单测覆盖 8 种角色的正反例（含"带逗号句子不判多值"）；三份样例数据
  模式识别正确；普通数据集界面不出现"单选题/多选题/量表题"字样；问卷样例题型
  识别结果与升级前一致。
- **阶段二**：概览中的均值/中位数/相关系数与 pandas/scipy 手算一致；构造 y≈2x 数据
  能报告强相关；分组差异给出 ANOVA p 值；报告三种模式章节正确、通用报告无问卷术语；
  未配置 LLM 时 AI 区块显示降级提示且其余功能完好；`pytest` 全绿。
- **阶段三**：分析计划只含白名单操作；引用不存在字段时被拒绝并提示；AI 输出数字
  与本地计算一致（抽查断言）。
- **阶段四**：建模准备度对含目标变量数据集给出完整清单；无目标变量时明确说明。

## 六、主要风险及兼容方案

1. **问卷回归风险**：题型派生结果与旧检测器不一致 → 保留 `question_type_detector.py`
   原逻辑作为派生的题型判断内核，并用 `sample_survey.csv` 固化回归测试。
2. **模式误判**：启发式打分对边界数据可能判错 → 界面永远提供手动三态切换，
   且识别证据透明展示。
3. **大文件性能**：相关性/分组差异组合爆炸 → 限制参与列数（数值/分类各取前 8/10 列）、
   分组样本量门槛。
4. **LLM 幻觉**：提示词只提供已计算结果 + 明确"不得编造"约束 + 降级路径；
   第三阶段的执行层完全本地化。
5. **旧界面键/会话状态残留**：Streamlit 组件 key 增加数据集指纹，切换文件时状态重置。
6. **中英一致性**：所有新增文案同时提供 en / zh-CN，报告与界面共用 i18n 层。
