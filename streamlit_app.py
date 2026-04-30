"""
TM Journal Extractor — Streamlit web app
Extracts Quality Oracle trademark entries from MyIPO (Malaysia) and IPOS (Singapore) journal PDFs.
Deploy: push to GitHub → connect to share.streamlit.io → done.
"""

import io
import re
import zipfile
from collections import defaultdict

import pdfplumber
import pypdf
import streamlit as st

# ── Malaysia (MyIPO) patterns ──────────────────────────────────────────────────
AGENT_QO_RE   = re.compile(r'Quality Oracle|Surian\s+Tower', re.IGNORECASE)
AGENT_ANY_RE  = re.compile(r'(?:(?<=\n)|^)AGENT\s*:', re.IGNORECASE | re.MULTILINE)
AGENT_LINE_RE = re.compile(r'AGENT\s*:', re.IGNORECASE)
TM_PATTERN    = re.compile(r'\bTM\d{10}\b')

# ── Singapore (IPOS) patterns ──────────────────────────────────────────────────
SG_TM_NO_RE         = re.compile(r'National\s+Trade\s+Mark\s+No[:\s]+(\S+)', re.IGNORECASE)
SG_AGENT_HEADER_RE  = re.compile(r'Agent\s+Details/Address\s+for\s+Service', re.IGNORECASE)
SG_AGENT_QO_RE      = re.compile(r'Quality\s+Oracle', re.IGNORECASE)
SG_OWNER_HEADER_RE  = re.compile(r'Applicant/Proprietor\s+Details', re.IGNORECASE)


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


def build_sg_position_index(pages):
    tm_list, agent_list = [], []
    for page_idx, text in pages:
        for m in SG_TM_NO_RE.finditer(text):
            tm_list.append((page_idx, m.start(), m.group(1).strip()))
        for m in SG_AGENT_HEADER_RE.finditer(text):
            is_qo = bool(SG_AGENT_QO_RE.search(text[m.start(): m.start() + 500]))
            agent_list.append((page_idx, m.start(), is_qo))
    return tm_list, agent_list


def extract_sg_owner(entry_text: str) -> str:
    m = SG_OWNER_HEADER_RE.search(entry_text)
    if not m:
        return "Unknown Owner"
    after = entry_text[m.end():]
    lines = [l.strip() for l in after.splitlines() if l.strip()]
    if not lines:
        return "Unknown Owner"
    first_line = lines[0]
    name = first_line.split(';')[0].strip() if ';' in first_line else first_line
    return re.sub(r'\s+', ' ', name).strip() or "Unknown Owner"


def find_qo_entries_sg(pages: list[tuple[int, str]]) -> list[dict]:
    tm_list, agent_list = build_sg_position_index(pages)
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

        entries.append({
            "tm_no":      tm_no,
            "start_page": tm_page,
            "end_page":   agent_page,
            "owner":      extract_sg_owner(entry_text),
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

st.markdown("""
<style>
/* ── Global ── */
[data-testid="stAppViewContainer"] { background: #f7f8fa; }
[data-testid="stHeader"] { background: transparent; }

/* ── Header card ── */
.qo-header {
    background: linear-gradient(135deg, #1a3a6b 0%, #2563b0 100%);
    border-radius: 14px;
    padding: 28px 32px 22px;
    margin-bottom: 24px;
    color: white;
}
.qo-header h1 { margin: 0 0 4px; font-size: 1.75rem; font-weight: 700; color: white; }
.qo-header p  { margin: 0; font-size: 0.92rem; opacity: 0.82; color: white; }

/* ── Section labels ── */
p.section-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #6b7280;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    margin: 0 0 6px;
}

/* ── Metric cards row ── */
.metric-row { display: flex; gap: 14px; margin-bottom: 20px; }
.metric-card {
    flex: 1;
    background: white;
    border-radius: 10px;
    padding: 16px 20px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    text-align: center;
}
.metric-card .val { font-size: 2rem; font-weight: 700; color: #1a3a6b; line-height: 1.1; }
.metric-card .lbl { font-size: 0.78rem; color: #6b7280; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.04em; }

/* ── Results table ── */
[data-testid="stMarkdownContainer"] table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}
[data-testid="stMarkdownContainer"] th {
    background: #1a3a6b;
    color: white;
    padding: 10px 16px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-align: left;
}
[data-testid="stMarkdownContainer"] td {
    padding: 9px 16px;
    border-bottom: 1px solid #f0f1f3;
    color: #374151;
}
[data-testid="stMarkdownContainer"] tr:nth-child(even) td { background: #f9fafb; }
[data-testid="stMarkdownContainer"] code {
    font-weight: 600;
    color: #1a3a6b;
    background: transparent;
    font-size: 0.88rem;
}

/* ── Download button ── */
[data-testid="stDownloadButton"] button {
    background: linear-gradient(135deg, #1a3a6b, #2563b0) !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    padding: 12px !important;
    transition: opacity 0.2s !important;
}
[data-testid="stDownloadButton"] button:hover { opacity: 0.88 !important; }

/* ── Radio pills ── */
[data-testid="stRadio"] > div { gap: 8px; }
[data-testid="stRadio"] label {
    border: 1.5px solid #d1d5db !important;
    border-radius: 8px !important;
    padding: 6px 16px !important;
    font-size: 0.88rem !important;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
}
[data-testid="stRadio"] label:has(input:checked) {
    border-color: #1a3a6b !important;
    background: #eef2ff !important;
    color: #1a3a6b !important;
    font-weight: 600 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="qo-header">
  <h1>TM Journal Extractor</h1>
  <p>Quality Oracle · Extracts all agent entries from trademark journal PDFs, one file per trademark</p>
</div>
""", unsafe_allow_html=True)

# ── Upload panel ──────────────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("<p class='section-label'>SELECT JURISDICTION</p>", unsafe_allow_html=True)
    journal_type = st.radio(
        "Jurisdiction",
        ["Malaysia (MyIPO)", "Singapore (IPOS)"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.divider()
    st.markdown("<p class='section-label'>UPLOAD JOURNAL PDF</p>", unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload journal PDF", type="pdf", label_visibility="collapsed")

# ── Results ───────────────────────────────────────────────────────────────────
if uploaded:
    pdf_bytes = uploaded.read()

    with st.spinner("Scanning journal…"):
        pages = load_pages(pdf_bytes)
        if journal_type == "Singapore (IPOS)":
            entries = find_qo_entries_sg(pages)
        else:
            entries = find_qo_entries(pages)

    # Metrics row
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-card">
            <div class="val">{len(entries)}</div>
            <div class="lbl">Entries Found</div>
        </div>
        <div class="metric-card">
            <div class="val">{len(pages)}</div>
            <div class="lbl">Pages Scanned</div>
        </div>
        <div class="metric-card">
            <div class="val">{"SG" if "Singapore" in journal_type else "MY"}</div>
            <div class="lbl">Jurisdiction</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if entries:
        # Results table
        rows_md = "| TM Number | Page(s) |\n|---|---|\n"
        for e in entries:
            span = (f"p{e['start_page']+1}" if e["start_page"] == e["end_page"]
                    else f"p{e['start_page']+1}–{e['end_page']+1}")
            rows_md += f"| `{e['tm_no']}` | {span} |\n"
        st.markdown(rows_md)

        # Build ZIP and download
        with st.spinner("Packaging PDFs…"):
            zip_data = build_zip(pdf_bytes, entries)

        st.download_button(
            label=f"⬇  Download {len(entries)} PDF{'s' if len(entries) != 1 else ''} as ZIP",
            data=zip_data,
            file_name="QO_trademarks.zip",
            mime="application/zip",
            use_container_width=True,
        )

        st.markdown(
            "<div style='font-size:0.78rem;color:#9ca3af;text-align:center;margin-top:8px'>"
            "Each PDF contains the journal cover page + the trademark's page(s), "
            "named <code>[TM Number]_Journal Page.pdf</code></div>",
            unsafe_allow_html=True,
        )

    else:
        st.warning("No Quality Oracle entries found in this journal.", icon="⚠️")
