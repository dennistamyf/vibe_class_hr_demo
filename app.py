from pathlib import Path

import streamlit as st

from hr_screening import (
    DEFAULT_MODEL,
    InputError,
    OpenRouterError,
    create_bundle,
    discover_folders,
    generate_interview_questions,
    load_settings,
    read_listing_inputs,
    save_settings,
    scan_candidates,
    screen_candidate,
)


st.set_page_config(page_title="Candidate Screening", page_icon="◈", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
    :root { --ink: #18302c; --muted: #65736f; --paper: #f5f7f2; --green: #177a58; --coral: #d46449; }
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: var(--ink); }
    .stApp { background: radial-gradient(ellipse at 90% 0%, #e2efe5 0, transparent 35%), var(--paper); }
    h1, h2, h3 { font-family: 'Manrope', sans-serif; letter-spacing: 0; }
    h1 { font-size: 2.25rem; }
    [data-testid="stMetric"] { background: #fff; border: 1px solid #dce5dc; border-radius: 6px; padding: 14px 16px; }
    div.stButton > button[kind="primary"] { background: var(--green); border-color: var(--green); }
    div[data-testid="stProgressBar"] > div > div { background: var(--green); }
    .eyebrow { color: var(--coral); font-weight: 700; text-transform: uppercase; font-size: .74rem; letter-spacing: .08em; }
    </style>
    """,
    unsafe_allow_html=True,
)

project_root = Path(__file__).resolve().parent
default_data = project_root / "HR_dummy_data"
st.markdown('<div class="eyebrow">Local HR workspace</div>', unsafe_allow_html=True)
st.title("Candidate screening")
st.caption("AI-assisted screening for human review. Review the evidence and scoring before making hiring decisions.")

with st.sidebar:
    st.header("Input folders")
    candidates_root_text = st.text_input("Candidate batches folder", str(default_data / "candidates"))
    listings_root_text = st.text_input("Job listings folder", str(default_data / "listing"))
    output_root_text = st.text_input("Output bundle folder", str(default_data / "output"))
    candidates_root = Path(candidates_root_text).expanduser()
    listings_root = Path(listings_root_text).expanduser()
    output_root = Path(output_root_text).expanduser()
    st.divider()
    st.header("OpenRouter")
    saved_settings = load_settings()
    api_key_entry = st.text_input(
        "Replace API key",
        value="",
        placeholder="Saved key available; leave blank to use it",
        type="password",
        key="openrouter_api_key_replacement_v2",
    )
    api_key = api_key_entry.strip() or saved_settings["openrouter_api_key"]
    model = st.text_input("Model handle", value=saved_settings["model"] or DEFAULT_MODEL)
    if st.button("Save settings", icon="🔒"):
        if not api_key.strip() or not model.strip():
            st.error("Enter both an API key and model handle before saving.")
        else:
            save_settings(api_key.strip(), model.strip())
            st.success("Settings saved locally.")

missing_roots = [str(path) for path in (candidates_root, listings_root) if not path.is_dir()]
if missing_roots:
    st.error("Required input folder not found: " + ", ".join(missing_roots))
    st.info("Create and populate the candidate and listing folders manually, then update their paths in the sidebar.")
    st.stop()

if output_root.exists() and not output_root.is_dir():
    st.error(f"The output bundle folder must be a folder, not a file: {output_root}")
    st.stop()

batches = discover_folders(candidates_root)
listings = discover_folders(listings_root)
if not batches or not listings:
    st.info("No candidate batches or job listings were found. Add folders using the documented input structure, then refresh this page.")
    st.code("candidates/batch_xx/candidate.pdf\nlisting/listing_xx/listing_xx.txt\nlisting/listing_xx/scoring template.txt")
    st.stop()

left, right = st.columns(2)
with left:
    selected_batch = st.selectbox("Candidate batch", batches, format_func=lambda path: path.name)
with right:
    selected_listing = st.selectbox("Job listing", listings, format_func=lambda path: path.name)

validation_messages: list[str] = []
job_text = ""
guidance = ""
candidates: list[tuple[Path, str]] = []
candidate_errors: list[str] = []
pdf_count = 0
try:
    job_text, guidance = read_listing_inputs(selected_listing)
except InputError as exc:
    validation_messages.append(str(exc))
candidates, candidate_errors, pdf_count = scan_candidates(selected_batch)
validation_messages.extend(candidate_errors)

if pdf_count:
    first, second, third = st.columns(3)
    first.metric("CVs available", pdf_count)
    second.metric("CVs readable", len(candidates))
    third.metric("Scoring template", "Ready" if guidance else "Missing")

with st.expander("Review selected inputs", expanded=True):
    st.write(f"**Batch:** `{selected_batch}`")
    st.write(f"**Listing:** `{selected_listing}`")
    st.write(f"**Output bundle folder:** `{output_root}`")
    st.write(f"**Job listing and scoring guidance:** {'Ready' if job_text and guidance else 'Invalid'}")
    if pdf_count:
        st.write("**PDF files:** " + ", ".join(path.name for path in sorted(selected_batch.iterdir()) if path.is_file() and path.suffix.casefold() == ".pdf"))
    if validation_messages:
        for message in validation_messages:
            st.error(message)

candidate_count = len(candidates)
top_count = st.number_input(
    "Top candidates to select",
    min_value=1,
    max_value=max(1, candidate_count),
    value=min(3, max(1, candidate_count)),
    step=1,
    disabled=not candidate_count,
)
ready = bool(job_text and guidance and candidates and not validation_messages and api_key.strip() and model.strip())
if not api_key.strip():
    st.caption("Enter an OpenRouter API key in the sidebar to enable generation.")
if not model.strip():
    st.caption("Enter a model handle in the sidebar to enable generation.")

if st.button("Generate interview bundle", type="primary", icon="✨", disabled=not ready):
    try:
        save_settings(api_key.strip(), model.strip())
    except OSError:
        st.error("Could not save OpenRouter settings securely to the local settings folder.")
        st.stop()
    progress = st.progress(0, text="Preparing screening")
    status = st.empty()
    evaluations = []
    try:
        for index, (source_path, cv_text) in enumerate(candidates, start=1):
            status.write(f"Screening candidate {index} of {candidate_count}: {source_path.name}")
            try:
                evaluation = screen_candidate(api_key.strip(), model.strip(), job_text, guidance, source_path.name, cv_text)
            except OpenRouterError as exc:
                raise OpenRouterError(f"Screening failed for {source_path.name}: {exc}") from None
            evaluations.append((source_path, evaluation))
            progress.progress(int(index / candidate_count * 70), text=f"Screened {index} of {candidate_count} candidates")

        from hr_screening import rank_candidates

        ranked = rank_candidates(evaluations)
        interview_responses = {}
        for index, (source_path, evaluation) in enumerate(ranked[: int(top_count)], start=1):
            status.write(f"Generating interview plan {index} of {int(top_count)}: {source_path.name}")
            try:
                interview_responses[source_path.name] = generate_interview_questions(
                    api_key.strip(), model.strip(), job_text, guidance, evaluation
                )
            except OpenRouterError as exc:
                raise OpenRouterError(f"Interview plan failed for {source_path.name}: {exc}") from None
            progress.progress(70 + int(index / int(top_count) * 25), text=f"Prepared {index} of {int(top_count)} interview plans")

        output_path = create_bundle(candidates, evaluations, int(top_count), interview_responses, output_root)
        progress.progress(100, text="Interview bundle complete")
        status.success(f"Completed bundle: {output_path}")
        st.success("All candidates were screened and the selected interview plans are ready.")
        scoring_file = output_path / "scoring_sheet.md"
        st.download_button("Download scoring sheet", scoring_file.read_bytes(), file_name="scoring_sheet.md", mime="text/markdown")
        for question_file in sorted((output_path / "interview_questions").glob("*.md")):
            st.download_button(f"Download {question_file.name}", question_file.read_bytes(), file_name=question_file.name, mime="text/markdown")
        selected_dir = output_path / "selected_candidates"
        st.caption(f"Selected CVs: {selected_dir}")
        for candidate_file in sorted(selected_dir.glob("*.pdf")):
            st.download_button(f"Download {candidate_file.name}", candidate_file.read_bytes(), file_name=candidate_file.name, mime="application/pdf")
    except (OpenRouterError, InputError) as exc:
        progress.empty()
        status.error(str(exc))
    except (OSError, KeyError) as exc:
        progress.empty()
        status.error(f"Bundle generation stopped during file creation. No completed bundle was published. ({type(exc).__name__})")
    except Exception as exc:
        progress.empty()
        status.error(f"Generation stopped unexpectedly. No completed bundle was published. ({type(exc).__name__})")