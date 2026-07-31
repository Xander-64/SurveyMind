# 问卷生成模块（survey generation）— 设计方案 v2

> 2026-07-30 起草，v2 已并入 11 处评审修正。目标读者：没有看过此前任何开发会话的接手者。
> 状态：**设计已通过，进入实施。** 实施顺序见 §14。

## 0. 定位调整

SurveyMind 的对外定位从「通用数据分析平台」改为 **「问卷全流程工具」(survey end-to-end)**：
问卷生成 → 导出模板 → （用户自行在问卷星 / Google Forms 投放）→ 回收数据上传 → 现有分析管线。

**不删任何代码。** `field_semantics` / `dataset_mode` / `general_overview` 全部保留，
`general` 模式从「卖点」降级为「鲁棒性兜底」：上传非标准问卷时仍能做基础字段分析。
`field_semantics` 在问卷场景下承担核心职责——识别并剔除提交时间、IP、答题时长、
昵称等非题目字段。`insight` 屏保留，标题改为「数据质量与字段识别」。

### 范围红线（绝对不做）

不做问卷投放与在线收集：**不做填答链接、不做答案数据库、不做用户系统**。
生成端与分析端之间**只用文件桥接**：导出 CSV 模板 → 用户拿去第三方平台投放 →
回收数据走现有 `/api/upload`。

---

## 1. 题型词表（唯一真源：`src/question_type_detector.py`）

| 常量 | 字面值 | 生成模块可产出 |
| --- | --- | :---: |
| `QUESTION_TYPE_NUMERIC` | `"numeric question"` | ✅ |
| `QUESTION_TYPE_SCALE` | `"scale question"` | ✅ |
| `QUESTION_TYPE_SINGLE` | `"single-choice question"` | ✅ |
| `QUESTION_TYPE_MULTIPLE` | `"multiple-choice question"` | ✅ |
| `QUESTION_TYPE_OPEN` | `"open-ended text question"` | ✅ |
| `QUESTION_TYPE_EMPTY` | `"empty question"` | ❌ 检测侧产物（全空列） |
| `QUESTION_TYPE_UNKNOWN` | `"unknown"` | ❌ 检测侧产物（元数据列 / 缺失 ≥80%） |

三条边界（不知道就会断闭环）：

1. `get_question_type_options()` 返回 6 项（含 `unknown`，**不含 `EMPTY`**）；
   backend 的 `SHORT_TYPE_KEYS` 是另一套 6 项（`num/scale/single/multi/open/empty`，
   **不含 `unknown`**），`POST /api/{sid}/types` 只接受这 6 个短码。
   **生成模块一律挂常量本身，短码只在 API 边界转换。**
2. `detect_question_types()` **丢弃** `UNKNOWN` 列（不进 dict），`EMPTY` 列保留。
   「某列消失」与「某列判 empty」是两种不同信号。
3. **词表里没有「矩阵题」。** 矩阵题在回收数据里就是 N 列 `scale question`。
   矩阵必须设计为 Section/Question 的**组织结构**（一组共享 `scale_spec` 的题），
   **绝不新增题型常量**——新增即断闭环。

约束落地：`GENERATABLE_TYPES` 必须 `from src.question_type_detector import ...`，
禁止字符串字面量；测试断言 `set(GENERATABLE_TYPES) <= set(get_question_type_options())`。

---

## 2. 复用现有 LLM 层

配置与调用（`src/llm_client.py`）：OpenAI 兼容 chat-completions，
`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 全部来自环境变量，默认 DeepSeek。

| 函数 | 消息结构 | 失败行为 | 现有调用方 |
| --- | --- | --- | --- |
| `ask_llm(prompt, timeout=120)` | 单条 user | **抛异常** | backend `/ai-report`；源码注释写明 "Do not change" |
| `call_llm(system, user, temperature=0.2, timeout=90)` | system + user | **返回 `None`** | `ai_report.py` 降级层 |

**生成模块一律用 `call_llm`**（要降级不要异常）。

降级三态（`src/ai_report.py`，直接 import，不新造）：

```
AI_STATUS_OK             = "ok"
AI_STATUS_NOT_CONFIGURED = "not_configured"
AI_STATUS_FAILED         = "failed"     # ← 不是 "api_error"
```

防幻觉三手法（生成侧照搬结构，内容反向）：

1. **规则常量拼进 system prompt**：`_GROUNDING_RULES` 是双语常量，
   `get_persona_prompt()` 拼 `persona + "\n\n" + rules`。
   生成侧新写 `_GENERATION_RULES`：分析侧是「只准解释给定数字」，
   生成侧是「只准用给定题型词表、不得声称引用已验证量表」。
2. **先本地算，再喂结果**：`build_analysis_digest()` 用 `.head(n).to_string()`
   严格限行喂给 LLM。生成侧对应的是「结构由本地决定，只让 LLM 写文案」（§6）。
3. **低温 + 静默降级**：`temperature=0.2`；`None` → 状态置 `failed`。

---

## 3. i18n 挂载方式

`src/i18n.py` 单文件，模块级 `TRANSLATIONS = {"en": {...}, "zh-CN": {...}}` 扁平 key→字符串。
`t(language, key, **kwargs)` 三级回退：语言→`en`；key→en 同 key；再无→**返回 key 本身**
（漏翻译是静默的）。枚举值另建表（`QUESTION_TYPE_TRANSLATIONS` /
`FIELD_ROLE_TRANSLATIONS` / `DATASET_MODE_LABEL_KEYS`）+ `translate_*` 函数。

新文案：

- 界面级 → 加进 `TRANSLATIONS`，前缀 `gen_*`。**必须同时加 en 与 zh-CN。**
- 校验规则文案 → **另建 `VALIDATOR_RULE_TRANSLATIONS`**，以 `rule_id` 为键，
  值为 `{en: {message, suggestion}, "zh-CN": {...}}`，消息体是带 `{column}` /
  `{points}` 占位符的模板。理由：几十条规则塞进扁平表会把文件撑到 600+ 行。

**关键约束**：前端**不走** `i18n.py`（`.zh`/`.en` 双 span + `body[data-lang]`，
切换语言不重新请求）。**凡是 API 返回自然语言，必须一次返回 zh + en 双份。**

---

## 4. 前端新增一屏的标准做法（提炼自 `frontend/assets/insight.js`）

1. **独立 IIFE 文件**，自己的闭包 + 自己的 `API` 解析
   （`localStorage.sm_api` > `config.js` > 同源，localhost 回退 `http://127.0.0.1:8000`）。
   **不改 `data.js` 任何函数。**
2. **跨文件状态只走 localStorage**：`sm_session`（`data.js:748` 上传成功时写入）、
   `sm_api`、`sm_lang`、`sm_screen`。本模块新增 `sm_draft`（§10）。
3. **三处增量**：`nav.js` 的 `order` 数组加一项；`index.html` 加一个 `.step` 按钮 +
   一个 `<section class="screen" id="screen-X">`。**现有屏 DOM/CSS 一概不动**
   （DOM 结构是 `data.js` 的选择器契约）。
4. **懒加载**：监听 `.step[data-screen="X"]` 的 click + document 上 `[data-go="X"]`
   事件委托 + 页面恢复时若该屏已 `active` 则立即加载。
5. **只用设计稿 class 词汇**：`.card/.card-h/.metrics/.metric/.dt/.sel/.pill/.ins/
   .btn/.ghost/.scrollx/.legend/.mono/.num-cell`。新徽章类另起，
   **颜色只引用 `:root` tokens**。
6. **下拉 = `chipEmbedSelect`**：`opacity:0` 的原生 `<select>` 绝对定位盖在 `.sel` chip 上。
7. **双语 = `dual(zhHTML, enHTML)`** 生成 `.zh`/`.en` 双 span。
8. **每文件自带 `esc()`**，写 `innerHTML` 前必转；`richText()` 把反引号转 `<b>`。
9. **错误统一 `.catch(showLoadError)`** 在屏内提示，**不用 alert**。

---

## 5. 数据模型

原则：JSON 可序列化 dataclass，单一真源，所有自然语言字段都是 `{zh-CN, en}` 双语对象。

```
Survey
├─ schema_version: int
├─ survey_id: str (uuid hex)
├─ title / description: LocalizedText
├─ primary_language: "zh-CN" | "en"
├─ created_at: float
├─ estimated_minutes: int              # 本地估算，非 LLM
├─ constructs: [Construct]
├─ sections: [Section]
├─ response_metadata_spec: ResponseMetadataSpec     # §5.3，本轮只留位
└─ generation_provenance: {llm_model, prompt_version, generated_at,
                           user_brief, fallback_used: bool}

Section
├─ section_id: str
├─ title / intro: LocalizedText
├─ purpose: "screening" | "demographic" | "construct" | "open_feedback" | "attention"
├─ randomize_questions: bool           # 声明用，导给投放平台，本工具不实现
└─ questions: [Question]

Question
├─ question_id: str                    # "Q07"，稳定标识
├─ code: str                           # ★ CSV 列名，回收对齐的锚点
├─ text: LocalizedText
├─ question_type: str                  # ★ 必须来自 §1 的 5 个可生成常量
├─ construct_id: str | None
├─ reverse_coded: bool
├─ attention_check: bool
├─ attention_expected_value: str | None
├─ required: bool
├─ source: "generated"                 # ★ 只有这一个取值，见 §6
├─ options: [Option]
├─ scale_spec: ScaleSpec | None
├─ multi_select_limits: {min, max} | None
├─ numeric_spec: {min, max, unit, integer_only} | None
├─ open_spec: {max_length, placeholder} | None
├─ physical_encoding_hint: str         # §12.3，默认 "delimited_single_column"
└─ display_logic: dict | None          # 跳转逻辑，本轮只存不用

Option    = {value, label: LocalizedText, order: int, exclusive: bool}
ScaleSpec = {points: int, polarity: "unipolar" | "bipolar",
             min_label, max_label, mid_label: LocalizedText | None,
             labels: [LocalizedText] | None}
Construct = {construct_id, name, definition: LocalizedText,
             expected_direction: "positive" | "negative" | None}
```

**单一真源**：题目归属只存 `Question.construct_id`，`Construct` **不存** `question_ids`。

**`code` 三条硬约束**（§7 规则 20 校验）：ASCII `^[A-Za-z][A-Za-z0-9_]{0,30}$`、
全局唯一、**`is_metadata_column(code)` 必须为 False**——否则模板一上传就被剔除。

### 5.3 `response_metadata_spec`（本轮只留位置，不采集）

```
response_metadata_spec = {
  schema_version: 1,
  enabled: false,                      # 本轮恒 false
  column_prefix: "_meta_",
  fields: {
    duration_total_seconds:    {column: "_meta_duration_total", dtype: "numeric"},
    per_question_dwell:        {column_pattern: "_meta_dwell_{question_id}", dtype: "numeric"},
    dropout_position:          {column: "_meta_dropout_at", dtype: "question_id"},
    option_order_seed:         {column: "_meta_option_seed", dtype: "string"},
    per_question_option_order: {column_pattern: "_meta_order_{question_id}",
                                dtype: "string(csv of option values)"}
  },
  source_mappings: {},                 # 未来：平台字段名 → 上面的规范名
  collected_by: null                   # 未来："self_hosted" | "wjx" | "qualtrics"
}
```

未来扩展点：

- 接自建收集层 → `collected_by: "self_hosted"`，前端按 `column_pattern` 埋点。
- 接第三方平台 API → 填 `source_mappings`（如问卷星「答题时长」→ `_meta_duration_total`，
  Qualtrics `Duration (in seconds)` → 同名），一层重命名即可复用全部下游。
- 有了 `per_question_option_order` 才能做 **order effect / primacy bias** 分析，
  这是留这个位置最实质的理由。

> ⚠️ **衔接点（本轮不实现，但必须记录）**：现有 `is_metadata_column()` 是 token 化后
> 看是否含 `id`/时间/编号，**`_meta_duration_total` 不含这些词，不会被自动剔除**。
> 将来真的采集元数据时，必须在 `preprocessing` 补一条 `_meta_` 前缀识别，
> 否则元数据列会混进题型分析。

---

## 6. LLM 调用设计

### 分工原则（本节最重要）

**LLM 只写文案，不做结构决策。**

| 本地代码决定 | LLM 负责 |
| --- | --- |
| 题型、量表点数、构念划分、题序、反向题/注意力题的位置与数量、样本量、统计方法、`code` 生成 | 题干文本、选项标签、章节引导语、中英对照 |

理由：结构决策必须可测试可复现；文案生成才是 LLM 的比较优势。同时把幻觉面
收窄到「措辞」一个维度。

### 调用结构

**先做单次调用**（更早看到东西跑起来），效果不佳再拆两阶段（蓝图 → 文案）。

- System prompt = 生成者 persona + `_GENERATION_RULES` + **完整 JSON Schema 骨架**
  （字段名、类型、枚举值全列出）+ 「只输出 JSON，不要 markdown 代码块，不要解释文字」。
- User prompt = 用户 brief + **本地已算好的结构约束**（"恰好 3 个构念，每构念 4 题 scale，
  5 点；另 2 题 demographic single；反向题 ≥1；注意力题 1"）。

### 强制严格 JSON（不依赖 provider 的 json_mode）

`llm_client` 是通用 OpenAI 兼容层，各家对 `response_format: json_object` 支持不一，
**未经验证，设计不依赖它**。四道本地闸：

1. prompt 给完整骨架 + 禁止解释文字；
2. `_extract_json_block(text)`：剥 ` ```json ` fence、取第一个 `{` 到最后一个 `}`；
3. `json.loads`；
4. **结构校验器**（不同于 §7 的方法学校验器）：必填字段缺失、`question_type` 不在词表、
   `options` 为空、`scale_spec.points` 非正整数 → 一律视为解析失败。

### 重试与降级

| 尝试 | 动作 |
| --- | --- |
| #1 | 正常调用，`temperature=0.2` |
| #2 | 原 prompt + 追加「你上次的输出无法解析：{error}。只输出合法 JSON。」 |
| #3 | `temperature=0.0` + 精简骨架 |
| 仍失败 | `AI_STATUS_FAILED` → **降级到本地模板生成器** |
| 无 API key | `AI_STATUS_NOT_CONFIGURED` → **直接走本地模板生成器** |

> **本地模板生成器 `templates.py` 不是可选项。** 分析侧没 key 只是少一段解读，
> 生成侧没 key 就没有产品。必须保证零配置状态下完整闭环可演示。

### 防「编造已验证量表」

1. **Prompt 约束**：禁止声称题目来自 SERVQUAL / TAM / UTAUT / Big Five / PANAS / SUS
   等任何已发表量表；禁止编造文献、作者、年份、DOI；若用户要求使用某已验证量表，
   回答「本工具不提供已验证量表原文，请自行获取授权版本」。
2. **本地输出侧过滤器（可测试，不靠 prompt）**：正则扫
   `\(\s*[A-Z][a-z]+.{0,40}(19|20)\d{2}\s*\)`、`doi:`、`et al.`、`改编自`
   + 一张已知量表名词表。命中 → 报 `fabricated_citation`。
3. **数据模型层（最硬）**：`Question.source` 只有 `"generated"` 一个合法取值，
   **schema 里根本不存在 `"validated_scale"` 这个位置**。

---

## 7. 方法学校验器（本模块核心）

纯函数、无 IO、无 LLM、可完全单测：`validate_survey(survey) -> list[ValidationIssue]`

```
ValidationIssue = {
  rule_id, severity: "error" | "warning",
  scope: "question" | "section" | "construct" | "survey",
  target_id, message: LocalizedText,
  evidence: str,                 # 命中片段，便于人工判断误报
  suggestion: LocalizedText | None
}
```

每条规则一个独立纯函数，注册进 `RULES` 列表。

### 7.0 严重度校准原则 ★

**在 §11 基准测试给出误报率之前，所有基于词表/正则的语义类规则一律为 `warning`。**
`error` 只留给**结构类**与**形式可判定类**（唯一性、字段存在性、计数、正则形状）。

理由：不能用精度未知的规则卡住导出。等 §11 给出各语义规则的实测误报率后，
再逐条决定是否升级为 `error`，且升级必须有基准数据支撑。

### 7.1 文本类（全部 warning）

| # | rule_id | 判定 | 严重度 | 可测试性 |
| --- | --- | --- | --- | --- |
| 1 | `double_barreled` | **见 §7.1.1 的正式判定标准** | warning | §7.1.1 + 困难反例 fixture |
| 2 | `leading_question` | 命中倾向词表：`优秀的\|出色的\|糟糕的\|难道不\|不觉得\|众所周知` / `excellent\|obviously\|don't you agree` | warning | 词表逐词一例 |
| 3 | `double_negative` | **先按逗号/分号/句号切分为分句，两个否定词必须落在同一分句内**才计数 | warning | 中文「不」进复合词频率过高（不错/不同/不仅/不过/对不起），白名单方案不可靠，故改用分句约束 + 降级为 warning |
| 4 | `absolute_wording` | 命中 `总是\|从不\|所有\|全部\|每次\|绝对\|一定` / `always\|never\|all\|every` | warning | 问频率时「总是」是合法锚点 |
| 5 | `jargon` | 命中领域术语词表，或英文缩写 `\b[A-Z]{2,5}\b` 且同题内无括号解释 | warning | 「您如何评价我们的 SaaS 的 ARR 贡献」→ 2 命中 |
| 6 | `question_length` | 中文 > 40 字 / 英文 > 25 词 | warning | 边界值测试 |
| 7 | `fabricated_citation` | §6 的引用正则 + 量表名词表 | warning\* | 每种模式一例 |

\* 规则 7 虽是正则类，但**误伤代价低、漏报代价高**，且 §6 第 3 层（schema 无
`validated_scale` 取值）已是硬保障，故此处仍取 warning，符合 §7.0。

#### 7.1.1 规则 1 `double_barreled` 的正式判定标准 ★

**标准（正式表述）**：

> 一道题构成双筒问题 (double-barreled)，当且仅当其题干中的并列连词所连接的
> **两个并列项同时处在「被评价对象」(evaluation object) 的位置**——即两者都是
> 该题要求受访者作出判断的**标的**——而非描述**作答情境** (response context)，
> 例如同伴、场景、渠道、时间等修饰成分。

**操作化检验 (operationalization)**：

> 把该题按并列项拆成两道独立的问题。**若同一名受访者可能对这两道题给出
> 不同的答案，则原题为双筒。** 若拆分后题意改变、其中一问不成立、或两问
> 必然同答，则不是双筒。

这条操作化检验是判定的**唯一裁决依据**；下面的实现启发式只是它的近似。

**实现启发式**（近似上述标准，不等于标准本身）：

1. 定位并列连词（`和 | 与 | 以及 | 并且 | 、` / ` and | or `）；
2. 取连词左右两侧的片段，要求**双侧各命中一个「可评价属性」词表条目**
   （质量 / 速度 / 价格 / 服务 / 态度 / 界面 / 功能 / 性能 / 外观 / 售后 / 内容 / 方式…）；
3. 三条**否决守卫 (guards)**，命中任一即判定为非双筒：
   - **同伴守卫**：并列项为人称（家人 / 朋友 / 同事 / 同学 / 父母…）→ 描述作答情境；
   - **复合概念守卫**：出现 `比值 | 比例 | 之比 | 比率 | 关系 | 差异 | 对比 | 之间` /
     `ratio | relationship | difference | between` → 两项合成单一概念；
   - **联合量词守卫**：出现 `都 | 均 | 同时` / `both` → 问的是「两者皆…」这一
     单一联合命题，拆分会改变命题。

**3 个正例（标注理由）**：

| 题干 | 为什么是双筒 |
| --- | --- |
| 您对本店的**服务质量**和**配送速度**是否满意？ | 两项均为被评价标的。拆成两问后，一名受访者完全可能「对质量满意、对速度不满」→ 答案可不同 |
| 这款产品的**外观设计**和**售后服务**是否达到您的预期？ | 两项是彼此独立的可评价属性，无必然相关，拆分后答案可不同 |
| 您认为课程的**内容**和**授课方式**安排合理吗？ | 内容与形式是两个独立评价维度，可以「内容好但方式差」 |

**3 个反例（标注理由）**：

| 题干 | 为什么不是双筒 |
| --- | --- |
| 您**和家人**一起用餐的频率是？ | 「您和家人」是作答情境中的同伴关系，不是被评价对象。拆成「您用餐的频率」「家人用餐的频率」已改变题意，原题问的是「一起用餐」这一件事 → **同伴守卫** |
| 您如何评价**质量和价格**的比值？ | 「质量和价格的比值」是单一复合概念（性价比）。拆开后该概念不复存在，其中一问不成立 → **复合概念守卫** |
| **线上和线下**渠道您**都**使用过吗？ | 「都」把两项合成一个联合命题，问的是「是否两者皆有」。拆分改变了命题本身 → **联合量词守卫** |

> **诚实说明**：规则 1、2、5 纯规则做不到高精度，误报是本模块最大技术风险。
> 缓解：(a) 正反例测试集固化行为；(b) 前端允许 dismiss 单条 issue；
> (c) `evidence` 必须回显命中片段。实际误报率未知，需 §11 跑出来。

### 7.2 量表类

| # | rule_id | 判定 | 严重度 |
| --- | --- | --- | --- |
| 8 | `likert_points_valid` | **分档**，见下 | 分档 |
| 9 | `likert_label_symmetry` | (a) `len(labels) == points`；(b) **仅 `polarity == "bipolar"` 时**：奇数点必须有中性中间项（`一般\|中立\|neutral\|neither`）；(c) 首尾极性相反；(d) 前后半强度词镜像（`非常/比较` ↔ `比较/非常`） | (a) **error**；(b)(c)(d) warning |
| 10 | `likert_polarity_consistency` | 同一构念内所有 scale 题的 `points` 与 `polarity` 必须一致 | **error** |

**规则 8 分档（修正：不再一律 error）**：

| points | 判定 | 文案要点 |
| --- | --- | --- |
| 5 / 7 / 10 | 通过 | — |
| 4 / 6 | warning | **无中点是正当的强迫选择(forced-choice)设计**，用于对抗中庸倾向与默许偏差(acquiescence bias)。但**不带 schema 上传时会被识别为 `numeric question`**——带 schema 上传则由 §12.3 的 `text_label`/声明值域正常还原 |
| 2 / 3 | warning | 点数过少，方差与区分度受限 |
| 其他（≤1、>10、非整数） | **error** | 形式不可用 |

> **设计原则**：`_is_scale_question()` 的 1-5/1-7/1-10 值域限制是**我们自己代码的
> 实现细节，不应反向阉割方法学校验器**。校验器只负责说明代价，由用户决定。

**规则 9(b) 的前置条件（修正）**：中性中间项要求**只对 `polarity == "bipolar"` 生效**。
单极量表（unipolar，如「从不→总是」「完全不重要→极其重要」）的中点是**中等强度**
而非中立，原写法会误报。`ScaleSpec.polarity` 已有该字段，加前置条件即可。

### 7.3 结构类

| # | rule_id | 判定 | 严重度 |
| --- | --- | --- | --- |
| 11 | `matrix_rows_limit` | 同 section 内共享同一 `scale_spec` 的题数 > 8 | warning（> 12 升 **error**） |
| 12 | `question_order` | section.purpose 偏序：`screening` 全在最前 → 其他 → `demographic` 全在最后 | 甄别题不在最前 = **error**；人口统计不在最后 = warning |
| 13 | `construct_min_items` | 按 `construct_id` 分组计数 < 3 | **error** |
| 13b | `construct_items_are_scale` | 构念内出现非 scale 题 | **error** |
| 14 | `reverse_coded_present` | 全问卷 `reverse_coded=True` ≥ 1 | **error**；构念级（≥4 题的构念至少 1 个）= warning |
| 15 | `attention_check_present` | `attention_check=True` ≥ 1，且 `attention_expected_value` 非空并存在于该题 options | **error** |
| 16 | `attention_check_position` | 注意力题不应是第 1 题或最后 1 题 | warning |
| 17 | `option_count` | single/multiple 选项数 ∈ [2, 10] | < 2 **error**；> 10 warning |
| 18 | `option_mutual_exclusivity` | multiple 的 `exclusive` 选项 ≤ 1 个且排最后 | warning |
| 19 | `option_label_uniqueness` | 同题选项标签重复 | **error** |
| 20 | `code_uniqueness_and_shape` | `code` 唯一 + 匹配 `^[A-Za-z][A-Za-z0-9_]{0,30}$` + **`is_metadata_column(code)` 为 False** | **error** |
| 21 | `bilingual_completeness` | 所有 LocalizedText 两语均非空 | warning |

**规则 13 文案（修正）**：不得写「Cronbach's α 需 ≥3 题项」——**α 在 k=2 时有定义**，
该说法数学上不准确。正确文案：

> zh-CN：少于 3 个题项时内部一致性估计不稳定，且构念内容覆盖不足。
> en: With fewer than 3 items the internal-consistency estimate is unstable and the
> construct is under-represented.

### 7.4 统一可测试性方案

- `tests/fixtures/surveys/golden_survey.json` —— 人工校准的合规问卷，
  断言 `validate_survey()` **返回 0 个 error**（最重要的回归护栏）。
- `tests/fixtures/surveys/edge_cases.json` —— 每条规则一个最小违规反例。
- **`tests/fixtures/surveys/hard_negatives.json`** ★ —— **含并列连词但不构成
  双筒**的句子，**≥8 条**（「您和家人用餐的频率」「质量和价格的比值」
  「线上和线下都使用过吗」等，中英各若干）。断言**规则 1 一条都不触发**。
  **理由：只有明显正例的测试集没有意义**——任何「见到并列连词就报」的实现
  都能通过纯正例测试集，却在真实问卷上误报率爆炸。困难反例是这条规则
  唯一有效的护栏。
- **`tests/fixtures/surveys/ambiguous.json`** ★ —— **人类标注也会分歧**的句子
  （「您对我们的服务和产品满意吗」「客服人员的专业性和态度」
  「Was the staff friendly and helpful?」等）。
  **不进 pass/fail 断言**，只记录规则的**当前行为**（characterization record）。
- 每条规则 ≥1 正例 + 1 反例；文本类 ≥5 + 5。
- `make_survey(**overrides)` builder helper，避免每例手写整份 JSON。

**为什么 `ambiguous.json` 被排除在断言之外**：

这些句子的「正确答案」在人类标注者之间就不一致。对它们写 pass/fail 断言，
等于把**其中一种任意读法固化成规范**——之后任何对规则的合理改进都会撞上
这条断言而被误判为回归，测试于是从护栏退化成阻力。

改为**记录当前行为**：测试读入这批句子，跑规则，把结果与快照比对；
快照变化**不判失败，而是要求在 review 中显式确认**。这样规则行为的漂移
始终可见，但不会把一个有争议的判断伪装成客观标准。

---

## 8. 分析计划生成（纯本地，零 LLM）

`build_analysis_plan(survey) -> AnalysisPlan`。**所有统计量本地算，不交给 LLM。**

### 8.0 通则：样本量一律以精确分布为权威 ★

**凡是输出给用户执行的样本量 (`min_n`)，一律以精确分布搜索
（`scipy.stats.nct` 等）在 n 上求得的最小值为权威。闭式公式只作对照，
且必须在 caveat 中标注该闭式值的实际功效。**

理由：`min_n` 是给用户执行的建议，**不能给出一个达不到声明功效的数字**。
闭式正态近似系统性地高估功效，其给出的 n 通常比真实所需小 1–2。

已按此通则确定的值（d=0.5, power=.8）：

| 场景 | 闭式近似 | 闭式值的实际功效 | **权威值（精确）** |
| --- | --- | --- | --- |
| 两组均值，α=.05 | 63 | 0.7952 ✗ | **64** |
| ANOVA k=3 → pairwise+Bonferroni，α′=.01667 | 84 | 0.7934 ✗ | **86** |
| ANOVA k=4，α′=.00833 | 97 | 0.7917 ✗ | **99** |
| ANOVA k=5，α′=.00500 | 107 | 0.7928 ✗ | **109** |

**以后新增任何样本量场景直接按本通则执行，不再逐个确认。**

### 8.1 信度：Cronbach's α + 置信区间 + 题项-总分相关 ★

点估计不够，**α 必须带 95% CI**。

**Feldt 方法**（F 分布闭式解，`scipy.stats.f`，零新依赖）。基于
`(1 − α̂)/(1 − α) ~ F(df₁, df₂)`，`df₁ = n − 1`，`df₂ = (n − 1)(k − 1)`：

```
lower = 1 − (1 − α̂) / F_{p/2}(df₁, df₂)
upper = 1 − (1 − α̂) / F_{1−p/2}(df₁, df₂)
```

**实现方式已定**：直接用上式解边界，**不做恒等式变换**。

> **注释里保留的等价关系说明**：存在一个等价的乘法形式，由倒数恒等式
> `1/F_q(d₁,d₂) = F_{1−q}(d₂,d₁)` 得到，即
> `lower = 1 − (1−α̂)·F_{1−p/2}(df₂, df₁)` —— **注意 df 必须交换**。
> 数值验证（α̂=0.82, n=150, k=5）：除法形式 = `[0.7655, 0.8591]`；
> 乘法 + df 交换 = `[0.7655, 0.8591]` ✅ 一致；乘法 + df 未交换 =
> `[0.7701, 0.8618]` ✗。写乘法形式而忘记交换 df 是一个静默错误
> （不报错，只给偏窄/偏移的区间），故本实现一律用除法形式。

**caveats 必须写明的前提假设**：

- Feldt CI 依赖**经典测量理论 (classical test theory)** 的**本质 τ 等价
  (essential tau-equivalence)** 假设——即各题项测量同一潜变量且**真分数方差相等**
  （载荷相等，仅容许常数差）。
- **题项方差不齐时该区间偏窄**（over-precise），实际覆盖率低于名义 95%。
- 因此 CI 必须与 §8.1 的题项-总分相关一起读：若存在 r < 0.30 的低区分度题项，
  τ 等价假设很可能已被破坏，此时 CI 宽度不可尽信。
- 若需放宽假设，应改用同余 (congeneric) 模型下的 ω 系数（McDonald's omega），
  但那需要因子分析支持，超出本模块范围。

**同时必须报题项-总分相关 (corrected item-total correlation)**：每个题项与
**其余题项之和**的相关（而非与含自身的总分），理由：**α 会随题项数机械上升
（Spearman-Brown）**，只看 α 会把「题多」误读成「信度高」。
输出每题一行，并标出 r < 0.30 的低区分度题项。

### 8.2 最小样本量估算

严格 power analysis 需 `statsmodels`（新依赖），**不引入**。用两条可验算、纯
`scipy` 的规则：

**(a) 经验法则（修正）**：`N ≥ max(10 × 全部量表题项总数, 100)`。
不是「最大构念题项数 × 10」——10:1 规则针对的是**全部题项**。

> caveat 必须注明：该经验规则在文献中存在 **5:1 到 20:1 的分歧**，此处取中间值 10:1。

**(b) 闭式公式**：

| 场景 | 公式 | 默认参数 | 结果 |
| --- | --- | --- | --- |
| 比例估计 | `n = z²·p(1−p)/e²` | p=0.5, e=0.05, 95% | **385** |
| 两组均值 | 见下：**以非中心 t 精确解为准** | d=0.5, α=.05, power=.8 | **64** |

> **两组均值 —— 权威值是 64，不是 63**：
>
> 闭式正态近似 `n = 2(z_{α/2}+z_β)²/d²` 代入得 62.79 → 63。但该近似**高估了功效**：
> 在精确的**非中心 t 分布 (noncentral t)** 下实测
> `n=63 → power 0.795`、`n=64 → power 0.801`——**n=63 达不到声明的 0.80**。
>
> **`min_n` 是给用户执行的建议，不能给一个达不到声明功效的数字。**
> 故实现上 `min_n` 由 `scipy.stats.nct` **在 n 上搜索得到的精确最小值**为权威，
> 闭式解只作为搜索起点与 caveat 中的对照值。
>
> caveat 文案：「闭式正态近似给出 62.79 → 63；但精确非中心 t 分布下 n=63 的
> 实际功效仅 0.795，故取 64。」

**(c) ANOVA（修正：不用「每组 ≥30」的拍脑袋下限）**

降解为**两两比较 (pairwise) + Bonferroni 校正**：`m = k(k−1)/2` 次比较，
把 `α/m` 代入两组场景，**同样以非中心 t 搜索的精确最小值为权威**：

| 组数 k | 比较数 m | α′ | 闭式近似 | 该 n 的实际功效 | **精确 n/组** |
| --- | --- | --- | --- | --- | --- |
| 3 | 3 | .01667 | 84 | 0.7934 ✗ | **86** |
| 4 | 6 | .00833 | 97 | 0.7917 ✗ | **99** |
| 5 | 10 | .00500 | 107 | 0.7928 ✗ | **109** |

> **为什么不是 84/97/107**：与两组场景同因——闭式正态近似给出的 84/97/107
> 实际功效仅 0.792–0.793，**均低于声明的 0.80**，属于「达不到声明功效的建议值」。
> 按 §8.2(b) 既定原则，`min_n` 一律取 `scipy.stats.nct` 搜索出的精确最小值。
> 闭式值保留在 caveat 中作对照。

caveat 还须注明：这是**保守估计**（Bonferroni 本身保守，且整体 F 检验所需
样本通常小于全部两两比较），比 ANOVA 的精确功效分析偏大。

### 8.3 分组比较方法选择 ★

**关键区分：t 检验 / ANOVA 只用于构念得分 (composite score)；单个李克特题是
定序变量 (ordinal)，必须走非参数 (nonparametric) 分支。**

| 因变量 | 分组 | 建议方法 |
| --- | --- | --- |
| **构念得分**（题项均值，近似连续） | 2 组 | independent-samples **t 检验** |
| 构念得分 | 3+ 组 | one-way **ANOVA** |
| **单个李克特题**（ordinal） | 2 组 | **Mann-Whitney U** (`scipy.stats.mannwhitneyu`) |
| 单个李克特题 | 3+ 组 | **Kruskal-Wallis** (`scipy.stats.kruskal`) |
| 单个李克特题 | 3+ **有序**组（如学历、年龄段） | **Somers' D**（主）+ **Spearman ρ**（效应量伴随），见 §8.3.1 |
| single/multiple × single/multiple | — | **卡方检验**（附「期望频数 ≥5」前提） |
| scale × scale（跨构念） | — | **Pearson correlation** |
| multiple 题描述 | — | 频次 + 响应率，**必须标注分母口径**（受访者数 vs 响应数）——对应 `CODE_REVIEW_REPORT.md` #14 |

#### 8.3.1 有序分组的趋势检验：为什么不做 Jonckheere-Terpstra

**决定：批 3 不实现 J-T，不手写。**

`scipy 1.13.1` 确实没有 J-T（`mannwhitneyu`/`kruskal`/`somersd`/`page_trend_test`
都有，J-T 没有）。但**不做的理由是验证成本，不是实现成本**：J-T 的正态近似需要
**并结 (ties) 校正**，而李克特数据恰恰是重并结场景；校正写错**不会报错**，
只会给出有偏的 p 值——**没有权威实现可对拍，错误无法被发现**。

**替代方案（scipy 已有，零新依赖）**：

| 方法 | 函数 | 定位 |
| --- | --- | --- |
| **Somers' D** | `scipy.stats.somersd` | **主检验**。有序×有序的定向关联度量，**显式处理并结**，自带 p 值。李克特数据重并结，这是选它作主检验的理由 |
| **Spearman ρ** | `scipy.stats.spearmanr` | **效应量伴随**。组序号作有序变量与作答值的单调相关 |

**与 J-T 的关系和差别（文档中必须如实写明，不得混称）**：

- **J-T** 是 k 样本**趋势检验**，原假设「各组分布相同」对立假设「各组中位数按
  给定顺序单调排列」；统计量是所有有序组对 `(i<j)` 的 Mann-Whitney U 之和。
- **Somers' D / Spearman ρ** 是**有序关联度量及其显著性检验**，回答的是
  「组序号与作答值之间是否存在单调关联」。
- 两者在常见问卷场景（有序人口统计变量 × 李克特题）**结论通常一致，但不是同一个
  检验**。报告与界面上**必须标为「有序关联检验（Somers' D）」，
  严禁标成「Jonckheere-Terpstra」**。

**J-T 记入「可选扩展」（§15.4）**：若未来实现，**必须拿一份已发表的算例
(worked example) 对拍验证才算通过**——含并结的算例，且断言统计量与 p 值双双吻合。
没有对拍就不合入。

### 8.4 输出

一张双语表：`construct / analysis / method / required_columns / min_n / assumptions / caveats`。
所有 caveat 与 §8.1–8.3 的注记逐条落表。

---

## 9. 导出格式

### (a) CSV 数据模板 —— 两份（已拍板）

**已验证的硬冲突**：只有表头、0 行的 CSV **无法通过 `/api/upload`**。
路径：`upload` → `_clean_for_storage` → `soft_clean_dataframe` →
`dropna(axis=1, how="all")`，0 行时每列全空 → 全删 → `shape[1] == 0` →
HTTP 400 `"No usable survey columns remain after preprocessing."`

**决定：导出两份，不改清洗契约。**

- `{id}_template.csv` —— 纯空表头，给投放平台用。
- `{id}_sample.csv` —— 3 行合成示例数据，用于端到端自检与演示，**能被 upload 吃进去**。

列展开：列名 = `Question.code`，按 section → question 顺序。多选题默认
**单列分号拼接**（与 `MULTI_CHOICE_DELIMITER = ";"` 一致），可选哑变量模式
（`{code}__{option_value}` N 列）。

### (b) 人可读问卷文档

`{id}.zh-CN.md` / `{id}.en.md` 两份（与现有 `/report?language=` 模式一致）。
结构：标题 / 引导语 / 预计用时 / 逐 section（编号、引导语、逐题：编号、题干、
题型标注、选项、量表锚点、`[反向计分]`/`[注意力检测]` 标记）/ 附录（构念-题目
对照表 + 分析计划表 + 校验摘要）。复用 `report/common.py` 的
`_df_to_markdown_table` / `_bullet` / `_numbered`。

### (c) 另外两份

- `{id}_schema.json` —— **§12 回收对齐的锚点，必须导出**。
- `{id}_codebook.md` —— 变量名 → 题干 → 取值编码。学术问卷标配，本质是分析计划表的变体。

---

## 10. 后端端点 + 前端新屏

### 端点（薄封装 + session 模式）

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/gen/drafts` | POST | body `{brief, language, construct_count, target_length, use_llm}` → `{draft_id, survey, validation, analysis_plan, ai_status}` |
| `/api/gen/{draft_id}` | GET / PUT | 取回 / 整体替换（PUT 返回重新校验结果） |
| `/api/gen/{draft_id}/validate` | POST | 只跑校验器（纯本地、毫秒级） |
| `/api/gen/{draft_id}/analysis-plan` | GET | 纯本地 |
| `/api/gen/{draft_id}/export` | GET | `?format=csv\|sample\|md\|json\|codebook&language=&download` |
| `/api/gen/templates` | GET | 本地模板清单（无 key 也能用） |

存储 `drafts_tmp/{draft_id}/survey.json`，复用现有内存缓存 + 定时过期机制。

**草稿持久化（已拍板）**：

1. TTL **24 小时**（不是 uploads 的 1 小时）。
2. **生成成功后自动触发一次 `schema.json` 下载**（浏览器端 `a[download]` 触发，
   无需用户点击）——这是无数据库前提下最可靠的持久化。
3. `draft_id` 写入 `localStorage.sm_draft`，**24 小时内重开浏览器自动续上**
   （启动时 `GET /api/gen/{draft_id}`，404 则清除 key 并回到空白态）。

### 前端新屏 `screen-build`（「问卷设计 / Survey Builder」）

`order = ['build','upload','overview','insight','types','stats','cross','export']`，
侧边栏符号用 ✎（与 insight 的 ✦ 同为不编号）。新增
`frontend/assets/build.js`（独立 IIFE，§4 九条约定逐条照抄）。

屏内五块：

1. **Brief 卡** —— 主题 textarea + 目标人群 input + 构念数/题量 chip select +
   语言 chip + 生成按钮 + AI 状态提示（无 key 显示「将使用本地模板生成」）
2. **问卷结构树** —— section → question；每行：编号、题干、题型徽章
   （**复用 `.tb.num/.scale/.single/.multi/.open` 五色**）、`[反向]`/`[注意力]` pill
3. **校验面板** —— error/warning 分组，每条含 rule_id、消息、evidence、定位按钮
4. **分析计划表** —— 复用 `.dt`
5. **导出卡** —— 五个按钮（空模板 / 示例 CSV / Markdown / schema.json / codebook）

**编辑能力范围**：本轮只做删题、改题干、改题型、切换反向/注意力标记。
**不做**拖拽排序、不做选项级富编辑。

**零新依赖**：不引框架、不引图表库（这一屏无图表需求）。

---

## 11. 真值测试集（ground truth）

### 合成器 `src/survey_gen/synthetic.py`

输入 `Survey schema + n_respondents + 噪声参数` → 输出 `(df, ground_truth)`。
**`ground_truth = {code: question_type}` 直接来自 schema，标注成本为零。**

生成逻辑：scale 按构念给潜变量得分加噪声再离散到 `1..points`（反向题取
`points+1−x`）；single 按 Dirichlet 抽的类别分布采样；multiple 每选项独立伯努利
后拼串；numeric 正态/对数正态；open 从短语模板库拼句。

### 噪声开关

| 开关 | 模拟什么 | 验证什么 |
| --- | --- | --- |
| `missing_rate` | 跳答 | 缺失 ≥80% 的 `unknown` 降级 |
| `scale_as_text` | `"5分"` / `"非常满意"` | `_coerce_numeric_like_values` + §12.3 `text_label` 映射 |
| `delimiter_mix` | 多选混用 `;，、/` | `split_multi_choice_response` |
| `add_metadata_columns` | 注入 提交时间/IP/答题时长/昵称/序号 | **`field_semantics` 剔除非题目字段的能力** |
| `platform_rename` | 问卷星式改名 `"1、您的性别是？"` | §12.2 指纹匹配 |
| `dummy_columns` | 多选拆成 N 个 0/1 列 | §12.3 逆哑变量 |
| `straightliner_ratio` | 一批人全选同档 | 注意力检测题的实际效力 |

### 测试文件组织

```
tests/
├── fixtures/surveys/golden_survey.json     # 合规问卷，断言 0 error
├── fixtures/surveys/edge_cases.json        # 逐规则最小违规反例
├── fixtures/surveys/hard_negatives.json    # 含并列连词但非双筒，断言不触发
├── fixtures/surveys/ambiguous.json         # 人类分歧句，只记录行为不断言
├── test_survey_schema.py
├── test_survey_validator.py
├── test_analysis_plan.py
├── test_survey_export.py
├── test_synthetic_data.py
└── test_detection_accuracy.py        # ★ 真值评估
```

**指标**：整体 accuracy、逐题型 precision/recall/F1、混淆矩阵、按噪声档位的
准确率曲线。**另外必须输出 §7.1 各语义规则在 golden 问卷上的误报率**——
这是 §7.0 严重度升级的唯一依据。

**阈值**：先跑 baseline，阈值设在 baseline 略低处（实测 0.92 → 断言 ≥0.88），
作为**回归护栏而非目标**。

**产出物**：`docs/detection-benchmark.md`（混淆矩阵 + 准确率曲线 + 误报率表）。

> **必须写进文档的局限**：合成数据准确率**天然高于真实数据**，因为合成器与检测器
> 共享同一套假设。合成集只用于**回归检测与相对比较**，不构成真实性能声明。

---

## 12. 题型解析的权威链与 schema 对齐

> 设计目标：**schema 是先验不是真理，检测器从推断者变成审计员。**

### 12.1 优先级链

```
declared_type  (prior)      来自 schema；无 schema 时为 None
detected_type  (audit)      来自 detect_question_type()，★ 永远计算，永不跳过
conflict       (flag)       declared ≠ detected 时置位
active_type    (authority)  最终生效值
resolution                  "declared" | "detected" | "user"
```

`meta.json` 扩展（**`question_types` 键语义完全不变**，仍等于 active，五屏零改动）：

```json
{
  "question_types":  {"sat_01": "scale question"},
  "detected_types":  {"sat_01": "numeric question"},
  "declared_types":  {"sat_01": "scale question"},
  "type_resolution": {"sat_01": "declared"},
  "type_conflicts":  [{"column": "...", "declared": "...", "detected": "...",
                       "conflict_type": "...", "detail": "..."}],
  "schema_link": {
    "draft_id": "...", "survey_id": "...",
    "match_confidence": 0.91, "match_method": "jaccard_bigram+value_set",
    "matched": {"csv_col": "question_code"},
    "unmatched_csv": [], "unmatched_schema": []
  }
}
```

**解析顺序 `user > declared > detected`，但有一个关键例外**：当 `conflict_type`
属于**硬冲突集合**（数据明确证伪声明）时，`declared` **不自动生效**，`active`
退回 `detected` 并标红等待用户裁决。

API 增量：`/detect` 每项增加 `declared` / `resolution` / `conflict` 三个字段；
新增 `POST /api/{sid}/schema-link`、`GET /api/{sid}/conflicts`。

前端增量：types 屏每行加来源 pill（声明/检测/已修正），冲突行标警告色。
**现有 `.tb` 徽章和覆盖下拉一律不动。**

### 12.2 回收数据 ↔ schema 对齐

**L1 精确匹配**：CSV 列名 == `Question.code`。自家模板走这条，命中率 100%。

**L2 模糊匹配**（平台改过名）。三路相似度：

| 分量 | 算法 |
| --- | --- |
| **名称相似** `s_name` | 规范化（去题号前缀 `^\d+[、.．)]\s*`、去「（单选题）」等平台后缀、全半角、大小写、去标点）后做**字符 bigram Jaccard**（中文用 bigram 比分词稳且零依赖） |
| **位置相似** `s_pos` | `1 − |csv_idx/len_csv − q_idx/len_q|`（平台通常保序） |
| **取值集合相似** `s_val` | CSV 列实际取值集合 ∩ schema 声明 option 标签集合的 Jaccard |

#### ★ 权重必须按题型动态调整（修正：修补一个真实漏洞）

**漏洞**：固定权重 `s_val = 0.4` 在量表题上**完全退化**——一份问卷里所有 5 点
量表题的取值集合都是 `{1..5}`，`s_val` 恒为 1.0，**零区分度**，且因权重最高会
**淹没名称与位置的有效信号**。匈牙利算法会在量表题之间做近乎随机的一对一分配。

**这是最危险的错配**：题型判对了（都是 scale），**任何题型冲突检查都不报警**，
但**构念归属全错**，α 与构念得分**静默出错**。

**修法**：

| 声明题型 | `s_name` | `s_pos` | `s_val` | 说明 |
| --- | --- | --- | --- | --- |
| **scale** | **0.55** | **0.35** | **≤0.10** | 取值集合几乎无信息；改为依赖名称 + 位置 |
| single / multiple | 0.35 | 0.15 | **0.50** | 选项标签在往返中通常原样保留，是最强信号 |
| numeric / open | 0.55 | 0.25 | 0.20 | 取值集合发散，参考价值中等 |

**外加结构约束：矩阵题的连续列块 (contiguous block)**。矩阵题在回收数据里
必然是**连续列块**，且共享同一 `scale_spec`。据此加一条块级对齐：

1. 在 schema 侧识别「共享同一 `scale_spec` 的连续题序列」= 一个 block；
2. 在 CSV 侧识别「取值域一致、位置连续」的列段 = 候选 block；
3. 先在**块级别**做匹配（用块内首尾题的名称相似度 + 块长度），块匹配成功后
   **块内按位置顺序一一对应**，不再让匈牙利算法在块内自由分配。

> 这条约束把「N 个无法区分的量表题」从 N! 种分配收敛到 1 种。

**必须写测试覆盖的场景**（§14 批 7 验收项）：
一份含 2 个构念 × 各 4 题 5 点量表的问卷，开 `platform_rename`，断言
(a) 8 个量表题**全部匹配到正确的 question_id**；(b) 构念归属零错配；
(c) 若刻意打乱块顺序，匹配置信度应下降到 `uncertain` 档而不是给出错误的高置信度。

#### 分配算法与三档置信度

`scipy.optimize.linear_sum_assignment`（匈牙利算法，scipy 已有）做一对一最优分配。

| 综合分 / 整体匹配率 | 处置 |
| --- | --- |
| ≥ 0.75 且匹配率 ≥ 60% | `matched`，`declared_type` 生效 |
| 0.45 – 0.75 | `uncertain`，declared 仅作**建议**，active 用 detected |
| < 0.45 或整体匹配率 < 40% | **整体降级为纯检测模式** |

**降级路径 = 现有行为逐字节不变**，最坏情况就是回到今天。

**手动兜底**：前端提供「上传 schema.json」入口 + 「CSV 列 ↔ 题目」手动对照表。

**未匹配上的 CSV 列**（提交时间/IP/时长/昵称）→ 交给 **`field_semantics`** 判角色。
**这是新定位下保留 field_semantics 的价值落点。**

### 12.3 语义题型 → 物理编码映射层

`PhysicalEncoding` 与 `question_type` **正交**：

| 语义题型 | 物理编码 | 识别信号 | 归一化目标 |
| --- | --- | --- | --- |
| multiple | `delimited_single_column` | 单列、含分隔符、token 跨行复用 | 原样进现有管线 |
| multiple | `dummy_columns` | N 列共享前缀（`Q5_`/`Q5__`/`Q5.`）或列名形如「题干-选项」，取值 ⊆ `{0,1}`/`{是,否}`/`{TRUE,FALSE}`/`{空,选项名}` | **逆哑变量**：折叠回一列分号串 |
| multiple | `count_columns` | 每选项一列但取值是次数 | 本轮不支持，报 warning |
| scale | `numeric` | 数值 `1..points` | 原样 |
| scale | `text_label` | 取值 ⊆ 声明的 labels | **按 labels 顺序映射回 `1..points`** |
| scale | `score_text` | `"5分"` | 现有 `_coerce_numeric_like_values` 已支持 |
| single | `code` | 取值是选项 value（A/B/C 或 1/2/3） | 用 schema 的 value→label 还原 |

> **`text_label` 是 schema 创造的、纯检测永远做不到的价值**：检测器看到
> 「满意/一般/不满意」只能判 single-choice，**无法知道「满意」是第 4 档还是第 5 档**，
> 也就无法算构念得分。有了 `labels` 顺序，量表才能还原成数值。
> 这是「全流程闭环」最有说服力的单点论据。

**与 `split_multi_choice_response` 的关系（明确划界）**：

- **不替换、不修改它。** 它是 token 级归一化（一个单元格 → 选项列表），
  已被 detector / descriptive / cross 三处依赖，且已把 `,;；，、/|空格` 归一到 `;`。
- 新映射层在**它的上游**，只负责把 `dummy_columns` / `text_label` 这类**平台形态**
  折叠或还原成单列文本形态，之后一切照走现有管线。
- 落点：`src/survey_link/physical_encoding.py`，
  `normalize_physical_encoding(df, schema_link) -> (df_normalized, encoding_report)`，
  在 backend `_save_session` 之后、`detect_question_types` 之前作为**可选步骤**。
  **无 schema 时完全跳过 → 现有行为逐字节不变。**

### 12.4 冲突类型清单与前端提示

| conflict_type | 判定 | 硬/软 | active 归属 |
| --- | --- | --- | --- |
| `scale_points_mismatch` | 声明 5 点，数据 distinct 数 > 5 或上界 > 5 | **hard** | detected，待裁决 |
| `scale_out_of_range` | 出现 < 1 或 > points 的值 | **hard** | detected |
| `declared_single_but_multivalued` | 声明 single，检出多值分隔符比例 > 15% | **hard** | detected |
| `declared_scale_but_text` | 声明 scale，数据是无法映射的自由文本 | **hard** | detected |
| `type_mismatch` | declared ≠ detected 且不属上述细分 | soft | declared（可撤销） |
| `declared_multi_but_single_valued` | 声明 multiple，无任何分隔符 | soft | declared |
| `option_unknown_value` | 出现 schema 未声明的选项标签，比例 > 5% | soft | declared，列出未知值 |
| `option_missing` | 声明的选项 0 次出现 | info | declared |
| `column_missing` | schema 有题，CSV 无列 | soft | — |
| `column_extra` | CSV 有列，schema 无题 | info | 交 `field_semantics` |
| `attention_check_failed_rate` | 注意力题通过率 < 70% | info | —（数据质量） |
| `reverse_coding_suspect` | **见下** | soft | —（提示忘了反向计分） |

**`reverse_coding_suspect` 的三条护栏（修正）**：

1. **只在未重编码的原始数据上计算**。若管线已对 `reverse_coded=True` 的题
   做过 `points+1−x`，此检查**必须跳过**（否则正负号翻转，结论完全反过来）。
   实现上须显式接收「是否已重编码」标志，不得靠推断。
2. **最小样本量门槛**：有效配对 `n < 30` 时不报（小样本相关系数极不稳定）。
3. **效应量阈值**：仅当 `r > +0.30`（即明确的正相关，而非任意正值）才报。
   `|r| ≤ 0.30` 视为无结论。

> 这三条缺一不可。缺 1 会给出方向相反的结论，缺 2、3 会在小样本下疯狂误报。

**前端提示方式**：
- types 屏冲突行左侧 3px `--warn` 边条；题型单元格显示「声明:量表 / 检测:数值」
  双行；覆盖下拉旁加「采用声明」「采用检测」两个 `.btn.ghost`
- 可折叠「冲突汇总」卡（复用 `.ins.warn`），点击定位
- hard 冲突未裁决时，export 屏下载按钮旁给 warning 提示——**只提示，不阻断**

---

## 13. 硬约束（实施中随时对照）

1. 现有六屏（upload/overview/insight/types/stats/cross/export）的 DOM/CSS **一概不动**；
   新界面全部增量另起。
2. 新界面只引用 `:root` 现有 design tokens，不新造颜色/字体/阴影/圆角。
3. **不引入任何第三方前端依赖**（框架、图表库皆不可）。
4. 后端不新增分析逻辑，一律调 `src/`。
5. 生成模块的题型一律用 `question_type_detector` 的常量，禁止字符串字面量。
6. 每批交付：**pytest 全绿**（当前基线 137 passed）+ 本地启动验证步骤。
7. 线上部署行为（现有端点响应结构、`src/preprocessing` 严格清洗语义、`render.yaml`）
   不做破坏性变更——只加字段、加参数，缺省行为不变。
8. **不修改** `PROJECT_LOG.md` / `TASK.md` / `BUG_TRACK.md` / `CODE_REVIEW_REPORT.md`
   （涉及协作者署名，由项目所有者自行处理）。

---

## 14. 分批实施计划

| 批 | 内容 | 工作量 | 可验证产出 |
| --- | --- | --- | --- |
| **0** ✅ | **拆分 `report_generator.py` → `src/report/` 包**：`common` / `llm_prompt` / `survey` / `general` / `mixed` / `dispatch`；`__init__.py` 导出公开 API；`report_generator.py` 降为 shim，re-export 全部 36 个名字（含 `_build_numeric_findings`） | 半天 | **已完成**：137 passed（基线 137），测试零改动，AST 逐函数比对 36/36 一致（方法见 §16） |
| **1** ✅ | `survey_gen/schema.py` + `vocabulary.py` + `validator.py`（22 个规则函数 / 34 个 rule_id）+ 四份 fixture + `i18n.VALIDATOR_RULE_TRANSLATIONS` | 一天 | **已完成**：229 passed（基线 137，新增 92）；golden 问卷 **0 error 且 0 warning**；34/34 rule_id 均有双语文案且被测试触达 |
| **2** | `templates.py`（3-4 个本地主题模板）+ `export.py`（5 种导出）+ `synthetic.py` | 一天 | **第一个完整闭环，零 API key**：模板 → 校验 0 error → 导出 → 合成 200 行 → 喂 `/api/upload` → 200 且题型对得上 |
| **3** | `analysis_plan.py`（§8.1 Feldt CI + item-total、§8.2 三组样本量**均以 nct 精确搜索为准**、§8.3 非参数分支 + §8.3.1 Somers' D 趋势检验）+ `test_detection_accuracy.py` + `docs/detection-benchmark.md` | 一天 | 分析计划表 + **混淆矩阵 + 语义规则误报率表** |
| **4** | `llm_author.py`：prompt 骨架 + `_extract_json_block` + 结构校验 + 2 次重试 + 三态降级 | 一天 | mock `call_llm` 覆盖四条路径；无 key 自动走模板；引用过滤器有测试 |
| **5** | `/api/gen/*` 全部端点 + `drafts_tmp`（24h TTL）+ `test_api_gen.py` | 一天 | curl 走通四步；**现有 `test_api` / `test_api_v2` 一字不改全绿** |
| **6** | 前端 `screen-build` + `build.js` + index.html/nav.js 增量 + 自动下载 schema.json + `sm_draft` 续接 | 一天 | 浏览器完整演示；无 key 显示模板降级；双语正常；控制台无报错 |
| **7** | §12 全部：`survey_link/alignment.py`（动态权重 + 连续列块）+ `physical_encoding.py` + schema-link/conflicts 端点 + types 屏增量 | 一天 | §12.2 的量表块匹配三项断言全过；**关掉 schema 时行为与今天逐字节一致** |
| **8** | insight 屏改标题「数据质量与字段识别」+ README 与对外表述改为「问卷全流程工具」 | 半天 | 文档一致性 |

合计约 8.5 天。**前 6 批（约 6 天）即构成完整可演示闭环。**

排序理由：批 0 前置——生成模块会新增第四种输出结构（问卷文档 + codebook），
1031 行单文件再加会失控，且这批零风险有测试护栏。批 2 是第一个「能看」的里程碑
且刻意不依赖 LLM。批 7 排最后——技术难度最高，且前 6 批已构成完整产品。

---

## 15. 技术债与待确认

### 15.1 技术债：测试仍走兼容 shim，新路径未被直接覆盖 ★

批 0 之后，`app.py` 与 `backend/main.py` 已改为 `from src.report import ...`，
但 **4 个测试文件仍从 `src.report_generator` 导入**
（`test_report.py` / `test_report_modes.py` / `test_datasets_smoke.py` /
`test_survey_compatibility.py`）——这是「测试一字不改」这一验收条件的直接后果。

**风险**：`src/report/__init__.py` 的 `__all__` 若漏名或写错，**测试不会发现**，
因为测试走的是 shim（shim 逐个显式 re-export 36 个名字，与 `__all__` 无关）。
换言之，新公开路径目前**没有回归保护**。

**两条出路（本轮不动，只记录）**：

- (a) 把测试迁到 `from src.report import ...`，**shim 只对外**（保留给下游/旧代码）；
- (b) 明确宣布 **shim 即公开 API**，`src.report` 只是内部组织，`__all__` 不承担契约。

倾向 (a)，但迁移会改动 4 个测试文件，须与「重构批次测试零改动」的原则分开的
独立批次里做，以免混淆「重构是否引入行为变更」的判断。

### 15.1b 技术债：`is_metadata_column` 的语言不对称 ★（批 1 发现）

`src/preprocessing.is_metadata_column` 实际只匹配**中文关键词 `时间` / `编号`**
加上 **token `id`**（含 camelCase 拆分，故 `UserID` / `student_id` 命中）。

**缺口**：英文时间戳列名一个都不认。实测：

| 列名 | 判为元数据 |
| --- | --- |
| `提交时间` / `问卷编号` / `UserID` | ✅ |
| `submit_time` / `timestamp` / `submitted_at` | ❌ |

**为什么这对本模块要紧**：第三方平台的**英文导出**恰恰产出这类列名。
回收数据里的 `submit_time` 不会被剔除，会进入问卷视图并被当成一道题参与
题型识别与统计。这是既有实现的缺口，非批 1 引入。

**处置**：本轮不改（改动 `is_metadata_column` 会牵动 `test_metadata` /
`test_preprocessing` / `test_api` 三组契约测试）。已用
`test_metadata_guard_is_asymmetric_across_languages` **固化当前行为**，
使其可见。**修复归入批 7 的对齐层**——那里本来就要统一处理 `_meta_` 前缀
（§5.3），两件事同源，一起改一次。

### 15.2 待确认

1. ~~Feldt CI 的 df 顺序~~ —— **已定**：采用除法形式直接解边界，不做恒等式变换
   （§8.1）。
2. **§7.1 语义规则的实际误报率未知**，批 3 的基准跑出来后再决定是否有规则可升 `error`。
3. **L2 动态权重的具体数值**（0.55/0.35/0.10 等）是初值，需用 §11 的
   `platform_rename` 合成集实测调优。
4. **Bonferroni 样本量取 86/99/109（精确）而非 84/97/107（闭式）** —— 评审原话
   指定采用 84/97/107，但那三个值的实际功效仅 0.792–0.793，低于声明的 0.80，
   与评审自己确立的「`min_n` 不能给达不到声明功效的数字」原则冲突。
   本文档按该原则统一取精确值，**此处待最终确认**（§8.2c）。

### 15.3 明确不做

- 问卷投放与在线收集（填答链接、答案数据库、用户系统）—— §0 范围红线。
- 第三、四阶段功能（向数据提问 / 文本主题 / 时间序列 / 建模准备度）。
- 前端框架与图表库。

### 15.4 可选扩展（有前置验收条件才可实现）

- **Jonckheere-Terpstra 趋势检验**：若未来实现，**必须拿一份已发表的算例
  (worked example) 对拍验证**——须含并结 (ties) 的算例，且统计量与 p 值双双吻合，
  否则不合入。理由见 §8.3.1：并结校正写错不报错，只给有偏 p 值。
- **McDonald's ω**（放宽 τ 等价假设的信度系数）：需因子分析支持，会引入
  `statsmodels`/`factor_analyzer` 依赖，超出当前范围。

---

## 16. 重构验证方法（标准做法，后续任何重构照此办理）

批 0 采用的验证流程，效果良好，**定为本项目重构的标准动作**：

1. **不手抄代码。** 用 `ast.parse` 取每个顶层定义的精确行范围
   （含 `decorator_list` 的起始行），按行范围**切片原文**写入新模块。
   人不参与代码搬运，从源头消除转录错误。
2. **切片前做覆盖检查**：断言「每一个非空行要么属于某个 AST 节点，要么是导入」，
   任何未被覆盖的非空行（游离注释等）都会导致脚本中止，防止静默丢代码。
3. **先算依赖再分模块**：用 AST 遍历建立函数间调用图 + 被调用图，
   据此决定模块归属与 import 方向，并确认**无环**。
4. **导入按实际引用生成**，不靠人工判断。注意 `from __future__ import annotations`
   下注解是字符串，纯 `ast.Name` 遍历会漏掉只在注解中出现的名字，
   需**辅以对切片文本的正则扫描**兜底。
5. **AST 逐函数比对作为验收硬指标**：
   `ast.dump(原函数) == ast.dump(新函数)`，要求 **N/N 全等**。
   这比 diff 更强——它证明的是语法树等价，不受空行/缩进/换行影响。
   批 0 结果：**36/36 一致**。
6. **测试零改动 + 全绿**：重构批次**不允许修改任何测试**。测试一旦要改，
   就说明不是纯重构，必须拆成两个批次。批 0 结果：137 passed（基线 137）。
7. **静态检查新模块**：`pyflakes src/<pkg>/*.py` 须 exit 0
   （re-export facade 因固有的「导入未使用」告警需单独排除）。
8. **原文件保留备份**至临时目录，便于随时对拍与回滚。

> 这套流程把「重构有没有改变行为」从主观判断变成可执行的断言。
> 后续拆 `i18n.py`、拆 `app.py` 等，一律照此执行并在提交信息里写明 `N/N` 比对结果。
