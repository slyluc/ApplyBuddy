import requests
from bs4 import BeautifulSoup
import fitz  # PyMuPDF
from openai import OpenAI
import streamlit as st
from io import BytesIO
from docx import Document
from fpdf import FPDF
import re

# ================================
# API KEY HANDLING
# ================================
if "api_key" not in st.session_state:
    st.session_state.api_key = None
if "show_api_input" not in st.session_state:
    st.session_state.show_api_input = True

def save_api_key():
    if st.session_state.temp_api_key:
        st.session_state.api_key = st.session_state.temp_api_key
        st.session_state.show_api_input = False
        del st.session_state["temp_api_key"]

def change_api_key():
    st.session_state.show_api_input = True

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
# FUNCTIONS
# ================================

def scrape_job_description(url):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style"]):
            script.extract()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)
    except Exception as e:
        return f"Error scraping job description: {e}"

def read_cv(file):
    if file.name.lower().endswith(".pdf"):
        doc = fitz.open(stream=file.read(), filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    else:
        return file.read().decode("utf-8")

def extract_keywords(job_desc):
    """Very basic skill keyword extraction (could be upgraded with NLP)."""
    # Look for common skill-like words (capitalized, tech skills, etc.)
    words = re.findall(r'\b[A-Za-z][A-Za-z+\-#]+\b', job_desc)
    keywords = {w.strip() for w in words if len(w) > 2}
    return list(keywords)

def find_missing_keywords(job_keywords, cv_text):
    cv_lower = cv_text.lower()
    missing = [kw for kw in job_keywords if kw.lower() not in cv_lower]
    return missing

def highlight_missing_keywords(job_desc, missing_keywords):
    """Highlight missing keywords in red HTML."""
    highlighted = job_desc
    for kw in missing_keywords:
        highlighted = re.sub(rf"\b{re.escape(kw)}\b",
                             f"<span style='color:red; font-weight:bold'>{kw}</span>",
                             highlighted, flags=re.IGNORECASE)
    return highlighted

def generate_cover_letter_and_cv_tips(job_description, cv_text, tone):
    prompt = f"""
    You are an expert career coach and recruiter.

    TASKS:
    1. Based on the job description below, write a highly tailored cover letter 
       for the applicant using their CV.
       - The tone of the letter should be: {tone}
    2. Suggest concrete improvements to the CV so it matches the job better.

    JOB DESCRIPTION:
    {job_description}

    APPLICANT CV:
    {cv_text}

    Output format:
    ---
    COVER LETTER:
    [Your generated cover letter here]
    ---
    CV IMPROVEMENT SUGGESTIONS:
    [List improvements here]
    ---
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # Replace with gpt-5/gpt-5o if available
        messages=[
            {"role": "system", "content": "You are a professional career coach."},
            {"role": "user", "content": prompt}
        ]
    )
    return completion.choices[0].message.content

def save_as_docx(text):
    doc = Document()
    doc.add_paragraph(text)
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def save_as_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)
    for line in text.split("\n"):
        pdf.multi_cell(0, 10, line)
    buffer = BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

# ================================
# STREAMLIT APP
# ================================
st.set_page_config(page_title="💼 JobGenie – AI Job Application Helper", page_icon="💼")

st.title("💼 JobGenie – AI Job Application Helper")
st.write("Upload your CV, paste a job link, pick a tone, and get a custom cover letter + CV tips.")

job_url = st.text_input("Job posting URL")
cv_file = st.file_uploader("Upload your CV (PDF or TXT)", type=["pdf", "txt"])
tone_choice = st.selectbox("Choose tone for your cover letter:",
                           ["Professional", "Friendly", "Confident", "Humble", "Creative"])

if st.button("Generate Cover Letter & CV Tips"):
    if not job_url or not cv_file:
        st.warning("Please provide both a job posting URL and a CV file.")
    else:
        with st.spinner("Scraping job posting and generating content..."):
            job_desc = scrape_job_description(job_url)
            cv_content = read_cv(cv_file)

            # Keyword analysis
            job_keywords = extract_keywords(job_desc)
            missing_keywords = find_missing_keywords(job_keywords, cv_content)
            highlighted_job_desc = highlight_missing_keywords(job_desc, missing_keywords)

            # AI generation
            output = generate_cover_letter_and_cv_tips(job_desc, cv_content, tone_choice)

        st.success("Done!")

        st.markdown("### 📌 Job Posting with Missing Skills Highlighted")
        st.markdown(highlighted_job_desc, unsafe_allow_html=True)

        st.markdown("### 📄 AI Output")
        st.markdown(output)

        # Extract only the cover letter text for export
        if "COVER LETTER:" in output:
            cover_letter_text = output.split("COVER LETTER:")[1].split("CV IMPROVEMENT")[0].strip()
        else:
            cover_letter_text = output

        # Download buttons
        st.download_button("📄 Download Cover Letter (Word)",
                           data=save_as_docx(cover_letter_text),
                           file_name="cover_letter.docx")

        st.download_button("📄 Download Cover Letter (PDF)",
                           data=save_as_pdf(cover_letter_text),
                           file_name="cover_letter.pdf")
