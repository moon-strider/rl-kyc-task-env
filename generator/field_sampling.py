"""Deterministic field sampling for all three document schemas.

All sampling functions accept a seeded numpy Generator and a Faker instance
so the caller controls reproducibility.  The Faker instance should already
have its own seed set before this module is called.
"""

from __future__ import annotations

import re
import string
from datetime import date, timedelta
from typing import Any

import numpy as np
from faker import Faker

from generator.utils import rng_choice, rng_randint, rng_uniform

# ---------------------------------------------------------------------------
# Faker locale pool
# ---------------------------------------------------------------------------
_LOCALES = ["en_US", "en_GB", "en_CA"]

# Locale → country name mapping (used for POA)
_LOCALE_COUNTRY = {
    "en_US": "United States",
    "en_GB": "United Kingdom",
    "en_CA": "Canada",
}

# ---------------------------------------------------------------------------
# Shared date helpers
# ---------------------------------------------------------------------------
_EPOCH = date(1970, 1, 1)


def _random_date(rng: np.random.Generator, start: date, end: date) -> date:
    delta = (end - start).days
    offset = int(rng.integers(0, delta + 1))
    return start + timedelta(days=offset)


def _fmt(d: date) -> str:
    return d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Government-ID field sampling
# ---------------------------------------------------------------------------
GID_COUNTRIES = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
    "Singapore",
    "Germany",
]

_DOC_NUM_PATTERNS = ["A7", "A2N6", "N9"]  # shorthand codes


def _gen_doc_number(rng: np.random.Generator) -> str:
    pattern = rng_choice(rng, _DOC_NUM_PATTERNS)
    if pattern == "A7":
        letter = rng_choice(rng, list(string.ascii_uppercase))
        digits = "".join(str(rng_randint(rng, 0, 9)) for _ in range(7))
        return letter + digits
    elif pattern == "A2N6":
        letters = "".join(rng_choice(rng, list(string.ascii_uppercase)) for _ in range(2))
        digits = "".join(str(rng_randint(rng, 0, 9)) for _ in range(6))
        return letters + digits
    else:  # N9
        return "".join(str(rng_randint(rng, 0, 9)) for _ in range(9))


def _clean_name(raw: str) -> str:
    """Strip honorifics/titles and keep only 2-3 word names."""
    parts = raw.split()
    titles = {
        "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sir", "Miss", "Jr.", "Sr.",
        "Mr", "Mrs", "Ms", "Dr", "Prof", "Rev", "Rev.",
        "II", "III", "IV", "Esq.", "Esq",
    }
    parts = [p for p in parts if p not in titles]
    parts = parts[:3]
    if len(parts) < 2:
        parts = ["John", "Doe"]
    return " ".join(parts)


def sample_government_id(rng: np.random.Generator, faker: Faker) -> dict[str, Any]:
    dob_start = date(1960, 1, 1)
    dob_end = date(2005, 12, 31)
    dob = _random_date(rng, dob_start, dob_end)

    # Issue date: DOB + 18 years <= issue_date <= DOB + 60 years
    min_issue = date(dob.year + 18, dob.month, dob.day)
    max_issue = date(min(dob.year + 60, 2026), 12, 31)
    if min_issue > max_issue:
        min_issue = max_issue
    issue = _random_date(rng, min_issue, max_issue)

    # Expiry: +5 or +10 years
    years_offset = rng_choice(rng, [5, 10])
    expiry = date(issue.year + years_offset, issue.month, issue.day)

    doc_num = _gen_doc_number(rng)
    country = rng_choice(rng, GID_COUNTRIES)
    full_name = _clean_name(faker.name())

    # Distractors
    place_of_birth = faker.city()
    sex = rng_choice(rng, ["M", "F"])
    height_cm = rng_randint(rng, 155, 200)

    return {
        # Target fields
        "full_name": full_name,
        "date_of_birth": _fmt(dob),
        "document_number": doc_num,
        "issue_date": _fmt(issue),
        "expiry_date": _fmt(expiry),
        "issuing_country": country,
        # Distractor fields (used by renderer but not in target)
        "_place_of_birth": place_of_birth,
        "_sex": sex,
        "_height": f"{height_cm} cm",
        "_nationality": country,
    }


# ---------------------------------------------------------------------------
# Proof-of-address field sampling
# ---------------------------------------------------------------------------
def _locale_address(rng: np.random.Generator, faker: Faker, locale: str) -> tuple[str, str, str, str]:
    """Return (address_line1, city, postal_code, country) locale-consistently."""
    # Create a locale-specific Faker
    locale_faker = Faker(locale)
    locale_faker.seed_instance(int(rng.integers(0, 2**31)))
    address_line1 = locale_faker.street_address()
    # Ensure no newlines in address_line1 (some locales produce multi-line)
    address_line1 = address_line1.replace("\n", ", ")
    city = locale_faker.city()
    country = _LOCALE_COUNTRY[locale]
    if locale == "en_US":
        postal_code = locale_faker.zipcode()
    elif locale == "en_GB":
        postal_code = locale_faker.postcode()
    else:  # en_CA
        postal_code = locale_faker.postalcode()
    return address_line1, city, postal_code, country


_UTILITY_PROVIDERS = [
    "Pacific Gas & Electric",
    "Southern Water Authority",
    "Ontario Energy Group",
    "National Grid Services",
    "City Power & Light",
    "Metro Water Utilities",
    "Atlantic Energy Co.",
    "Western Electricity Board",
    "Midlands Water Supply",
    "Coastal Power Solutions",
]

_TELECOM_PROVIDERS = [
    "BrightLine Communications",
    "Apex Telecom",
    "NovaTel Services",
    "ClearPath Internet",
    "SkyLink Broadband",
    "PrimeFibre Networks",
    "ConnectPlus",
    "Velocity Telecom",
    "Signal One Ltd.",
    "FiberLink Corp.",
]

_BANK_NAMES = [
    "Meridian Trust Bank",
    "Northstar Savings Bank",
    "Pacific Coast Bank",
    "Atlantic Commerce Bank",
    "Heritage Federal Bank",
    "Pinnacle National Bank",
    "Summit Credit Union",
    "Keystone Banking Group",
    "Riverdale Savings",
    "Cornerstone Bank",
]

_INSURANCE_NAMES = [
    "Apex Insurance Group",
    "Guardian Life Assurance",
    "Pinnacle Insurance Co.",
    "Horizon Mutual",
    "SafeGuard Insurance",
    "Sterling Life Insurance",
    "Landmark Assurance Ltd.",
    "BlueStar Insurance",
    "Fortis Insurance Group",
    "Atlas Mutual Assurance",
]

_ENERGY_PROVIDERS = [
    "GreenPeak Energy",
    "SolarEdge Utilities",
    "ClearEnergy Corp.",
    "NorthStar Power",
    "EcoBright Energy",
]

_WATER_PROVIDERS = [
    "Crystal Clear Water",
    "Blue Ridge Water Co.",
    "Valley Water Services",
    "PureFlow Water Authority",
    "AquaSource Utilities",
]

_PROVIDER_POOLS: dict[str, list[str]] = {
    "poa_utility_bill": _UTILITY_PROVIDERS,
    "poa_telecom_invoice": _TELECOM_PROVIDERS,
    "poa_bank_statement": _BANK_NAMES,
    "poa_insurance_notice": _INSURANCE_NAMES,
    "poa_energy_statement_center": _ENERGY_PROVIDERS,
    "poa_water_bill_split": _WATER_PROVIDERS,
}


def sample_proof_of_address(
    rng: np.random.Generator, faker: Faker, template_name: str
) -> dict[str, Any]:
    locale = rng_choice(rng, _LOCALES)
    address_line1, city, postal_code, country = _locale_address(rng, faker, locale)

    stmt_start = date(2025, 1, 1)
    stmt_end = date(2026, 3, 31)
    stmt_date = _random_date(rng, stmt_start, stmt_end)

    provider_pool = _PROVIDER_POOLS.get(template_name, _UTILITY_PROVIDERS)
    issuer_name = rng_choice(rng, provider_pool)

    full_name = _clean_name(faker.name())

    # Distractors
    due_offset = rng_randint(rng, 10, 21)
    due_date = stmt_date + timedelta(days=due_offset)
    account_number = "".join(str(rng_randint(rng, 0, 9)) for _ in range(10))
    prev_balance = f"{rng_uniform(rng, 0.0, 200.0):.2f}"
    amount_due = f"{rng_uniform(rng, 5.0, 500.0):.2f}"

    # Provider address (distractor)
    provider_faker = Faker("en_US")
    provider_faker.seed_instance(int(rng.integers(0, 2**31)))
    provider_addr = provider_faker.street_address()

    return {
        # Target fields
        "full_name": full_name,
        "address_line1": address_line1,
        "city": city,
        "postal_code": postal_code,
        "country": country,
        "statement_date": _fmt(stmt_date),
        "issuer_name": issuer_name,
        # Distractors
        "_due_date": _fmt(due_date),
        "_account_number": account_number,
        "_prev_balance": prev_balance,
        "_amount_due": amount_due,
        "_provider_address": provider_addr,
        "_provider_city_state": f"{provider_faker.city()}, {provider_faker.state_abbr()} {provider_faker.zipcode()}",
    }


# ---------------------------------------------------------------------------
# Payment-receipt field sampling
# ---------------------------------------------------------------------------
_MERCHANT_NAMES = [
    "Apex Retail Ltd.",
    "CloudStore Inc.",
    "TechMart Online",
    "Metro Supplies Co.",
    "QuickShip Commerce",
    "PrimeGoods Marketplace",
    "Nexus Digital Store",
    "Horizon Electronics",
    "Summit Services LLC",
    "BrightBuy Online",
    "Valor Merchants",
    "Crestline Commerce",
    "Sterling Goods Ltd.",
    "Pacific Trade Corp.",
    "Keystone Retail",
    "Atlas Commerce Inc.",
    "Nova Marketplace",
    "Vertex Supplies",
    "Meridian Shop",
    "Pinnacle Retail Group",
]

_CURRENCIES = ["USD", "EUR", "GBP"]

_REF_PATTERNS = ["TRX6", "PMT8", "REFAN7"]  # shorthand


def _gen_reference_id(rng: np.random.Generator) -> str:
    pattern = rng_choice(rng, _REF_PATTERNS)
    if pattern == "TRX6":
        digits = "".join(str(rng_randint(rng, 0, 9)) for _ in range(6))
        return f"TRX-{digits}"
    elif pattern == "PMT8":
        digits = "".join(str(rng_randint(rng, 0, 9)) for _ in range(8))
        return f"PMT-{digits}"
    else:  # REFAN7
        chars = string.ascii_uppercase + string.digits
        suffix = "".join(rng_choice(rng, list(chars)) for _ in range(7))
        return f"REF{suffix}"


def sample_payment_receipt(rng: np.random.Generator, faker: Faker) -> dict[str, Any]:
    sender_name = _clean_name(faker.name())
    recipient_name = rng_choice(rng, _MERCHANT_NAMES)

    amount_cents = rng_randint(rng, 500, 500000)  # 5.00 – 5000.00
    amount = f"{amount_cents / 100:.2f}"

    currency = rng_choice(rng, _CURRENCIES)

    pay_start = date(2025, 1, 1)
    pay_end = date(2026, 3, 31)
    payment_date = _random_date(rng, pay_start, pay_end)

    reference_id = _gen_reference_id(rng)

    # Distractors
    fee = f"{rng_uniform(rng, 0.50, 25.00):.2f}"
    tax_rate = rng_uniform(rng, 0.05, 0.15)
    subtotal_cents = rng_randint(rng, 500, 500000)
    subtotal = f"{subtotal_cents / 100:.2f}"
    tax = f"{subtotal_cents / 100 * tax_rate:.2f}"
    invoice_id = "INV-" + "".join(str(rng_randint(rng, 0, 9)) for _ in range(6))
    auth_code = "AUTH-" + "".join(str(rng_randint(rng, 0, 9)) for _ in range(6))

    return {
        # Target fields
        "sender_name": sender_name,
        "recipient_name": recipient_name,
        "amount": amount,
        "currency": currency,
        "payment_date": _fmt(payment_date),
        "reference_id": reference_id,
        # Distractors
        "_fee": fee,
        "_tax": tax,
        "_subtotal": subtotal,
        "_invoice_id": invoice_id,
        "_auth_code": auth_code,
    }
