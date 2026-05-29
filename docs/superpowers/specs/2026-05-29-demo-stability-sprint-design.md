# SurveyMind Demo Stability Sprint Design

## Goal

Make SurveyMind reliable enough for classmates and real survey users to upload their own questionnaire files, inspect results, and export a report without seeing crashes or confusing demo data.

This sprint prioritizes stability, clear user feedback, and a dependable upload-first workflow over large new features.

## Audience

The primary audience is classmates or real users who have CSV or Excel survey exports and want quick analysis. They may not know the project internals, may upload messy data, and should not need to understand Python, Streamlit, or local AI setup.

## Scope

### In Scope

- Replace the automatic demo-dataset startup behavior with an upload-first main screen.
- Keep the demo dataset available in the repository for tests, documentation, and developer use.
- Validate uploaded CSV, XLSX, and XLS files before analysis.
- Improve graceful handling for empty, corrupt, unsupported, or unusable files.
- Preserve the existing workflow after a valid upload:
  - data preview
  - column metadata
  - automatic question type detection
  - manual question type overrides
  - descriptive summaries
  - charts
  - cross-analysis
  - markdown report export
- Ensure each major analysis section can fail independently with a useful warning while the rest of the page continues.
- Add focused regression tests for preprocessing, question detection, analysis safety, and report generation.
- Add a manual Streamlit regression checklist for realistic demo verification.

### Out Of Scope

- Making local Ollama or AI report generation part of the main stable demo path.
- Adding a database, authentication, session history, or project management features.
- Full browser-based end-to-end automation unless manual regression continues to miss UI failures.
- Large architecture refactors unrelated to upload stability and demo reliability.

## User Flow

1. The user opens the app and sees an upload-first screen. No dataset is analyzed automatically.
2. The user uploads a CSV, XLSX, or XLS survey file.
3. SurveyMind validates the upload:
   - unsupported file types are rejected
   - empty files are rejected
   - corrupt or unreadable files show a readable error
4. SurveyMind preprocesses valid input:
   - trims whitespace from column names
   - converts blank or whitespace-only cells to missing values
   - removes all-empty columns
   - removes obvious metadata columns such as time, ID, or numbering fields
5. If no usable survey columns remain, SurveyMind stops analysis and explains the issue.
6. After a valid dataset is available, SurveyMind shows preview and metadata.
7. SurveyMind detects question types and lets users override incorrect classifications.
8. Descriptive tables, charts, cross-analysis, and report generation use the active question types.
9. If one section cannot analyze a field or chart, it shows a warning and other sections remain usable.
10. The user exports a markdown report based on the available analysis results.

## Architecture

SurveyMind should keep its current Streamlit plus modular Python structure.

### `app.py`

`app.py` remains the workflow controller and UI safety layer. It should own the upload-first page behavior, call the existing modules in order, and protect each user-facing section with clear empty-state and error handling.

The app should not auto-load the demo dataset in the normal user path. If the demo dataset remains accessible, it should be explicit and secondary, such as for development or documentation rather than the first screen.

### Data Loading And Preprocessing

Input loading and cleanup should stay centralized around the existing data loading and preprocessing path. The sprint should tighten that path rather than duplicating cleanup inside analysis modules.

The preprocessing contract should be:

- input: a loaded `pandas.DataFrame`
- output: a cleaned `pandas.DataFrame` with at least one usable survey column
- failure: a readable exception or status that `app.py` can convert into a user-facing message

### Analysis Modules

The existing modules should keep their current responsibilities:

- `src/question_type_detector.py`: classify fields into supported question types
- `src/descriptive_analysis.py`: produce descriptive summaries
- `src/visualization.py`: build Plotly figures
- `src/cross_analysis.py`: compute cross-tab or grouped comparisons
- `src/report_generator.py`: generate markdown reports from available analysis results

Each module may return empty results for unsupported or unsuitable data. The UI should treat empty results as normal partial-success states, not crashes.

## Error Handling And UX

The app should use calm, readable messages instead of tracebacks.

- Unsupported file type: show that CSV or Excel is required and stop before analysis.
- Empty file: explain that a non-empty file is required.
- Corrupt CSV or Excel file: explain that the file is unreadable and ask for a valid file.
- No usable columns after preprocessing: explain that no survey response columns remain.
- Empty summary or chart result: show a warning in that section.
- Bad individual column: skip or warn for that column while preserving other results.
- Cross-analysis mismatch: filter dropdown choices to supported columns when the compatibility rules are known; show a warning when a selected pair still cannot be analyzed.
- Partial report generation: generate from available sections and include a limitations note when any major analysis section is empty or skipped.

The first screen should focus on file upload. Language settings can remain in the sidebar, but the main content should not imply that a sample dataset has already been analyzed.

## Testing Plan

### Automated Tests

Add focused tests for:

- preprocessing blank values, whitespace column names, all-empty columns, and metadata columns
- upload error behavior for unsupported and empty files, plus corrupt CSV or Excel fixtures if they can be represented as small local test files
- question detection on clean, messy, and edge-case datasets already in `data/`
- descriptive analysis functions returning empty or safe results instead of raising for sparse or unusual columns
- report generation working when some analysis sections are empty or partial

These tests should avoid depending on Streamlit browser automation where plain Python tests can cover the behavior.

### Manual Regression Checklist

Create or update a checklist covering:

- app opens to upload-first state
- normal CSV upload
- messy CSV upload
- normal Excel upload
- empty file upload
- corrupt or unsupported file upload
- question type override
- chart switching
- cross-analysis selection
- markdown report export
- Chinese and English language switching where relevant

## Success Criteria

- The app does not analyze the demo dataset automatically on startup.
- Valid CSV and Excel survey files can move through the full analysis workflow.
- Invalid uploads show user-friendly errors without crashing the page.
- Empty or unsupported analysis sections show warnings rather than tracebacks.
- One failed chart, summary, or cross-analysis does not prevent the rest of the app from working.
- The markdown report can export from available analysis results.
- The stability path is covered by focused automated tests and a manual demo checklist.

## Implementation Notes

- Existing uncommitted local AI/Ollama work should not become part of the stable demo path in this sprint.
- If AI report code remains present during implementation, it should be optional and should not block upload, analysis, charting, or markdown export.
- Keep edits closely scoped to stability and demo reliability.
