# TM Journal Extractor

A web app for **Quality Oracle** that extracts trademark entries from trademark journal PDFs — supports both **Malaysia (MyIPO)** and **Singapore (IPOS)**. Upload a journal, get one PDF per trademark (cover page + trademark page) bundled into a ZIP.

**Live app:** https://qo-publication-journal-extractor.streamlit.app

---

## What it does

- Select the journal type: **Malaysia (MyIPO)** or **Singapore (IPOS)**
- Detects all trademarks where the agent is Quality Oracle (matches by firm name or office address)
- Handles multi-page trademark entries automatically
- Outputs one PDF per trademark, named `[TM Number]_Journal Page.pdf`
- Bundles all PDFs into a single ZIP for download

## How to use

### Malaysia (MyIPO)
1. Download the latest journal PDF from [MyIPO IP Journal](https://ipjournal.myipo.gov.my/ipjournal/index.cfm?pg=publication/tm_pub&type=lt)
2. Open the [live app](https://qo-publication-journal-extractor.streamlit.app)
3. Select **Malaysia (MyIPO)**
4. Upload the journal PDF
5. Click **Download all PDFs as ZIP**

### Singapore (IPOS)
1. Download the latest Trade Marks Journal PDF from the IPOS website
2. Open the [live app](https://qo-publication-journal-extractor.streamlit.app)
3. Select **Singapore (IPOS)**
4. Upload the journal PDF
5. Click **Download all PDFs as ZIP**

## Update the app

Edit any file directly on [GitHub](https://github.com/QO-BIG/qo-publication-journal-extractor) — the live app updates automatically within seconds.

## Run locally

```bash
pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```
