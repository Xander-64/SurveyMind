# SurveyMind Task Board

## 🔥 当前优先任务（必须做）
- [ ] 回归测试真实问卷上传与图表切换
- [ ] 部署前复测

## 🧩 进行中任务
- [ ] 检查 `app.py` 与 `src/question_type_detector.py` 的真实数据兼容性

## 💤 待做（Backlog）
- [ ] 优化题型识别
- [ ] 优化报告生成

## ✅ 已完成
- [x] 加固结果展示层 UI fallback
- [x] GitHub 部署
- [x] Streamlit 部署
- [x] 建立协作文档体系（项目日志 / 任务 / Bug 跟踪）
- [x] 修复 scale question 崩溃（代码层面）
- [x] 真实问卷上传不崩（第二轮本地测试通过）
- [x] 空数据容错
- [x] 第一轮真实问卷测试
- [x] 验证 scale summary 展示稳定性
- [x] 修复 `StreamlitDuplicateElementId`：为所有 `st.plotly_chart()` 添加唯一 `key`
- [x] 排查 `render_visualization_explorer()` 中 Plotly 图表重复 ID 问题

## UI Fallback Notes
- 结果展示前统一检查数据是否存在；空结果改为 `st.warning()`，不再直接渲染。
- 图表展示统一包裹 `try/except`；图表构建或渲染失败时显示 warning，页面继续保留其他模块。
- 主展示流程按模块降级；单个区块失败不会导致整页空白或整页崩溃。
- 分析逻辑未修改，仅保护 Streamlit 展示层。
