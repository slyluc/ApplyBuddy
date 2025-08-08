# app.py
import os
from io import BytesIO

import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from openai import OpenAI
import streamlit as st
from docx import Document

# Use fpdf2 (supports embedding Unicode fonts)
from fpdf import FPDF

# ================================
# STREAMLIT CONFIG
# ================================
st.set_page_config(page_title="ApplyBuddy – Job Application Helper", page_icon="💼")

st.title("💼 ApplyBuddy – Job Application Helper")
st.write("Upload your CV, paste a job link, pick a tone, and get a custom cover letter + CV tips.")

# ================================
# API KEY HANDLING
# ================================
if "api_key" not in st.session_state:
    st.session_state.api_key = None
if "show_api_input" not in st.session_state:
    st.session_state.show_api_input = True

def save_api_key():
    if st.session_state.temp_api_key:
        st.session_state.api_key = st.session_state.temp_api_key.strip()
        st.session_state.show_api_input = False
        del st.session_state["temp_api_key"]

def change_api_key():
    st.session_state.show_api_input = True

with st.expander("🔐 OpenAI API Key", expanded=st.session_state.show_api_input):
    if st.session_state.show_api_input:
        st.text_input("Enter your OpenAI API key:", type="password", key="temp_api_key")
        st.button("Save API Key", on_click=save_api_key)
    else:
        st.success("✅ API key saved and active.")
        st.button("Change API Key", on_click=change_api_key)

# Stop if no API key is set
if not st.session_state.api_key:
    st.stop()

# Initialize OpenAI client
client = OpenAI(api_key=st.session_state.api_key)

# ================================
# HELPERS
# ================================
def scrape_job_description(url: str, timeout: int = 20) -> str:
    """Scrape visible text from a job posting page."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (JobGenie/1.0)"}
        )
        resp.raise_for_status()
    except Exception as e:
        return f"[Scrape error] {e}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove scripts/styles
    for script in soup(["script", "style", "noscript"]):
        script.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

def read_cv(file) -> str:
    """Read uploaded CV (PDF or TXT)."""
    name = (file.name or "").lower()
    try:
        if name.endswith(".pdf"):
            # Read PDF via PyMuPDF
            data = file.read()
            doc = fitz.open(stream=data, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            return text.strip()
        else:
            # Treat as text
            return file.read().decode("utf-8", errors="ignore").strip()
    except Exception as e:
        return f"[CV read error] {e}"

def generate_cover_letter_and_cv_tips(job_description: str, cv_text: str, tone: str, model: str) -> str:
    """Use OpenAI to generate cover letter and CV tips."""
    prompt = f"""
You are an expert career coach and technical recruiter.

TASKS:
1) Based on the job description below, write a highly tailored cover letter for the applicant using their CV.
   - The tone of the letter should be: {tone}
   - Keep it to one page equivalent (max ~350 words).
   - Use clear, concise language and specific evidence from the CV that matches job needs.
2) Suggest concrete, bullet-point improvements to the CV so it matches the job better.
   - Focus on measurable impact, keywords, and ordering.

JOB DESCRIPTION:
{job_description}

APPLICANT CV:
{cv_text}

Output format:
---
COVER LETTER:
[Your cover letter]
---
CV IMPROVEMENT SUGGESTIONS:
[Bulleted list]
---
""".strip()

    completion = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a professional career coach."},
            {"role": "user", "content": prompt},
        ],
    )

    return completion.choices[0].message.content

def save_as_docx(text: str) -> BytesIO:
    doc = Document()
    for para in text.split("\n\n"):
        doc.add_paragraph(para)
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf

# --- Unicode-safe PDF export using fpdf2 + embedded TTF ---
FONT_PATH = "assets/fonts/DejaVuSans.ttf"  # add this TTF to your repo

def save_as_pdf(text: str) -> BytesIO:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Try to embed Unicode font; fallback to ASCII sanitize if not found
    def sanitize_ascii(s: str) -> str:
        # Replace common smart punctuation to keep things readable if we must fallback
        SMART_MAP = str.maketrans({
            "’": "'",
            "‘": "'",
            "“": '"',
            "”": '"',
            "–": "-",
            "—": "-",
            "•": "*",
            "…": "...",
        })
        return s.translate(SMART_MAP).encode("ascii", "ignore").decode("ascii")

    try:
        if not os.path.exists(FONT_PATH):
            raise FileNotFoundError(FONT_PATH)
        pdf.add_font("DejaVu", "", FONT_PATH, uni=True)
        pdf.set_font("DejaVu", size=12)
        safe_text = text  # full Unicode
    except Exception:
        pdf.set_font("Arial", size=12)  # core font (latin-1 only)
        safe_text = sanitize_ascii(text)

    for line in safe_text.split("\n"):
        pdf.multi_cell(0, 8, line)

    buf = BytesIO()
    pdf.output(buf)  # fpdf2 supports writing to a stream
    buf.seek(0)
    return buf

# ================================
# UI INPUTS
# ================================
job_url = st.text_input("Job posting URL")
cv_file = st.file_uploader("Upload your CV (PDF or TXT)", type=["pdf", "txt"])
tone_choice = st.selectbox(
    "Choose tone for your cover letter:",
    ["Professional", "Friendly", "Confident", "Humble", "Creative"]
)


# Model dropdown with pricing info
model_choices = {
    "GPT-5 (input $1.25 / output $10)": "gpt-5",
    "GPT-5 mini (input $0.25 / output $2)": "gpt-5-mini",
    "GPT-5 nano (input $0.05 / output $0.40)": "gpt-5-nano",
    "GPT-4o mini (input $0.15 / output $0.60)": "gpt-4o-mini",
    "GPT-4.5 (input $75 / output $150)": "gpt-4.5",
    "o1-pro (input $150 / output $600)": "o1-pro",
}

model_label = st.selectbox(
    "Choose a model (with pricing):",
    list(model_choices.keys()),
    index=0
)
model_name = model_choices[model_label]



# ================================
# RUN
# ================================
if st.button("Generate Cover Letter & CV Tips"):
    if not job_url or not cv_file:
        st.warning("Please provide both a job posting URL and a CV file.")
        st.stop()

    with st.spinner("Scraping job posting and generating content..."):
        job_desc = scrape_job_description(job_url)
        if job_desc.startswith("[Scrape error]"):
            st.error(job_desc)
            st.stop()

        cv_content = read_cv(cv_file)
        if cv_content.startswith("[CV read error]"):
            st.error(cv_content)
            st.stop()

        model = model_name.strip() or model_default

        try:
            output = generate_cover_letter_and_cv_tips(job_desc, cv_content, tone_choice, model)
        except Exception as e:
            st.error(f"[OpenAI error] {e}")
            st.stop()

    st.success("Done!")

    st.markdown("### 📄 AI Output")
    st.markdown(output)

    # Extract only the cover letter for export
    if "COVER LETTER:" in output.upper():
        # robust split (case-insensitive)
        upper = output.upper()
        start = upper.find("COVER LETTER:")
        end = upper.find("CV IMPROVEMENT")
        if end == -1:
            cover_letter_text = output[start + len("COVER LETTER:"):].strip()
        else:
            cover_letter_text = output[start + len("COVER LETTER:"): end].strip()
    else:
        cover_letter_text = output

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📄 Download Cover Letter (Word)",
            data=save_as_docx(cover_letter_text),
            file_name="cover_letter.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    with col2:
        st.download_button(
            "📄 Download Cover Letter (PDF)",
            data=save_as_pdf(cover_letter_text),
            file_name="cover_letter.pdf",
            mime="application/pdf",
        )
