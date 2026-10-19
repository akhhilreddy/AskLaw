"""Pure, bounded, source-linked analysis: no model, network, DB or filing action."""
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re

from app.schemas.agreement import AGREEMENT_DISCLAIMER, AgreementText

ANALYSIS_VERSION = "1"
REVIEW_ANALYSIS_VERSION = "2"
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
_SECTION_NAMES = (r"(?:Security deposit|Rent(?: and payment)?|Notice(?: period| and other terms)?|"
                  r"Lock[ -]in(?: period)?|Termination(?: and notice)?|Renewal|"
                  r"Maintenance and deductions|Disputes(?: and jurisdiction)?)")
_HEADING = re.compile(
    r"(?m)^[ \t]*(?:(?:\d{1,3}[.)]|\d{1,3}(?:\.\d{1,3})+[.)]?|[A-Z][.)])"
    r"[ \t]+[A-Za-z]|Clause[ \t]+\d{1,3}[.:) -]+[A-Za-z]|"
    + _SECTION_NAMES + r"[ \t]*:?[ \t]*\r?$)", re.I)
_BARE_HEADING = re.compile(_SECTION_NAMES + r"[ \t]*:?", re.I)
_QUALIFIER = re.compile(r"^(?:however|except|unless|provided|subject to|but|this|that|such|it|"
                        r"the (?:above|foregoing|deposit|amount|notice|payment))\b", re.I)


def _trim_span(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _review_units(text):
    """Prefer explicit numbered/named sections; never rewrite extracted text."""
    headings = {match.start() for match in _HEADING.finditer(text)}
    boundaries = sorted(set([0, *headings, len(text)]))
    for start, end in zip(boundaries, boundaries[1:]):
        if start in headings:
            a, b = _trim_span(text, start, end)
            if a < b:
                yield a, b, True
        else:
            # Text without structural headings gets local sentence context,
            # rather than treating a single-newline PDF page as one clause.
            for paragraph in re.finditer(r"\S[\s\S]*?(?=\r?\n[ \t]*\r?\n|\Z)", text[start:end]):
                a, b = _trim_span(text, start + paragraph.start(), start + paragraph.end())
                if a < b:
                    yield a, b, False


def _sentence_spans(text, start, end):
    spans = []
    cursor = start
    for boundary in re.finditer(r"[.!?][ \t\r\n]+(?=[A-Z0-9\"(])", text[start:end]):
        stop = start + boundary.start() + 1
        # Do not sever currency, common honorifics or section abbreviations.
        word = re.search(r"([A-Za-z]+)\.$", text[cursor:stop])
        if word and word.group(1).lower() in {"rs", "mr", "mrs", "ms", "dr", "no", "sec", "art", "etc"}:
            continue
        a, b = _trim_span(text, cursor, stop)
        if a < b:
            spans.append((a, b))
        cursor = start + boundary.end()
    a, b = _trim_span(text, cursor, end)
    if a < b:
        spans.append((a, b))
    return spans


def _term_mentions(document, pattern):
    mentions = []
    for page in document.pages:
        text = page.text
        digest = sha256(text.encode()).hexdigest()
        selected = {}
        for start, end, structured in _review_units(text):
            if structured and _BARE_HEADING.fullmatch(text[start:end]):
                # A standalone page/category title followed immediately by a
                # numbered section is not itself a substantive term passage.
                continue
            matches = list(re.finditer(pattern, text[start:end], re.I))
            if not matches:
                continue
            sentences = _sentence_spans(text, start, end)
            for match in matches:
                hit_start, hit_end = start + match.start(), start + match.end()
                a, b = start, end
                scope = "clause_candidate"
                if not structured or end - start > MAX_PASSAGE_CHARACTERS:
                    scope = "context_excerpt"
                    for index, (first, last) in enumerate(sentences):
                        if first <= hit_start < last:
                            a, b = first, last
                            # Keep immediately following qualifying sentences
                            # within the same section/paragraph, when bounded.
                            for next_start, next_end in sentences[index + 1:]:
                                if not _QUALIFIER.match(text[next_start:next_end]) or next_end - a > MAX_PASSAGE_CHARACTERS:
                                    break
                                b = next_end
                            break
                partial = b - a > MAX_PASSAGE_CHARACTERS
                if partial:
                    # Centre a bounded window on the actual hit, not on the
                    # beginning of a long clause that may omit the keyword.
                    a = max(a, hit_start - MAX_PASSAGE_CHARACTERS // 2)
                    b = min(b, a + MAX_PASSAGE_CHARACTERS)
                    if hit_end > b:
                        a, b = max(start, hit_end - MAX_PASSAGE_CHARACTERS), hit_end
                    a, b = _trim_span(text, a, b)
                selected[(a, b)] = {"document_id": document.document_id, "page_number": page.page_number,
                    "start": a, "end": b, "quote": text[a:b], "page_text_sha256": digest,
                    "scope": scope, "is_partial": partial}
                if len(selected) + len(mentions) > MAX_PASSAGES:
                    raise ValueError("Too many passages for bounded agreement analysis")
        # Multiple keyword hits may pick a qualifying sentence already included
        # by an earlier hit. Show that source range once, not again as a subset.
        retained = []
        for a, b in sorted(selected, key=lambda span: (span[0], -span[1])):
            if retained and a >= retained[-1][0] and b <= retained[-1][1]:
                continue
            retained.append((a, b))
        mentions.extend(selected[key] for key in retained)
        if len(mentions) > MAX_PASSAGES:
            raise ValueError("Too many passages for bounded agreement analysis")
    return mentions


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
    passages(document)  # Preserve the existing global input-complexity guard.
    terms = []
    for kind, pattern in TERM_PATTERNS.items():
        mentions = _term_mentions(document, pattern)
        terms.append({"kind": kind, "status": "mentions_found" if mentions else "not_identified",
                      "mentions": mentions})
    return {"analysis_version": REVIEW_ANALYSIS_VERSION, "document_id": document.document_id,
            "title": document.title, "extracted_text_sha256": text_digest(document),
            "terms": terms, "disclaimer": AGREEMENT_DISCLAIMER,
            "limitations": ["Keyword-assisted English text review, not a legal risk score.",
                            "Not identified means the matcher found no mention, not that the term is absent.",
                            "Numbered/named sections are clause candidates; unstructured text uses local sentence context.",
                            "Context excerpts and clipped passages may omit qualifications; read the full agreement.",
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
    """Deterministic JSON export; the frontend separately renders HTML reports."""
    return json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
