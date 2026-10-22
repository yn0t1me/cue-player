from datetime import datetime

from pydantic import BaseModel


class ChunkLayoutSegmentResponse(BaseModel):
    segment_id: str
    sequence_index: int
    start: float
    end: float
    text: str
    boundary_offsets: list[int]
    chunks: list[str]


class ChunkLayoutResponse(BaseModel):
    id: str
    revision_id: str
    content_sha256: str
    created_at: datetime
    updated_at: datetime
    segments: list[ChunkLayoutSegmentResponse]


class ChunkLayoutStateResponse(BaseModel):
    video_id: str
    revision_id: str
    layout: ChunkLayoutResponse | None
