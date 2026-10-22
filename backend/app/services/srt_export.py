"""Read-only, Raw-derived SRT for review outside the application."""

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import VideoStatus
from app.core.errors import AppError
from app.db.models import RawTranscriptCue, Video
from app.services.transcript.normalizer import TranscriptNormalizer
from app.services.transcript.vtt import PersistedRawCueData


def _srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{whole_seconds:02},{millis:03}'


def export_raw_srt(session: Session, video_id: str) -> tuple[str, str]:
    video = session.get(Video, video_id)
    if video is None:
        raise AppError(404, 'VIDEO_NOT_FOUND', '找不到这个视频，请返回视频库。')
    if video.status != VideoStatus.READY:
        raise AppError(409, 'TRANSCRIPT_NOT_READY', '字幕尚未就绪，无法导出。')

    cues = session.scalars(
        select(RawTranscriptCue)
        .where(RawTranscriptCue.video_id == video_id)
        .order_by(RawTranscriptCue.sequence_index)
    ).all()
    valid_cues = [PersistedRawCueData(
        id=cue.id, sequence_index=cue.sequence_index,
        start_seconds=cue.start_seconds, end_seconds=cue.end_seconds,
        text=cue.text,
    ) for cue in cues if math.isfinite(cue.start_seconds)
        and math.isfinite(cue.end_seconds)
        and 0 <= cue.start_seconds <= cue.end_seconds]
    segments = TranscriptNormalizer().normalize(valid_cues)
    blocks: list[str] = []
    for segment in segments:
        start, end = segment.start_seconds, segment.end_seconds
        start_ms = round(start * 1000)
        end_ms = max(round(end * 1000), start_ms + 1)
        blocks.append(
            f'{len(blocks) + 1}\n{_srt_time(start)} --> {_srt_time(end_ms / 1000)}\n{segment.text}'
        )
    if not blocks:
        raise AppError(409, 'RAW_TRANSCRIPT_UNAVAILABLE', '这个视频没有可导出的原始字幕。')
    return '\n\n'.join(blocks) + '\n', video.youtube_video_id
