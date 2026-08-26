"""Domain validation for raw LLM tool-call output (Step 9). Nothing from
app/services/extraction/anthropic_provider.py reaches the observations table
without passing through here first -- the provider's own strict JSON-schema
mode (see prompt.py) is defense in depth, never a substitute for this.
"""

from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from app.db.models.knowledge_type_config import KnowledgeTypeConfig


class InvalidExtractionOutputError(Exception):
    """Raised when the provider's output fails schema or domain validation --
    malformed shape, out-of-range confidence, or a knowledge_type that isn't in
    the allowed set. `message` is always safe to persist and show."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class _ObservationCandidate(BaseModel):
    knowledge_type: str
    value: dict
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1, max_length=2000)


class _ExtractionOutput(BaseModel):
    observations: list[_ObservationCandidate]


class ValidatedObservation(BaseModel):
    """A candidate that has passed BOTH shape validation and the
    allowed-knowledge-types check -- safe to turn into an Observation row."""

    knowledge_type_id: UUID
    value: dict
    confidence: float
    evidence: str


def validate_llm_output(
    raw: dict, allowed_types: list[KnowledgeTypeConfig]
) -> list[ValidatedObservation]:
    """Validates the provider's raw tool-call input against the required shape,
    then against the actual allowed knowledge types loaded from PostgreSQL for
    this request (never a hardcoded list). Raises InvalidExtractionOutputError
    on any violation -- a partially-valid response is rejected as a whole rather
    than silently dropping the bad parts, so a validation bug never causes silent
    data loss."""
    try:
        parsed = _ExtractionOutput.model_validate(raw)
    except ValidationError as exc:
        raise InvalidExtractionOutputError(
            f"LLM output failed schema validation ({exc.error_count()} error(s))."
        ) from exc

    allowed_ids_by_type = {t.knowledge_type: t.id for t in allowed_types}

    validated: list[ValidatedObservation] = []
    for candidate in parsed.observations:
        knowledge_type_id = allowed_ids_by_type.get(candidate.knowledge_type)
        if knowledge_type_id is None:
            raise InvalidExtractionOutputError(
                f"LLM returned an unknown knowledge_type: {candidate.knowledge_type!r}"
            )
        validated.append(
            ValidatedObservation(
                knowledge_type_id=knowledge_type_id,
                value=candidate.value,
                confidence=candidate.confidence,
                evidence=candidate.evidence.strip(),
            )
        )
    return validated
