# 方法学校验器的外部效度检验

> 2026-07-31。对应实现：`src/survey_gen/validator.py`、
> `tests/test_survey_external_validity.py`。
> 设计背景见 `docs/specs/survey-generation-module.md` §7、§17。

## 1. 为什么要做

`tests/fixtures/surveys/golden_survey.json` 是**规则作者自己构造**的问卷，
它跑出 0 error 0 warning 属于自我循环，**不构成对精确率（precision）的任何证据**。

下一批要写的 `templates.py`（本地问卷模板生成器）必须通过校验器。
**校验器歪了，模板就会被扭曲**：它会被迫回避某些正当的量表设计，
或被迫塞进某些并不适用的题型。因此必须先用一份与本规则体系无关的
专业问卷做检验。

判据（事前约定）：**如果一份专业设计的问卷触发了大量 error，那是我们的规则错了，
不是问卷错了。**

## 2. 材料与方法

### 2.1 材料

**中国家庭追踪调查（China Family Panel Studies, CFPS）2018 年汇总问卷**，
北京大学中国社会科学调查中心（ISSS）编制并公开发布。

- 来源：<https://www.isss.pku.edu.cn/cfps/> → 文档中心 → 调查问卷
- 文档：CFPS 2018 汇总问卷，PDF，233 页
- 取样：手工转写 **51 题**，覆盖工作满意度电池（6 题）、人际信任电池（6 题）、
  尽责性电池（11 题，含 3 道反向计分）、社会公平感知电池（8 题）、
  婚姻与生活满意度（6 题）、单选题（7 题）、数值题（3 题）、开放题（1 题）

选择理由：CFPS 是长期运行的全国性追踪调查，问卷由方法学专业团队设计，
且**问卷文档公开可下载**。中国综合社会调查（CGSS）也在候选之列，
但其官网仅公布问卷结构说明，实际题目位于需注册登录的 CNSDA 数据档案，
无法直接取得。

### 2.2 转写规则

统一执行，以保证校验器看到的是**受访者听到的题目**而非施测系统的内部结构：

1. 剥离 `【CAPI】` 加载指令与 `访员注意` / `F1` 访员说明；
2. 其余题干逐字保留；
3. **仅转写中文**。CFPS 是单语工具；若由我补写英文，等于把自己的文案
   送进措辞规则，会污染这次检验；
4. **构念只在原问卷自身用共同引导语成组之处声明**（工作满意度、信任、
   尽责性、社会公平四组）。CFPS 不随问卷发布构念表，此处是我们对其
   可见分组的建模；
5. 0-10 量表如实记为 `points=11`。

### 2.3 版权隔离（重要）

本仓库将用于研究生申请展示，**不逐字转载第三方问卷**。fixture 因此拆为两份：

| 文件 | 是否提交 | 内容 |
| --- | :---: | --- |
| `tests/fixtures/surveys/external_structure.json` | ✅ | 仅结构：点数、极性、构念分组、反向计分标记、选项数量、矩阵行数、题型、章节用途、单语声明。题干/选项/量表锚点**全部替换为占位符** |
| `tests/fixtures/surveys/external_wording.json` | ❌ 已入 `.gitignore` | 完整转写，含原问卷文案。仅存在于本地 |

拆分点不是随意的，它**恰好对应规则对文案的依赖**：10 条触发规则中，
7 条只依赖结构，由提交的文件守住；3 条依赖实际文案
（`likert_intensity_mirror` / `absolute_wording` / `likert_endpoint_polarity`），
由本地文件守住。依赖文案的测试在文件缺失时 `skip`，并打印说明——
**这是有意设计的状态，不是环境损坏**。

新克隆的仓库若要复跑完整检验，按 §2.1、§2.2 自行下载并转写即可。

### 2.4 两份措辞语料的分工（不可互换）

版权隔离带来一个副作用：`external_wording.json` 进了 `.gitignore`，
**CI 上那 8 条测试永远跳过**——也就是精确率最不确定的三条文本规则
在 CI 里零覆盖。为此另建一份可提交的语料。

| 语料 | 提交 | 撰写者 | 角色 |
| --- | :---: | --- | --- |
| `tests/fixtures/surveys/synthetic_wording.json` | ✅ | **本项目原创**（32 条，中英混合） | **CI 的回归护栏**。仿真实问卷句式，每条都刻意贴着某条规则的边界（`near` 字段注明贴的是哪条） |
| `tests/fixtures/surveys/external_wording.json` | ❌ | 第三方专业机构 | **外部效度证据**。仅本地 |

**两者不可互相替代**，理由必须说清楚：

- `synthetic_wording.json` 由**规则作者本人**撰写，它跑通只能证明
  「规则不会在看起来像问卷的文字上乱报」，**不能证明规则可泛化**——
  这与 `golden_survey.json` 是同一种循环，只是循环得浅一些。
- `external_wording.json` 出自**从未见过这套规则的人**，
  **只有它构成外部效度证据**。

一句话：**前者是护栏，后者是证据。** CI 上有护栏没有证据，
是版权隔离的已知代价，不应被含混过去。

## 3. 结果

51 题共触发 **104 条**（9 error / 95 warning）。

| rule_id | 严重度 | 次数 | 判定 | 由哪份 fixture 守住 |
| --- | --- | ---: | --- | --- |
| `likert_points_invalid` | **error** | 8 | ❌ 误报 | 结构 |
| `attention_check_present` | **error** | 1 | ❌ 误报 | 结构 |
| `bilingual_completeness` | warning | 59 | ⚪ 产品要求的产物 | 结构 |
| `likert_points_forced_choice` | warning | 19 | ✅ 正确 | 结构 |
| `likert_intensity_mirror` | warning | 6 | ❌ 误报 | 措辞 |
| `absolute_wording` | warning | 5 | ❌ 误报 | 措辞 |
| `reverse_coded_per_construct` | warning | 3 | ✅ 真实 | 结构 |
| `likert_endpoint_polarity` | warning | 1 | ❌ 误报 | 措辞 |
| `matrix_rows_limit` | warning | 1 | ✅ 真实 | 结构 |
| `option_count_too_many` | warning | 1 | ❌ 误报 | 结构 |

**零触发**：`double_barreled`、`leading_question`、`double_negative`、`jargon`、
`question_length`、`fabricated_citation`、`code_shape`、`code_uniqueness`、
`code_is_metadata`、`option_label_uniqueness`、`construct_min_items`、
`construct_items_are_scale`、`question_order_screening`。

## 4. 逐条判定

### 4.1 ❌ `likert_points_invalid` × 8 —— 规则错，且牵出既有代码缺陷

0-10 量表被判 error。0-10 是最常用的量表形态之一（NPS、生活满意度阶梯、
本问卷的信任电池），对它报错不可辩护。

检验这一条时实测发现，缺陷不止在校验器，**检测器 `_is_scale_question` 同样
识别不了 0 起量表**，且**只修一处是半修复**：

| 声明量表 | 现状 | 只放宽下界 | 放宽下界 + unique 上限 |
| --- | --- | --- | --- |
| 1-5 / 1-7 / 1-10 | ✅ scale | ✅ | ✅ |
| 0-4 / 0-6 | ❌ numeric | ✅ | ✅ |
| **0-10** | ❌ numeric | **❌ 仍失效** | ✅ |
| 1-2 / 0-1 | ❌ numeric | ❌ | ❌（有意保留） |
| 0-100 | ❌ numeric | ❌ | ❌（正确） |

原因：`in_scale_range` 要求 `1 <= min`；放宽后 0-10 的 11 个不同取值
又被 `unique_count > 10` 卡掉。**完整修复需同时改两处。**
二值量表（1-2 / 0-1）维持现状——放宽 `unique_count < 3` 下界会把大量
0/1 哑变量误判成量表，代价更大。

**这同时证伪了本项目此前的一处记载**：设计文档与
`likert_points_forced_choice` 的建议文案都称「4/6 点不带 schema 会被识别为
numeric question」。实测 4 点与 6 点**能被正确识别**为量表题；
真正的缺口是 0 起量表与二值量表。该文案在向用户陈述一件不存在的事，须改。

**已实施**：`ScaleSpec` 增加 `min_value`，把「点数」与「取值范围」分开表示。
分档重定：`points < 2 或 > 11` 才 error；`{4,6}` forced-choice warning
（**删去了那句不成立的代价陈述**，改为说明分辨率取舍）；`{2,3}` coarse warning；
其余通过。**0 起量表另立 `likert_points_zero_based` warning**，文案说明
「这是通行做法，无需修改；请把 schema 与数据一并保留」。

**检测器侧的放宽已否决，两件事就此解耦。** 实测显示放宽会让计数变量误判率
从 20% 升到 100%（见 `docs/detection-benchmark.md`），而误判方向的代价是不对称的。
检测器改为提供 `scale_candidate` 旁路提示，题型判定不变。
**校验器的这项修复不依赖检测器做任何改动。**

### 4.2 ❌ `attention_check_present` × 1 —— 类别错误

CFPS 采用 **CAPI 面访**，访员在场。注意力检测题是**自填式网络问卷**的约定，
对访员施测工具强制要求它，是把一种施测方式的规范套到另一种上。

**已实施**：`Survey.administration_mode` + `schema.MODE_POLICY` 一张表，
被每条模式相关规则读取，而不是给单条规则开后门。当前挂靠四项参数：

| 参数 | 自填式 | 访员施测 |
| --- | --- | --- |
| `requires_attention_check` | True | **False** |
| `max_stem_chars_zh` / `max_stem_words_en` | 40 / 25 | **60 / 40** |
| `matrix_rows_warn` / `matrix_rows_error` | 8 / 12 | **12 / 16** |
| `expects_dont_know_option` | False | True（**预留，暂无规则读取**） |

以后新增模式相关规则只需加一个键，不需要再改规则结构。
副作用：本问卷 11 题的矩阵在访员施测下不再触发 `matrix_rows_limit`
（有卡片辅助，阈值提到 12），这是预期内的。

### 4.3 ❌ `likert_intensity_mirror` × 6 —— 词表不全

满意度锚点「非常不满意 / 不太满意 / 一般 / 比较满意 / 非常满意」被判强度不对称。
`不太` 与 `比较` 在中文里正是一对镜像强度词，但 `INTENSIFIER_TIERS` 未收 `不太`。

**已实施**：补入 `不太 / 不很 / 还算 / 有点 / 略微` 等 tier-1 词。该问卷的 6 条全部消失。

### 4.4 ❌ `absolute_wording` × 5 —— 作用域错，不是词表错

5 次命中全部来自 `总是`，且全部出自尽责性量表的特质题（形如「对于事情我总是
准备充分」）。这是特质测量的标准句式，`总是` 在此是量表锚点而非绝对化陷阱。

**曾考虑**把 `总是 / always` 移出词表，**已否决**：那样一来
「您总是对我们的服务满意吗」这类真正的绝对化措辞就永远抓不到，
**用一个误报换掉整条规则的检出能力是亏的**。

**已实施**：限定作用域，**检出能力完整保留**。

- 只检查题干，**从不检查选项标签与量表锚点**——「从不 / 总是」是完全正当的
  单极锚点对（已加测试固化）；
- 题目属于**已声明构念的量表电池**（有 `construct_id` 且为 scale 题）时降为
  `info`；
- 单独成题的满意度/是否类问题**维持 warning**：
  「您总是对我们的服务满意吗」仍然被抓到（已加测试固化）。

新增 `SEVERITY_INFO` 档。该问卷的 5 条从 warning 转为 info，全部出自尽责性电池。

### 4.5 ❌ `likert_endpoint_polarity` × 1 —— 词表漏项

锚点「很不好 / 很好」。负极词表收了 `很差 / 较差 / 差`，**未收 `不好`**。

**已实施**：补入 `不好 / 不佳 / 不行 / 不高 / 不足`。该问卷的 1 条消失。

### 4.6 ❌ `option_count_too_many` × 1 —— 残差码不应计数

一道「生病时谁照顾您」的单选题有 11 个选项，其中 3 个是**残差/特殊码**
（其他人员、没生过病、不需要照顾）。

**已实施**：`Option.residual: bool`，计数时排除。该问卷的 11 选项题
（含 3 个残差码）降到 8 个实质选项，不再触发。
**批 3 待办（已记）**：残差类别在**分析阶段**同样要排除——频次分布的分母、
卡方检验的列联表都不应把「其他 / 不适用 / 拒答」当作实质类别。

### 4.7 ⚪ `bilingual_completeness` × 59 —— 产品意见，非方法学

单语工具必然全量触发（51 题 + 7 章节 + 1 标题）。它占全部触发的一半以上，
**会把校验器的信噪比冲垮**。强制双语是我们的产品决定，不是方法学要求。

**已实施**：`Survey.languages: list`，`bilingual_completeness` 只检查声明的语言。
本问卷声明单语后，59 条全部消失。

### 4.8 ✅ `likert_points_forced_choice` × 19 —— 规则正确

CFPS 的尽责性组与社会态度组确实全部采用 4 点量表
（十分不同意/不同意/同意/十分同意，另设一个不读出的中立选项）。

这直接验证了此前把该档从 error 改为 warning 的决定：
**若保持 error，一份专业问卷的 19 道题会被挡住导出。**

### 4.9 ✅ `reverse_coded_per_construct` × 3、`matrix_rows_limit` × 1 —— 真实

三个 6–8 题的电池确实不含反向计分题；11 题共用同一量表格式的矩阵确实
容易诱发直线作答。

值得记录的是：尽责性电池因含 3 道反向题而**正确地未触发**
`reverse_coded_per_construct`——规则具备区分力，不是无差别报警。

## 5. 修复后的结果

| | 初测 | schema 修复后 | C/D/E/F 后 |
| --- | ---: | ---: | ---: |
| 结构骨架（提交的 fixture） | 92 条 / **9 error** | 31 条 / 0 error | **30 条 / 0 error** |
| 完整转写（本地） | 104 条 / **9 error** | 43 条 / 0 error | **35 条 / 0 error** |

**一份专业设计的问卷现在不触发任何 error。** error 是唯一会挡住导出的东西，
所以这正是事前判据要求的结果。剩下的全部是 warning：

| rule_id | 严重度 | 次数 | 性质 |
| --- | --- | ---: | --- |
| `likert_points_forced_choice` | warning | 19 | ✅ 真实，正当设计的说明 |
| `likert_points_zero_based` | warning | 8 | ⚪ 提示性，提醒保留 schema |
| `reverse_coded_per_construct` | warning | 3 | ✅ 真实 |
| `absolute_wording` | **info** | 5 | ⚪ 特质题惯例，已降档 |

**warning 层已无任何误报。**

## 6. 结论

1. **9 条 error 全部是误报，现已全部消除**，且消除方式都是补充 schema 表达能力
   （`min_value`、`administration_mode`、`languages`），**没有一条是靠降低严重度
   蒙混过去的**。
2. 余下 4 类 warning 误报为词表、作用域与计数口径问题，属下一批。
3. **最有价值的正面结果**：最令人担心精确率的三条语义规则
   （双筒问题、引导性问题、专业术语）在 51 道专业撰写的题目上**误报为 0**。
   这是自建 fixture 无法提供的证据。
4. 触发计数已在 `tests/test_survey_external_validity.py` 中固化，
   调整规则时须同步更新期望值并在提交信息中说明理由。
