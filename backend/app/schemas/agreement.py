"""Bounded text-only agreement analysis. No assessment of legal enforceability."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_AGREEMENT_CHARACTERS = 100_000
MAX_AGREEMENT_PAGES = 50
AGREEMENT_DISCLAIMER = (
    "Document analysis only. This report does not determine whether a term is lawful, "
    "enforceable or applicable to your circumstances. AskLaw provides legal information, not legal advice."
)


class AgreementPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_number: Annotated[int, Field(strict=True, ge=1, le=MAX_AGREEMENT_PAGES)]
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=MAX_AGREEMENT_CHARACTERS)]

    @model_validator(mode="after")
    def readable_text(self):
        if (not self.text.strip() or "\ufffd" in self.text
                or any(ord(char) < 32 and char not in "\n\r\t" for char in self.text)):
            raise ValueError("A readable text page is required; scanned or corrupt pages are unsupported")
        return self


class AgreementText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=80)]
    title: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=255)]
    page_count: Annotated[int, Field(strict=True, ge=1, le=MAX_AGREEMENT_PAGES)]
    pages: list[AgreementPage] = Field(min_length=1, max_length=MAX_AGREEMENT_PAGES)

    @model_validator(mode="after")
    def complete_bounded_pages(self):
        if [page.page_number for page in self.pages] != list(range(1, self.page_count + 1)):
            raise ValueError("All pages must be present exactly once in source order")
        if sum(len(page.text) for page in self.pages) > MAX_AGREEMENT_CHARACTERS:
            raise ValueError("Agreement text exceeds the analysis size limit")
        return self


DocumentId = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-fA-F]{24}$")]


class AgreementReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: DocumentId


class AgreementCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before_id: DocumentId
    after_id: DocumentId

    @model_validator(mode="after")
    def different_versions(self):
        if self.before_id.lower() == self.after_id.lower():
            raise ValueError("Select two different uploaded versions")
        return self
