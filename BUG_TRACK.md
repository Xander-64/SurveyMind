# SurveyMind Bug Tracker

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
- 负责人：王须弥

---

## ⚠️ 中优先级 Bug

（空）

---

## 💤 低优先级 Bug

（空）

---

## Upload Regression Test Cases

### BUG-002 File Upload Robustness
- 测试范围：仅验证上传输入阶段保护，不改变后续分析逻辑
- 用例 1：空文件上传
  预期结果：显示 `st.error("The uploaded file is empty. Please upload a non-empty CSV or Excel file.")`，页面不崩溃
- 用例 2：不支持的文件类型上传（如 `.txt` / `.json`）
  预期结果：显示 `st.error("Unsupported file type. Please upload a CSV or Excel file.")`，页面不崩溃
- 用例 3：损坏的 CSV 文件上传
  预期结果：显示可读错误信息，页面不崩溃
- 用例 4：损坏的 Excel 文件上传（如伪装成 `.xlsx` 的无效内容）
  预期结果：显示 `st.error("The uploaded file appears to be corrupted or unreadable. Please upload a valid CSV or Excel file.")`，页面不崩溃
- 用例 5：正常 CSV / Excel 上传
  预期结果：数据正常进入既有分析流程，后续逻辑无变更

