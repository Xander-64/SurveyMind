# SurveyMind Bug Tracker

## ✅ Debug Round 3 Final Validation

- 日期：2026-05-09
- 结论：最终集成测试通过
- 覆盖任务：
  - Scale question handling
  - Multiple-choice parsing
  - Question type detection
- 验收结果：
  - 真实世界 messy dataset 不崩溃
  - 主要题型均能稳定处理
  - 系统可进入下一阶段

---

## 🧨 高优先级 Bug

### BUG-001 Scale Question 崩溃
- 描述：
  上传真实问卷时报错
- 报错：
  KeyError: "['mean', 'median', 'std'] not in index"
  StreamlitDuplicateElementId: There are multiple plotly_chart elements with the same auto-generated ID.
- 影响：
  页面直接崩溃，真实数据分析流程无法继续
- 涉及文件：
  - src/descriptive_analysis.py
  - app.py
  - src/question_type_detector.py
- 状态：已修复（第二轮本地测试通过）
- 回归记录：
  - 2026-05-08 使用混合量表测试数据完成上传路径验证，页面无 `exception` / `st.error`
  - 自动识别下 `推荐意愿` 作为量表题统计正常：`mean=4.25`、`median=4.50`、`std=0.96`
  - 手动将 `满意度评分` 覆盖为量表题后，`"5分"`、`"4分"`、`"3分"` 被正确识别，空值和 `"满意"` 被安全忽略，统计结果为 `mean=4.00`、`median=4.00`、`std=1.00`
  - 未发现本次 scale question 修复引入新的页面崩溃
- 负责人：王须弥

---

## ⚠️ 中优先级 Bug

### BUG-003 Question Type Detection 不稳定
- 描述：
  真实问卷字段可能包含元数据列、空列、混合类型列和格式不统一的题目列，导致题型误判或后续分析崩溃。
- 影响：
  元数据字段可能进入分析流程；空列可能产生无意义题型；混合数值/文本字段可能被误判后触发统计错误。
- 涉及文件：
  - src/question_type_detector.py
  - src/cross_analysis.py
- 状态：已修复
- 当前检测规则：
  - 列名包含 `时间`、`ID`、`编号`：单列检测返回 `unknown`，批量检测跳过该列
  - 缺失率达到 80% 及以上：单列检测返回 `unknown`，批量检测跳过该列
  - 多选分隔符出现在至少两条有效回答中：识别为 `multiple-choice question`，其中空格分隔仅用于短文本选项串
  - 大部分有效值可转为数值或 `"5分"` 等分值文本，且为小范围整数取值：识别为 `scale question`
  - 小基数短文本：识别为 `single-choice question`
  - 长文本且唯一率较高：识别为 `open-ended text question`
- 边界情况：
  - 混合数值 + 文本：如 `"5分"`、`"4分"`、`"一般"`，可稳定识别并避免崩溃
  - 全文本量表候选：如 `"满意"`、`"一般"`，不会被强行识别为 scale
  - 空列 / mostly NaN：返回 `unknown` 并在批量检测中跳过
  - 元数据列：如 `提交时间`、`用户ID`、`问卷编号`，返回 `unknown` 并在批量检测中跳过
  - 异常对象输入：不会抛出 `KeyError` 或导致检测崩溃
- 测试记录：
  - 2026-05-08 使用用户提供的 8 行题型识别 CSV 完成 Streamlit 上传渲染测试：页面无 `KeyError`、无 `exception` / `st.error`
  - 2026-05-08 验收识别结果通过：`满意度=scale question`、`推荐意愿=scale question`、`喜欢的功能=multiple-choice question`、`性别=single-choice question`、`奇怪列=single-choice question`
  - 2026-05-08 元数据与空列验证通过：`提交时间`、`用户ID`、`空列` 单列检测为 `unknown`，批量检测中跳过，不参与题型覆盖和后续分析
  - 2026-05-08 混合值验证通过：`满意度` 中 `"满意"`、`"一般"` 和空值不会导致崩溃，`"5分"`、`"4分"`、`"3分"` 被用于量表统计
  - 2026-05-08 检测 smoke test 通过：覆盖元数据列、空列、混合量表、多选题、小基数类别和开放文本
  - 2026-05-08 Streamlit 上传渲染测试通过：包含 `unknown` 跳过列的数据集页面无 `exception` / `st.error`
  - 2026-05-08 交叉分析回归测试通过：scale-like object 列会先安全转数值再计算分组统计
- 负责人：王须弥

---

### BUG-002 Multiple-choice Parsing 不稳定
- 描述：
  真实问卷中的多选题可能混用不同分隔符，导致选项拆分和频次统计不一致。
- 影响：
  多选题统计、图表和交叉分析可能把多个选项当作一个整体，或在空字符串场景下产生异常选项。
- 涉及文件：
  - src/question_type_detector.py
  - src/descriptive_analysis.py
  - src/cross_analysis.py
- 状态：已修复
- 当前支持格式：
  - 分号：`图表;报告`
  - 英文逗号：`图表,导出`
  - 中文逗号 / 顿号：`图表，导出`、`图表、分析`
  - 空格：`图表 报告`
  - 单值：`报告`
  - 空值：`NaN`、`None`、空字符串
- 测试记录：
  - 2026-05-08 使用用户提供的 10 行 CSV 完成 Streamlit 上传渲染测试：页面无 `exception` / `st.error`
  - 2026-05-08 题型识别测试通过：`喜欢的功能` 被识别为 `multiple-choice question`
  - 2026-05-08 频次结果检查通过：`图表=7`、`报告=5`、`导出=4`、`空白=1`；真实空单元格未进入频次表
  - 2026-05-08 分隔符测试通过：`;`、`、`、空格在上传数据中正确拆分；`,` 通过 quoted comma / 函数级校验确认可拆分
  - 2026-05-08 多选描述统计 smoke test 通过：不同分隔符会统一拆分并正确计数，空值不会进入频次表
  - 2026-05-08 交叉分析 smoke test 通过：多选字段 explode 后不会产生 `"nan"` 选项列
  - 2026-05-08 边界测试通过：`NaN`、`None`、空字符串、单值和混合类型输入均不崩溃
  - 2026-05-08 自动题型识别回归检查通过：英文句子不会仅因为包含空格就被识别为多选题
- 负责人：王须弥

---

## 💤 低优先级 Bug

（空）
