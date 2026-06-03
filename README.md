# GST Invoice Validation System

Validates invoices against a master company database.

## Files
- `app.py` — Streamlit UI (3 pages: Validate, Database, How It Works)
- `database.py` — Master company records (add companies here)
- `extractor.py` — PDF text extraction engine
- `validator.py` — Field-by-field validation logic
- `style.css` — UI styling
- `requirements.txt` — Python dependencies

## Setup
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Add a new company
Open `database.py` and add an entry inside `COMPANIES` dict.

## Deploy to Streamlit Cloud
1. Push to GitHub
2. Go to share.streamlit.io
3. Point to app.py
