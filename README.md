# GST Invoice Validator

Validates GST invoices against a master company database.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Mobile PDF Upload (New)

On the **Validate Invoice** page, switch to the **📱 Mobile** tab.

- Upload a saved PDF from your phone's Files app
- Or take/pick a **photo** of a printed invoice (JPG / PNG / WebP)

Photos are automatically converted to PDF before extraction runs.
No extra packages needed — Pillow is already in requirements.txt.

> **Tip:** For best OCR results from photos, ensure good lighting,
> hold the camera parallel to the paper, and make sure the GST
> number is clearly visible.

## Files

| File | Purpose | Changed? |
|------|---------|----------|
| `app.py` | Streamlit UI | ✅ Mobile tab added |
| `extractor.py` | PDF text extraction | ✅ `image_to_pdf_bytes()` added |
| `style.css` | Visual styles | ✅ Mobile upload styles added |
| `validator.py` | Field validation logic | — unchanged |
| `database.py` | Company master data | — unchanged |
| `requirements.txt` | Dependencies | — unchanged (Pillow was already listed) |
