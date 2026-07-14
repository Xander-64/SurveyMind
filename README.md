# SurveyMind

[简体中文说明](README.zh-CN.md)

SurveyMind is a bilingual Streamlit-based AI-assisted data analysis platform. It analyzes both questionnaire exports and general tabular datasets (modeling data, business tables, logs): upload a CSV or Excel file and it detects the dataset mode, profiles every field, generates a data overview with quality checks and variable relationships, recommends charts and analyses, and exports a structured markdown report in either English or Chinese.

## Dataset Modes and Field Roles

Uploaded files are automatically classified into one of three modes (with a manual override):

- **General dataset** — fields are profiled with generic roles: numeric metric, categorical dimension, date/time, identifier/ID, boolean, free text, multi-value field, empty/unusable. Survey terms such as "single-choice question" never appear in this mode.
- **Survey dataset** — the classic questionnaire pipeline: question type detection (numeric/scale/single/multiple/open), descriptive statistics, cross analysis, and the survey report.
- **Mixed dataset** — general profiling plus the survey-specific layers for scale/choice/open-text columns.

Every mode gets the generic data overview: shape and dtypes, missing/duplicate checks, likely ID fields, numeric distributions, categorical top values, date ranges and monthly trends, IQR outlier flags, Pearson correlations, ANOVA-backed group differences, plus 3-5 dynamically generated analysis suggestions and auto-recommended charts.

An optional AI interpretation layer (configured via `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` in `.env`) switches between a general data analyst, survey analyst, or mixed-data analyst persona depending on the mode. The LLM only explains statistics that were already computed locally with pandas/NumPy/SciPy; when the AI service is unavailable, all rule-based analysis remains fully functional.

This project is designed as a clean portfolio piece for data analytics internships, graduate school applications, and GitHub presentation. The implementation focuses on readable Python modules, practical survey-analysis logic, and a user-friendly interface.

## Project Background

Survey data is common in academic research, student organizations, market research, and product feedback, but exploratory analysis can be repetitive and time-consuming. SurveyMind turns a raw CSV or Excel file into an interactive analysis workflow that quickly surfaces:

- dataset quality and structure
- respondent profile patterns
- descriptive statistics for numeric and categorical questions
- subgroup comparisons across selected variables
- a reusable markdown report summary

## Features

- Upload CSV or Excel questionnaire data
- Fall back to a bundled demo survey dataset when no file is uploaded
- Switch the full interface between English and Chinese from the Streamlit sidebar
- Automatically detect numeric, scale, single-choice, multiple-choice, and open-ended questions
- Allow manual question type overrides when automatic detection is not ideal
- Generate descriptive statistics for numeric and categorical variables
- Visualize survey data with Plotly bar charts, histograms, box plots, and cross-tab charts
- Compare one grouping variable against one target variable
- Generate a rule-based markdown report with findings, recommendations, and limitations in English or Chinese
- Download the generated report directly from the app

## Supported Question Types

SurveyMind currently supports five questionnaire-style field types:

- `numeric question`: continuous or discrete numeric responses such as age, income, spending, or scale scores stored as numbers
- `scale question`: Likert-style numeric items such as 1-5, 1-7, or 1-10 ratings
- `single-choice question`: one response selected from a small set of categories
- `multiple-choice question`: multi-select responses stored in one cell using delimiters
- `open-ended text question`: free-text responses with longer text and relatively high uniqueness

These question types drive the rest of the app, including descriptive summaries, chart options, cross-analysis behavior, and report generation.

## Bilingual Support

SurveyMind now supports both English and Chinese users.

- The language selector lives in the Streamlit sidebar.
- The selected language affects the page title, section headers, button labels, help text, chart titles, warnings, report section titles, recommendation text, and report download file name.
- This makes the app easier to use for Chinese students, campus organizations, survey coursework, and English-facing portfolio presentation at the same time.

## How Question Type Detection Works

Question type detection is rule-based and is implemented in [src/question_type_detector.py](/Users/yoghur/Desktop/SurveyMind/src/question_type_detector.py).

### Detection Rules

- Numeric columns are classified as `numeric question`.
- Numeric columns are classified as `scale question` when they look like Likert-style items:
  - 3 to 10 unique non-null values
  - values are mostly integers
  - value range is consistent with 1-5, 1-7, or 1-10 scales
- Remaining numeric columns are classified as `numeric question`.
- Multiple-choice detection runs before single-choice detection.
- A text column is classified as `multiple-choice question` when a meaningful share of non-null responses contains common multi-select delimiters.
- Supported multiple-choice delimiters are:
  - comma `,`
  - semicolon `;`
  - Chinese semicolon `；`
  - Chinese comma `，`
  - Chinese enumeration comma `、`
  - slash `/`
  - vertical bar `|`
  - newline `\n`
- By default, if at least 15% of non-null responses contain one of these delimiters, the column is treated as multiple-choice.
- Low-cardinality text columns are classified as `single-choice question`.
- Longer text columns with many unique values are classified as `open-ended text question`.

### Example Multiple-Choice Formats

The detector is designed to catch common stored formats such as:

- `A;B;C`
- `跑步、游泳、羽毛球`
- `跑步, 游泳`
- `跑步|游泳`
- multi-line responses separated by line breaks

## Manual Question Type Override

Automatic detection is helpful, but real questionnaire exports can still be messy. To keep the app practical, SurveyMind lets users manually override detected question types in the Streamlit interface.

### How to Override

1. Open the `Automatic Question Type Detection` section in the app.
2. Expand `Manual Question Type Override`.
3. Use the dropdown for any column that was classified incorrectly.
4. The selected `active_type` is then used by downstream summaries, charts, cross-analysis, and report generation.
5. Use `Reset Overrides to Detected Types` to revert to the automatic classification.

This makes it possible to correct edge cases without editing code.

## Visualization Behavior

- For single categorical variables, bar charts default to percentage instead of raw count.
- A `Display mode` toggle lets users switch between `Percentage` and `Count`.
- Counts remain available through hover data even when percentage is the active y-axis.
- Cross-tab charts support `Raw Count`, `Row Percentage`, and `Column Percentage`.
- Group comparison charts default to `Row Percentage` to make category mixes easier to compare across groups.

## Tech Stack

- Python
- pandas
- numpy
- Streamlit
- Plotly
- openpyxl
- scipy

## Project Structure

```text
surveymind/
├── app.py
├── requirements.txt
├── README.md
├── data/
│   └── sample_survey.csv
├── src/
│   ├── data_loader.py
│   ├── question_type_detector.py
│   ├── descriptive_analysis.py
│   ├── visualization.py
│   ├── cross_analysis.py
│   └── report_generator.py
├── outputs/
│   └── sample_report.md
└── assets/
```

## How to Run Locally

1. Clone the repository.
2. Move into the project folder.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the Streamlit app:

```bash
streamlit run app.py
```

5. Open the local URL shown in the terminal, usually `http://localhost:8501`.

The project should continue to run with:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Example Use Case

Imagine a student researcher collecting questionnaire data about student consumption and fitness behavior. With SurveyMind, they can upload the survey export and immediately:

- inspect missing values and column types
- identify whether questions are numeric, single-choice, multi-select, or open-ended
- compare fitness spending across genders or grades
- review charts for spending and exercise behavior
- export a concise markdown report for coursework, presentations, or stakeholder sharing

## How This Project Demonstrates Data Analytics Skills

This project showcases several practical analytics skills:

- data ingestion from multiple file formats
- data cleaning and exploratory data analysis
- rule-based feature engineering for survey question classification
- descriptive statistics and cross-tabulation analysis
- interactive visualization design
- modular Python project organization
- product thinking through an end-to-end analytics workflow

## Current Limitations

- Question type detection is rule-based rather than model-based, so unusual exports may still need manual overrides.
- Multiple-choice parsing assumes consistent delimiters within a column.
- Cross-analysis is descriptive only and does not yet include statistical significance testing.
- Open-ended text analysis currently reports valid response counts and a placeholder note instead of real theme extraction.
- The report generator is dataset-agnostic, but the quality of findings still depends on the uploaded data being reasonably clean and survey-like.
- Bilingual output is rule-based, so nuanced wording may still improve in later iterations.

## Future LLM Integration Plan

The current MVP intentionally does not call any external AI API. However, the codebase includes a clean placeholder for future LLM-based reporting in [src/report_generator.py](/Users/yoghur/Desktop/SurveyMind/src/report_generator.py).

Planned LLM integration directions include:

- summarizing open-ended text responses into themes, concerns, and representative quotes
- improving narrative report writing beyond rule-based templates
- suggesting follow-up analyses based on detected patterns
- generating more context-aware recommendations for different survey domains
- adding optional human-in-the-loop review before final report export

## Future Improvements

- support statistical significance tests for group comparisons
- add richer multi-select parsing and smarter handling of messy exports
- add LLM-powered narrative analysis and deeper insight generation
- add theme extraction and sentiment analysis for text feedback
- export reports to PDF or PowerPoint
- add session history and reusable project templates

## Demo Dataset

The bundled demo dataset contains 360 synthetic responses on student consumption and fitness behavior. It is intended for testing the app without needing to upload a file.

## Notes

- The current report generator is rule-based and does not call any external AI API.
- A placeholder function is included for future LLM integration.
- The app is structured so new analytical modules can be added without overloading `app.py`.
