\
\
\
\
\
\
\
\
\
\
\
\
\
   

from __future__ import annotations

from typing import Any

                 
W = 1600
H = 2200

                                                                             
         
                                                                             

def _el(
    text: str,
    x: int,
    y: int,
    font_size: int = 30,
    is_label: bool = False,
    block_id: int = 0,
    bold: bool = False,
    fill: tuple[int, int, int] | None = None,
) -> dict:
    return {
        "kind": "text",
        "text": str(text),
        "x": x,
        "y": y,
        "font_size": font_size,
        "is_label": is_label,
        "block_id": block_id,
        "bold": bold,
        "fill": fill,
    }


def _lv_row(
    label: str,
    value: str,
    x_label: int,
    x_value: int,
    y: int,
    font_size: int = 30,
    block_id: int = 0,
) -> list[dict]:
                                                                
    return [
        _el(label, x_label, y, font_size, is_label=True, block_id=block_id),
        _el(value, x_value, y, font_size, is_label=False, block_id=block_id),
    ]


def _header_bar(text: str, y: int, font_size: int = 52, block_id: int = 0) -> dict:
    return _el(text, W // 2, y, font_size, is_label=False, block_id=block_id, bold=True)


def _hline_marker(y: int, block_id: int = 0) -> dict:
    return {
        "kind": "line",
        "x1": 60,
        "y1": y + 1,
        "x2": W - 60,
        "y2": y + 1,
        "width": 2,
        "fill": (80, 80, 80),
        "block_id": block_id,
    }


def _vline_marker(x: int, y1: int, y2: int, block_id: int = 0, width: int = 2) -> dict:
    return {
        "kind": "line",
        "x1": x,
        "y1": y1,
        "x2": x,
        "y2": y2,
        "width": width,
        "fill": (96, 108, 128),
        "block_id": block_id,
    }


def _rect(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    block_id: int = 0,
    outline: tuple[int, int, int] | None = (96, 108, 128),
    fill: tuple[int, int, int] | None = None,
    width: int = 2,
) -> dict:
    return {
        "kind": "rect",
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "outline": outline,
        "fill": fill,
        "width": width,
        "block_id": block_id,
    }


                                                              
                                
                                                              

def gid_passport_grid(fields: dict[str, Any]) -> list[dict]:
                                         
    els: list[dict] = []
    bid = 0

            
    els.append(_el("PASSPORT", W // 2, 80, 58, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["issuing_country"].upper(), W // 2, 150, 34,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(195, bid))
    bid += 1

                                                     
    photo_x, photo_y = 80, 220
    els.append(_el("[PHOTO]", photo_x + 30, photo_y + 80, 26,
                   is_label=True, block_id=bid))
    bid += 1

                                                     
    rx = 480
    els.append(_el("Surname and Given Names", rx, 230, 26, is_label=True, block_id=bid))
    els.append(_el(fields["full_name"], rx, 265, 34, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("Nationality", rx, 330, 26, is_label=True, block_id=bid))
    els.append(_el(fields["issuing_country"], rx, 365, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Sex", rx, 420, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_sex", "M"), rx, 455, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Place of Birth", rx + 200, 420, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_place_of_birth", ""), rx + 200, 455, 30,
                   is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(505, bid))
    bid += 1

                              
    col1_x, col2_x = 80, 840
    row_y = [540, 680, 820]
    label_offset_y = 0
    val_offset_y = 36

    pairs = [
        ("Date of Birth", fields["date_of_birth"]),
        ("Document No.", fields["document_number"]),
        ("Issue Date", fields["issue_date"]),
        ("Expiry Date", fields["expiry_date"]),
        ("Issuing Country", fields["issuing_country"]),
        ("Height", fields.get("_height", "")),
    ]

    for i, (lbl, val) in enumerate(pairs):
        col_x = col1_x if i % 2 == 0 else col2_x
        ry = row_y[i // 2]
        els.append(_el(lbl, col_x, ry + label_offset_y, 26, is_label=True, block_id=bid))
        els.append(_el(val, col_x, ry + val_offset_y, 32, is_label=False, block_id=bid))
        bid += 1

    els.append(_hline_marker(960, bid))
    bid += 1

                               
    els.append(_el("P<" + fields["issuing_country"][:3].upper() + fields["full_name"].upper().replace(" ", "<"),
                   80, 1000, 22, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields["document_number"] + "<<<<<" + fields["date_of_birth"].replace("-", ""),
                   80, 1035, 22, is_label=False, block_id=bid))
    bid += 1

    return els


def gid_idcard_compact(fields: dict[str, Any]) -> list[dict]:
    els: list[dict] = []
    bid = 0

    els.append(_rect(70, 45, W - 70, 170, block_id=bid, fill=(34, 84, 140), outline=None))
    els.append(_el("IDENTITY CARD", W // 2, 70, 50, is_label=False, block_id=bid, bold=True, fill=(255, 255, 255)))
    bid += 1
    els.append(_el("OFFICIAL DOCUMENT — NOT FOR COMMERCIAL USE",
                   W // 2, 135, 22, is_label=True, block_id=bid, fill=(235, 241, 248)))
    bid += 1
    els.append(_hline_marker(170, bid))
    bid += 1

    els.append(_rect(80, 205, 300, 595, block_id=bid, outline=(120, 132, 148), fill=(242, 246, 250)))
    els.append(_el("[PHOTO]", 140, 360, 34, is_label=True, block_id=bid))
    bid += 1
    els.append(_rect(340, 205, W - 80, 760, block_id=bid, outline=(120, 132, 148), fill=(250, 252, 255)))
    bid += 1

    lx, vx = 380, 760
    y = 240
    step = 80

    rows = [
        ("ID Number", fields["document_number"]),
        ("Full Name", fields["full_name"]),
        ("Date of Birth", fields["date_of_birth"]),
        ("Issue Date", fields["issue_date"]),
        ("Expiry Date", fields["expiry_date"]),
        ("Issuing Country", fields["issuing_country"]),
        ("Nationality", fields["issuing_country"]),
        ("Sex", fields.get("_sex", "M")),
    ]

    for lbl, val in rows:
        els.extend(_lv_row(lbl + ":", val, lx, vx, y, font_size=30, block_id=bid))
        y += step
        bid += 1

    els.append(_hline_marker(y + 10, bid))
    bid += 1

    els.append(_el("Signature", 1040, 720, 24, is_label=True, block_id=bid))
    els.append(_rect(1150, 728, 1460, 732, block_id=bid, outline=(80, 80, 80), fill=(80, 80, 80), width=1))
    bid += 1
    els.append(_el("This card remains the property of the issuing authority.",
                   W // 2, y + 40, 22, is_label=True, block_id=bid))
    bid += 1

    return els


def gid_form_official(fields: dict[str, Any]) -> list[dict]:
                                                                    
    els: list[dict] = []
    bid = 0

                
    els.append(_el("GOVERNMENT IDENTITY DOCUMENT", W // 2, 70, 46,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("Form GID-2025 | Official Use Only",
                   W // 2, 130, 24, is_label=True, block_id=bid))
    bid += 1
    els.append(_hline_marker(165, bid))
    bid += 1

                                     
    els.append(_el("SECTION 1 — PERSONAL INFORMATION",
                   80, 195, 28, is_label=True, block_id=bid, bold=True))
    bid += 1

    lx, vx = 80, 460
    y = 250
    step = 90

    personal_rows = [
        ("Holder Name", fields["full_name"]),
        ("Date of Birth", fields["date_of_birth"]),
        ("Place of Birth", fields.get("_place_of_birth", "")),
        ("Height", fields.get("_height", "")),
    ]

    for lbl, val in personal_rows:
        els.extend(_lv_row(lbl, val, lx, vx, y, font_size=30, block_id=bid))
        y += step
        bid += 1

    els.append(_hline_marker(y + 5, bid))
    bid += 1

                                     
    y += 40
    els.append(_el("SECTION 2 — DOCUMENT DETAILS",
                   80, y, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    y += 55

    doc_rows = [
        ("Doc No.", fields["document_number"]),
        ("Issuing Country", fields["issuing_country"]),
        ("Date of Issue", fields["issue_date"]),
        ("Date of Expiry", fields["expiry_date"]),
    ]

    for lbl, val in doc_rows:
        els.extend(_lv_row(lbl, val, lx, vx, y, font_size=30, block_id=bid))
        y += step
        bid += 1

    els.append(_hline_marker(y + 5, bid))
    bid += 1

                     
    y += 40
    els.append(_el("Authorized Signature:", lx, y, 28, is_label=True, block_id=bid))
    els.append(_el("_" * 40, vx, y, 28, is_label=False, block_id=bid))
    bid += 1
    y += 60
    els.append(_el("Issuing Officer:", lx, y, 28, is_label=True, block_id=bid))
    bid += 1

    return els


def gid_card_horizontal(fields: dict[str, Any]) -> list[dict]:
                                                                        
    els: list[dict] = []
    bid = 0

                         
    els.append(_el("REPUBLIC OF " + fields["issuing_country"].upper(),
                   W // 2, 60, 36, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("NATIONAL IDENTITY CARD",
                   W // 2, 110, 48, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(165, bid))
    bid += 1

                            
    els.append(_el("[PHOTO]", 100, 270, 26, is_label=True, block_id=bid))
    bid += 1

                                
    cx = 430
    els.append(_el("Name", cx, 200, 26, is_label=True, block_id=bid))
    els.append(_el(fields["full_name"], cx, 238, 36, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("Birth Date", cx, 300, 26, is_label=True, block_id=bid))
    els.append(_el(fields["date_of_birth"], cx, 336, 32, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Sex", cx, 395, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_sex", "M"), cx, 430, 30, is_label=False, block_id=bid))
    bid += 1

                                   
    rx = 950
    els.append(_el("Passport No.", rx, 200, 26, is_label=True, block_id=bid))
    els.append(_el(fields["document_number"], rx, 238, 34, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("Issued On", rx, 300, 26, is_label=True, block_id=bid))
    els.append(_el(fields["issue_date"], rx, 336, 32, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Valid Until", rx, 395, 26, is_label=True, block_id=bid))
    els.append(_el(fields["expiry_date"], rx, 430, 32, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Country of Issue", rx, 490, 26, is_label=True, block_id=bid))
    els.append(_el(fields["issuing_country"], rx, 526, 30, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(580, bid))
    bid += 1

                            
    els.append(_el("Electronic Chip Embedded — ISO 14443 Compliant",
                   W // 2, 615, 22, is_label=True, block_id=bid))
    bid += 1
    els.append(_el("This document is the property of the issuing government.",
                   W // 2, 650, 22, is_label=True, block_id=bid))
    bid += 1

    return els


                                                              
                                   
                                                              

def poa_utility_bill(fields: dict[str, Any]) -> list[dict]:
                              
    els: list[dict] = []
    bid = 0

                     
    els.append(_el(fields["issuer_name"], W // 2, 70, 52,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("UTILITY BILL", W // 2, 135, 36, is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(180, bid))
    bid += 1

                                              
    px = 1100
    els.append(_el(fields.get("_provider_address", ""), px, 200, 24,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields.get("_provider_city_state", ""), px, 232, 24,
                   is_label=False, block_id=bid))
    bid += 1

                                             
    lx, vx = 80, 380
    els.append(_el("Statement Date", lx, 200, 26, is_label=True, block_id=bid))
    els.append(_el(fields["statement_date"], vx, 200, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Due Date", lx, 235, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_due_date", ""), vx, 235, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Account Number", lx, 270, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_account_number", ""), vx, 270, 26, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(315, bid))
    bid += 1

                            
    els.append(_el("Bill To", 80, 345, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["full_name"], 80, 385, 32, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["address_line1"], 80, 425, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(f"{fields['city']}, {fields['postal_code']}", 80, 463, 30,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields["country"], 80, 501, 30, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(545, bid))
    bid += 1

                          
    els.append(_el("DESCRIPTION", 80, 575, 26, is_label=True, block_id=bid, bold=True))
    els.append(_el("AMOUNT", 1300, 575, 26, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(610, bid))
    bid += 1

                                
    rows = [
        ("Previous Balance", fields.get("_prev_balance", "0.00")),
        ("Current Charges", fields.get("_amount_due", "0.00")),
        ("Service Fee", "2.50"),
        ("Taxes & Levies", "1.80"),
    ]
    y = 640
    for desc, amt in rows:
        els.append(_el(desc, 80, y, 28, is_label=False, block_id=bid))
        els.append(_el(amt, 1300, y, 28, is_label=False, block_id=bid))
        bid += 1
        y += 50

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("TOTAL DUE", 80, y + 30, 32, is_label=True, block_id=bid, bold=True))
    els.append(_el(fields.get("_amount_due", "0.00"), 1300, y + 30, 32,
                   is_label=False, block_id=bid, bold=True))
    bid += 1

    return els


def poa_telecom_invoice(fields: dict[str, Any]) -> list[dict]:
    els: list[dict] = []
    bid = 0

    els.append(_rect(70, 45, W - 70, 175, block_id=bid, fill=(28, 102, 161), outline=None))
    els.append(_el(fields["issuer_name"], W // 2, 70, 52,
                   is_label=False, block_id=bid, bold=True, fill=(255, 255, 255)))
    bid += 1
    els.append(_el("INVOICE", W // 2, 135, 42, is_label=False, block_id=bid, bold=True, fill=(231, 241, 250)))
    bid += 1
    els.append(_hline_marker(185, bid))
    bid += 1

                            
    lx, rx = 80, 900
    els.append(_el("Bill Date", lx, 215, 26, is_label=True, block_id=bid))
    els.append(_el(fields["statement_date"], lx + 240, 215, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Due Date", lx, 250, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_due_date", ""), lx + 240, 250, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Account No.", rx, 215, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_account_number", ""), rx + 240, 215, 26, is_label=False, block_id=bid))
    bid += 1

                                   
    els.append(_el(fields.get("_provider_address", ""), rx, 250, 24, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields.get("_provider_city_state", ""), rx, 278, 24, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(310, bid))
    bid += 1

                    
    els.append(_el("Customer Name", 80, 340, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["full_name"], 80, 378, 32, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["address_line1"], 80, 418, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(f"{fields['city']}, {fields['postal_code']}", 80, 456, 30,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields["country"], 80, 494, 30, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(535, bid))
    bid += 1

                    
    els.append(_el("Service Period:", 80, 565, 26, is_label=True, block_id=bid))
    els.append(_el("01 Jan 2025 — 31 Jan 2025", 360, 565, 26, is_label=False, block_id=bid))
    bid += 1

             
    els.append(_el("CHARGES SUMMARY", 80, 615, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(645, bid))
    bid += 1

    charges = [
        ("Monthly Plan", "29.99"),
        ("Data Add-on", "9.99"),
        ("Roaming Charges", "5.50"),
        ("Taxes", fields.get("_tax", "4.52")),
    ]
    y = 670
    for desc, amt in charges:
        els.append(_el(desc, 80, y, 28, is_label=False, block_id=bid))
        els.append(_el(amt, 1300, y, 28, is_label=False, block_id=bid))
        bid += 1
        y += 50

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("Amount Due", 80, y + 30, 32, is_label=True, block_id=bid, bold=True))
    els.append(_el(fields.get("_amount_due", "0.00"), 1300, y + 30, 32,
                   is_label=False, block_id=bid, bold=True))
    bid += 1

    return els


def poa_bank_statement(fields: dict[str, Any]) -> list[dict]:
                                
    els: list[dict] = []
    bid = 0

                 
    els.append(_el(fields["issuer_name"], W // 2, 70, 52,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("BANK STATEMENT", W // 2, 135, 38, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("For Personal Account Use Only",
                   W // 2, 180, 22, is_label=True, block_id=bid))
    bid += 1
    els.append(_hline_marker(210, bid))
    bid += 1

                    
    lx, vx = 80, 380
    els.append(_el("Issued On", lx, 240, 26, is_label=True, block_id=bid))
    els.append(_el(fields["statement_date"], vx, 240, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Account Number", lx, 275, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_account_number", ""), vx, 275, 26, is_label=False, block_id=bid))
    bid += 1

                               
    bx = 900
    els.append(_el(fields.get("_provider_address", ""), bx, 240, 24, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields.get("_provider_city_state", ""), bx, 268, 24, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(315, bid))
    bid += 1

                                  
    els.append(_el("Account Holder", 80, 345, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["full_name"], 80, 383, 32, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["address_line1"], 80, 423, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(f"{fields['city']}, {fields['postal_code']}", 80, 461, 30,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields["country"], 80, 499, 30, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(540, bid))
    bid += 1

             
    els.append(_el("ACCOUNT SUMMARY", 80, 570, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(600, bid))
    bid += 1

    rows = [
        ("Opening Balance", fields.get("_prev_balance", "0.00")),
        ("Total Credits", "0.00"),
        ("Total Debits", "0.00"),
        ("Closing Balance", fields.get("_amount_due", "0.00")),
    ]
    y = 625
    for lbl, val in rows:
        els.append(_el(lbl, 80, y, 28, is_label=True, block_id=bid))
        els.append(_el(val, 1300, y, 28, is_label=False, block_id=bid))
        bid += 1
        y += 52

    return els


def poa_insurance_notice(fields: dict[str, Any]) -> list[dict]:
    els: list[dict] = []
    bid = 0

    els.append(_rect(90, 55, W - 90, 175, block_id=bid, outline=(104, 112, 124), fill=(241, 244, 248)))
    els.append(_el(fields["issuer_name"], W // 2, 70, 50,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("POLICY STATEMENT NOTICE", W // 2, 132, 36,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(178, bid))
    bid += 1

                     
    lx, vx = 80, 380
    els.append(_el("Statement Date", lx, 210, 26, is_label=True, block_id=bid))
    els.append(_el(fields["statement_date"], vx, 210, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Due Date", lx, 245, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_due_date", ""), vx, 245, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Account Number", lx, 280, 26, is_label=True, block_id=bid))
    els.append(_el(fields.get("_account_number", ""), vx, 280, 26, is_label=False, block_id=bid))
    bid += 1

                      
    px = 900
    els.append(_el(fields.get("_provider_address", ""), px, 210, 24, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields.get("_provider_city_state", ""), px, 238, 24, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(320, bid))
    bid += 1

                           
    els.append(_el("Mailing Address", 80, 350, 28, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["full_name"], 80, 388, 32, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["address_line1"], 80, 428, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_el(f"{fields['city']}, {fields['postal_code']}", 80, 466, 30,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el(fields["country"], 80, 504, 30, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(548, bid))
    bid += 1

                    
    els.append(_el("POLICY DETAILS", 80, 578, 28, is_label=True, block_id=bid, bold=True))
    bid += 1

    policy_rows = [
        ("Policy Number", fields.get("_account_number", "")),
        ("Policy Type", "Comprehensive Home"),
        ("Coverage Period", f"{fields['statement_date']} to {fields.get('_due_date', '')}"),
        ("Premium Due", fields.get("_amount_due", "0.00")),
    ]
    y = 625
    for lbl, val in policy_rows:
        els.extend(_lv_row(lbl, val, 80, 380, y, font_size=28, block_id=bid))
        bid += 1
        y += 55

    return els


                                                              
                                  
                                                              

def pay_bank_transfer(fields: dict[str, Any]) -> list[dict]:
                                             
    els: list[dict] = []
    bid = 0

    els.append(_el("BANK TRANSFER CONFIRMATION", W // 2, 70, 46,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(f"Reference: {fields['reference_id']}", W // 2, 128, 30,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(170, bid))
    bid += 1

    lx, vx = 80, 480
    y = 210
    step = 80

    rows = [
        ("From", fields["sender_name"]),
        ("To", fields["recipient_name"]),
        ("Payment Date", fields["payment_date"]),
        ("Amount", f"{fields['currency']} {fields['amount']}"),
        ("Currency", fields["currency"]),
        ("Transaction ID", fields["reference_id"]),
        ("Subtotal", fields.get("_subtotal", "0.00")),
        ("Fee", fields.get("_fee", "0.00")),
        ("Tax", fields.get("_tax", "0.00")),
        ("Invoice ID", fields.get("_invoice_id", "")),
        ("Auth Code", fields.get("_auth_code", "")),
    ]

    for lbl, val in rows:
        is_lbl = True
        els.extend(_lv_row(lbl, val, lx, vx, y, font_size=30, block_id=bid))
        bid += 1
        y += step

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("Transfer completed successfully.", W // 2, y + 40, 28,
                   is_label=True, block_id=bid))
    bid += 1

    return els


def pay_wallet_receipt(fields: dict[str, Any]) -> list[dict]:
                                        
    els: list[dict] = []
    bid = 0

    els.append(_el("PAYMENT RECEIPT", W // 2, 60, 50,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["recipient_name"], W // 2, 120, 38,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(168, bid))
    bid += 1

                          
    currency_sym = {"USD": "$", "EUR": "€", "GBP": "£"}.get(fields["currency"], "")
    els.append(_el(f"{currency_sym}{fields['amount']}", W // 2, 200, 72,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields["currency"], W // 2, 285, 30, is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(325, bid))
    bid += 1

                   
    lx, vx = 80, 480
    y = 360

    rows = [
        ("Payer", fields["sender_name"]),
        ("Merchant", fields["recipient_name"]),
        ("Processed On", fields["payment_date"]),
        ("Payment Ref", fields["reference_id"]),
        ("Subtotal", fields.get("_subtotal", "0.00")),
        ("Service Fee", fields.get("_fee", "0.00")),
        ("Total Paid", f"{fields['currency']} {fields['amount']}"),
        ("Auth Code", fields.get("_auth_code", "")),
    ]

    for lbl, val in rows:
        els.extend(_lv_row(lbl, val, lx, vx, y, font_size=30, block_id=bid))
        bid += 1
        y += 75

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("Thank you for your payment.", W // 2, y + 35, 26,
                   is_label=True, block_id=bid))
    bid += 1

    return els


def pay_paid_invoice(fields: dict[str, Any]) -> list[dict]:
    els: list[dict] = []
    bid = 0

    els.append(_rect(70, 50, W - 70, 178, block_id=bid, outline=(104, 112, 124), fill=(246, 246, 246)))
    els.append(_el("INVOICE", W // 2, 70, 60, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el(fields.get("_invoice_id", "INV-000000"), W // 2, 140, 32,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(182, bid))
    bid += 1

                               
    lx, rx = 80, 900
    els.append(_el("Paid By", lx, 215, 26, is_label=True, block_id=bid))
    els.append(_el(fields["sender_name"], lx, 250, 32, is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("Payee", rx, 215, 26, is_label=True, block_id=bid))
    els.append(_el(fields["recipient_name"], rx, 250, 32, is_label=False, block_id=bid, bold=True))
    bid += 1

    els.append(_hline_marker(300, bid))
    bid += 1

                  
    lx2, vx2 = 80, 380
    y = 335
    meta_rows = [
        ("Payment Date", fields["payment_date"]),
        ("Reference", fields["reference_id"]),
        ("Auth Code", fields.get("_auth_code", "")),
        ("Currency", fields["currency"]),
    ]
    for lbl, val in meta_rows:
        els.extend(_lv_row(lbl, val, lx2, vx2, y, font_size=28, block_id=bid))
        bid += 1
        y += 60

    els.append(_hline_marker(y + 5, bid))
    bid += 1

                
    y += 40
    els.append(_el("ITEM", 80, y, 26, is_label=True, block_id=bid, bold=True))
    els.append(_el("AMOUNT", 1300, y, 26, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(y + 30, bid))
    bid += 1
    y += 55

    line_items = [
        ("Goods/Services", fields.get("_subtotal", "0.00")),
        ("Shipping Fee", fields.get("_fee", "0.00")),
        ("Tax", fields.get("_tax", "0.00")),
    ]
    for item, amt in line_items:
        els.append(_el(item, 80, y, 28, is_label=False, block_id=bid))
        els.append(_el(amt, 1300, y, 28, is_label=False, block_id=bid))
        bid += 1
        y += 52

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("TOTAL PAID", 80, y + 30, 34, is_label=True, block_id=bid, bold=True))
    els.append(_el(f"{fields['currency']} {fields['amount']}", 1300, y + 30, 34,
                   is_label=False, block_id=bid, bold=True))
    bid += 1

    els.append(_rect(1030, 208, 1450, 330, block_id=bid, outline=(188, 52, 44), width=5))
    els.append(_el("PAID", 1240, 228, 58, is_label=False, block_id=bid, bold=True, fill=(188, 52, 44)))
    els.append(_el(f"Date {fields['payment_date']}", 1240, 288, 24, is_label=False, block_id=bid, fill=(188, 52, 44)))
    bid += 1

    return els


def pay_checkout_receipt(fields: dict[str, Any]) -> list[dict]:
                                         
    els: list[dict] = []
    bid = 0

                            
    els.append(_el(fields["recipient_name"], W // 2, 70, 48,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("PAYMENT RECEIPT", W // 2, 128, 36, is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(172, bid))
    bid += 1

            
    els.append(_el("Sender", 80, 205, 26, is_label=True, block_id=bid))
    els.append(_el(fields["sender_name"], 80, 240, 30, is_label=False, block_id=bid))
    bid += 1

                
    els.append(_el("Date", 80, 290, 26, is_label=True, block_id=bid))
    els.append(_el(fields["payment_date"], 300, 290, 26, is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Ref ID", 80, 325, 26, is_label=True, block_id=bid))
    els.append(_el(fields["reference_id"], 300, 325, 26, is_label=False, block_id=bid))
    bid += 1

    els.append(_hline_marker(365, bid))
    bid += 1

           
    els.append(_el("ITEM", 80, 395, 26, is_label=True, block_id=bid, bold=True))
    els.append(_el("QTY", 900, 395, 26, is_label=True, block_id=bid, bold=True))
    els.append(_el("PRICE", 1200, 395, 26, is_label=True, block_id=bid, bold=True))
    bid += 1
    els.append(_hline_marker(425, bid))
    bid += 1

    items = [
        ("Item A", "1", fields.get("_subtotal", "0.00")),
        ("Service Charge", "1", fields.get("_fee", "0.00")),
    ]
    y = 455
    for name, qty, price in items:
        els.append(_el(name, 80, y, 28, is_label=False, block_id=bid))
        els.append(_el(qty, 900, y, 28, is_label=False, block_id=bid))
        els.append(_el(price, 1200, y, 28, is_label=False, block_id=bid))
        bid += 1
        y += 52

    els.append(_hline_marker(y + 5, bid))
    bid += 1
    els.append(_el("Subtotal", 80, y + 30, 28, is_label=True, block_id=bid))
    els.append(_el(fields.get("_subtotal", "0.00"), 1200, y + 30, 28,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_el("Tax", 80, y + 68, 28, is_label=True, block_id=bid))
    els.append(_el(fields.get("_tax", "0.00"), 1200, y + 68, 28,
                   is_label=False, block_id=bid))
    bid += 1
    els.append(_hline_marker(y + 105, bid))
    bid += 1
    els.append(_el("Total", 80, y + 130, 34, is_label=True, block_id=bid, bold=True))
    els.append(_el(f"{fields['currency']} {fields['amount']}", 1200, y + 130, 34,
                   is_label=False, block_id=bid, bold=True))
    bid += 1
    els.append(_el("Payment Amount", 80, y + 185, 28, is_label=True, block_id=bid))
    els.append(_el(fields["amount"], 1200, y + 185, 28, is_label=False, block_id=bid))
    bid += 1

    return els


                                                              
                          
                                                              
PUBLIC_TEMPLATES: dict[str, callable] = {
                   
    "gid_passport_grid": gid_passport_grid,
    "gid_idcard_compact": gid_idcard_compact,
    "gid_form_official": gid_form_official,
    "gid_card_horizontal": gid_card_horizontal,
                      
    "poa_utility_bill": poa_utility_bill,
    "poa_telecom_invoice": poa_telecom_invoice,
    "poa_bank_statement": poa_bank_statement,
    "poa_insurance_notice": poa_insurance_notice,
                     
    "pay_bank_transfer": pay_bank_transfer,
    "pay_wallet_receipt": pay_wallet_receipt,
    "pay_paid_invoice": pay_paid_invoice,
    "pay_checkout_receipt": pay_checkout_receipt,
}

                                                
PUBLIC_TEMPLATE_NAMES: dict[str, list[str]] = {
    "government_id": [
        "gid_passport_grid",
        "gid_idcard_compact",
        "gid_form_official",
        "gid_card_horizontal",
    ],
    "proof_of_address": [
        "poa_utility_bill",
        "poa_telecom_invoice",
        "poa_bank_statement",
        "poa_insurance_notice",
    ],
    "payment_receipt": [
        "pay_bank_transfer",
        "pay_wallet_receipt",
        "pay_paid_invoice",
        "pay_checkout_receipt",
    ],
}
