from dataclasses import dataclass
from enum import Enum, auto
from html import unescape
import re

from app.services.transcript.vtt import PersistedRawCueData

NORMALIZATION_VERSION = 2
MAX_FRAGMENT_LENGTH = 120
MAX_SEGMENT_LENGTH = 160
MAX_FRAGMENT_GAP_SECONDS = 0.35
AUTO_ROLLING_CUE_MAX_SECONDS = 0.05
AUTO_ROLLING_GAP_SECONDS = 0.05

_VTT_TAG = re.compile(
    r'</?(?:c(?:\.[^>\s]+)*|i|b|u|ruby|rt|v|lang)(?:\s+[^>]*)?>'
    r'|<\d{2}:\d{2}(?::\d{2})?\.\d{3}>',
    re.IGNORECASE,
)
_END_PUNCTUATION = re.compile(r'[.!?…。！？]["\'”’）)\]]*$')


@dataclass(frozen=True, slots=True)
class LearningSegmentData:
    sequence_index: int
    start_seconds: float
    end_seconds: float
    text: str
    source_ref_type: str
    source_refs: dict[str, list[str]]
    normalization_version: int = NORMALIZATION_VERSION


@dataclass(slots=True)
class _Segment:
    start_seconds: float
    end_seconds: float
    text: str
    cue_ids: list[str]
    auto_rolling_source: '_SourceCue | None' = None


@dataclass(frozen=True, slots=True)
class _SourceCue:
    start_seconds: float
    end_seconds: float
    cue_id: str


class _AutoRollingResult(Enum):
    NOT_APPLICABLE = auto()
    MERGED = auto()
    START_NEW = auto()


class TranscriptNormalizer:
    """Conservative cue-level normalization for manual and automatic captions."""

    def normalize(self, cues: list[PersistedRawCueData]) -> list[LearningSegmentData]:
        segments: list[_Segment] = []
        for incoming in _prepare_segments(cues):
            auto_rolling_result = (
                _merge_auto_rolling(segments[-1], incoming)
                if segments else _AutoRollingResult.NOT_APPLICABLE)
            if auto_rolling_result is _AutoRollingResult.MERGED:
                continue
            if auto_rolling_result is _AutoRollingResult.START_NEW:
                segments.append(incoming)
            elif segments and _is_rolling_expansion(segments[-1], incoming):
                current = segments[-1]
                current.text = incoming.text
                current.end_seconds = max(current.end_seconds, incoming.end_seconds)
                current.cue_ids.extend(incoming.cue_ids)
            elif segments and _should_merge_fragments(segments[-1], incoming):
                current = segments[-1]
                current.text = f'{current.text} {incoming.text}'
                current.end_seconds = max(current.end_seconds, incoming.end_seconds)
                current.cue_ids.extend(incoming.cue_ids)
            else:
                segments.append(incoming)
        return [LearningSegmentData(
            sequence_index=index,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            text=segment.text,
            source_ref_type='cue',
            source_refs={'cue_ids': segment.cue_ids},
        ) for index, segment in enumerate(segments)]


def clean_vtt_text(text: str) -> str:
    return ' '.join(unescape(_VTT_TAG.sub('', text)).split())


def _prepare_segments(cues: list[PersistedRawCueData]) -> list[_Segment]:
    ordered = sorted(cues, key=lambda item: item.sequence_index)
    prepared = []
    index = 0
    while index < len(ordered):
        cue = ordered[index]
        text = clean_vtt_text(cue.text)
        if not text:
            index += 1
            continue
        if index + 1 < len(ordered):
            following = ordered[index + 1]
            following_text = clean_vtt_text(following.text)
            duration = cue.end_seconds - cue.start_seconds
            gap = following.start_seconds - cue.end_seconds
            if (following_text
                    and duration <= AUTO_ROLLING_CUE_MAX_SECONDS
                    and 0 <= gap <= AUTO_ROLLING_GAP_SECONDS
                    and following_text.casefold().startswith(f'{text.casefold()} ')):
                prepared.append(_Segment(
                    start_seconds=cue.start_seconds,
                    end_seconds=max(cue.end_seconds, following.end_seconds),
                    text=following_text,
                    cue_ids=[cue.id, following.id],
                    auto_rolling_source=_SourceCue(
                        following.start_seconds,
                        following.end_seconds,
                        following.id,
                    ),
                ))
                index += 2
                continue
        prepared.append(_Segment(
            start_seconds=cue.start_seconds,
            end_seconds=cue.end_seconds,
            text=text,
            cue_ids=[cue.id],
        ))
        index += 1
    return prepared


def _merge_auto_rolling(current: _Segment, incoming: _Segment) -> _AutoRollingResult:
    source = incoming.auto_rolling_source
    if current.auto_rolling_source is None or source is None:
        return _AutoRollingResult.NOT_APPLICABLE
    gap = incoming.start_seconds - current.end_seconds
    if not -AUTO_ROLLING_GAP_SECONDS <= gap <= AUTO_ROLLING_GAP_SECONDS:
        return _AutoRollingResult.NOT_APPLICABLE
    incoming_words = incoming.text.split()
    overlap = _suffix_prefix_word_overlap(current.text, incoming.text)
    if overlap == 0:
        return _AutoRollingResult.NOT_APPLICABLE
    novel_words = incoming_words[overlap:]
    if not novel_words:
        current.end_seconds = max(current.end_seconds, incoming.end_seconds)
        current.cue_ids.extend(incoming.cue_ids)
        return _AutoRollingResult.MERGED
    novel_text = ' '.join(novel_words)
    combined_length = len(current.text) + 1 + len(novel_text)
    if (_END_PUNCTUATION.search(current.text) is not None
            or combined_length > MAX_SEGMENT_LENGTH):
        incoming.start_seconds = source.start_seconds
        incoming.end_seconds = source.end_seconds
        incoming.text = novel_text
        incoming.cue_ids = [source.cue_id]
        return _AutoRollingResult.START_NEW
    current.text = f'{current.text} {novel_text}'
    current.end_seconds = max(current.end_seconds, incoming.end_seconds)
    current.cue_ids.extend(incoming.cue_ids)
    return _AutoRollingResult.MERGED


def _suffix_prefix_word_overlap(current_text: str, incoming_text: str) -> int:
    current_words = current_text.casefold().split()
    incoming_words = incoming_text.casefold().split()
    for size in range(min(len(current_words), len(incoming_words)), 0, -1):
        if current_words[-size:] == incoming_words[:size]:
            return size
    return 0


def _is_rolling_expansion(current: _Segment, incoming: _Segment) -> bool:
    current_text = current.text.casefold()
    incoming_text = incoming.text.casefold()
    return (incoming.start_seconds < current.end_seconds
            and incoming_text.startswith(f'{current_text} '))


def _should_merge_fragments(current: _Segment, incoming: _Segment) -> bool:
    gap = incoming.start_seconds - current.end_seconds
    combined_length = len(current.text) + 1 + len(incoming.text)
    return (0 <= gap <= MAX_FRAGMENT_GAP_SECONDS
            and len(current.text) <= MAX_FRAGMENT_LENGTH
            and combined_length <= MAX_SEGMENT_LENGTH
            and current.text.casefold() != incoming.text.casefold()
            and _END_PUNCTUATION.search(current.text) is None)
