# Local HR Candidate Screening

A single-user Streamlit application for screening PDF CVs against a job listing and HR scoring guidance. Input folders remain manually managed. Screening and interview-plan requests send the selected listing, scoring template, and extracted CV text to OpenRouter.

## Requirements

- Python 3.11 or newer
- An OpenRouter API key and a model available to that account

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

The included `HR_dummy_data/` folder is selected by default. The output bundle folder also defaults to `HR_dummy_data/output`. To use other inputs or save bundles elsewhere, change the folder paths in the app sidebar. Candidate folders contain PDF files. Each listing folder must contain `<listing-folder-name>.txt` and `scoring template.txt`.

## Settings and outputs

The API key and model are saved outside this project at `~/.hr_candidate_screening/settings.json`. The settings directory and file are restricted to the current user (`0700` and `0600`). The API key is shown only in a password field and is not included in output Markdown. A safe example of the settings format is:

```json
{
  "openrouter_api_key": "",
  "model": "nvidia/nemotron-3-ultra-550b-a55b:free"
}
```

Completed bundles are written under the selected output folder as `timestamp_YYYYMMDDHHMM/`. Work is staged in a hidden temporary directory and promoted only after screening, ranking, PDF copying, and all interview plans succeed. Failed runs remove the temporary bundle.

## Offline tests

```bash
python -m unittest
```