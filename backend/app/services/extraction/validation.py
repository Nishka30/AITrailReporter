"""Domain validation for raw LLM tool-call output (Step 9). Nothing from
app/services/extraction/anthropic_provider.py reaches the observations table
without passing through here first -- the provider's own strict JSON-schema
mode (see prompt.py) is defense in depth, never a substitute for this.
"""

from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from app.db.models.knowledge_type_config import KnowledgeTypeConfig
from app.services.knowledge_type_policy import (
    MAX_NEW_TYPES_PER_EXTRACTION,
    InvalidKnowledgeTypeProposalError,
    ResolvedTypePolicy,
    normalize_type_name,
    resolve_policy,
)


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


class _NewTypeCandidate(BaseModel):
    """Shape validation only. The enum VALUES are checked separately, by
    knowledge_type_policy.resolve_policy -- deliberately not duplicated as a
    Pydantic Literal here, so the profile tables in that module stay the single
    place those vocabularies are defined."""

    knowledge_type: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=255)
    volatility: str
    scope: str
    significance: str
    value: dict
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: str = Field(min_length=1, max_length=2000)


class _ExtractionOutput(BaseModel):
    observations: list[_ObservationCandidate]
    # Absent entirely == no proposals. Keeps this validator backward-compatible
    # with any response shaped like the pre-Step-16 tool.
    new_knowledge_types: list[_NewTypeCandidate] = Field(default_factory=list)


class ValidatedObservation(BaseModel):
    """A candidate that has passed BOTH shape validation and the
    allowed-knowledge-types check -- safe to turn into an Observation row."""

    knowledge_type_id: UUID
    value: dict
    confidence: float
    evidence: str


class ValidatedNewType(BaseModel):
    """A proposed new category that has passed shape validation AND
    deterministic policy resolution. `policy` carries application-computed
    column values only -- no number in it originated from the model.

    Deliberately NOT a ValidatedObservation: it has no knowledge_type_id yet,
    because the row it will reference does not exist until the extraction
    transaction creates (or resolves) it.
    """

    model_config = {"arbitrary_types_allowed": True}

    policy: ResolvedTypePolicy
    value: dict
    confidence: float
    evidence: str


def validate_llm_output(
    raw: dict, allowed_types: list[KnowledgeTypeConfig]
) -> tuple[list[ValidatedObservation], list[ValidatedNewType]]:
    """Validates the provider's raw tool-call input against the required shape,
    then against the actual allowed knowledge types loaded from PostgreSQL for
    this request (never a hardcoded list). Returns
    (observations, new_type_proposals).

    Raises InvalidExtractionOutputError on any violation -- a partially-valid
    response is rejected as a whole rather than silently dropping the bad
    parts, so a validation bug never causes silent data loss. This
    all-or-nothing rule now covers new-type proposals too: one malformed
    proposal rejects the ENTIRE extraction rather than persisting the
    observations that happened to be fine, which keeps "no partial
    persistence" true across both arrays.
    """
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

    # The schema already caps this via maxItems, but that cap only STEERS the
    # model -- it is not the safety boundary (same reasoning as the module
    # docstring). Enforced here for real.
    if len(parsed.new_knowledge_types) > MAX_NEW_TYPES_PER_EXTRACTION:
        raise InvalidExtractionOutputError(
            f"LLM proposed {len(parsed.new_knowledge_types)} new knowledge types; "
            f"at most {MAX_NEW_TYPES_PER_EXTRACTION} are allowed per extraction."
        )

    validated_new: list[ValidatedNewType] = []
    seen_names: set[str] = set()
    for proposal in parsed.new_knowledge_types:
        # Normalize FIRST, so the existing-type lookup below compares like with
        # like ("Trail-Condition" must match the seeded `trail_condition`).
        try:
            normalized_name = normalize_type_name(proposal.knowledge_type)
        except InvalidKnowledgeTypeProposalError as exc:
            raise InvalidExtractionOutputError(
                f"LLM proposed an invalid knowledge type: {exc.message}"
            ) from exc

        # CASE A via the wrong array: the proposal's normalized name already
        # exists as an active type, i.e. the model reached for a "new" category
        # that we already have. Not an error -- rejecting the whole extraction
        # over it would be harsh and would throw away a real observation.
        # Recorded against the EXISTING type instead, which is exactly the
        # outcome Case A prescribes.
        existing_id = allowed_ids_by_type.get(normalized_name)
        if existing_id is not None:
            validated.append(
                ValidatedObservation(
                    knowledge_type_id=existing_id,
                    value=proposal.value,
                    confidence=proposal.confidence,
                    evidence=proposal.evidence.strip(),
                )
            )
            continue

        # Two proposals normalizing to the SAME name within one response (e.g.
        # "Water Source" and "water-source"). Collapsed rather than rejected --
        # the second is redundant, not malformed. Only the first is kept, so
        # one extraction can never insert the same category twice.
        if normalized_name in seen_names:
            continue

        # Only now, for a genuinely new category, is full policy resolution
        # (enum vocabularies + reserved-name guard) applied.
        try:
            policy = resolve_policy(
                proposal.knowledge_type,
                proposal.display_name,
                proposal.volatility,
                proposal.scope,
                proposal.significance,
            )
        except InvalidKnowledgeTypeProposalError as exc:
            raise InvalidExtractionOutputError(
                f"LLM proposed an invalid knowledge type: {exc.message}"
            ) from exc

        seen_names.add(policy.knowledge_type)
        validated_new.append(
            ValidatedNewType(
                policy=policy,
                value=proposal.value,
                confidence=proposal.confidence,
                evidence=proposal.evidence.strip(),
            )
        )

    return validated, validated_new
