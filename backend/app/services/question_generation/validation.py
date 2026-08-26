"""Domain validation for raw LLM tool-call output (Step 12). Nothing from
app/services/question_generation/anthropic_provider.py reaches the questions
table without passing through here first -- mirrors
app/services/extraction/validation.py's role for extraction.
"""

from pydantic import BaseModel, Field, ValidationError


class InvalidQuestionOutputError(Exception):
    """Raised when the provider's output fails schema validation or is
    effectively empty. `message` is always safe to persist and show."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class _QuestionCandidate(BaseModel):
    question_text: str
    short_context: str | None = None


class ValidatedQuestion(BaseModel):
    """A candidate that has passed shape + non-empty validation -- safe to
    persist as a Question's question_text/short_context."""

    question_text: str = Field(min_length=1, max_length=1000)
    short_context: str | None = Field(default=None, max_length=500)


def validate_question_output(raw: dict) -> ValidatedQuestion:
    """Validates the provider's raw tool-call input. Raises
    InvalidQuestionOutputError on any violation -- a malformed or effectively
    empty (whitespace-only) question_text must never be persisted as a
    successful generated question."""
    try:
        parsed = _QuestionCandidate.model_validate(raw)
    except ValidationError as exc:
        raise InvalidQuestionOutputError(
            f"LLM output failed schema validation ({exc.error_count()} error(s))."
        ) from exc

    question_text = parsed.question_text.strip()
    if not question_text:
        raise InvalidQuestionOutputError("LLM returned an empty question_text.")

    short_context = parsed.short_context.strip() if parsed.short_context else None

    try:
        return ValidatedQuestion(question_text=question_text, short_context=short_context or None)
    except ValidationError as exc:
        raise InvalidQuestionOutputError(
            f"LLM output failed validation after normalization ({exc.error_count()} error(s))."
        ) from exc
