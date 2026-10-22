"""Read original evidence and atomically publish source-timed text and chunks."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from sqlalchemy import func, null, select, text as sql_text
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import SubtitleSource
from app.core.errors import AppError
from app.db.models import (LearningTranscriptSegment, RawTranscriptCue, TranscriptChunkLayout,
                           TranscriptChunkSegment, TranscriptRevision, Video)
from app.schemas.source_learning import (LearningPreviewSummary, LearningPublishResponse,
                                         SourceLearningCandidateSegment, SourceLearningPreviewResponse)
from app.services.chunk_layouts import get_chunk_layout, layout_digest
from app.services.processing.caption_store import CaptionStore
from app.services.srt_export import _srt_time
from app.services.transcript.source_learning import (
    MAX_SOURCE_BYTES, LearningSource, RebuiltLearning, SourceLearningError,
    TimedLearningSentence, extract_learning_source, parse_source_vtt, rebuild_learning_result,
)
from app.services.transcript.vtt import PersistedRawCueData
from app.services.transcripts import get_transcript


_UNAVAILABLE = '这个视频缺少可验证的原始字幕，无法使用来源字幕处理。'
_WARNING_MESSAGES = {
    'TEXT_CHANGED': '文字已调整，请回听检查表达；文字变化未经音频验证。',
    'CUE_START_TIMING': '句首依据为原始字幕块起点，请回听检查。',
    'VERY_SHORT_SEGMENT': '这一句很短，请回听检查。',
    'LONG_END_HOLD': '末词后保留时间较长，请回听检查句尾。',
}


def _application_error(error: SourceLearningError) -> AppError:
    status = (413 if error.code in {'LEARNING_SOURCE_TOO_LARGE', 'LEARNING_RESULT_TOO_LARGE'}
              else 409 if error.code in {'SOURCE_TIMING_UNAVAILABLE', 'LEARNING_SOURCE_MISMATCH'}
              else 422)
    return AppError(status, error.code, str(error))


def read_learning_source(session: Session, video_id: str, data_dir: Path) -> LearningSource:
    get_transcript(session, video_id)
    video = session.get(Video, video_id)
    if video.subtitle_source not in (SubtitleSource.YOUTUBE_AUTO, SubtitleSource.YOUTUBE_MANUAL):
        raise AppError(409, 'SOURCE_TIMING_UNAVAILABLE',
                       '语音转写暂不支持此学习字幕处理入口。')
    try:
        path = CaptionStore(data_dir).path_for(video_id)
        # Neither request paths nor symlinked files outside the managed location
        # may be read. Existing Raw rows alone cannot certify legacy completeness.
        if path.resolve() != path.absolute():
            raise AppError(409, 'SOURCE_TIMING_UNAVAILABLE', _UNAVAILABLE)
        with path.open('rb') as stream:
            content = stream.read(MAX_SOURCE_BYTES + 1)
    except (OSError, ValueError):
        raise AppError(409, 'SOURCE_TIMING_UNAVAILABLE', _UNAVAILABLE) from None
    try:
        original = parse_source_vtt(content)
        rows = session.scalars(select(RawTranscriptCue).where(
            RawTranscriptCue.video_id == video_id).order_by(RawTranscriptCue.sequence_index)).all()
        complete = len(rows) == len(original) and all(
            row.sequence_index == cue.sequence_index
            and row.source_type == video.subtitle_source
            and row.start_seconds == cue.start_seconds
            and row.end_seconds == cue.end_seconds
            and row.text.replace('\r\n', '\n').replace('\r', '\n') == cue.text
            for row, cue in zip(rows, original, strict=True))
        cues = tuple(PersistedRawCueData(
            id=row.id, sequence_index=row.sequence_index,
            start_seconds=row.start_seconds, end_seconds=row.end_seconds, text=row.text,
        ) for row in rows) if complete else original
        return extract_learning_source(video.youtube_video_id, video.subtitle_source, cues)
    except SourceLearningError as error:
        raise _application_error(error) from None


def _rebuild(source: LearningSource, result: str) -> RebuiltLearning:
    try:
        return rebuild_learning_result(source, result)
    except SourceLearningError as error:
        raise _application_error(error) from None


def preview_source_learning(session: Session, video_id: str, data_dir: Path,
                            result: str) -> SourceLearningPreviewResponse:
    source = read_learning_source(session, video_id, data_dir)
    rebuilt = _rebuild(source, result)
    current = get_transcript(session, video_id)
    candidates = [SourceLearningCandidateSegment(
        sequence_index=sentence.sequence_index,
        start=sentence.start_ms / 1000, end=sentence.end_ms / 1000,
        text=sentence.text, translation_zh=sentence.translation_zh, chunks=list(sentence.chunks),
        boundary_offsets=list(sentence.boundary_offsets),
        first_unit_id=sentence.first_unit_id, last_unit_id=sentence.last_unit_id,
        source_text=sentence.source_text,
        start_basis=sentence.start_basis, end_basis=sentence.end_basis,
    ) for sentence in rebuilt.sentences]
    warnings = [dict(
        code=warning.code, sequence_index=warning.sequence_index,
        start=candidates[warning.sequence_index].start,
        end=candidates[warning.sequence_index].end,
        message=_WARNING_MESSAGES[warning.code],
    ) for warning in rebuilt.warnings]
    old = current.segments
    return SourceLearningPreviewResponse(
        video_id=video_id, base_revision_id=current.revision_id,
        preview_digest=rebuilt.preview_digest(current.revision_id),
        source_digest=rebuilt.source_digest, extractor_version=source.extractor_version,
        current_segments=old, segments=candidates, warnings=warnings,
        summary=LearningPreviewSummary(
            current_count=len(old), candidate_count=len(candidates),
            text_changed=[item.text for item in old] != [item.text for item in candidates],
            timing_changed=len(old) != len(candidates) or any(
                round(first.start * 1000) != round(second.start * 1000)
                or round(first.end * 1000) != round(second.end * 1000)
                for first, second in zip(old, candidates)),
            split_segment_count=sum(bool(item.boundary_offsets) for item in candidates),
            chunk_count=sum(len(item.chunks) for item in candidates),
        ),
    )


def _evidence(rebuilt: RebuiltLearning, sentence: TimedLearningSentence) -> dict:
    evidence = dict(
        extractor_version=rebuilt.extractor_version, source_digest=rebuilt.source_digest,
        first_unit_id=sentence.first_unit_id, last_unit_id=sentence.last_unit_id,
        units=[{key: value for key, value in asdict(unit).items()
                if key != 'end_cue_sequence_index' or value is not None}
               for unit in sentence.source_units],
        start_basis=sentence.start_basis, end_basis=sentence.end_basis,
    )
    evidence.update(result_format=rebuilt.result_format, source_type=rebuilt.source_type,
                    processing_mode=rebuilt.processing_mode)
    return evidence


def _matches(session: Session, video_id: str, revision_id: str,
             rebuilt: RebuiltLearning) -> bool:
    layout = session.scalar(select(TranscriptChunkLayout).where(
        TranscriptChunkLayout.revision_id == revision_id,
        TranscriptChunkLayout.video_id == video_id))
    if layout is None:
        return False
    rows = session.execute(select(LearningTranscriptSegment, TranscriptChunkSegment)
        .join(TranscriptChunkSegment,
              TranscriptChunkSegment.segment_id == LearningTranscriptSegment.id)
        .where(LearningTranscriptSegment.revision_id == revision_id,
               TranscriptChunkSegment.layout_id == layout.id)
        .order_by(LearningTranscriptSegment.sequence_index)).all()
    if len(rows) != len(rebuilt.sentences):
        return False
    return all(
        segment.video_id == video_id and segment.sequence_index == sentence.sequence_index
        and segment.source_ref_type == 'source_units'
        and segment.normalization_version is None and segment.normalization_run_id is None
        and segment.source_refs == _evidence(rebuilt, sentence)
        and round(segment.start_seconds * 1000) == sentence.start_ms
        and round(segment.end_seconds * 1000) == sentence.end_ms
        and segment.text == sentence.text
        and segment.translation_zh == sentence.translation_zh
        and list(chunk.boundary_offsets) == list(sentence.boundary_offsets)
        for (segment, chunk), sentence in zip(rows, rebuilt.sentences, strict=True))


def publish_source_learning(session_factory: sessionmaker[Session], video_id: str,
                            data_dir: Path, result: str, expected_revision_id: str,
                            preview_digest: str) -> LearningPublishResponse:
    with session_factory() as session:
        locked = session.execute(sql_text(
            'UPDATE videos SET current_revision_id = current_revision_id WHERE id = :id'),
            {'id': video_id})
        if locked.rowcount != 1:
            raise AppError(404, 'VIDEO_NOT_FOUND', '找不到这个视频，请返回视频库。')
        source = read_learning_source(session, video_id, data_dir)
        rebuilt = _rebuild(source, result)
        if rebuilt.preview_digest(expected_revision_id) != preview_digest:
            raise AppError(409, 'SOURCE_LEARNING_PREVIEW_MISMATCH',
                           '返回结果已变化，请重新预览后再确认。')
        current = get_transcript(session, video_id)
        current_revision = session.get(TranscriptRevision, current.revision_id)
        canonical = [[item.start_ms, item.end_ms, item.text] for item in rebuilt.sentences]
        digest = hashlib.sha256(json.dumps(
            canonical, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        if (current_revision.origin == 'source_aligned'
                and current_revision.content_sha256 == digest
                and len(current.segments) == len(rebuilt.sentences)
                and _matches(session, video_id, current.revision_id, rebuilt)):
            session.rollback()
            return LearningPublishResponse(
                transcript=current, chunk_layout=get_chunk_layout(session, video_id))
        if current.revision_id != expected_revision_id:
            raise AppError(409, 'TRANSCRIPT_REVISION_CONFLICT',
                           '当前字幕已变化，请重新复制指令并预览返回结果。')
        number = session.scalar(select(func.max(TranscriptRevision.revision_number)).where(
            TranscriptRevision.video_id == video_id)) or 0
        revision = TranscriptRevision(video_id=video_id, origin='source_aligned',
                                      revision_number=number + 1, content_sha256=digest)
        session.add(revision)
        session.flush()
        segments = [LearningTranscriptSegment(
            video_id=video_id, revision_id=revision.id, sequence_index=item.sequence_index,
            start_seconds=item.start_ms / 1000, end_seconds=item.end_ms / 1000,
            text=item.text, translation_zh=item.translation_zh, source_ref_type='source_units',
            source_refs=_evidence(rebuilt, item), normalization_version=null(),
        ) for item in rebuilt.sentences]
        session.add_all(segments)
        session.flush()
        layout = TranscriptChunkLayout(
            video_id=video_id, revision_id=revision.id,
            content_sha256=layout_digest(revision.id, [
                (segment.id, item.boundary_offsets)
                for segment, item in zip(segments, rebuilt.sentences, strict=True)]))
        session.add(layout)
        session.flush()
        session.add_all(TranscriptChunkSegment(
            layout_id=layout.id, segment_id=segment.id,
            boundary_offsets=list(item.boundary_offsets),
        ) for segment, item in zip(segments, rebuilt.sentences, strict=True))
        session.get(Video, video_id).current_revision_id = revision.id
        session.commit()
        return LearningPublishResponse(
            transcript=get_transcript(session, video_id),
            chunk_layout=get_chunk_layout(session, video_id))


def export_learning_srt(session: Session, video_id: str) -> tuple[str, str]:
    current = get_transcript(session, video_id)
    content = '\n\n'.join(
        f'{item.sequence_index + 1}\n{_srt_time(item.start)} --> {_srt_time(item.end)}\n{item.text}'
        for item in current.segments) + '\n'
    return content, session.get(Video, video_id).youtube_video_id
