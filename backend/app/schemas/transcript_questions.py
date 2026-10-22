from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.transcript_marks import TranscriptSelectionRequest, TranscriptAnchorResponse


class QuestionFields(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @field_validator('question', check_fields=False)
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Question must not be blank')
        return value

    @field_validator('answer', check_fields=False)
    @classmethod
    def optional_answer(cls, value: str | None) -> str | None:
        return value if value and value.strip() else None


class CreateTranscriptQuestionRequest(TranscriptSelectionRequest, QuestionFields):
    question: str = Field(min_length=1, max_length=10_000)
    answer: str | None = Field(default=None, max_length=100_000)


class UpdateTranscriptQuestionRequest(QuestionFields):
    # Omission preserves the field; explicit null is allowed only for answer.
    question: str = Field(default=None, min_length=1, max_length=10_000)
    answer: str | None = Field(default=None, max_length=100_000)

    @model_validator(mode='after')
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError('Provide question or answer')
        return self


class TranscriptQuestionResponse(TranscriptAnchorResponse):
    question: str
    answer: str | None


class TranscriptQuestionListResponse(BaseModel):
    items: list[TranscriptQuestionResponse]
