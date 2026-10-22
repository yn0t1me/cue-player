import asyncio
import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import SubtitleSource
from app.db.models import RawTranscriptCue, RawTranscriptWord
from app.services.transcript.vtt import PersistedRawCueData


class TranscriptionValidationError(ValueError):
    pass


class STTTranscriptionError(RuntimeError):
    pass


class STTModelLoadError(STTTranscriptionError):
    pass


class EmptyTranscriptionError(TranscriptionValidationError):
    pass


@dataclass(frozen=True, slots=True)
class TranscriptionWordData:
    text: str
    start_seconds: float | None
    end_seconds: float | None
    confidence: float | None


@dataclass(frozen=True, slots=True)
class TranscriptionSegmentData:
    sequence_index: int
    start_seconds: float
    end_seconds: float
    text: str
    words: tuple[TranscriptionWordData, ...]
    source_payload: dict[str, int | float | list[int] | None]


@dataclass(frozen=True, slots=True)
class TranscriptionData:
    language: str
    language_probability: float | None
    duration_seconds: float
    duration_after_vad_seconds: float
    segments: tuple[TranscriptionSegmentData, ...]


@dataclass(frozen=True, slots=True)
class PersistedRawWordData:
    id: str
    cue_id: str
    sequence_index: int
    text: str
    start_seconds: float | None
    end_seconds: float | None
    confidence: float | None


@dataclass(frozen=True, slots=True)
class PersistedSTTTranscript:
    cues: tuple[PersistedRawCueData, ...]
    words: tuple[PersistedRawWordData, ...]


ModelFactory = Callable[..., Any]


def _finite_number(value: Any, label: str, *, optional: bool = False) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TranscriptionValidationError(f'{label} must be a number')
    value = float(value)
    if not math.isfinite(value):
        raise TranscriptionValidationError(f'{label} must be finite')
    return value


def _time(value: Any, label: str, *, optional: bool = False) -> float | None:
    value = _finite_number(value, label, optional=optional)
    if value is not None and value < 0:
        raise TranscriptionValidationError(f'{label} must not be negative')
    return value


def _probability(value: Any, label: str, *, optional: bool = False) -> float | None:
    value = _finite_number(value, label, optional=optional)
    if value is not None and not 0 <= value <= 1:
        raise TranscriptionValidationError(f'{label} must be between 0 and 1')
    return value


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TranscriptionValidationError(f'{label} must not be empty')
    return value


def _optional_finite_payload(value: Any) -> float | None:
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


def _segment_payload(segment: Any) -> dict[str, int | float | list[int] | None]:
    segment_id = getattr(segment, 'id', None)
    seek = getattr(segment, 'seek', None)
    tokens = getattr(segment, 'tokens', None)
    return {
        'segment_id': segment_id if isinstance(segment_id, int) and not isinstance(segment_id, bool) else None,
        'seek': seek if isinstance(seek, int) and not isinstance(seek, bool) else None,
        'tokens': ([token for token in tokens
                    if isinstance(token, int) and not isinstance(token, bool)]
                   if isinstance(tokens, Sequence) and not isinstance(tokens, (str, bytes)) else []),
        'avg_logprob': _optional_finite_payload(getattr(segment, 'avg_logprob', None)),
        'compression_ratio': _optional_finite_payload(
            getattr(segment, 'compression_ratio', None)),
        'no_speech_probability': _optional_finite_payload(
            getattr(segment, 'no_speech_prob', None)),
        'temperature': _optional_finite_payload(getattr(segment, 'temperature', None)),
    }


def map_transcription(segments: Iterable[Any], info: Any) -> TranscriptionData:
    language = _nonempty_text(getattr(info, 'language', None), 'transcription language')
    language_probability = _probability(
        getattr(info, 'language_probability', None),
        'language probability', optional=True)
    duration = _time(getattr(info, 'duration', None), 'audio duration')
    duration_after_vad = _time(
        getattr(info, 'duration_after_vad', None), 'duration after VAD')

    mapped_segments = []
    previous_segment_start = -math.inf
    previous_word_start = -math.inf
    for segment_index, segment in enumerate(segments):
        start = _time(getattr(segment, 'start', None), 'segment start')
        end = _time(getattr(segment, 'end', None), 'segment end')
        if start is None or end is None:  # Defensive narrowing for static checkers.
            raise TranscriptionValidationError('segment time is missing')
        if end < start:
            raise TranscriptionValidationError('segment end precedes its start')
        if start < previous_segment_start:
            raise TranscriptionValidationError('segments are not ordered by start time')
        previous_segment_start = start

        mapped_words = []
        source_words = getattr(segment, 'words', None) or ()
        for word in source_words:
            word_start = _time(getattr(word, 'start', None), 'word start', optional=True)
            word_end = _time(getattr(word, 'end', None), 'word end', optional=True)
            if word_start is not None and word_end is not None and word_end < word_start:
                raise TranscriptionValidationError('word end precedes its start')
            if word_start is not None:
                if word_start < previous_word_start:
                    raise TranscriptionValidationError('words are not ordered by start time')
                previous_word_start = word_start
            mapped_words.append(TranscriptionWordData(
                text=_nonempty_text(getattr(word, 'word', None), 'word text'),
                start_seconds=word_start,
                end_seconds=word_end,
                confidence=_probability(
                    getattr(word, 'probability', None), 'word confidence', optional=True),
            ))
        mapped_segments.append(TranscriptionSegmentData(
            sequence_index=segment_index,
            start_seconds=start,
            end_seconds=end,
            text=_nonempty_text(getattr(segment, 'text', None), 'segment text'),
            words=tuple(mapped_words),
            source_payload=_segment_payload(segment),
        ))
    if not mapped_segments:
        raise EmptyTranscriptionError('transcription contains no segments')
    return TranscriptionData(
        language=language,
        language_probability=language_probability,
        duration_seconds=duration,
        duration_after_vad_seconds=duration_after_vad,
        segments=tuple(mapped_segments),
    )


class FasterWhisperTranscriber:
    def __init__(self, settings: Settings, model_factory: ModelFactory | None = None):
        self.settings = settings
        self.model_factory = model_factory or WhisperModel
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            model_path = self.settings.stt_model_path
            if model_path is None:
                raise STTModelLoadError('STT model path is not configured')
            try:
                self._model = self.model_factory(
                    str(model_path),
                    device=self.settings.stt_device,
                    compute_type=self.settings.stt_compute_type,
                    local_files_only=True,
                )
            except Exception as error:
                raise STTModelLoadError('faster-whisper model could not be loaded') from error
        return self._model

    def _transcribe(self, audio_path: Path) -> TranscriptionData:
        try:
            model = self._load_model()
            segments, info = model.transcribe(
                str(audio_path),
                language='en',
                vad_filter=self.settings.stt_vad_filter,
                word_timestamps=True,
            )
            return map_transcription(segments, info)
        except TranscriptionValidationError:
            raise
        except STTModelLoadError:
            raise
        except Exception as error:
            raise STTTranscriptionError('faster-whisper could not transcribe the audio') from error

    async def transcribe(self, audio_path: Path) -> TranscriptionData:
        return await asyncio.to_thread(self._transcribe, audio_path)


def persist_stt_transcript(session: Session, video_id: str,
                           transcription: TranscriptionData) -> PersistedSTTTranscript:
    cue_rows = [RawTranscriptCue(
        video_id=video_id,
        sequence_index=segment.sequence_index,
        start_seconds=segment.start_seconds,
        end_seconds=segment.end_seconds,
        text=segment.text,
        source_type=SubtitleSource.STT,
        source_payload=segment.source_payload,
    ) for segment in transcription.segments]
    session.add_all(cue_rows)
    session.flush()

    word_rows = []
    for cue, segment in zip(cue_rows, transcription.segments, strict=True):
        for word in segment.words:
            word_rows.append(RawTranscriptWord(
                video_id=video_id,
                cue_id=cue.id,
                sequence_index=len(word_rows),
                text=word.text,
                start_seconds=word.start_seconds,
                end_seconds=word.end_seconds,
                confidence=word.confidence,
            ))
    session.add_all(word_rows)
    session.flush()

    cues = tuple(PersistedRawCueData(
        id=row.id,
        sequence_index=row.sequence_index,
        start_seconds=row.start_seconds,
        end_seconds=row.end_seconds,
        text=row.text,
    ) for row in cue_rows)
    words = tuple(PersistedRawWordData(
        id=row.id,
        cue_id=row.cue_id,
        sequence_index=row.sequence_index,
        text=row.text,
        start_seconds=row.start_seconds,
        end_seconds=row.end_seconds,
        confidence=row.confidence,
    ) for row in word_rows)
    return PersistedSTTTranscript(cues=cues, words=words)
