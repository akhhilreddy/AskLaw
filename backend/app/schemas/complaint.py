"""Bounded, user-confirmed complaint facts. No generated law or automatic filing."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.agreement import DocumentId

Short = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, max_length=200)]
Text = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, max_length=2000)]
Identifier = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{1,40}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceReference(StrictModel):
    evidence_id: Identifier
    document_id: DocumentId
    label: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120)]
    category: Literal["invoice", "delivery", "correspondence", "other"] = "other"
    page_number: int = Field(strict=True, ge=1, le=50)
    start: int = Field(strict=True, ge=0, le=100000)
    end: int = Field(strict=True, gt=0, le=100000)
    page_text_sha256: Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def bounded_excerpt(self):
        if not 0 < self.end - self.start <= 2000:
            raise ValueError("Select 1 to 2,000 characters from the source page")
        return self


class TimelineEvent(StrictModel):
    event_id: Identifier
    kind: Literal["purchase", "delivery", "problem", "contact", "response", "other"]
    occurred_on: Annotated[str, StringConstraints(strict=True, pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None
    description: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=1000)]
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=5)

    @field_validator("occurred_on")
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value


class ComplaintCase(StrictModel):
    title: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120)]
    issue_type: Literal["defective_product", "refused_refund"] = "defective_product"
    buyer_name: Short = ""
    seller_name: Short = ""
    seller_contact: Short = ""
    product: Short = ""
    order_reference: Short = ""
    amount_inr: Annotated[str, StringConstraints(strict=True, pattern=r"^(?:|\d{1,10}(?:\.\d{1,2})?)$")] = ""
    description: Text = ""
    requested_resolution: Text = ""
    facts_confirmed: bool = Field(default=False, strict=True)
    events: list[TimelineEvent] = Field(default_factory=list, max_length=30)
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=15)
    letter_text: Annotated[str, StringConstraints(strict=True, max_length=16000)] = ""

    @model_validator(mode="after")
    def consistent_references(self):
        evidence_ids = [item.evidence_id for item in self.evidence]
        event_ids = [item.event_id for item in self.events]
        if len(set(evidence_ids)) != len(evidence_ids) or len(set(event_ids)) != len(event_ids):
            raise ValueError("Event and evidence IDs must be unique")
        if any(identifier not in evidence_ids for event in self.events for identifier in event.evidence_ids):
            raise ValueError("A timeline event refers to unknown evidence")
        return self


class ComplaintUpdate(StrictModel):
    revision: int = Field(strict=True, ge=1)
    data: ComplaintCase


class PackRequest(StrictModel):
    revision: int = Field(strict=True, ge=1)


class ImportRequest(StrictModel):
    document_ids: list[DocumentId] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def distinct_documents(self):
        if len(set(value.lower() for value in self.document_ids)) != len(self.document_ids):
            raise ValueError("Select distinct documents")
        return self


class IntakeRequest(StrictModel):
    description: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=10, max_length=2000)]
    consent_to_ai: bool = Field(strict=True)

    @field_validator("consent_to_ai")
    @classmethod
    def explicit_consent(cls, value):
        if not value:
            raise ValueError("Consent is required for AI intake")
        return value
