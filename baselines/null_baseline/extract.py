import json
import os

def predict(document_dir: str) -> dict:
    meta_path = os.path.join(document_dir, "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    
    schema_name = meta["schema_name"]
    
    if schema_name == "government_id":
        fields = {
            "full_name": None,
            "date_of_birth": None,
            "document_number": None,
            "issue_date": None,
            "expiry_date": None,
            "issuing_country": None
        }
    elif schema_name == "proof_of_address":
        fields = {
            "full_name": None,
            "address_line1": None,
            "city": None,
            "postal_code": None,
            "country": None,
            "statement_date": None,
            "issuer_name": None
        }
    elif schema_name == "payment_receipt":
        fields = {
            "sender_name": None,
            "recipient_name": None,
            "amount": None,
            "currency": None,
            "payment_date": None,
            "reference_id": None
        }
    else:
        fields = {}
        
    return {
        "schema_name": schema_name,
        "fields": fields
    }
