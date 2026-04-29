# TM Journal Extractor

Extracts Quality Oracle trademark entries from MyIPO IP Journal PDFs. Upload a journal, download each trademark as its own PDF (cover page + trademark page).

## What it does

- Detects all trademarks where the agent is Quality Oracle (matches by name or office address)
- Handles multi-page entries automatically
- Outputs one PDF per trademark, named `Journal page - TM2025XXXXXX.pdf`
- Bundles all PDFs into a single ZIP for download

## Run locally

```bash
pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click **New app** → select repo → main file: `streamlit_app.py` → **Deploy**

## Usage

1. Download the latest journal PDF from [MyIPO IP Journal](https://ipjournal.myipo.gov.my/ipjournal/index.cfm?pg=publication/tm_pub&type=lt)
2. Upload the PDF in the app
3. Click **Download all PDFs as ZIP**
