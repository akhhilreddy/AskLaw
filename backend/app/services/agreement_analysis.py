"""Pure, bounded, source-linked analysis: no model, network, DB or filing action."""
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re

from app.schemas.agreement import AGREEMENT_DISCLAIMER, AgreementText

ANALYSIS_VERSION = "1"
MAX_PASSAGES = 256
MAX_PASSAGE_CHARACTERS = 2000
# These identify candidate mentions, not complete clauses, legal defects or a
# finding that an unrecognised term is absent. Every result retains its quote.
TERM_PATTERNS = {
    "security_deposit": r"\b(?:security\s+deposit|refundable\s+deposit|deposit)\b",
    "rent_and_payment": r"\b(?:rent|payment|payable|monthly\s+fee)\b",
    "notice_period": r"\bnotice\b",
    "lock_in": r"\block[\s-]*in\b",
    "termination": r"\b(?:terminat\w*|evict\w*)\b",
    "renewal": r"\b(?:renew\w*|extend\w*|extension)\b",
    "deductions_and_charges": r"\b(?:deduct\w*|penalt\w*|charges?|non[\s-]*refundable)\b",
    "disputes_and_jurisdiction": r"\b(?:arbitrat\w*|jurisdiction|disputes?|courts?)\b",
}
_NUMBERS = re.compile(
    r"(?:₹|Rs\.?|INR)\s*\d[\d,]*(?:\.\d+)?|\b\d+(?:\.\d+)?\s*(?:(?:days?|months?|years?)\b|%)", re.I)


def text_digest(document):
    # This is an extracted-text identity, NOT a hash/certification of PDF bytes.
    payload = {"page_count": document.page_count,
               "pages": [page.model_dump() for page in document.pages]}
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()).hexdigest()


def passages(document: AgreementText):
    result = []
    for page in document.pages:
        page_digest = sha256(page.text.encode()).hexdigest()
        for paragraph in re.finditer(r"\S[\s\S]*?(?=\r?\n[ \t]*\r?\n|\Z)", page.text):
            for start in range(paragraph.start(), paragraph.end(), MAX_PASSAGE_CHARACTERS):
                end = min(start + MAX_PASSAGE_CHARACTERS, paragraph.end())
                result.append({"document_id": document.document_id, "page_number": page.page_number,
                               "start": start, "end": end, "quote": page.text[start:end],
                               "page_text_sha256": page_digest})
                if len(result) > MAX_PASSAGES:
                    raise ValueError("Too many passages for bounded agreement analysis")
    return result


def review_agreement(document: AgreementText):
    source_passages = passages(document)
    terms = []
    for kind, pattern in TERM_PATTERNS.items():
        mentions = [passage for passage in source_passages if re.search(pattern, passage["quote"], re.I)]
        terms.append({"kind": kind, "status": "mentions_found" if mentions else "not_identified",
                      "mentions": mentions})
    return {"analysis_version": ANALYSIS_VERSION, "document_id": document.document_id,
            "title": document.title, "extracted_text_sha256": text_digest(document),
            "terms": terms, "disclaimer": AGREEMENT_DISCLAIMER,
            "limitations": ["Keyword-assisted English text review, not a legal risk score.",
                            "Not identified means the matcher found no mention, not that the term is absent.",
                            "Passages may be bounded excerpts rather than complete clauses.",
                            "No law, state-specific rule, deadline or enforceability opinion is inferred."]}


def _normalized(passage):
    # Only whitespace is ignored for alignment. Punctuation, case and numbers
    # remain significant. Similarity never proves two clauses have equal effect.
    return re.sub(r"\s+", " ", passage["quote"]).strip()


def _tokens(items):
    return [match.group() for item in items for match in _NUMBERS.finditer(item["quote"])]


def compare_agreements(before: AgreementText, after: AgreementText):
    left, right = passages(before), passages(after)
    changes = []
    for tag, a, b, c, d in SequenceMatcher(None, [_normalized(item) for item in left],
                                         [_normalized(item) for item in right], autojunk=False).get_opcodes():
        if tag == "equal":
            for first, second in zip(left[a:b], right[c:d], strict=True):
                if first["quote"] != second["quote"]:
                    changes.append({"kind": "formatting_only", "before": [first], "after": [second],
                                    "numeric_tokens_before": _tokens([first]), "numeric_tokens_after": _tokens([second])})
            continue
        old, new = left[a:b], right[c:d]
        changes.append({"kind": {"replace": "changed", "delete": "removed", "insert": "added"}[tag],
                        "before": old, "after": new,
                        "numeric_tokens_before": _tokens(old), "numeric_tokens_after": _tokens(new)})
    return {"analysis_version": ANALYSIS_VERSION,
            "before": {"document_id": before.document_id, "title": before.title,
                       "extracted_text_sha256": text_digest(before)},
            "after": {"document_id": after.document_id, "title": after.title,
                      "extracted_text_sha256": text_digest(after)},
            "summary": {kind: sum(item["kind"] == kind for item in changes)
                        for kind in ("added", "removed", "changed", "formatting_only")},
            "changes": changes, "disclaimer": AGREEMENT_DISCLAIMER,
            "limitations": ["Compares extracted text, not signatures, stamps, images or PDF layout.",
                            "Changes are passage groups, not guaranteed one-to-one clause matches.",
                            "Numeric tokens are quoted observations, not amounts legally owed or calculated deadlines.",
                            "No text change does not prove the original PDF files are identical or legally equivalent."]}


def export_report(report):
    """Deterministic JSON export foundation; PDF/UI export is a later slice."""
    return json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
