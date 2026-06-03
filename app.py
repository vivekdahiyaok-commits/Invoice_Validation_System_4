# ─────────────────────────────────────────────────────────────
#  app.py — GST Invoice Validation System
#  Validates invoices against a master company database
# ─────────────────────────────────────────────────────────────

import streamlit as st
import json
from datetime import datetime

st.set_page_config(
    page_title="Invoice Validator",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

with open("style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# ── Module imports ────────────────────────────────────────────
try:
    from extractor import extract_pages, parse_invoice, parse_gst_certificate
    EXTRACT_OK = True
except ImportError as e:
    EXTRACT_OK = False
    st.error(f"extractor.py import error: {e}")

try:
    from validator import validate_invoice
    VALID_OK = True
except ImportError as e:
    VALID_OK = False
    st.error(f"validator.py import error: {e}")

try:
    from database import COMPANIES, get_company, get_all_gst_numbers
    DB_OK = True
except ImportError as e:
    DB_OK = False
    st.error(f"database.py import error: {e}")

# ── Status display constants ──────────────────────────────────
ICON  = {"match": "✅", "fuzzy": "⚠️", "mismatch": "❌",
         "missing": "🔍", "unknown": "❓"}
CLS   = {"match": "card-match", "fuzzy": "card-fuzzy",
         "mismatch": "card-mismatch", "missing": "card-missing",
         "unknown": "card-unknown"}
BADGE = {"match": "VERIFIED", "fuzzy": "CLOSE MATCH",
         "mismatch": "MISMATCH", "missing": "NOT FOUND",
         "unknown": "NOT IN DB"}
BAR_COLOR = {"match": "#167a48", "fuzzy": "#a06800",
             "mismatch": "#b51c1c", "missing": "#1858a8", "unknown": "#666"}

# ─────────────────────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('''
    <div class="sb-wrap">
      <div class="sb-logo-row">
        <div class="sb-icon">🧾</div>
        <div>
          <div class="sb-brand">Invoice Validator</div>
          <div class="sb-tagline">GST Compliance System</div>
        </div>
      </div>
      <div class="sb-rule"></div>
    </div>
    ''', unsafe_allow_html=True)

    page = st.radio(
        "Navigation",
        ["🔍  Validate Invoice", "🏢  Database", "📖  How It Works"],
        label_visibility="collapsed",
    )

    st.markdown('<div class="sb-rule"></div>', unsafe_allow_html=True)

    if DB_OK:
        count = len(COMPANIES)
        st.markdown(f'''
        <div class="sb-stat">
          <div class="sb-stat-num">{count}</div>
          <div class="sb-stat-lbl">Companies in Database</div>
        </div>
        ''', unsafe_allow_html=True)

    st.markdown('''
    <div class="sb-rule"></div>
    <div class="sb-help">
      <div class="sb-help-title">Quick Guide</div>
      <div class="sb-help-item">1. Upload invoice PDF</div>
      <div class="sb-help-item">2. System extracts fields</div>
      <div class="sb-help-item">3. Matches against DB</div>
      <div class="sb-help-item">4. Get field-by-field result</div>
    </div>
    ''', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
#  PAGE: VALIDATE INVOICE
# ─────────────────────────────────────────────────────────────
if "Validate" in page:

    # Header
    st.markdown('''
    <div class="page-header">
      <div class="page-eyebrow">GST COMPLIANCE</div>
      <h1 class="page-title">Invoice Validator</h1>
      <p class="page-sub">Upload an invoice — the system automatically extracts the seller's
      GST number, name &amp; address and validates them against the master database.</p>
    </div>
    ''', unsafe_allow_html=True)

    # ── Upload section ─────────────────────────────────────
    st.markdown('<div class="section-label">UPLOAD INVOICE</div>', unsafe_allow_html=True)

    up_col, info_col = st.columns([3, 2], gap="large")

    with up_col:
        inv_file = st.file_uploader(
            "Upload Invoice PDF",
            type=["pdf"],
            label_visibility="collapsed",
            key="inv_upload",
        )
        if inv_file:
            st.markdown(f'<div class="file-chip">✓ {inv_file.name} ({round(inv_file.size/1024, 1)} KB)</div>',
                        unsafe_allow_html=True)

    with info_col:
        st.markdown('''
        <div class="info-box">
          <div class="info-title">What gets validated</div>
          <div class="info-row"><span class="info-dot green"></span>GST Number (exact match)</div>
          <div class="info-row"><span class="info-dot green"></span>Company Name (fuzzy match)</div>
          <div class="info-row"><span class="info-dot green"></span>Registered Address</div>
          <div class="info-row"><span class="info-dot green"></span>Invoice Number (format check)</div>
        </div>
        ''', unsafe_allow_html=True)

    # ── Manual override ────────────────────────────────────
    with st.expander("✏️  Manually enter or fix extracted values"):
        st.markdown('<p class="override-hint">If auto-extraction picks up wrong values, correct them here. These override the PDF extraction.</p>', unsafe_allow_html=True)
        ov1, ov2 = st.columns(2, gap="large")
        with ov1:
            ov_gst  = st.text_input("GST Number",      key="ov_gst",  placeholder="e.g. 06AAJCT0674P1ZR")
            ov_name = st.text_input("Company Name",    key="ov_name", placeholder="Exact name from invoice")
        with ov2:
            ov_addr = st.text_area ("Address",         key="ov_addr", height=80,  placeholder="Address as shown on invoice")
            ov_inv  = st.text_input("Invoice Number",  key="ov_inv",  placeholder="e.g. TI/PI/2627/1014")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Validate button ────────────────────────────────────
    btn_col, _ = st.columns([1, 3])
    with btn_col:
        run = st.button("🔍  Validate Invoice", type="primary", use_container_width=True)

    # ── Processing ─────────────────────────────────────────
    if run:
        inv_data = {}

        bar = st.progress(0, text="Starting…")

        # Extract from PDF
        if inv_file and EXTRACT_OK:
            bar.progress(20, text="Reading invoice PDF…")
            pages    = extract_pages(inv_file)
            inv_data = parse_invoice(pages)

        bar.progress(55, text="Applying manual overrides…")

        # Apply manual overrides
        overrides = {
            'gst_no':         st.session_state.get('ov_gst',  '').strip(),
            'name':           st.session_state.get('ov_name', '').strip(),
            'address':        st.session_state.get('ov_addr', '').strip(),
            'invoice_number': st.session_state.get('ov_inv',  '').strip(),
        }
        for field, val in overrides.items():
            if val:
                inv_data[field] = val

        if not inv_data:
            bar.empty()
            st.markdown('<div class="alert-err">❌ No data found. Upload a PDF or fill in the manual fields above.</div>',
                        unsafe_allow_html=True)
            st.stop()

        bar.progress(75, text="Looking up company in database…")

        # Run validation
        result = validate_invoice(inv_data)
        bar.progress(100, text="Done!")
        bar.empty()

        # ── Show extracted data ──────────────────────────
        with st.expander("📋  Extracted values from invoice"):
            ed1, ed2 = st.columns(2)
            with ed1:
                st.markdown("**Auto-extracted from PDF**")
                st.json({
                    "GST Number":     inv_data.get('gst_no', '—'),
                    "Company Name":   inv_data.get('name', '—'),
                    "Address":        inv_data.get('address', '—'),
                    "Invoice Number": inv_data.get('invoice_number', '—'),
                })
            with ed2:
                if result['company_found']:
                    co = result['company']
                    st.markdown("**Matched company in database**")
                    st.json({
                        "GST Number":  co.get('gst_no', '—'),
                        "Legal Name":  co.get('legal_name', '—'),
                        "Address":     co.get('full_address', '—'),
                        "Registered":  co.get('registered_on', '—'),
                        "Status":      "✅ Active" if co.get('active') else "❌ Inactive",
                    })
                else:
                    st.markdown("**Database lookup**")
                    st.warning("Company not found in database.")

        st.markdown('<div class="results-rule"></div>', unsafe_allow_html=True)

        # ── Company card ─────────────────────────────────
        if result['company_found']:
            co = result['company']
            st.markdown(f'''
            <div class="company-card">
              <div class="company-icon">🏢</div>
              <div class="company-info">
                <div class="company-name">{co.get("legal_name","")}</div>
                <div class="company-meta">
                  <span class="company-tag gst-tag">{co.get("gst_no","")}</span>
                  <span class="company-tag">📍 {co.get("city","")}, {co.get("state","")}</span>
                  <span class="company-tag">📅 Since {co.get("registered_on","")}</span>
                  {"<span class='company-tag active-tag'>✅ Active</span>" if co.get("active") else "<span class='company-tag inactive-tag'>❌ Inactive</span>"}
                </div>
              </div>
            </div>
            ''', unsafe_allow_html=True)

        # ── Verdict banner ───────────────────────────────
        s = result['summary']
        if not result['company_found']:
            vcls, vicon, vtxt = "verdict-unknown", "❓", "Company not found in database — cannot validate"
        elif s['mismatch'] == 0 and s['missing'] == 0:
            if s['fuzzy'] == 0:
                vcls, vicon, vtxt = "verdict-pass", "✅", "Invoice fully verified — all fields match the database"
            else:
                vcls, vicon, vtxt = "verdict-warn", "⚠️", "Invoice likely valid — minor formatting differences found"
        elif s['mismatch'] > 0:
            vcls, vicon, vtxt = "verdict-fail", "❌", f"{s['mismatch']} field(s) have errors — review required"
        else:
            vcls, vicon, vtxt = "verdict-warn", "⚠️", f"{s['missing']} field(s) could not be extracted"

        st.markdown(f'''
        <div class="verdict {vcls}">
          <div class="verdict-left">{vicon}</div>
          <div class="verdict-body">
            <div class="verdict-title">{vtxt}</div>
            <div class="verdict-counts">
              <span class="vc green">✅ {s["match"]} exact</span>
              <span class="vc amber">⚠️ {s["fuzzy"]} close</span>
              <span class="vc red">❌ {s["mismatch"]} mismatch</span>
              <span class="vc blue">🔍 {s["missing"]} missing</span>
            </div>
          </div>
        </div>
        ''', unsafe_allow_html=True)

        # ── Field result cards ───────────────────────────
        st.markdown('<div class="fields-label">FIELD BY FIELD RESULTS</div>', unsafe_allow_html=True)

        for r in result['results']:
            status  = r.get('status', 'missing')
            icon    = ICON.get(status, '🔍')
            cls     = CLS.get(status, 'card-missing')
            badge   = BADGE.get(status, 'UNKNOWN')
            score   = r.get('score', 0)
            bar_c   = BAR_COLOR.get(status, '#888')
            db_val  = r.get('db_value', '') or ''
            inv_val = r.get('invoice_value', '') or ''
            reason  = r.get('reason', '')
            correct = r.get('correct_value', '')

            correct_block = ''
            if correct:
                correct_block = f'''
                <div class="correct-strip">
                  <span class="correct-lbl">CORRECT VALUE</span>
                  <span class="correct-val">{correct}</span>
                </div>'''

            st.markdown(f'''
            <div class="field-card {cls}">
              <div class="fc-head">
                <div class="fc-title">{r.get("field","")}</div>
                <div class="fc-right">
                  <span class="fc-badge">{icon} {badge}</span>
                  {"<span class='fc-score'>"+str(score)+"%</span>" if score else ""}
                </div>
              </div>
              <div class="fc-bar-wrap">
                <div class="fc-bar" style="width:{score}%;background:{bar_c}"></div>
              </div>
              <div class="fc-body">
                <div class="fc-row">
                  <span class="fc-lbl">DATABASE</span>
                  <span class="fc-val db-val">{db_val or "<em>—</em>"}</span>
                </div>
                <div class="fc-row">
                  <span class="fc-lbl">INVOICE</span>
                  <span class="fc-val inv-val">{inv_val or "<em>not found</em>"}</span>
                </div>
                <div class="fc-row">
                  <span class="fc-lbl">ANALYSIS</span>
                  <span class="fc-val reason-val">{reason}</span>
                </div>
              </div>
              {correct_block}
            </div>
            ''', unsafe_allow_html=True)

        # ── Download report ──────────────────────────────
        st.markdown("<br>", unsafe_allow_html=True)
        report = {
            "generated_at":   datetime.now().isoformat(),
            "verdict":        vtxt,
            "invoice_data":   inv_data,
            "company":        result.get('company', {}),
            "results":        result['results'],
            "summary":        result['summary'],
        }
        dl1, dl2, _ = st.columns([1, 1, 2])
        with dl1:
            st.download_button(
                "⬇️ JSON Report",
                data=json.dumps(report, indent=2),
                file_name=f"validation_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                use_container_width=True,
            )
        with dl2:
            rows = ["Field,Database Value,Invoice Value,Status,Score,Reason"]
            for r in result['results']:
                rows.append(
                    f'"{r.get("field","")}","{r.get("db_value","")}","{r.get("invoice_value","")}",{r.get("status","")},{r.get("score",0)},"{r.get("reason","")}"'
                )
            st.download_button(
                "⬇️ CSV Report",
                data="\n".join(rows),
                file_name=f"validation_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
            )


# ─────────────────────────────────────────────────────────────
#  PAGE: DATABASE
# ─────────────────────────────────────────────────────────────
elif "Database" in page:
    st.markdown('''
    <div class="page-header">
      <div class="page-eyebrow">MASTER RECORDS</div>
      <h1 class="page-title">Company Database</h1>
      <p class="page-sub">These are the verified company records. All invoice validations are checked against this data.</p>
    </div>
    ''', unsafe_allow_html=True)

    if not DB_OK:
        st.error("Database module not loaded.")
        st.stop()

    # Search
    search = st.text_input("🔍 Search by GST number or company name", placeholder="Type to filter…")

    for gst, co in COMPANIES.items():
        if search:
            if search.upper() not in gst and search.upper() not in co.get('legal_name','').upper():
                continue

        with st.expander(f"🏢  {co.get('legal_name','')}  |  {gst}"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"""
**GST Number:** `{co.get('gst_no','')}`
**Legal Name:** {co.get('legal_name','')}
**Constitution:** {co.get('constitution','')}
**Registered On:** {co.get('registered_on','')}
**Status:** {"✅ Active" if co.get('active') else "❌ Inactive"}
                """)
            with c2:
                st.markdown(f"""
**Registered Address:**
{co.get('full_address','')}

**City:** {co.get('city','')}
**State:** {co.get('state','')}
**PIN:** {co.get('pincode','')}
                """)

            st.markdown("**Accepted Name Variations:**")
            for t in co.get('trade_names', []):
                st.markdown(f"• {t}")

    st.markdown("---")
    st.markdown("**To add a new company:** Open `database.py` in VS Code and add a new entry inside the `COMPANIES` dictionary following the existing format.", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
#  PAGE: HOW IT WORKS
# ─────────────────────────────────────────────────────────────
elif "How" in page:
    st.markdown('''
    <div class="page-header">
      <div class="page-eyebrow">DOCUMENTATION</div>
      <h1 class="page-title">How It Works</h1>
    </div>
    ''', unsafe_allow_html=True)

    st.markdown("""
### System Overview

This system validates invoices by comparing the seller's details against a pre-verified master database.

---

### Step 1 — PDF Extraction
The invoice PDF is read by `extractor.py` using `pdfplumber`.
It scans the **entire document** to find:
- GST number (matches Indian 15-char format `06AAJCT0674P1ZR`)
- Company name (near GST number, or after beneficiary/company labels)
- Address (after GST label, or near 6-digit pincode)
- Invoice number (after Invoice No / Proforma # labels)

---

### Step 2 — Database Lookup
The extracted GST number is looked up in `database.py`.
If found → the company's verified record is retrieved.
If not found → validation stops and asks to add the company first.

---

### Step 3 — Field-by-Field Validation

| Field | Method | Rules |
|---|---|---|
| GST Number | Exact match | Must be character-for-character identical |
| Company Name | Fuzzy match | Accepts abbreviations like "Pvt Ltd" = "Private Limited" |
| Address | Fuzzy + pincode | Accepts branch address if pincode matches |
| Invoice Number | Format check | Must contain letters + numbers, min 4 chars |

---

### Step 4 — Result Scoring

| Score | Status | Meaning |
|---|---|---|
| 100% | ✅ Match | Exact / near-exact |
| 72–89% | ⚠️ Close | Likely same, minor formatting differences |
| < 72% | ❌ Mismatch | Genuinely different — could be wrong company |
| 0% | 🔍 Missing | Field not found in invoice |

---

### Adding a New Company

Open `database.py` and add a new entry in the `COMPANIES` dictionary:

```python
"YOUR_GST_NUMBER": {
    "gst_no":       "YOUR_GST_NUMBER",
    "legal_name":   "FULL LEGAL NAME FROM CERTIFICATE",
    "trade_names":  ["Full Name", "Short Name", "Abbreviation"],
    "address_line": "Street Address",
    "city":         "City",
    "state":        "State",
    "pincode":      "XXXXXX",
    "full_address": "Complete Address String",
    "known_addresses": ["Address 1", "Address 2"],
    "constitution": "Private Limited Company",
    "registered_on": "DD/MM/YYYY",
    "active": True,
}
```

Save the file and restart the Streamlit app.

---

### Common Issues

**Invoice shows Gurgaon address but GST certificate shows Kharkhoda address**
→ This is normal for companies with multiple offices. Both are added to `known_addresses` in the database.

**Name extracted as "Trigya Innovations" but DB has full legal name**
→ The fuzzy matcher handles this. Score will be ~85% = Close Match, which is acceptable.

**GST not found in invoice**
→ Use the manual override fields to paste the GST number directly.
    """)
