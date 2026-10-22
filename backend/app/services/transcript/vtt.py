from dataclasses import dataclass
from io import BytesIO
import math

import webvtt
from webvtt.errors import MalformedCaptionError, MalformedFileError
from sqlalchemy.orm import Session

from app.core.enums import SubtitleSource
from app.db.models import RawTranscriptCue


class VTTParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RawCueData:
    sequence_index: int
    start_seconds: float
    end_seconds: float
    text: str
    source_payload: dict


@dataclass(frozen=True, slots=True)
class PersistedRawCueData:
    id: str
    sequence_index: int
    start_seconds: float
    end_seconds: float
    text: str


def parse_vtt(content: bytes) -> list[RawCueData]:
    try:
        captions = webvtt.from_buffer(BytesIO(content))
        cues = [
            RawCueData(
                sequence_index=index,
                start_seconds=_timestamp_seconds(caption.start_time),
                end_seconds=_timestamp_seconds(caption.end_time),
                text=caption.raw_text,
                source_payload={
                    'identifier': caption.identifier or None,
                    'start': caption.start,
                    'end': caption.end,
                    'lines': list(caption.lines),
                },
            )
            for index, caption in enumerate(captions)
        ]
    except (UnicodeError, ValueError, TypeError, MalformedCaptionError, MalformedFileError) as exc:
        raise VTTParseError('Unable to parse WebVTT content') from exc
    if not cues:
        raise VTTParseError('WebVTT content contains no cues')
    if any(not math.isfinite(cue.start_seconds) or not math.isfinite(cue.end_seconds)
           or cue.start_seconds < 0 or cue.end_seconds < cue.start_seconds for cue in cues):
        raise VTTParseError('WebVTT content contains an invalid cue time range')
    return cues


def _timestamp_seconds(timestamp) -> float:
    hours, minutes, seconds, milliseconds = timestamp.to_tuple()
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def persist_raw_cues(session: Session, video_id: str, cues: list[RawCueData],
                     source_type: SubtitleSource) -> list[PersistedRawCueData]:
    rows = [RawTranscriptCue(
        video_id=video_id,
        sequence_index=cue.sequence_index,
        start_seconds=cue.start_seconds,
        end_seconds=cue.end_seconds,
        text=cue.text,
        source_type=source_type,
        source_payload=cue.source_payload,
    ) for cue in cues]
    session.add_all(rows)
    session.flush()
    return [PersistedRawCueData(
        id=row.id,
        sequence_index=row.sequence_index,
        start_seconds=row.start_seconds,
        end_seconds=row.end_seconds,
        text=row.text,
    ) for row in rows]
