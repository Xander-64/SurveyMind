# 路 2：通用数据分析功能接入前后端分离版 — 交接方案

> 2026-07-15 起草。目标读者：没有看过此前任何开发会话的接手者。
> 状态：方案待产品确认后实施。**在用户确认第 3、4 节的方案前，不要动手写代码。**

## 0. 一句话背景

SurveyMind 有两条并行界面：
- **Streamlit 版**（`app.py`）：已完成"通用数据分析平台"升级（数据模式识别、字段角色、通用概览、智能建议、图表推荐、模式化报告、AI 三人设），功能全但只是内部工具形态；
- **前后端分离版**（`backend/main.py` + `frontend/`）：部署在 Render 上的对外产品，但只有旧的问卷分析五屏，没有任何新功能。

本方案 = 把 Streamlit 版已有的全部新功能接入前后端分离版，做成完整产品。**Python 分析逻辑全部已存在于 `src/`，本工作不写新分析算法，只做 API 封装 + 前端呈现。**

## 1. 当前架构现状

### 1.1 后端（backend/main.py，FastAPI，~450 行）

薄封装模式：每个端点 = 读 session 的 DataFrame → 调一个 `src/` 函数 → 序列化 JSON。**端点里不写分析逻辑**（这是既定原则，请沿用）。

- **Session 机制**：上传后 DataFrame 存 `uploads_tmp/{session_id}/data.parquet`，元信息存 `meta.json`（filename、created_at、question_types、detected_types）。内存缓存 `_session_cache`，1 小时过期自动清理（`SESSION_MAX_AGE_SECONDS`）。
- **现有端点**：`GET /health`、`POST /api/upload`、`POST /api/demo`、`GET /api/{sid}/overview`、`GET /api/{sid}/detect`、`POST|DELETE /api/{sid}/types`（题型手动覆盖/重置）、`GET /api/{sid}/stats`、`POST /api/{sid}/cross`、`GET /api/{sid}/report`、`POST /api/{sid}/ai-report`。
- **CORS**：环境变量 `CORS_ALLOWED_ORIGINS`（逗号分隔），默认放行本地 5500 端口。
- **部署**：`render.yaml`，启动命令 `uvicorn backend.main:app`，健康检查 `/health`。前端托管在静态站点（Render Sites），通过 `frontend/config.js` 的 `apiBaseUrl` 指向 API。

### 1.2 前端（frontend/，无框架、无构建、零第三方 JS 依赖）

- `index.html`（~1100 行）：**由设计稿 `design/SurveyMind 数据分析界面.html`（Claude Design 产物）导出**，含全部 CSS 与屏幕 DOM。字体（Albert Sans、IBM Plex Mono）以本地 woff2 内嵌（`assets/*.woff2`），**整个前端完全自包含，不依赖任何 CDN**——这是有意的部署属性，请勿破坏。
- `assets/nav.js`（手写，~60 行）：屏幕切换。侧边栏 `.step[data-screen=X]` ↔ `section.screen#screen-X`；步骤顺序在 `order = ['upload','overview','types','stats','cross','export']` 数组里；`[data-go]` 按钮跳屏；双语切换 = `body[data-lang]` 属性 + 每处文案写成 `<span class="zh">…</span><span class="en">…</span>` 双 span，CSS 控制显隐。
- `frontend/data.js`（手写，~900 行）：数据层。**用 querySelector 定位设计稿的现有 DOM，把假数据替换为 API 真数据**；动态重建的行/单元格严格复用设计稿已有的 class 和 inline-style 模式。已有的手写图形函数：
  - `renderBars(container, values)`：`<div class="bars"><div class="b" style="height:x%">` 条形图（直方图/频次都用它）；
  - `heatColor(ratio)`：热力色插值，端点 `[236,241,249]`（--accent-soft）→ `[62,92,153]`（--accent），交叉分析热力矩阵就是 div 网格 + 该函数上色；
  - `typeBadge(short)`：题型徽章 HTML（`.tb.num/.scale/.single/.multi/.open/.empty`）。
- **六个屏幕**：`screen-overview / types / stats / cross / export`（五个来自设计稿）+ `screen-upload`（后来手写的拖拽上传屏，inline style 全部引用 tokens）。
- **API 地址解析**（data.js 顶部）：`localStorage.sm_api` > `config.js` > localhost 默认 `http://127.0.0.1:8000`。

### 1.3 Design tokens（index.html `:root`，第 ~221 行起）

所有颜色/圆角/阴影都是 CSS 变量，新界面**只能引用这些变量，不得新造色值**：

- 底色与表面：`--bg #FAFBFC`、`--surface`、`--surface-2`、`--sidebar`
- 文字：`--ink #1A1F29`、`--ink-2 #4A5260`、`--ink-3 #6B7280`、`--muted`
- 主色系：`--accent #3E5C99`、`--accent-600/700`、`--accent-soft #ECF1F9`、`--accent-soft-2`、`--accent-line #C2D1EA`、`--accent-ink`
- 线条：`--line #EAEDF1`、`--line-2`、`--line-strong`
- 圆角：`--r-sm/-md/-lg(16px)`；阴影：`--sh-sm/--sh/--sh-md/--sh-pop`
- 题型徽章五色（num 蓝 / scale 绿 / single 紫 / multi 黄 / open 粉 / empty 灰）已在 CSS 中定义（`.tb.*`）。

### 1.4 五屏各自的接线方式（data.js）

| 屏 | 数据来源 | 动态化程度 |
|---|---|---|
| upload | POST /api/upload、/api/demo | 手写屏，拖拽/点击上传 |
| overview | GET /overview | 指标卡、字段元信息表、预览表全动态 |
| types | GET /detect、POST/DELETE /types | 题型表 + 覆盖下拉（下拉是隐形嵌在设计稿 `.sel` chip 里的 select） |
| stats | GET /stats | 数值摘要、量表分布、频次表、直方图（renderBars）全动态 |
| cross | POST /cross | 分组表/热力矩阵（div 网格+heatColor）动态，两个选择器 |
| export | GET /report(?download) | Markdown 预览 + 下载 |

### 1.5 Python 逻辑层（src/，两套并存）

- 问卷管线（backend 在用）：`preprocessing.py`（**严格清洗：删 ID/时间列**）、`question_type_detector.py`、`descriptive_analysis.py`、`cross_analysis.py`、`report_generator.py`（问卷报告 + `build_dataset_summary`/`build_llm_prompt`）、`llm_client.py`。
- 通用平台（目前只有 Streamlit 在用）：`field_semantics.py`（8 种字段角色）、`dataset_mode.py`（general/survey/mixed 检测 + 题型派生）、`general_overview.py`（质量/相关性/ANOVA 分组差异/异常值/时间趋势/发现）、`analysis_suggestions.py`、`chart_recommender.py`、`ai_report.py`（三人设 + 本地统计摘要 + 防幻觉约束，底层 `llm_client.call_llm` 失败返回 None）。

## 2. 新功能清单及现状矩阵

| # | 功能 | Python 逻辑 | Streamlit 界面 | API 端点 | 前端界面 |
|---|------|:---:|:---:|:---:|:---:|
| 1 | 数据集模式识别 + 手动切换 | ✅ dataset_mode.py | ✅ | ❌ | ❌ |
| 2 | 字段角色识别 + 手动覆盖 | ✅ field_semantics.py | ✅ | ❌ | ❌ |
| 3 | 通用数据概览（质量/数值/分类/日期/相关性/分组差异/异常值/发现） | ✅ general_overview.py | ✅ | ❌ | ❌ |
| 4 | 智能分析建议（3-5 条动态） | ✅ analysis_suggestions.py | ✅ | ❌ | ❌ |
| 5 | 自动图表推荐 | ✅ chart_recommender.py | ✅ | ❌ | ❌ |
| 6 | 模式化报告（通用/问卷/混合三结构） | ✅ report_generator.generate_report | ✅ | ⚠️ 现有 /report 只出问卷版 | ❌ |
| 7 | AI 三人设解读（含降级） | ✅ ai_report.py | ✅ | ⚠️ 现有 /ai-report 固定问卷人设 | ❌ |

测试基准数据：`data/sample_general.csv`（普通订单数据，应判 general）、`data/sample_survey.csv`（问卷，应判 survey）、`data/sample_mixed.csv`（混合，应判 mixed）。

## 3. 实施设计

### 3.1 后端端点设计（新增 4 组、扩展 2 个）

全部沿用现有 session 模式与"薄封装"原则：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/{sid}/mode` | GET | 返回 `{detected: {mode, survey_score, general_score, signals[]}, active: mode}`；active 可被 PUT 覆盖，存 meta.json |
| `/api/{sid}/mode` | PUT | body `{mode}` ∈ general/survey/mixed，手动切换 |
| `/api/{sid}/semantics` | GET | 字段角色表：`{fields:[{column, role, confidence, evidence[], non_null, unique, missing_pct}], role_options[]}` |
| `/api/{sid}/semantics` | PUT / DELETE | 单字段角色覆盖 / 全部重置（镜像现有 /types 的模式） |
| `/api/{sid}/general-overview` | GET | 一次性返回：quality、numeric_summary、categorical_summary、datetime_summary、time_trends、correlations、group_differences、id_candidates、findings（zh+en 双份）、suggestions（zh+en 双份）、chart_specs |
| `/api/{sid}/report` | GET（扩展） | 新增 `mode` 参数；**缺省 survey，与现状完全一致**（五屏 export 不受影响） |
| `/api/{sid}/ai-report` | POST（扩展） | body 可选 `{mode, language}`；缺省走原问卷 prompt（兼容）；给了 mode 则走 `ai_report.generate_ai_report` 三人设 |

`meta.json` 新增键：`dataset_mode`（active）、`mode_detection`（缓存的检测结果）、`field_roles` / `detected_roles`（角色与基线，镜像 question_types/detected_types 的现有模式）。`FieldProfile` 用 `dataclasses.asdict` 序列化。

**关键改造（本设计最大的坑，见 §6.1）**：`/api/upload` 目前用 `src/preprocessing.preprocess_input_dataframe` 清洗，**会删掉 ID/时间列**，而新功能（ID 识别、日期范围、时间趋势）恰恰需要这些列。方案：
- `_save_session` 改存**宽松清洗**的 df（仅 strip 列名、空白串→NA、去全空列——与 `app.py` 本地版一致）；
- meta 记录 `metadata_columns`（由 `src/preprocessing.is_metadata_column` 判定的列名清单）；
- **现有端点**（detect/stats/cross/report 问卷版）读 session 后先 `df.drop(columns=metadata_columns)` 再调分析——对外行为与现在逐字节一致（用现有 test_api 断言不变来证明）；
- **新端点**用全量 df。
- upload/demo 响应体加 `mode` 字段（增量字段不破坏现有前端）。

### 3.2 前端新屏设计

**硬约束回顾：现有五屏（+upload 屏）的 DOM/CSS/SVG 一概不动；新界面另起；只用现有 tokens。**

新增**一个**屏幕 `screen-insight`（"智能分析 / Smart Insights"），插在侧边栏 overview 之后（`nav.js` 的 `order` 数组加一项 `'insight'`，侧边栏加一个新 `.step` 按钮——这是增量，不触碰现有 step）。屏内自上而下五个区块，全部复用设计稿的卡片/表格/徽章 class：

1. **模式卡**：检测结果 + 双分数 + 依据列表 + 三态切换（复用 `.sel` chip 嵌 select 的既有做法）；
2. **字段角色表**：列名 / 角色徽章（新增 8 个角色 badge 类 `.rb.*`，配色从题型五色映射：numeric→num 蓝、categorical→single 紫、multi_value→multi 黄、free_text→open 粉、datetime→scale 绿、identifier/boolean/empty→灰系，全部取自已有 badge 色）/ 证据 / 覆盖下拉；
3. **概览区块**：质量指标卡行（复用 overview 屏的指标卡模式）+ 主要发现列表 + ID/日期字段提示；
4. **推荐图表网格**（批 3 填充，见 §3.3）：相关性矩阵、分组差异、时间趋势、直方图；
5. **报告与 AI**：模式化报告下载按钮（带 `mode` 参数调 /report）+ AI 解读卡（人设标签、生成按钮、`not_configured/api_error` 降级提示）。

问卷/混合模式下，types/stats/cross 五屏照常可用（题型由派生逻辑保证一致）；general 模式下新屏是主战场，五屏仍可点击（显示的是问卷视角结果，不隐藏、不改动）。

### 3.3 图表方案（最关键决策）— 建议：零依赖手写渲染器 `frontend/assets/charts.js`

**结论先行：不引入任何图表库；新建一个 ~400 行的手写渲染器，延续 data.js 已有的 div 图形语言，仅时间趋势折线一处用内联 SVG。**

理由：

1. **前端已经在这么做了**。直方图（`renderBars` 的 div 条形）和交叉热力矩阵（div 网格 + `heatColor` 插值）都是手写的，视觉与设计稿零割裂。新图表沿同一模式是最自然的延伸，不是另起炉灶。
2. **需求是"概览级小数据"**：相关矩阵 ≤10×10、时间趋势 ≤36 个月点、分组对比 ≤10 组、直方图 8 桶。不需要图表库的缩放、动画、大数据渲染能力。
3. **库的代价明确大于收益**：
   - Chart.js（~70KB gz）：canvas 渲染，热力图和箱线都要第三方插件；默认圆角/动画风格与设计稿的克制质感不合，覆盖样式的工作量不小于手写；
   - ECharts（~350KB gz）：全能，但默认视觉风格强烈，与 tokens 对齐成本最高；
   - Plotly.js（~1.2MB gz）：体积直接排除；
   - uPlot（~15KB）：只擅长时序折线，覆盖不了矩阵/分组图。
   且当前前端**完全自包含（连字体都本地 woff2）**，引库要么走 CDN（破坏自包含、增加线上故障面）、要么 vendor 大文件——两头都亏。
4. **tokens 单一来源**：手写 DOM/SVG 的 fill/stroke 直接写 `var(--accent)` / `var(--accent-soft)` 等 CSS 变量，未来改主题图表自动跟随；canvas 库做不到（颜色是绘制时快照）。
5. **可测试**：渲染函数是纯函数（数据 → HTML/SVG 字符串），配合 API 返回的 chart_specs 可做数值一致性断言。

四个图表原语（进 `charts.js`，全部吃 `/general-overview` 返回的 `chart_specs`）：

| 原语 | 实现 | 视觉 |
|---|---|---|
| `renderHistogram` | 复用现有 div.bars 模式 | 与 stats 屏直方图完全同款 |
| `renderCorrMatrix` | div 网格（复用 cross 屏热力矩阵的 class 与 `heatColor`）；负相关用 `--ink-3` 灰系второй色阶；每格标注 r 值 | 与 cross 屏热力同款 |
| `renderGroupedMeans` | 水平条 + 误差线（±std）+ ANOVA p 值徽章；div + 1px 边框线 | 条形复用 `.bars` 色，p 值徽章复用 `.tb` 徽章形态 |
| `renderTrendLine` | **唯一的内联 SVG**：`<polyline>` + 数据点圆点 + 月份轴，stroke=`var(--accent)`，点 fill=`var(--surface)` | 线条风格对齐设计稿的克制感 |

异常值不单独画图：在字段角色表的数值行内放"IQR 范围条 + 异常点计数徽章"（div），更贴合现有表格化设计。

交互范围：原生 `<title>` hover 提示 + 关键数值直接标注在图上（设计稿本身就是标注式风格）；**不做**缩放/框选/图表联动。

### 3.4 依赖与实施顺序

`mode`/`semantics` 端点 →（被依赖）`general-overview` → `suggestions`/`chart_specs`（并入 overview 响应）→ 前端骨架 → charts.js → 报告/AI。批次划分见 §4。

## 4. 分批实施计划（4 批，每批可运行、可看、pytest 全绿）

### 批 1：后端全量端点（不碰前端）
- 内容：§3.1 全部端点 + 宽松清洗改造 + meta 扩展；`tests/test_api_v2.py`（仿现有 test_api.py 风格，覆盖三份样例数据的 mode/semantics/general-overview/报告模式/AI 降级）。
- 验收：pytest 全绿（113 个现有 + 新增）；**现有 test_api.py 一字不改仍全过**（证明五屏契约未破坏）；文档给出 curl 示例。
- 本地验证：`python -m uvicorn backend.main:app --port 8000`，`curl http://127.0.0.1:8000/api/demo -X POST` 后逐个 curl 新端点。

### 批 2：前端新屏骨架（无动态图表）
- 内容：侧边栏新 step + `screen-insight` DOM（模式卡/角色表/质量卡/发现/建议，全部表格与徽章）+ data.js 接线（新增代码集中放文件尾部独立 section，或新建 `assets/insight.js`，不改动现有函数）。
- 验收：三份样例分别显示 general/survey/mixed；**通用数据集在新屏看不到任何"单选题/多选题/量表题"字样**；五屏回归照旧；语言切换双语正常。
- 本地验证：起 uvicorn + 浏览器打开 `frontend/index.html`（或 `python -m http.server 5500 -d frontend`）。

### 批 3：图表渲染器
- 内容：`assets/charts.js` 四原语 + 接入 insight 屏图表网格 + 角色表行内异常值条。
- 验收：图表数值与 API JSON 抽查一致；全部颜色引用 tokens 变量（代码 review 检查无硬编码色值，除 heatColor 既有端点）；控制台无报错。

### 批 4：模式化报告 + AI 三人设 + 收尾
- 内容：insight 屏报告区（mode 参数下载）+ AI 卡（人设标签/生成/降级提示）+ README 双语更新 + 样例数据端到端手册。
- 验收：三种模式的报告结构正确（通用报告含"数据集概览/字段与分布/数据质量/变量关系/主要发现/后续分析建议/分析限制"七节）；AI 未配置时降级提示、其余功能不受影响；pytest 全绿；Streamlit 版照常可用。

## 5. 硬约束（逐条，实施中随时对照）

1. 现有五屏 + upload 屏的 DOM/CSS/SVG **一概不动**；新界面全部增量另起；
2. 新界面只引用 `:root` 现有 design tokens，不新造颜色/字体/阴影/圆角；
3. `app.py`（Streamlit 版）保持可用——它与 backend 共享 `src/`，改 `src/` 时必须跑全量 pytest（含 Streamlit 的 AppTest 端到端测试）；
4. 每批交付：pytest 全绿 + 提供本地启动验证步骤；
5. 不引入第三方前端依赖（见 §3.3）；后端不新增分析逻辑，一律调 `src/`；
6. 线上部署行为（现有端点的响应结构、`src/preprocessing` 严格清洗语义、render.yaml）不做破坏性变更——只加字段、加参数，缺省行为不变。

## 6. 已知的坑与历史决策

1. **backend 上传会删 ID/时间列**（`src/preprocessing.preprocess_input_dataframe`，为问卷去噪设计）。新功能必须拿到这些列 → 批 1 的"宽松存储 + 读取时按需 drop"改造（§3.1）。**这是全项目最容易踩的坑**：不改它，通用概览的 ID 识别、日期范围、时间趋势全部拿不到数据；改坏它，五屏和线上行为回归。
2. **为什么前端是静态导出、无框架**：`frontend/index.html` 由 Claude Design 设计稿直接导出，保真度高；引 React/Vue 意味着整体重写且引入构建链，当时选择了"querySelector 增量接线"（data.js）作为最小成本路线。后果：**DOM 结构是 data.js 的选择器契约**，改 class 名/层级会静默断掉数据填充——所以硬约束规定五屏 DOM 不动。
3. **meta.json 的 `question_types` 是五屏的契约**：detect/stats/cross/report 都从它读题型。新功能的字段角色（`field_roles`）独立存放，**不要**复用或改写 question_types 键。
4. **双语机制**：前端不在语言切换时重新请求，靠 `.zh`/`.en` 双 span + `body[data-lang]` 显隐。因此新端点的自然语言内容（findings/suggestions/AI 文案）要么一次返回 zh+en 双份（推荐，`general-overview` 已按此设计），要么接受切换语言时内容不刷新的妥协。AI 报告例外：按当前语言单次生成即可。
5. **测试环境**：本机 `.venv` 是空壳，跑测试用 `/opt/anaconda3/bin/python -m pytest tests/ -q`（Python 3.12，fastapi/httpx/pandas/scipy 齐全）。`conftest.py`（根目录）负责 `src` 导入路径。
6. **两个已改写的契约测试**：`tests/test_metadata.py`、`tests/test_preprocessing.py` 原本断言"Streamlit 与 API 清洗必须一致"，2026-07 平台升级后已改写为新契约（API 严格清洗不变；Streamlit 保留元数据列做角色分析）。批 1 完成后，backend 也转向宽松存储，届时 `test_api` 中依赖删列行为的断言靠"读取时 drop"保持不变——若有失败，先查 drop 时机而不是改断言。
7. **`src/llm_client.py` 的双接口**：`ask_llm`（抛异常，backend 现有 /ai-report 用）与 `call_llm`（返回 None，`ai_report.py` 三人设用）并存，是有意设计，别合并。
8. **`QUESTION_TYPE_EMPTY`/`unknown`**：远程健壮性修复引入的新题型值，前端 badge 已有 empty 灰色类；字段角色体系里对应 `empty_or_constant`。
9. **Streamlit 版的宽松清洗是本地函数**（`app.py::preprocess_input_dataframe`），与 `src/preprocessing` 的严格版故意不同名不同域——见 `tests/test_preprocessing.py` 的注释。批 1 若把宽松清洗提升为 `src/` 公共函数（建议提到 `src/preprocessing.py` 里命名 `soft_clean_dataframe`），记得让 app.py 和 backend 共用一份并保留两个契约测试。
10. **三、四阶段功能（向数据提问 / 文本主题 / 时间序列 / 建模准备度）尚未开发**，范围待产品圈定（评估结论：建模准备度和向数据提问价值最高）。本方案只覆盖已完成的一、二阶段功能接入，别顺手扩scope。

## 7. 快速上手（接手者 checklist）

```bash
cd ~/Desktop/SurveyMind
git checkout feature/general-data-platform     # 工作分支（勿直接推 main）
/opt/anaconda3/bin/python -m pytest tests/ -q  # 应全绿（113 个）
python -m uvicorn backend.main:app --port 8000 # 后端
python -m http.server 5500 -d frontend         # 前端 → http://127.0.0.1:5500
python -m streamlit run app.py                 # Streamlit 版（对照新功能形态）
```

三份验收数据：`data/sample_general.csv` / `sample_survey.csv` / `sample_mixed.csv`。
相关文档：`docs/superpowers/specs/2026-07-13-general-data-analysis-upgrade.md`（平台升级原始设计）、`CODE_REVIEW_REPORT.md`、`BUG_TRACK.md`、`PROJECT_LOG.md`。

## 8. 批 1 交付记录（2026-07-15）

实施与 §3.1 一致，补充三个实现决策：

1. **删列坑的落点**：`_load_session`（现有端点共用的加载器）返回"问卷视图"（按 meta 的
   `metadata_columns` drop），新端点用 `_load_session_full` 拿全量 df。这样现有端点代码
   与行为都不变，`test_api.py::test_api_cleaning_matches_streamlit_pipeline`（直接断言
   `_load_session` 结果 == 严格清洗输出）原样通过。`question_types` 在 drop 后的视图上检测，
   与旧管线逐字节一致。upload/demo 响应的 `columns` 仍报问卷视图列数（增量字段 `mode` 已加）。
   全元数据列文件仍按旧行为 400（`No usable survey columns remain after preprocessing.`）。
2. **宽松清洗已提升为 `src/preprocessing.soft_clean_dataframe`**，app.py 与 backend 共用；
   严格版 `preprocess_input_dataframe` 重构为"宽松 + 删元数据列"（列级操作互相独立，等价，
   两个契约测试 `test_preprocessing.py`/`test_metadata.py` 未改动全过）。
3. **旧会话向后兼容**：升级前创建的 session（meta 无新键）由 `_ensure_platform_meta` 在
   新端点首次访问时回填，线上滚动升级不需要清空 `uploads_tmp/`。
4. `general-overview` 响应比 §3.1 多一个增量键 `numeric_histograms`（复用 /stats 的 8 桶
   直方图逻辑，按 numeric 角色列计算）——批 3 的 `renderHistogram` 需要分桶数据。

### 8.1 curl 验证示例

```bash
/opt/anaconda3/bin/python -m uvicorn backend.main:app --port 8000
SID=$(curl -s -X POST http://127.0.0.1:8000/api/upload \
  -F "file=@data/sample_general.csv" | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_id"])')

curl -s http://127.0.0.1:8000/api/$SID/mode                     # detected+active，应为 general
curl -s -X PUT http://127.0.0.1:8000/api/$SID/mode -H 'Content-Type: application/json' \
  -d '{"mode":"mixed"}'                                          # 手动切换
curl -s http://127.0.0.1:8000/api/$SID/semantics                # 字段角色表（order_id→identifier）
curl -s -X PUT http://127.0.0.1:8000/api/$SID/semantics -H 'Content-Type: application/json' \
  -d '{"column":"customer_age","role":"categorical_dimension"}' # 单字段覆盖
curl -s -X DELETE http://127.0.0.1:8000/api/$SID/semantics      # 重置全部覆盖
curl -s http://127.0.0.1:8000/api/$SID/general-overview        # 质量/相关性/趋势/发现（zh+en）
curl -s "http://127.0.0.1:8000/api/$SID/report?mode=general&language=zh-CN"   # 通用七节报告
curl -s -X POST http://127.0.0.1:8000/api/$SID/ai-report -H 'Content-Type: application/json' \
  -d '{"mode":"general","language":"zh-CN"}'                    # 未配 key 时 {"ok":false,"reason":"not_configured"}
curl -s http://127.0.0.1:8000/api/$SID/overview                # 回归：五屏视角仍看不到 order_id
```

## 9. 批 2 交付记录（2026-07-16）

新增 `frontend/assets/insight.js`（独立数据层，不改动 data.js 任何函数；会话 id 通过
`localStorage.sm_session` 与 data.js 共享，懒加载：点击侧边栏「智能分析」step 时才拉取
/mode + /semantics + /general-overview）。index.html 全部为增量插入：侧边栏新 step、
`screen-insight` section（插在 `<!-- screens injected below -->` 标记处）、一个只含
`.rb.*` 角色徽章类的新 `<style>` 块（全部引用既有 tokens）、一个 script 标签。
nav.js 仅在 order 数组加 `'insight'` 一项（§3.2 授权的增量）。

经产品确认的三个取舍：
1. **侧边栏序号**：新 step 用符号 ✦ 不编号，现有六屏的写死序号与「步骤 N」抬头零改动；
2. **角色徽章配色**：按 §3.2 映射执行（numeric→num 蓝、categorical→single 紫、
   multi_value→multi 黄、free_text→open 粉、datetime→scale 绿、identifier/boolean/empty→灰）；
   中英文角色文案沿用 `src/i18n.py` 的 FIELD_ROLE_TRANSLATIONS 措辞；
3. **上传落点**：保持统一落 overview，新屏靠侧边栏进入（不改 data.js 上传回调）。

屏内五块（批 2 范围）：模式卡（检测结果 + 双分数 pill + signals + `.sel` chip 嵌 select
三态切换，PUT /mode）、质量指标卡行（行数/字段数/平均缺失/重复行）、字段角色表
（角色徽章 + 依据 + 覆盖下拉 PUT /semantics + 重置 DELETE /semantics；角色覆盖后自动
重拉 general-overview 刷新指标与发现）、主要发现、分析建议（zh+en 双 span，语言切换
不重新请求）。推荐图表网格（批 3）与报告/AI 卡（批 4）按批次划分未在本批加入。


## 10. 批 4 交付记录（2026-08-01）

insight 屏补齐最后两块，路 2 的四批全部完成。纯前端接线，
后端端点早已实现且未改动一行。

**报告区**（`#ins-report-card`）
- 调 `/api/{sid}/report`，**带 `mode` 参数**。此前前端只传 `language`，
  `mode` 从未被使用过——也就是说通用报告与混合报告的两套结构
  在浏览器里一直不可达。实测三种模式的章节结构确实不同：
  general 七节 / survey 另七节 / mixed 合并十节。
- 「生成预览」在卡内渲染，「下载 Markdown」走 `&download=true`。
- 文件名与说明文字随当前模式变化（`sample_general_general_report.md`
  ↔ `sample_general_survey_report.md`）。

**AI 卡**（`#ins-ai-card`）
- 调 `/api/{sid}/ai-report`，**body 传 `{mode, language}`**。
  此前调用不传 body，后端因此永远走旧的问卷 prompt，三人设不可达。
- 人设 pill 随模式切换：通用数据分析师 / 问卷分析师 / 混合数据分析师。

**三态降级**（实测全部覆盖）

| API 响应 | 界面 |
| --- | --- |
| `{ok:true, markdown}` | 渲染 markdown，无提示 |
| `{ok:false, reason:"not_configured"}` | `.ins info`：说明如何配置 `.env`，并指出本页其余分析不受影响 |
| `{ok:false, reason:"api_error"}` | `.ins warn`：调用失败，其余分析不受影响 |

> **一处契约细节**：API 层用 `ok` / `reason: not_configured | api_error`，
> 而 `src/ai_report` 内部常量是 `AI_STATUS_OK / NOT_CONFIGURED / FAILED`。
> 两层词汇不同是有意的（`failed` 是内部状态，`api_error` 是对外原因），
> 前端按**线上契约**匹配，不去猜内部常量名。

**遵守的约束**：只改 `insight.js` 与 `index.html` 的增量插入，
`data.js` 与现有六屏 DOM 一行未动；只用既有 design tokens
（`--accent` / `--accent-soft` / `--accent-line` / `--muted` / `--r-sm`）与
既有 class（`.card` / `.card-h` / `.btn` / `.pill` / `.ins` / `.doc`）。

**验证注记**：本轮前端验证在 `127.0.0.1:5500` 完成。`localhost:5500` 上
浏览器缓存了旧版 `insight.js`，强制刷新无效——两者是不同 origin，
缓存独立。排查时若发现"磁盘上的代码是新的、页面行为是旧的"，先换 origin 再查逻辑。
