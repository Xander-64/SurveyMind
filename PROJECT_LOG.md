# SurveyMind Project Log

## 1. 项目简介
一个基于 Streamlit 的问卷分析工具，用于上传真实问卷数据并自动完成题型识别与分析。

## 2. 当前阶段
第三轮 Debug（真实数据兼容性 + 预处理加固）

## 3. 当前核心目标
- 修复 scale question 崩溃问题
- 让真实问卷上传后不崩溃
- 提升空数据与异常数据容错能力

## 4. 当前状态（实时）
- GitHub：主分支与部署流程已建立
- Streamlit：已部署，第二轮本地测试通过
- 本地运行：上传测试问卷后页面不崩溃
- 稳定性：Debug Round 3 最终集成测试通过，系统可进入下一阶段
- 稳定性：主要 bug 已修复，上传前预处理层已补强

## 5. 当前分工
### Xander（Owner）
- 负责主分支维护与部署
- 协调项目推进与发布节奏

### 王须弥（Debug）
- 负责排查并修复真实数据兼容性问题
- 重点检查 `app.py`、`src/descriptive_analysis.py`、`src/question_type_detector.py`

## 6. 今日进展（按时间倒序）
### 2026-05-09
- Debug Round 3 最终验收完成：scale question handling、multiple-choice parsing、question type detection 三项任务均已完成
- 最终集成测试通过：真实世界 messy dataset 上传与分析流程无崩溃
- 当前结论：主要题型均可稳定处理，系统状态稳定，可进入下一阶段

### 2026-05-08
- Task 3 验收测试：使用用户提供的 8 行 CSV 走 Streamlit 上传后渲染路径，页面无 `KeyError`、无 `exception` / `st.error`
- Task 3 验收识别结果：`满意度=scale question`、`推荐意愿=scale question`、`喜欢的功能=multiple-choice question`、`性别=single-choice question`、`奇怪列=single-choice question`
- Task 3 元数据处理：`提交时间`、`用户ID`、`空列` 单列检测为 `unknown`，批量检测跳过这些列，不参与后续分析
- Task 3 稳定性结论：本轮验收未发现误判阻塞项或新增崩溃，可以进入最终验收
- Task 3 完成：加固题型识别规则，保持简单可解释，不使用 ML 或复杂模型
- Task 3 检测规则：列名包含 `时间`、`ID`、`编号` 或缺失率达到 80% 及以上时，单列检测返回 `unknown`，批量检测会跳过这些列，避免元数据参与分析
- Task 3 检测规则：多选题优先识别，至少两条有效回答包含 `;`、`,`、`，`、`、`、换行或短文本空格型多选分隔符时，识别为 `multiple-choice question`
- Task 3 检测规则：有效值中 60% 及以上可转为数值或 `"5分"` 这类分值文本，且整数型小范围取值不超过 10 个时，识别为 `scale question`
- Task 3 检测规则：小基数短文本识别为 `single-choice question`；较长且高唯一率文本保留为 `open-ended text question`
- Task 3 边界测试：覆盖混合数值/文本、纯文本量表、空列、元数据列、异常对象输入，单列检测均返回有效类型或 `unknown`
- Task 3 渲染测试：使用包含 `提交时间`、`用户ID`、空列、`"5分"` / `"4分"` / `"一般"`、多选题和文本反馈的 CSV 走上传后渲染路径，页面无 `exception` / `st.error`
- Task 3 关联修复：数值/量表交叉分析前会安全转数值，避免 scale-like object 列在分组均值计算时崩溃
- Task 2 回归测试：使用用户提供的 10 行多选题 CSV 走 Streamlit 上传后渲染路径，页面无 `exception` / `st.error`
- Task 2 识别结果：`喜欢的功能` 被识别为 `multiple-choice question`
- Task 2 统计检查：多选频次为 `图表=7`、`报告=5`、`导出=4`、`空白=1`，真实空单元格未进入频次表
- Task 2 分隔符检查：`;`、`、`、空格在上传数据中正确拆分；`,` 通过 quoted comma / 函数级校验确认可拆分
- Task 2 当前结论：多选题解析测试通过，未发现新增崩溃，可进入 Task 3
- 回归测试：启动 Streamlit app，并使用用户提供的混合量表 CSV 走上传后渲染路径，页面无 `exception` / `st.error`
- 统计检查：`推荐意愿` 自动识别为量表题，结果为 `mean=4.25`、`median=4.50`、`std=0.96`
- 覆盖验证：手动将 `满意度评分` 设为量表题后，`"5分"`、`"4分"`、`"3分"` 被纳入统计，空值和 `"满意"` 被忽略，结果为 `mean=4.00`、`median=4.00`、`std=1.00`
- 当前结论：本次修改解决混合类型量表值导致统计崩溃的问题，未发现新增崩溃；未修改 UI，未新增功能
- 加固 `summarize_scale_questions()`：使用 `pd.to_numeric(errors="coerce")` 做数值转换，并兼容 `"5分"`、`"4分"` 等文本分值提取
- 统计前统一 `dropna()`；无有效数值、缺失字段、纯文本量表列会返回 `"Insufficient data"`，不再跳过或崩溃
- 输出继续包含 `mean`、`median`、`std`；当标准差或整列统计不可计算时，对应字段返回 `"Insufficient data"`
- 边界情况已覆盖：中文文本回答（如 `"满意"`、`"一般"`）、空字符串、`None`、混合数字/字符串、单个有效数值、缺失列、全无有效数值
- 测试记录：通过 `compileall`；通过混合量表数据 smoke test；通过全无有效数值量表列的报告生成 smoke test
### 2026-05-08
- 新增输入预处理层：在 `app.py` 的数据加载后、分析前统一清洗 `DataFrame`
- 处理内容：去除列名首尾空格、将空字符串/空白值标记为缺失、删除全空列
- 元数据过滤：自动移除包含 `时间`、`ID`、`编号` 的明显元数据列
- 稳定性：清洗后的 `DataFrame` 统一传入下游分析逻辑，若预处理后无可用列则显示友好错误并停止分析，避免页面崩溃
- 修改文件：`app.py`、`PROJECT_LOG.md`
- 当前结果：分析函数未改动，输入阶段容错和真实问卷兼容性进一步提升

### 2026-05-07
- 测试通过：完成第二轮本地测试，上传测试问卷后页面不崩溃
- 修改文件：`src/descriptive_analysis.py`、`app.py`
- 当前结果：scale question 崩溃与 `plotly_chart` 重复 ID 问题已完成修复，主要 bug 已修复
- 测试失败：完成 `fix-real-data-debug` 分支第一轮本地测试，无新增代码修改
- 失败原因：`render_visualization_explorer()` 中多个 `st.plotly_chart()` 生成重复 auto ID，Streamlit 抛出 `StreamlitDuplicateElementId`
- 当前结果：scale question 代码层修复已进入真实验证，但上传流程仍未稳定，需要为 Plotly 图表补充唯一 `key`
- 预测试完成：修复 scale question 处理逻辑，`summarize_scale_questions()` 改为手动计算 `count`、`mean`、`median`、`std`
- 增加 `"5分"`、`"4分"` 等文本分值提取，空列或无有效数据返回空 `DataFrame`
- `app.py` 增加 scale summary 展示前 empty 判断，并为 CSV `ParserError` 增加容错读取
- 当前结果：代码已修复，已通过 `compileall` 与简单混合数据测试，等待第一轮真实问卷上传验证
- 建立并统一协作文档体系：`PROJECT_LOG.md`、`TASK.md`、`BUG_TRACK.md`
- 修改文件：`PROJECT_LOG.md`、`TASK.md`、`BUG_TRACK.md`
- 当前结果：项目状态、任务和 bug 已可统一追踪

## 7. 已完成里程碑
- [x] GitHub 部署
- [x] Streamlit 部署
- [x] 已定位 scale question 崩溃报错信息
- [x] 第三轮 debug 主要 bug 修复完成
- [x] 真实数据上传流程本地测试不崩溃

## 8. 下一步计划（Top 3）
1. 回归测试真实问卷上传与图表切换流程
2. 部署前复测 Streamlit 线上环境
3. 继续观察题型识别与报告生成的真实数据表现
