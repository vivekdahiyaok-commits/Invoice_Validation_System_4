"""
validator.py
============
Validates invoice fields against the master company database.
Uses rapidfuzz if available, falls back to Python difflib (no install needed).
"""

import re
import difflib

try:
    from rapidfuzz import fuzz as _rf
    def _fuzzy(a, b):
        return max(
            _rf.ratio(a, b),
            _rf.token_sort_ratio(a, b),
            _rf.token_set_ratio(a, b),
            _rf.partial_ratio(a, b),
        )
    FUZZY_ENGINE = 'rapidfuzz'
except ImportError:
    def _fuzzy(a, b):
        """Pure-Python fallback using difflib."""
        if not a or not b:
            return 0
        base   = difflib.SequenceMatcher(None, a, b).ratio() * 100
        # token sort: sort words and compare
        ta = ' '.join(sorted(a.split()))
        tb = ' '.join(sorted(b.split()))
        tsort = difflib.SequenceMatcher(None, ta, tb).ratio() * 100
        # partial: slide shorter over longer
        short, long_ = (a, b) if len(a) <= len(b) else (b, a)
        partial = max(
            difflib.SequenceMatcher(None, short, long_[i:i+len(short)]).ratio() * 100
            for i in range(max(1, len(long_) - len(short) + 1))
        )
        return max(base, tsort, partial)
    FUZZY_ENGINE = 'difflib'

from database import get_company


# ── Normalisation ─────────────────────────────────────────────

def normalize(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def normalize_name(s):
    s = (s or '').lower()
    for pat, rep in [
        (r'\bpvt\b','private'), (r'\bltd\b','limited'),
        (r'\bco\b','company'),  (r'\bcorp\b','corporation'),
        (r'\binc\b','incorporated'), (r'\bllp\b','llp'),
    ]:
        s = re.sub(pat, rep, s)
    return re.sub(r'[^a-z0-9]', '', s)

def normalize_address(s):
    s = (s or '').lower()
    for pat, rep in [
        (r'\brd\b','road'),    (r'\bst\b','street'),
        (r'\bpvt\b','private'),(r'\bltd\b','limited'),
        (r'\bopp\b','opposite'),(r'\bpo\b','postoffice'),
        (r'\bdist\b','district'),(r'\bvill\b','village'),
        (r',\s*india\b',''),   # strip trailing "India" which is redundant
    ]:
        s = re.sub(pat, rep, s)
    return re.sub(r'[^a-z0-9]', '', s)


def _score(a, b):
    if not a or not b:
        return 0
    return round(_fuzzy(a, b))


def _status_from_score(score, is_gst=False):
    if is_gst:
        return 'match' if score == 100 else 'mismatch'
    if score >= 88:
        return 'match'
    if score >= 68:
        return 'fuzzy'
    return 'mismatch'


# ── Field validators ──────────────────────────────────────────

def validate_gst(inv_gst, db_gst):
    inv_gst = (inv_gst or '').strip().upper()
    db_gst  = (db_gst  or '').strip().upper()
    if not inv_gst:
        return dict(field='GST Number', status='missing', score=0,
                    db_value=db_gst, invoice_value='',
                    reason='GST number not found in invoice.',
                    correct_value=db_gst)
    exact = inv_gst == db_gst
    score = 100 if exact else _score(inv_gst, db_gst)
    if exact:
        reason = 'GST numbers match exactly.'
    else:
        reason = (f'Similar ({score}%) — possible OCR/typo error. '
                  f'Must be exact. Correct: {db_gst}')
    return dict(field='GST Number',
                status='match' if exact else 'mismatch',
                score=score, db_value=db_gst, invoice_value=inv_gst,
                reason=reason, correct_value=db_gst if not exact else '')


def validate_name(inv_name, company):
    inv_name = (inv_name or '').strip()
    legal    = company.get('legal_name', '')
    trades   = company.get('trade_names', [legal])
    if not inv_name:
        return dict(field='Company Name', status='missing', score=0,
                    db_value=legal, invoice_value='',
                    reason='Company name not found in invoice.',
                    correct_value=legal)
    inv_n = normalize_name(inv_name)
    best_score, best_match = 0, legal
    for trade in trades:
        s = _score(inv_n, normalize_name(trade))
        if s > best_score:
            best_score, best_match = s, trade
    status = _status_from_score(best_score)
    if status == 'match':
        reason = f'Name matches "{best_match}".'
    elif status == 'fuzzy':
        reason = (f'Close match to "{best_match}" ({best_score}%) — '
                   'likely abbreviated or short form. Acceptable.')
    else:
        reason = f'Name "{inv_name}" does not match. Correct: "{legal}".'
    return dict(field='Company Name', status=status, score=best_score,
                db_value=legal, invoice_value=inv_name, reason=reason,
                correct_value=legal if status == 'mismatch' else '')


def validate_address(inv_addr, company):
    inv_addr  = (inv_addr or '').strip()
    full_addr = company.get('full_address', '')
    known     = company.get('known_addresses', [full_addr])
    if not inv_addr:
        return dict(field='Address', status='missing', score=0,
                    db_value=full_addr, invoice_value='',
                    reason='Address not found in invoice.',
                    correct_value=full_addr)

    inv_n = normalize_address(inv_addr)
    all_addrs = list(dict.fromkeys([full_addr] + known))  # unique, registered first
    best_score, best_match = 0, full_addr
    for addr in all_addrs:
        s = _score(inv_n, normalize_address(addr))
        if s > best_score:
            best_score, best_match = s, addr

    # Pincode match gives a strong boost
    pin_re  = re.compile(r'\b\d{6}\b')
    db_pins = set(pin_re.findall(full_addr))
    iv_pins = set(pin_re.findall(inv_addr))
    pin_hit = bool(db_pins & iv_pins)
    if pin_hit and best_score < 72:
        best_score = max(best_score, 75)

    # City/state word match gives moderate boost
    city  = company.get('city', '').lower()
    state = company.get('state', '').lower()
    inv_l = inv_addr.lower()
    if city and city in inv_l and best_score < 72:
        best_score = max(best_score, 70)

    status = _status_from_score(best_score)

    is_known = best_match != full_addr
    if status == 'match':
        if is_known:
            reason = (f'Invoice shows a known operational address '
                      f'("{best_match}"). Registered address: "{full_addr}".')
        else:
            reason = 'Address matches registered address.'
    elif status == 'fuzzy':
        if pin_hit:
            reason = ('Pincode matches. Invoice may show a branch/billing address '
                      f'instead of registered address ("{full_addr}").')
        else:
            reason = (f'Partial match ({best_score}%) — may be abbreviated. '
                      f'Registered: "{full_addr}".')
    else:
        reason = (f'Address does not match any known address. '
                  f'Registered: "{full_addr}".')
    return dict(field='Address', status=status, score=best_score,
                db_value=full_addr, invoice_value=inv_addr, reason=reason,
                correct_value=full_addr if status == 'mismatch' else '')


def validate_invoice_number(inv_number):
    inv_number = (inv_number or '').strip()
    if not inv_number:
        return dict(field='Invoice Number', status='missing', score=0,
                    db_value='N/A', invoice_value='',
                    reason='Invoice number not found in the document.',
                    correct_value='')
    has_alpha = bool(re.search(r'[A-Za-z]', inv_number))
    has_digit = bool(re.search(r'\d', inv_number))
    if has_alpha and has_digit and len(inv_number) >= 4:
        return dict(field='Invoice Number', status='match', score=100,
                    db_value='N/A (not stored)', invoice_value=inv_number,
                    reason=f'Invoice number "{inv_number}" detected — format valid.',
                    correct_value='')
    return dict(field='Invoice Number', status='fuzzy', score=70,
                db_value='N/A (not stored)', invoice_value=inv_number,
                reason=f'"{inv_number}" detected but format looks unusual.',
                correct_value='')


# ── Main entry point ──────────────────────────────────────────

def validate_invoice(invoice_data: dict) -> dict:
    """
    Validate invoice_data against master DB.
    Returns company_found, company record, results list, summary.
    """
    inv_gst = (invoice_data.get('gst_no') or '').strip().upper()
    company = get_company(inv_gst)

    if not company:
        return dict(
            company_found=False, company=None,
            results=[dict(
                field='GST Number', status='unknown', score=0,
                db_value='Not in database',
                invoice_value=inv_gst or 'Not found in invoice',
                reason=(f'GST "{inv_gst}" is not in the master database. '
                         'Go to the Database tab to add this company.'),
                correct_value='',
            )],
            summary=dict(total=1, match=0, fuzzy=0, mismatch=0, missing=1),
        )

    results = [
        validate_gst(inv_gst, company['gst_no']),
        validate_name(invoice_data.get('name', ''), company),
        validate_address(invoice_data.get('address', ''), company),
        validate_invoice_number(invoice_data.get('invoice_number', '')),
    ]
    summary = dict(
        total    = len(results),
        match    = sum(1 for r in results if r['status'] == 'match'),
        fuzzy    = sum(1 for r in results if r['status'] == 'fuzzy'),
        mismatch = sum(1 for r in results if r['status'] in ('mismatch','unknown')),
        missing  = sum(1 for r in results if r['status'] == 'missing'),
    )
    return dict(company_found=True, company=company,
                results=results, summary=summary)
