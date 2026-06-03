"""
database.py
===========
Master database of verified company records.
This is the SINGLE SOURCE OF TRUTH.
When validating any invoice, all fields are checked against this data.

How to add a new company:
  Add a new dict entry inside COMPANIES with a unique key.
  Fill in gst_no, legal_name, trade_names, address, pincode, state, city.
"""

# ─────────────────────────────────────────────────────────────
#  MASTER COMPANY DATABASE
#  Source: Official GST Registration Certificates
# ─────────────────────────────────────────────────────────────

COMPANIES = {

    "06AAJCT0674P1ZR": {
        # ── Identity ──────────────────────────────────────────
        "gst_no":      "06AAJCT0674P1ZR",

        # Legal name exactly as on GST certificate
        "legal_name":  "TRIGYA INNOVATIONS INDIA PRIVATE LIMITED",

        # All acceptable short forms / trade names for this company
        "trade_names": [
            "TRIGYA INNOVATIONS INDIA PRIVATE LIMITED",
            "TRIGYA INNOVATIONS INDIA PVT LTD",
            "TRIGYA INNOVATIONS",
            "TRIGYA INNOVATIONS PVT LTD",
            "TRIGYA INNOVATIONS INDIA",
            "Trigya Innovations India Pvt Ltd",
            "Trigya Innovations",
        ],

        # ── Registered address (from certificate field 4) ─────
        "address_line": "44/3, OLD ROHTAK ROAD, OPP. POST OFFICE, KHARKHODA",
        "city":         "Sonipat",
        "state":        "Haryana",
        "pincode":      "131402",

        # Full address string (used for fuzzy matching)
        "full_address": "44/3, OLD ROHTAK ROAD, OPP. POST OFFICE, KHARKHODA, Sonipat, Haryana, 131402",

        # ── Known invoice addresses (branch / billing address) ─
        # Sometimes invoices show a different operational address
        "known_addresses": [
            "44/3, OLD ROHTAK ROAD, OPP. POST OFFICE, KHARKHODA, Sonipat, Haryana, 131402",
            "Gurgaon, Haryana, 122016",
            "Gurgaon Haryana 122016",
        ],

        # ── Meta ──────────────────────────────────────────────
        "constitution":   "Private Limited Company",
        "registered_on":  "14/01/2022",
        "active":         True,
    },

    # ── Add more companies below ──────────────────────────────
    # "GSTIN_HERE": {
    #     "gst_no":      "...",
    #     "legal_name":  "...",
    #     "trade_names": [...],
    #     "address_line": "...",
    #     "city":        "...",
    #     "state":       "...",
    #     "pincode":     "...",
    #     "full_address": "...",
    #     "known_addresses": [...],
    #     "constitution": "...",
    #     "registered_on": "...",
    #     "active": True,
    # },
}


def get_company(gst_no: str) -> dict | None:
    """Lookup a company by GST number. Returns None if not found."""
    if not gst_no:
        return None
    return COMPANIES.get(gst_no.strip().upper())


def get_all_gst_numbers() -> list:
    """Return all GST numbers in the database."""
    return list(COMPANIES.keys())


def company_exists(gst_no: str) -> bool:
    return gst_no.strip().upper() in COMPANIES
