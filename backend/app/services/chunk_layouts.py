import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    LearningTranscriptSegment,
    TranscriptChunkLayout,
    TranscriptChunkSegment,
)
from app.schemas.chunk_layouts import (
    ChunkLayoutResponse,
    ChunkLayoutSegmentResponse,
    ChunkLayoutStateResponse,
)
from app.services.transcripts import get_transcript


def _stored_layout(session: Session, revision_id: str) -> TranscriptChunkLayout | None:
    return session.scalar(select(TranscriptChunkLayout).where(
        TranscriptChunkLayout.revision_id == revision_id))


def _chunks_from_offsets(body: str, offsets: list[int]) -> list[str]:
    chunks: list[str] = []
    start = 0
    for offset in offsets:
        chunks.append(body[start:offset])
        start = offset + 1
    chunks.append(body[start:])
    return chunks


def _layout_response(session: Session, layout: TranscriptChunkLayout) -> ChunkLayoutResponse:
    rows = session.execute(
        select(TranscriptChunkSegment, LearningTranscriptSegment)
        .join(LearningTranscriptSegment,
              TranscriptChunkSegment.segment_id == LearningTranscriptSegment.id)
        .where(TranscriptChunkSegment.layout_id == layout.id)
        .order_by(LearningTranscriptSegment.sequence_index)
    ).all()
    return ChunkLayoutResponse(
        id=layout.id,
        revision_id=layout.revision_id,
        content_sha256=layout.content_sha256,
        created_at=layout.created_at,
        updated_at=layout.updated_at,
        segments=[ChunkLayoutSegmentResponse(
            segment_id=segment.id,
            sequence_index=segment.sequence_index,
            start=segment.start_seconds,
            end=segment.end_seconds,
            text=segment.text,
            boundary_offsets=list(chunk_segment.boundary_offsets),
            chunks=_chunks_from_offsets(segment.text, chunk_segment.boundary_offsets),
        ) for chunk_segment, segment in rows],
    )


def get_chunk_layout(session: Session, video_id: str) -> ChunkLayoutStateResponse:
    transcript = get_transcript(session, video_id)
    layout = _stored_layout(session, transcript.revision_id)
    return ChunkLayoutStateResponse(
        video_id=video_id,
        revision_id=transcript.revision_id,
        layout=_layout_response(session, layout) if layout is not None else None,
    )


def layout_digest(revision_id: str, rows: list[tuple[str, tuple[int, ...]]]) -> str:
    canonical = [revision_id, [[segment_id, list(offsets)] for segment_id, offsets in rows]]
    return hashlib.sha256(json.dumps(
        canonical, ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')).hexdigest()
