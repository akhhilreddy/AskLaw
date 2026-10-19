"""Conservative, offline suggestions. Source text is data, never instructions.

Recognise explicit labels and ISO-dated records only. No inferred legal claims,
identity resolution, currency conversion, or automatic persistence/confirmation.
"""
import re
from datetime import date
from hashlib import sha256
from uuid import uuid4

LABELS = {
    "buyer": "buyer_name", "customer": "buyer_name", "customer name": "buyer_name",
    "seller": "seller_name", "seller name": "seller_name", "seller contact": "seller_contact",
    "product": "product", "item": "product", "order reference": "order_reference",
    "order number": "order_reference", "order id": "order_reference",
    "transaction amount": "amount_inr", "total amount": "amount_inr", "grand total": "amount_inr",
}
DATES = {"purchase date": "purchase", "invoice date": "purchase", "delivery date": "delivery",
         "buyer message": "contact", "seller reply": "response"}


def suggest_from_documents(documents):
    suggestions = []
    for document in documents:
        for page in document.pages:
            lines = list(re.finditer(r"[^\n\r]+", page.text))
            for index, line in enumerate(lines):
                text = line.group().strip()
                field = value = kind = occurred_on = None
                labelled = re.fullmatch(r"([A-Za-z /]+):\s*(.+)", text)
                if labelled:
                    field = LABELS.get(labelled[1].lower())
                    value = labelled[2].strip()
                    if field == "amount_inr":
                        # Currency must be explicit; do not mistake tax/subtotal for total.
                        money = re.fullmatch(r"(?:INR|Rs\.?|₹)\s*((?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d{1,2})?)", value, re.I)
                        value = money[1].replace(",", "") if money else None
                        if value and not re.fullmatch(r"\d{1,10}(?:\.\d{1,2})?", value):
                            value = None
                dated = re.match(r"^(Purchase date|Invoice date|Delivery date|Buyer message|Seller reply)\s*[:|]\s*(\d{4}-\d{2}-\d{2})(?=$|[.\s])", text, re.I)
                if dated:
                    try:
                        occurred_on = date.fromisoformat(dated[2]).isoformat()
                        kind = DATES[dated[1].lower()]
                    except ValueError:
                        pass
                if not (field and value and len(value) <= 200) and not (kind and occurred_on):
                    continue
                start, end = line.span()
                # Include correspondence body, bounded at the next dated heading.
                if kind in ("contact", "response", "delivery"):
                    for following in lines[index + 1:]:
                        if kind == "delivery" and re.search(r"[.!?]\s*$", page.text[start:end]):
                            break
                        if re.match(r"\s*(?:(?:Buyer message|Seller reply|Purchase date|Invoice date|Delivery date)\s*[:|]|Test scope\s*$|AskLaw test fixture\b|Page \d+\s*$)", following.group(), re.I):
                            break
                        if following.end() - start > 1500:
                            break
                        end = following.end()
                quote = page.text[start:end]
                if len(quote) > 2000:
                    continue
                category = "correspondence" if kind in ("contact", "response") else "delivery" if kind == "delivery" else "invoice"
                reference = {"evidence_id": f"i-{uuid4()}", "document_id": document.document_id,
                             "label": f"Imported {field or kind}"[:120], "category": category,
                             "page_number": page.page_number, "start": start, "end": end,
                             "page_text_sha256": sha256(page.text.encode()).hexdigest()}
                candidate = {"suggestion_id": str(uuid4()), "reference": reference,
                             "quote": quote, "filename": document.title}
                if kind and occurred_on:
                    description = " ".join(quote.split())
                    if kind in ("contact", "response"):
                        body = [part.strip() for part in quote.splitlines()[1:]
                                if not re.match(r"\s*(?:From|To|Subject|Reference):", part, re.I)]
                        description = " ".join(body) or description
                    candidate["event"] = {"event_id": f"i-{uuid4()}", "kind": kind,
                                          "occurred_on": occurred_on, "description": description[:1000],
                                          "evidence_ids": [reference["evidence_id"]]}
                else:
                    candidate.update(field=field, value=value)
                suggestions.append(candidate)
                if kind == "contact":
                    # Only explicit first-person buyer statements, never seller text
                    # or a generated summary. Preserve the full containing excerpt.
                    normal = " ".join(quote.split())
                    for target, pattern in [
                        ("description", r"\b(I (?:purchased|bought|received)\b.*?)(?=\bI request\b|$)"),
                        ("requested_resolution", r"\b(I request\b.*?)(?=$)"),
                    ]:
                        statement = re.search(pattern, normal)
                        if statement and 0 < len(statement[1].strip()) <= 2000 and len(suggestions) < 60:
                            suggestions.append({"suggestion_id": str(uuid4()), "reference": reference.copy(),
                                                "quote": quote, "filename": document.title,
                                                "field": target, "value": statement[1].strip()})
                if len(suggestions) >= 60:
                    return {"suggestions": suggestions, "truncated": True}
    return {"suggestions": suggestions, "truncated": False}
