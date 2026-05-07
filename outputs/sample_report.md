# SurveyMind Analysis Report

## Dataset Overview

- Rows: 360
- Columns: 14
- Duplicate rows: 0
- Average missing value ratio: 1.13%

## Data Quality Summary

- 10 columns have no missing values.
- The highest missingness appears in `monthly_fitness_spending` (5.00%), `food_spending` (3.89%), `preferred_activities` (3.89%).
- Numeric or scale fields with missing values include `food_spending`, `monthly_fitness_spending`.

## Question Type Summary

- numeric question: 6 (examples: `monthly_allowance`, `food_spending`, `entertainment_spending`)
- scale question: 0
- single-choice question: 5 (examples: `gender`, `grade`, `major_type`)
- multiple-choice question: 2 (examples: `fitness_frequency`, `preferred_activities`)
- open-ended text question: 1 (examples: `open_feedback`)

## Key Findings

- `monthly_allowance` has the highest mean among numeric questions at 2193.69.
- `monthly_allowance` shows the widest spread, with a standard deviation of 564.01.
- `monthly_fitness_spending` has the highest missing rate among numeric questions at 5.00%.
- `food_spending` shows possible outliers based on the 1.5×IQR rule, with 5 flagged responses.
- `gender` is led by `Female` at 52.22%.
- `grade` is led by `Junior` at 23.89%.
- `major_type` is led by `STEM` at 36.67%.
- `fitness_goal` is led by `Health maintenance` at 30.00%.
- `bookkeeping_habit` is led by `Sometimes` at 31.67%.
- For multiple-choice question `fitness_frequency`, the most selected options are `week` (37.34%), `1-2 times` (28.26%), `3-4 times` (12.59%).
- For multiple-choice question `preferred_activities`, the most selected options are `Gym` (14.20%), `Swimming` (13.56%), `Yoga` (13.09%).
- `open_feedback` contains 349 valid open-ended responses. A future LLM workflow can summarize themes from this text field.

## Group Comparison Findings

- Within Non-binary, the most common fitness_goal response is Health maintenance at 33.3% of that group.
- The selected cross-tab contains 3 group categories and 5 target categories.

## Recommendations

1. For the multiple-choice question `fitness_frequency`, the most selected options are week (37.34%), 1-2 times (28.26%), 3-4 times (12.59%). These top 2-3 options are usually the best starting point because they capture the clearest respondent priorities or behaviors. Focus follow-up interpretation on those leading options first, and then compare option preferences across groups to see whether different student segments or user types are choosing differently.

2. Open-ended questions such as `open_feedback` should be used as a second layer of interpretation on top of the structured results. A practical workflow is to combine text summarization, keyword extraction, and light manual coding so repeated concerns and recurring themes can be surfaced reliably. These text responses often explain why people selected certain ratings or options, so they are especially helpful when you want to turn survey findings into concrete recommendations.

3. The current group comparison should be treated as a starting point rather than the final conclusion. Try repeating the comparison with other profile, demographic, or behavioral variables so you can distinguish broad averages from subgroup-specific patterns. This kind of follow-up is often the fastest way to turn a descriptive survey result into a more actionable insight.

## Limitations

- This report is rule-based and still depends on automatic or manually corrected question-type detection.
- The findings are descriptive and should not be treated as evidence of causality or statistical significance.
- Multiple-choice parsing assumes the uploaded data uses relatively consistent delimiters.
- 1 open-ended question(s) were detected, but full text-theme summarization is still a placeholder in this MVP.
