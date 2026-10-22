"""Exchange requests and locally rebuilt learning previews."""
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.chunk_layouts import ChunkLayoutStateResponse
from app.schemas.transcripts import TranscriptResponse, TranscriptSegmentResponse
from app.services.transcript.source_learning import TimeBasis


class SourceLearningPreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    result: str


class SourceLearningPublishRequest(SourceLearningPreviewRequest):
    expected_revision_id: str
    preview_digest: str


class LearningCandidateSegment(BaseModel):
    sequence_index: int
    start: float
    end: float
    text: str
    boundary_offsets: list[int]
    chunks: list[str]


class LearningPreviewSummary(BaseModel):
    current_count: int
    candidate_count: int
    text_changed: bool
    timing_changed: bool
    split_segment_count: int
    chunk_count: int


class LearningPreviewResponse(BaseModel):
    video_id: str
    base_revision_id: str
    preview_digest: str
    current_segments: list[TranscriptSegmentResponse]
    segments: list[LearningCandidateSegment]
    summary: LearningPreviewSummary
    warnings: list[dict]


class LearningPublishResponse(BaseModel):
    transcript: TranscriptResponse
    chunk_layout: ChunkLayoutStateResponse


class SourceLearningCandidateSegment(LearningCandidateSegment):
    translation_zh: str | None = None
    first_unit_id: str
    last_unit_id: str
    source_text: str
    start_basis: TimeBasis
    end_basis: Literal['next_sentence_start', 'source_cue_end']


class SourceLearningPreviewResponse(LearningPreviewResponse):
    source_digest: str
    extractor_version: str
    segments: list[SourceLearningCandidateSegment]
