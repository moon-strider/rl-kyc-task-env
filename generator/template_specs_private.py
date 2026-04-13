"""Private template layout functions (hidden templates).

Same element dict contract as template_specs_public.py.
These templates are used only for the hidden evaluation split.
"""

from __future__ import annotations

from typing import Any

from generator.template_specs_public import W, H, _el, _lv_row, _hline_marker

# ============================================================
# GOVERNMENT-ID PRIVATE TEMPLATES
# ============================================================

def gid_dense_smallcaps(fields: dict[str, Any]) -> list[dict]:
    """Dense small-caps style with tight line spacing."""
    els: list[dict] = []
    bid = 0

    # Header
    els.append(_el("TRAVEL DOCUMENT — GOVERNMENT ISSUE", W // 2, 60, 34,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["issuing_country"].upper(), W // 2, 102, 44,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(148, bid))
    bid += 1

    # Dense grid of label+value pairs, tightly packed
    lx, vx = 80, 420
    y = 178
    step = 62

    rows = [
        ("SURNAME AND GIVEN NAMES", fields["full_name"]),
        ("NATIONALITY", fields["issuing_country"]),
        ("DATE OF BIRTH", fields["date_of_birth"]),
        ("PERSONAL NO.", fields["document_number"]),
        ("SEX", fields.get("_sex", "M")),
        ("PLACE OF BIRTH", fields.get("_place_of_birth", "")),
        ("DATE OF ISSUE", fields["issue_date"]),
        ("DATE OF EXPIRY", fields["expiry_date"]),
        ("ISSUING COUNTRY", fields["issuing_country"]),
        ("HEIGHT", fields.get("_height", "")),
    ]

    for lbl, val in rows:
        els.append(_el(lbl, lx, y, 22, is_label=True, block_id=bid))
        els.append(_el(val, vx, y, 26, is_label=False, block_id=bid))
        bid += 1
        y += step

    els.append(_hline_marker(y + 5, bid))
    bid += 1

    # MRZ section
    y += 40
    els.append(_el("MACHINE READABLE ZONE", W // 2, y, 22, is_label=True, block_id=bid))
    bid += 1
    y += 36
    mrz1 = ("P<" + fields["issuing_country"][:3].upper() +
            fields["full_name"].upper().replace(" ", "<") + "<" * 10)[:44]
    mrz2 = (fields["document_number"] + "<" * 9 +
            fields["date_of_birth"].replace("-", "") + "<" * 10)[:44]
    els.append(_el(mrz1, 80, y, 22, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(mrz2, 80, y + 32, 22, is_label=False, block_id=bid))
    bid += 1

    return els


def gid_minimal_two_column(fields: dict[str, Any]) -> list[dict]:
    """Minimal two-column layout with a strong center divider."""
    els: list[dict] = []
    bid = 0

    # Minimal header
    els.append(_el("IDENTIFICATION DOCUMENT", W // 2, 80, 44,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(130, bid))
    bid += 1

    # Left column (personal)
    lc_x, lc_vx = 60, 320
    y = 170
    step = 90

    left_rows = [
        ("Name", fields["full_name"]),
        ("Date of Birth", fields["date_of_birth"]),
        ("Nationality", fields["issuing_country"]),
        ("Sex", fields.get("_sex", "M")),
    ]
    for lbl, val in left_rows:
        els.append(_el(lbl, lc_x, y, 26, is_label=True, block_id=bid))
        els.append(_el(val, lc_vx, y, 30, is_label=False, block_id=bid))
        bid += 1
        y += step

    # Right column (document)
    rc_x, rc_vx = 840, 1100
    y = 170

    right_rows = [
        ("Doc No.", fields["document_number"]),
        ("Issue Date", fields["issue_date"]),
        ("Expiry Date", fields["expiry_date"]),
        ("Issuing Country", fields["issuing_country"]),
    ]
    for lbl, val in right_rows:
        els.append(_el(lbl, rc_x, y, 26, is_label=True, block_id=bid))
        els.append(_el(val, rc_vx, y, 30, is_label=False, block_id=bid))
        bid += 1
        y += step

    # Center divider (vertical line represented as a narrow element)
    els.append(_hline_marker(560, bid))
    bid += 1

    # Footer
    els.append(_el("Place of Birth:", 60, 600, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_place_of_birth", ""), 300, 600, 28,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el("This document is valid only with the holder's signature.",
                   W // 2, 660, 22, is_label=True, block_id=bid))
    bid += 1

    return els


# ============================================================
# PROOF-OF-ADDRESS PRIVATE TEMPLATES
# ============================================================

def poa_energy_statement_center(fields: dict[str, Any]) -> list[dict]:
    """Energy statement with centered customer block."""
    els: list[dict] = []
    bid = 0

    # Header
    els.append(_el(fields["issuer_name"], W // 2, 70, 52,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("ENERGY STATEMENT", W // 2, 132, 36, is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(178, bid))
    bid += 1

    # Metadata row
    cx = W // 2 - 300
    els.append(_el("Bill Date", cx, 210, 26, is_label=True, block_id=bid))
    els.append(_el(fields["statement_date"], cx + 200, 210, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Account No.", cx + 500, 210, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_account_number", ""), cx + 700, 210, 26,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Due Date", cx, 248, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_due_date", ""), cx + 200, 248, 26, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(290, bid))
    bid += 1

    # Centered customer block
    center_x = W // 2 - 200
    els.append(_el("Service Address", center_x, 325, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["full_name"], center_x, 365, 32, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["address_line1"], center_x, 405, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(f"{fields['city']}, {fields['postal_code']}", center_x, 443, 30,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields["country"], center_x, 481, 30, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(525, bid))
    bid += 1

    # Usage table
    els.append(_el("ENERGY USAGE", 80, 558, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(588, bid))
    bid += 1

    rows = [
        ("Electricity (kWh)", "320", fields.get("_prev_balance", "0.00")),
        ("Gas (units)", "45", "18.50"),
        ("Standing Charge", "—", "12.00"),
        ("VAT/Tax", "—", fields.get("_tax", "0.00")),
    ]
    y = 615
    els.append(_el("ITEM", 80, y - 30, 24, is_label=True, block_id=bid, bold=True))
    els.append(_el("USAGE", 700, y - 30, 24, is_label=True, block_id=bid, bold=True))
    els.append(_el("CHARGE", 1200, y - 30, 24, is_label=True, block_id=bid, bold=True))
    bid += 1
    for item, usage, charge in rows:
        els.append(_el(item, 80, y, 28, is_label=False, block_id=bid))
        els.append(_el(usage, 700, y, 28, is_label=False, block_id=bid))
        els.append(_el(charge, 1200, y, 28, is_label=False, block_id=bid))
        bid += 1
        y += 52

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("Total Amount Due", 80, y + 30, 32, is_label=True, block_id=bid, bold=True))
    els.append(_el(fields.get("_amount_due", "0.00"), 1200, y + 30, 32,
                   is_label=False, block_id=bid, bold=True))
    bid += 1

    return els


def poa_water_bill_split(fields: dict[str, Any]) -> list[dict]:
    """Water bill with a split-panel layout (provider left, customer right)."""
    els: list[dict] = []
    bid = 0

    # Header (full width)
    els.append(_el(fields["issuer_name"], W // 2, 70, 52,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("WATER BILL", W // 2, 132, 36, is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(178, bid))
    bid += 1

    # Left panel: provider info
    els.append(_el("Service Provider", 80, 210, 26, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["issuer_name"], 80, 245, 28, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields.get("_provider_address", ""), 80, 282, 24, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields.get("_provider_city_state", ""), 80, 312, 24, is_label=False, block_id=bid))
    bid += 1

    # Right panel: customer address
    els.append(_el("Address", 840, 210, 26, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["full_name"], 840, 245, 32, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["address_line1"], 840, 285, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(f"{fields['city']}, {fields['postal_code']}", 840, 323, 30,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields["country"], 840, 361, 30, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(410, bid))
    bid += 1

    # Bill summary
    lx, vx = 80, 380
    y = 445
    meta_rows = [
        ("Issued On", fields["statement_date"]),
        ("Due Date", fields.get("_due_date", "")),
        ("Account Number", fields.get("_account_number", "")),
        ("Previous Balance", fields.get("_prev_balance", "0.00")),
        ("Current Charges", fields.get("_amount_due", "0.00")),
    ]
    for lbl, val in meta_rows:
        els.extend(_lv_row(lbl, val, lx, vx, y, font_size=28, block_id=bid))
        bid += 1
        y += 58

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("TOTAL PAYABLE", lx, y + 35, 34, is_label=True, block_id=bid, bold=True))
    els.append(_el(fields.get("_amount_due", "0.00"), 1300, y + 35, 34,
                   is_label=False, block_id=bid, bold=True))
    bid += 1

    return els


# ============================================================
# PAYMENT-RECEIPT PRIVATE TEMPLATES
# ============================================================

def pay_merchant_confirmation(fields: dict[str, Any]) -> list[dict]:
    """Merchant payment confirmation with a bold amount focus."""
    els: list[dict] = []
    bid = 0

    els.append(_el(fields["recipient_name"], W // 2, 70, 50,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("PAYMENT CONFIRMATION", W // 2, 130, 38,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(178, bid))
    bid += 1

    # Centered summary
    currency_sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(fields["currency"], "")
    els.append(_el("Amount Received", W // 2, 220, 28, is_label=True, block_id=bid))
    bid += 1
    els.append(_el(f"{currency_sym}{fields['amount']}", W // 2, 265, 68,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["currency"], W // 2, 345, 28, is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(385, bid))
    bid += 1

    # Details
    lx, vx = 80, 500
    y = 420
    rows = [
        ("Sender", fields["sender_name"]),
        ("Recipient", fields["recipient_name"]),
        ("Date", fields["payment_date"]),
        ("Transaction ID", fields["reference_id"]),
        ("Invoice ID", fields.get("_invoice_id", "")),
        ("Auth Code", fields.get("_auth_code", "")),
        ("Subtotal", fields.get("_subtotal", "0.00")),
        ("Fee", fields.get("_fee", "0.00")),
        ("Tax", fields.get("_tax", "0.00")),
        ("Total Paid", f"{fields['currency']} {fields['amount']}"),
    ]

    for lbl, val in rows:
        els.extend(_lv_row(lbl, val, lx, vx, y, font_size=30, block_id=bid))
        bid += 1
        y += 70

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("This confirmation serves as proof of payment.",
                   W // 2, y + 35, 24, is_label=True, block_id=bid))
    bid += 1

    return els


def pay_transaction_slip(fields: dict[str, Any]) -> list[dict]:
    """Transaction slip in a narrow column style."""
    els: list[dict] = []
    bid = 0

    els.append(_el("TRANSACTION SLIP", W // 2, 70, 48,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(118, bid))
    bid += 1

    # Narrow single-column label-value pairs
    lx, vx = 80, 600
    y = 155
    step = 72

    rows = [
        ("Payer", fields["sender_name"]),
        ("Payee", fields["recipient_name"]),
        ("Payment Amount", fields["amount"]),
        ("Currency", fields["currency"]),
        ("Payment Date", fields["payment_date"]),
        ("Ref ID", fields["reference_id"]),
        ("Auth Code", fields.get("_auth_code", "")),
        ("Invoice ID", fields.get("_invoice_id", "")),
        ("Subtotal", fields.get("_subtotal", "0.00")),
        ("Service Fee", fields.get("_fee", "0.00")),
        ("Tax Amount", fields.get("_tax", "0.00")),
    ]

    for lbl, val in rows:
        els.extend(_lv_row(lbl, val, lx, vx, y, font_size=30, block_id=bid))
        bid += 1
        y += step

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("TOTAL", lx, y + 30, 36, is_label=True, block_id=bid, bold=True))
    els.append(_el(f"{fields['currency']} {fields['amount']}", vx, y + 30, 36,
                   is_label=False, block_id=bid, bold=True))
    bid += 1

    return els


# ============================================================
# Private template dispatch
# ============================================================
PRIVATE_TEMPLATES: dict[str, callable] = {
    # government_id
    "gid_dense_smallcaps": gid_dense_smallcaps,
    "gid_minimal_two_column": gid_minimal_two_column,
    # proof_of_address
    "poa_energy_statement_center": poa_energy_statement_center,
    "poa_water_bill_split": poa_water_bill_split,
    # payment_receipt
    "pay_merchant_confirmation": pay_merchant_confirmation,
    "pay_transaction_slip": pay_transaction_slip,
}

PRIVATE_TEMPLATE_NAMES: dict[str, list[str]] = {
    "government_id": [
        "gid_dense_smallcaps",
        "gid_minimal_two_column",
    ],
    "proof_of_address": [
        "poa_energy_statement_center",
        "poa_water_bill_split",
    ],
    "payment_receipt": [
        "pay_merchant_confirmation",
        "pay_transaction_slip",
    ],
}
