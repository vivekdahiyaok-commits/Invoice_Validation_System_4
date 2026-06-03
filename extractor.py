"""
extractor.py
============
Precision PDF extractor built against real GST REG-06 certificates
and Trigya-style invoices. Falls back to generic heuristics for
other document formats.
"""

import re

# ── GST 15-char pattern ───────────────────────────────────────
GST_RE = re.compile(r'\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9])\b')

# ── Invoice number patterns ───────────────────────────────────
INV_RE = re.compile(
    r'(?:invoice\s*(?:no|number|#|num)?'
    r'|inv\s*(?:no|#)?'
    r'|bill\s*(?:no|number|#)?'
    r'|proforma\s*(?:invoice)?\s*#?'
    r'|tax\s*invoice\s*(?:no|#)?'
    r')\s*[:\-#]?\s*([A-Z0-9][A-Z0-9\-/_.]{2,30})',
    re.IGNORECASE
)

# ── Hash-prefixed invoice number  e.g. "# TI/PI/2627/1014" ───
HASH_INV_RE = re.compile(r'^#\s+([A-Z]{2,}[A-Z0-9/\-_.]{3,30})', re.IGNORECASE)


def _clean(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


# ─────────────────────────────────────────────────────────────
#  PDF TEXT EXTRACTION
# ─────────────────────────────────────────────────────────────

def extract_pages(uploaded_file) -> list:
    """Return list of page text strings."""
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=3, y_tolerance=3) or ''
                if len(text.strip()) < 30:
                    words = page.extract_words(x_tolerance=4, y_tolerance=4)
                    text = ' '.join(w['text'] for w in words)
                pages.append(text)
        return pages
    except Exception:
        return []


def full_text(pages: list) -> str:
    return '\n'.join(pages)


# ─────────────────────────────────────────────────────────────
#  GST NUMBER HELPERS
# ─────────────────────────────────────────────────────────────

def find_gst_numbers(text: str) -> list:
    """Return all unique GST numbers found in text."""
    found = GST_RE.findall(text)
    relaxed = re.compile(
        r'\b([0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][A-Za-z0-9][Zz][A-Za-z0-9])\b'
    )
    for m in relaxed.findall(text):
        found.append(m.upper())
    seen, result = set(), []
    for g in found:
        g = g.upper()
        if g not in seen:
            seen.add(g)
            result.append(g)
    return result


# ─────────────────────────────────────────────────────────────
#  GST CERTIFICATE PARSER  (Form GST REG-06)
# ─────────────────────────────────────────────────────────────

def parse_gst_certificate(pages: list) -> dict:
    """
    Parses the Government of India Form GST REG-06.

    Real line format (from actual PDF):
        Registration Number : 06AAJCT0674P1ZR
        1. Legal Name TRIGYA INNOVATIONS INDIA PRIVATE LIMITED
        2. Trade Name, if any TRIGYA INNOVATIONS INDIA PRIVATE LIMITED
        4. Address of Principal Place of 44/3, OLD ROHTAK ROAD -OPP. POST OFFICE,
        Business KHARKHODA, Haryana, Sonipat, Haryana, 131402
    """
    text  = full_text(pages)
    lines = text.splitlines()

    # ── GST Number ────────────────────────────────────────────
    gst_no = ''
    for line in lines:
        # "Registration Number : 06AAJCT0674P1ZR"
        if 'REGISTRATION NUMBER' in line.upper():
            m = GST_RE.search(line)
            if m:
                gst_no = m.group(1)
                break
        # Also check GSTIN label on annexure pages
        if line.strip().upper().startswith('GSTIN'):
            m = GST_RE.search(line)
            if m:
                gst_no = m.group(1)
                break
    if not gst_no:
        m = GST_RE.search(text)
        gst_no = m.group(1) if m else ''

    # ── Legal Name ────────────────────────────────────────────
    # Line starts with "1. Legal Name <NAME>" or "Legal Name <NAME>"
    name = ''
    legal_re = re.compile(
        r'(?:1\.\s*)?legal\s+name(?:\s+of\s+business)?\s+(.+)', re.IGNORECASE
    )
    for line in lines:
        m = legal_re.match(line.strip())
        if m:
            candidate = _clean(m.group(1))
            # Remove trailing junk like "2. Trade Name..."
            candidate = re.split(r'\s+\d+\.\s+', candidate)[0].strip()
            if len(candidate) > 4:
                name = candidate
                break

    # Fallback: "TRIGYA INNOVATIONS" anywhere after GST on same/adjacent line
    if not name and gst_no:
        for i, line in enumerate(lines):
            if gst_no in line:
                # Check same line after GST
                after = line.split(gst_no, 1)[1].strip()
                if len(after) > 4 and not after.startswith('www'):
                    name = _clean(after)
                    break
                # Check 1-2 lines above (company name often above GST in invoices)
                for offset in [-2, -1, 1, 2]:
                    idx = i + offset
                    if 0 <= idx < len(lines):
                        c = _clean(lines[idx])
                        if len(c) > 4 and not GST_RE.search(c) and not c.startswith('www'):
                            name = c
                            break
                if name:
                    break

    # ── Address ───────────────────────────────────────────────
    # Spans two lines in REG-06:
    #   "4. Address of Principal Place of  44/3, OLD ROHTAK ROAD..."
    #   "Business  KHARKHODA, Haryana, Sonipat, Haryana, 131402"
    address = ''
    addr_re = re.compile(
        r'(?:\d+\.\s*)?address\s+of\s+principal\s+place\s+(?:of\s+)?(.+)',
        re.IGNORECASE
    )
    for i, line in enumerate(lines):
        m = addr_re.match(line.strip())
        if m:
            part1 = _clean(m.group(1))
            # Remove trailing "Business" word that bleeds into next token
            part1 = re.sub(r'\s*business\s*$', '', part1, flags=re.IGNORECASE).strip()
            # Next line often starts with "Business <rest of address>"
            part2 = ''
            if i + 1 < len(lines):
                nxt = _clean(lines[i + 1])
                nxt_stripped = re.sub(r'^business\s+', '', nxt, flags=re.IGNORECASE).strip()
                # Only take it if it looks like an address (has digit or comma)
                if re.search(r'\d|,', nxt_stripped):
                    part2 = nxt_stripped
            address = (part1 + (', ' + part2 if part2 else '')).strip(', ')
            break

    # Fallback: look for pincode in text
    if not address:
        pin_re = re.compile(r'\b\d{6}\b')
        for i, line in enumerate(lines):
            if pin_re.search(line):
                start = max(0, i - 2)
                parts = []
                for j in range(start, min(i + 2, len(lines))):
                    l = _clean(lines[j])
                    if l and not re.match(r'^(gstin|registration|legal|trade|date|period|type)', l, re.IGNORECASE):
                        parts.append(l)
                address = ', '.join(parts)
                break

    return {
        'gst_no':  gst_no,
        'name':    name,
        'address': _clean(address),
        'source':  'GST Certificate',
    }


# ─────────────────────────────────────────────────────────────
#  INVOICE PARSER
# ─────────────────────────────────────────────────────────────

def parse_invoice(pages: list) -> dict:
    """
    Extracts SELLER details from an invoice.

    Real Trigya invoice structure:
        Proforma Invoice
        # TI/PI/2627/1014
        Gurgaon Haryana 122016
        India
        GSTIN: 06AAJCT0674P1ZR
        www.trigya.co
        ...
        Beneficiary Name:  Trigya Innovations India Pvt Ltd
    """
    text  = full_text(pages)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ── Invoice number ────────────────────────────────────────
    invoice_number = ''
    # "# TI/PI/2627/1014"  or  "Invoice No: TI/INV/001"
    for line in lines[:15]:                          # usually in first 15 lines
        m = HASH_INV_RE.match(line)
        if m:
            invoice_number = _clean(m.group(1))
            break
    if not invoice_number:
        m = INV_RE.search(text)
        if m:
            invoice_number = _clean(m.group(1))
    # Also accept Reference number if nothing else
    if not invoice_number:
        ref_re = re.compile(r'reference\s*[:\-]\s*([A-Z0-9][A-Z0-9/\-_.]{3,30})', re.IGNORECASE)
        m = ref_re.search(text)
        if m:
            invoice_number = _clean(m.group(1))

    # ── All GST numbers ───────────────────────────────────────
    all_gsts   = find_gst_numbers(text)
    seller_gst = ''

    # Seller GST is usually labelled "GSTIN:" in header (not under "Bill To")
    gstin_re = re.compile(r'GSTIN\s*[:\-]?\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9])', re.IGNORECASE)
    m = gstin_re.search(text)
    if m:
        seller_gst = m.group(1).upper()
    elif all_gsts:
        seller_gst = all_gsts[0]

    # ── Seller name ───────────────────────────────────────────
    # Strategy 1: "Beneficiary Name: Trigya Innovations India Pvt Ltd"
    seller_name = ''
    bene_re = re.compile(r'beneficiary\s+name\s*[:\-]\s*(.+)', re.IGNORECASE)
    m = bene_re.search(text)
    if m:
        seller_name = _clean(m.group(1))

    # Strategy 2: company name appears 1-3 lines BEFORE the GSTIN line
    if not seller_name and seller_gst:
        for i, line in enumerate(lines):
            if seller_gst in line.upper():
                for offset in range(-3, 0):
                    idx = i + offset
                    if idx < 0:
                        continue
                    c = _clean(lines[idx])
                    # Skip short lines, URLs, dates, "India", numeric lines
                    if (len(c) > 6
                            and not re.match(r'^(india|date|ref|bill|ship|www\.|http)', c, re.IGNORECASE)
                            and not GST_RE.search(c)
                            and not c.replace(' ', '').isdigit()
                            and re.search(r'[A-Za-z]{3}', c)):
                        seller_name = c
                break

    # Strategy 3: first non-header line with letters (company letterhead)
    if not seller_name:
        skip = re.compile(
            r'^(proforma|invoice|tax invoice|bill|#|date|ref|dear|to:|from:|page)',
            re.IGNORECASE
        )
        for line in lines[:8]:
            if skip.match(line):
                continue
            if len(line) > 5 and re.search(r'[A-Za-z]{3}', line) and not GST_RE.search(line):
                seller_name = _clean(line)
                break

    # ── Seller address ────────────────────────────────────────
    # In this invoice: address is lines between company header and GSTIN
    # "Gurgaon Haryana 122016"  "India"
    seller_addr = ''
    if seller_gst:
        for i, line in enumerate(lines):
            if seller_gst in line.upper():
                # Collect lines between start and this GSTIN line (seller header block)
                addr_parts = []
                for j in range(max(0, i - 5), i):
                    c = _clean(lines[j])
                    # Skip company name line and short non-address lines
                    if seller_name and c == seller_name:
                        continue
                    if (len(c) > 3
                            and not re.match(r'^(proforma|invoice|#\s+[A-Z]|bill\s+to|www\.)', c, re.IGNORECASE)
                            and not GST_RE.search(c)
                            and re.search(r'[A-Za-z]', c)):
                        addr_parts.append(c)
                if addr_parts:
                    seller_addr = ', '.join(addr_parts)
                break

    # Fallback address: pincode scan
    if not seller_addr:
        pin_re = re.compile(r'\b\d{6}\b')
        for i, line in enumerate(lines):
            if pin_re.search(line):
                start = max(0, i - 2)
                parts = [_clean(lines[j]) for j in range(start, min(i + 2, len(lines)))
                         if _clean(lines[j]) and 'bill to' not in lines[j].lower()]
                seller_addr = ', '.join(p for p in parts if p)
                break

    return {
        'gst_no':         seller_gst,
        'name':           seller_name,
        'address':        _clean(seller_addr),
        'invoice_number': invoice_number,
        'all_gsts':       all_gsts,
        'source':         'Invoice',
    }
