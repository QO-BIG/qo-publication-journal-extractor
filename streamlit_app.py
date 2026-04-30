"""
TM Journal Extractor — Streamlit web app
Extracts Quality Oracle trademark entries from MyIPO journal PDFs.
Deploy: push to GitHub → connect to share.streamlit.io → done.
"""

import io
import re
import zipfile
from collections import defaultdict

import pdfplumber
import pypdf
import streamlit as st

# ── Detection patterns ─────────────────────────────────────────────────────────
# Matches our office by name OR by address (covers "Tan Sin Su", "Quality Oracle",
# or any future agent name variation at the same address).
AGENT_QO_RE   = re.compile(r'Quality Oracle|Surian\s+Tower', re.IGNORECASE)
AGENT_ANY_RE  = re.compile(r'(?:(?<=\n)|^)AGENT\s*:', re.IGNORECASE | re.MULTILINE)
AGENT_LINE_RE = re.compile(r'AGENT\s*:', re.IGNORECASE)
TM_PATTERN    = re.compile(r'\bTM\d{10}\b')


# ── Core extraction ────────────────────────────────────────────────────────────
def load_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for i, page in enumerate(pdf.pages):
            pages.append((i, page.extract_text() or ""))
    return pages


def build_position_index(pages):
    tm_list, agent_list = [], []
    for page_idx, text in pages:
        for m in TM_PATTERN.finditer(text):
            tm_list.append((page_idx, m.start(), m.group()))
        for m in AGENT_ANY_RE.finditer(text):
            is_qo = bool(AGENT_QO_RE.search(text[m.start(): m.start() + 500]))
            agent_list.append((page_idx, m.start(), is_qo))
    return tm_list, agent_list


def extract_owner(entry_text: str) -> str:
    """
    Owner format in the journal:  COMPANY NAME ; Street, City, COUNTRY
    The name may wrap across lines before the semicolon.
    Strategy: find the semicolon line, take the part before it,
    then walk back to collect any wrapped name lines above it.
    """
    lines = [l.strip() for l in entry_text.splitlines()]

    # Locate AGENT line
    agent_idx = None
    for i, line in enumerate(lines):
        if AGENT_LINE_RE.search(line):
            agent_idx = i
            break
    if agent_idx is None:
        return "Unknown Owner"

    # Find the line with ';' separator (name ; address) before AGENT
    semicolon_idx = None
    for j in range(agent_idx - 1, -1, -1):
        if lines[j] and ';' in lines[j]:
            semicolon_idx = j
            break

    if semicolon_idx is None:
        # Fallback: first non-blank uppercase-starting line before AGENT
        for j in range(agent_idx - 1, -1, -1):
            line = lines[j]
            if line and line[0].isupper():
                return re.sub(r'\s+', ' ', line.split(';')[0].strip())
        return "Unknown Owner"

    # Part before ';' on the semicolon line = end of company name
    name_part = lines[semicolon_idx].split(';')[0].strip()
    name_lines = [name_part] if name_part else []

    # Walk back up to 5 lines to collect wrapped company name lines
    for j in range(semicolon_idx - 1, max(semicolon_idx - 6, -1), -1):
        line = lines[j]
        if not line:
            break
        # Stop at goods/services text (starts lowercase, or ends with '.' but not abbreviation)
        if line[0].islower():
            break
        if line.endswith('.') and not re.search(
            r'\b(LTD|INC|CORP|BHD|SDN|CO|B\.V|GmbH|LLC)\.$', line, re.IGNORECASE
        ):
            break
        name_lines.insert(0, line)

    owner = re.sub(r'\s+', ' ', ' '.join(name_lines)).strip()
    return owner or "Unknown Owner"


def find_qo_entries(pages: list[tuple[int, str]]) -> list[dict]:
    tm_list, agent_list = build_position_index(pages)
    entries = []

    for i, (tm_page, tm_pos, tm_no) in enumerate(tm_list):
        next_tm_page = tm_list[i + 1][0] if i + 1 < len(tm_list) else len(pages)
        next_tm_pos  = tm_list[i + 1][1] if i + 1 < len(tm_list) else 0

        matched_agent = None
        for ag_page, ag_pos, is_qo in agent_list:
            if (ag_page, ag_pos) <= (tm_page, tm_pos):
                continue
            if (ag_page, ag_pos) >= (next_tm_page, next_tm_pos):
                break
            matched_agent = (ag_page, is_qo)
            break

        if not matched_agent or not matched_agent[1]:
            continue

        agent_page = matched_agent[0]
        entry_text = "\n".join(pages[p][1] for p in range(tm_page, agent_page + 1))
        offset = entry_text.find(tm_no)
        if offset != -1:
            entry_text = entry_text[offset:]

        entries.append({
            "tm_no":      tm_no,
            "start_page": tm_page,
            "end_page":   agent_page,
            "owner":      extract_owner(entry_text),
        })

    return entries


def build_zip(pdf_bytes: bytes, entries: list[dict]) -> bytes:
    """Build an in-memory ZIP containing one PDF per trademark entry."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    cover  = reader.pages[0]

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            writer = pypdf.PdfWriter()
            writer.add_page(cover)
            for p in range(entry["start_page"], entry["end_page"] + 1):
                writer.add_page(reader.pages[p])

            pdf_out = io.BytesIO()
            writer.write(pdf_out)

            filename = f"{entry['tm_no']}_Journal Page.pdf"
            zf.writestr(filename, pdf_out.getvalue())

    return zip_buf.getvalue()


# ── Streamlit UI ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TM Journal Extractor",
    page_icon="📄",
    layout="centered",
)

st.title("📄 TM Journal Extractor")
st.caption("Upload a MyIPO trademark journal PDF — extracts all Quality Oracle entries, one PDF per trademark.")

uploaded = st.file_uploader("Choose journal PDF", type="pdf")

if uploaded:
    pdf_bytes = uploaded.read()

    with st.spinner("Parsing PDF…"):
        pages  = load_pages(pdf_bytes)
        entries = find_qo_entries(pages)

    st.success(f"Found **{len(entries)}** Quality Oracle trademark{'s' if len(entries) != 1 else ''} in {len(pages)} pages.")

    if entries:
        # Results table
        st.subheader("Entries detected")
        for e in entries:
            span = (f"p{e['start_page']+1}" if e["start_page"] == e["end_page"]
                    else f"p{e['start_page']+1}–{e['end_page']+1}")
            st.markdown(f"- **{e['tm_no']}** &nbsp; `{span}` &nbsp; {e['owner']}")

        # Build ZIP
        with st.spinner("Generating PDFs…"):
            zip_data = build_zip(pdf_bytes, entries)

        st.download_button(
            label=f"⬇️  Download all {len(entries)} PDFs as ZIP",
            data=zip_data,
            file_name="QO_trademarks.zip",
            mime="application/zip",
            use_container_width=True,
        )

        st.info(
            "Each PDF is named **TMXXXXXXXXXX_Journal Page.pdf** and contains "
            "the journal cover page + the page(s) where the trademark appears.",
            icon="ℹ️",
        )
    else:
        st.warning("No Quality Oracle entries found in this journal.")
