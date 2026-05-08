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
