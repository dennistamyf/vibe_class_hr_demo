# Build Guide: Local HR Candidate Screening and Interview Bundle Generator

This is the requirements specification for a self-contained local HR screening application. It is written for a coding agent implementing the product end to end. The agent should implement the product from this document, run verification checks, and report evidence. The application must never place API keys or other secrets in source files, Git, generated reports, or logs.

## 1. Product Goal

The HR department receives multiple CVs for a particular job posting and needs a consistent way to screen candidates against a predetermined scoring template. The application uses an LLM to support the screening process and generate an interview bundle for the strongest candidates.

The first usable version is a single-user local Python application with a simple, modern, friendly browser interface. It uses folders and files as its data storage; it does not require a database, login system, remote backend, or multi-user permissions.

HR manually creates and populates the input folders. The application scans those folders and does not create candidate batches or job listings from the interface.

Input structure:

```text
/candidates/
└── batch_xx/
    ├── candidate_a.pdf
    └── candidate_b.pdf

/listing/
└── listing_xx/
    ├── listing_xx.txt
    └── scoring template.txt
```

- `listing_xx.txt` contains the job posting.
- `scoring template.txt` contains free-form HR instructions defining how candidates should be evaluated. The application must pass these instructions to the LLM without requiring a fixed template schema.
- Every PDF in the selected candidate batch is screened.

The main workflow is:

1. HR selects an existing candidate batch and job listing.
2. The application validates the selected listing, scoring template, and readable PDF count.
3. HR enters the configurable number of top candidates to select.
4. HR enters or reviews the saved OpenRouter API key and model handle.
5. HR reviews the inputs and starts generation.
6. The application screens every candidate, ranks all candidates, selects the configured number of highest-scoring candidates, and generates the interview bundle.
7. The application displays a progress bar and current processing status, such as `Screening candidate 3 of 12`.

The default LLM provider is OpenRouter and the default model is:

```text
nvidia/nemotron-3-ultra-550b-a55b:free
```

The interface must allow HR to change the API key and model handle. The local application remembers these settings for future runs. The API key must not be committed, written into generated reports, or printed in logs.

Each successful generation creates a timestamped output folder:

```text
/output/timestamp_YYYYMMDDHHMM/
├── selected_candidates/
│   ├── candidate_a.pdf
│   └── candidate_b.pdf
├── scoring_sheet.md
└── interview_questions/
    ├── candidate_a.md
    └── candidate_b.md
```

The selected candidates' original CV PDFs are copied into `selected_candidates/`. The scoring sheet is a Markdown file containing every screened candidate. Interview question files are Markdown files generated only for the selected candidates. The LLM decides the appropriate number of interview questions for each selected candidate based on the candidate's evaluation.

The application must stop the entire generation if a CV cannot be read, an LLM response is invalid, or an OpenRouter request fails. It must show a clear error and must not present a partial output folder as a completed interview bundle.

Scope for the first usable version:

- Local Python application run from a project virtual environment.
- Browser-based interface on the local machine.
- Manual folder management for candidate batches and job listings.
- PDF text extraction, LLM screening, ranking, selection, and Markdown output.
- Saved local OpenRouter settings.
- Input review and validation before generation.
- Live progress bar and generation status.

Explicitly out of scope for the first version:

- User login, accounts, roles, or permissions.
- A database or cloud file storage.
- Automatic email, calendar, or applicant-tracking-system integration.
- Creating or editing candidate/listing folders in the application.
- Screening formats other than PDF CVs.
- Multiple HR users using the same application concurrently.

Stack preference: Python 3.11 or newer, a local virtual environment, Streamlit for the interface, `pypdf` for PDF text extraction, an OpenRouter-compatible HTTP or OpenAI-compatible client for LLM requests, Pydantic for validating LLM results, and Python standard-library file APIs for folder storage and output copying.

## 2. Roles and Access

| Role | Count | Access |
|---|---|---|
| Local HR user | One local user | Select input folders, review validation results, configure OpenRouter settings, start generation, view progress, and open generated Markdown reports and selected CVs |
| LLM service | External service used by the local app | Receives the job listing, scoring instructions, and extracted CV content through OpenRouter requests; does not receive direct access to the local filesystem |

Authentication and authorization rules:

- The application has no login, account system, or user-management workflow.
- The local HR user is assumed to have access to the application process and the manually managed input folders.
- The application may read PDFs from the selected `/candidates/batch_xx/` folder and text files from the selected `/listing/listing_xx/` folder.
- The application must not read unrelated folders or send files other than the selected listing, scoring template, and extracted CV content to the LLM service.
- The OpenRouter API key is entered by the local HR user and remembered locally for future runs. It must be handled as a secret and never displayed in full after entry, included in Markdown output, committed, or logged.
- The model handle is editable and remembered locally along with the API key.
- Generated output is stored locally under `/output/` and is available to the local user who can access the application folder.
- The LLM is an evaluation assistant, not an access-control authority. The application controls which local files are selected and which outputs are written.

## 3. Functional Requirements

### 3.1 Input discovery and selection

- Discover candidate batch folders under `/candidates/` and listing folders under `/listing/`.
- Allow HR to select one candidate batch and one listing from the discovered folders.
- A candidate batch consists of PDF files. The application must identify the PDFs available for screening and show their count and filenames.
- A listing folder must contain one job listing text file and one scoring template text file. The expected files are `listing_xx.txt` and `scoring template.txt`; the application must clearly report missing or ambiguous inputs.
- The application must not create, rename, or modify manually managed input folders or their source files.

### 3.2 Input validation and review

- Before generation, read and validate the selected job listing and free-form scoring template.
- Extract text from every PDF in the selected candidate batch.
- Show HR a pre-generation review containing the selected batch, selected listing, scoring template presence, PDF count, and readable PDF count.
- Reject the pre-generation step if required text files are missing, no PDFs are available, or a PDF cannot be read.
- Allow HR to enter a positive configurable number of top candidates. The application must validate that the number is at least one and does not exceed the number of screened candidates.
- Allow HR to enter the OpenRouter API key and model handle, defaulting the model to `nvidia/nemotron-3-ultra-550b-a55b:free`.
- Keep the Generate action unavailable until required inputs are valid.

### 3.3 Candidate screening

- Screen every readable candidate CV in the selected batch; selection must not happen before all candidates have been evaluated.
- Send the job listing, the complete free-form scoring guidance, and the extracted CV text to the configured OpenRouter model.
- Require each candidate evaluation to include:
  - Candidate identity based on the source filename or extracted CV information.
  - Criterion-by-criterion scores according to the HR scoring guidance.
  - Evidence quoted from the CV for the scores.
  - Strengths.
  - Concerns.
  - Missing information.
  - Overall score.
  - A recommendation.
- Preserve quoted evidence as evidence from the CV and do not allow the LLM to imply that unmentioned experience or qualifications are confirmed.
- Rank all successfully screened candidates by overall score and apply the configured top-candidate count.
- Resolve equal scores deterministically and record the ranking in the scoring sheet. The exact tie-break rule is `To be decided` unless specified during implementation.

### 3.4 Interview bundle generation

- On successful completion, create a new timestamped folder under `/output/timestamp_YYYYMMDDHHMM/`.
- Copy the original PDF files for the selected top candidates into `selected_candidates/`.
- Create `scoring_sheet.md` containing all screened candidates, their ranking, criterion-by-criterion scores, CV evidence, strengths, concerns, missing information, overall scores, and recommendations.
- Create one Markdown interview question file per selected candidate under `interview_questions/`.
- Generate interview questions from the selected candidate's screening result, the job listing, and the scoring guidance.
- Let the LLM decide the number of questions for each candidate. Questions should address relevant strengths, concerns, and missing information rather than use a fixed question count.
- Include enough context in each interview question file for HR to understand why the questions were generated.
- Do not create a completed bundle until screening, ranking, CV copying, and interview question generation all succeed.

### 3.5 Progress and completion state

- Show a progress bar during generation.
- Show the current phase and candidate progress, such as `Screening candidate 3 of 12`.
- Disable the Generate action while a generation is running.
- On success, show the output folder path and links or controls for opening the scoring sheet, interview question files, and selected candidate folder.
- On failure, show a clear error identifying the failed phase or candidate without exposing the API key or other secrets.
- A failed generation must stop the entire process and must not be described as complete. Partial temporary work must be cleaned up or clearly separated from completed `/output/timestamp_*/` bundles.

### 3.6 Error handling and edge cases

- Missing candidate root or listing root → show a setup error with the expected folder paths.
- No candidate batches or listings found → show an empty state with the required folder structure.
- Missing or ambiguous listing text file → stop before generation and identify the problem.
- Missing scoring template → stop before generation and identify the problem.
- Empty job listing or scoring template → stop before generation and identify the problem.
- No PDF files in the selected batch → stop before generation and identify the problem.
- Unreadable or textless PDF → stop the entire generation and identify the source filename.
- Invalid top-candidate count → prevent generation and explain the valid range.
- Invalid or empty API key/model handle → prevent generation or report the OpenRouter configuration error before screening.
- OpenRouter request failure, timeout, rate limit, or authentication failure → stop the entire generation and show a safe actionable error.
- Invalid LLM response or missing required evaluation fields → stop the entire generation and identify the affected candidate or phase.
- Duplicate candidate filenames in the output → preserve unique names or stop with a clear error; the chosen behavior is `To be decided` unless specified during implementation.
- Empty output states, loading states, and errors must be visible and understandable rather than blank screens.

### 3.7 Configuration and local execution

- Provide setup instructions for creating and activating a Python virtual environment.
- Provide dependency installation instructions and a local command to launch the Streamlit app.
- Store remembered OpenRouter settings in a local configuration mechanism that is excluded from version control. The exact mechanism is `To be decided` during implementation.
- Provide a safe example configuration without a real API key.
- The application must run entirely on the local machine except for outbound OpenRouter API requests made during screening and interview-question generation.

## 4. Data Model

To be designed in a later pass. The first version uses folders and files rather than a database.

## 5. API Specification

To be designed in a later pass. The first version is a local Streamlit application and has no required application API.

## 6. Architecture

To be designed in a later pass. The current stack preference is a local Streamlit application with Python file-based storage and OpenRouter integration.

## 7. Environment and Secrets

To be designed in a later pass. The application must use a Python virtual environment and keep the remembered OpenRouter API key out of source control, generated Markdown, and logs.

## 8. Build Phases

To be designed in a later pass.

## 9. Guardrails

To be designed in a later pass.

## 10. Error Handling and Edge Cases

The functional error and edge-case requirements are defined in Section 3.6. A complete implementation guardrail pass is deferred.

## 11. Definition of Done

To be designed in a later pass.
