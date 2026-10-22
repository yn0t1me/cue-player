"""Validated Raw input and deterministic generation evidence."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Literal

from app.core.enums import SubtitleSource
from app.services.transcript.normalizer import (
    AUTO_ROLLING_CUE_MAX_SECONDS,
    AUTO_ROLLING_GAP_SECONDS,
    MAX_FRAGMENT_GAP_SECONDS,
    MAX_FRAGMENT_LENGTH,
    MAX_SEGMENT_LENGTH,
    clean_vtt_text,
)
from app.services.transcript.stt import PersistedRawWordData
from app.services.transcript.vtt import PersistedRawCueData


NORMALIZATION_VERSION = 2
END_PUNCTUATION = re.compile(r"[.!?…。！？][\"'”’）)\]]*$")


class NormalizationValidationError(ValueError):
    """Raised when Raw normalization evidence is invalid."""

    def __init__(self, message: str, *, code: str = "invalid_alignment") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class RawTranscriptEvidence:
    source: SubtitleSource
    language: str
    cues: tuple[PersistedRawCueData, ...]
    words: tuple[PersistedRawWordData, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizationInputUnit:
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class NormalizedSegmentData:
    sequence_index: int
    start_seconds: float
    end_seconds: float
    text: str
    source_ref_type: Literal["cue"]
    source_refs: tuple[str, ...]
    normalization_version: int = NORMALIZATION_VERSION


@dataclass(frozen=True, slots=True)
class _SourceUnit:
    temporary_id: str
    text: str


@dataclass(slots=True)
class _CaptionSpan:
    start_seconds: float
    end_seconds: float
    tokens: list[_SourceUnit]
    auto_rolling_source_start: float | None = None
    auto_rolling_source_end: float | None = None

    @property
    def text(self) -> str:
        return " ".join(token.text for token in self.tokens)

    @property
    def is_auto_rolling(self) -> bool:
        return self.auto_rolling_source_start is not None


@dataclass(frozen=True, slots=True)
class NormalizationPlan:
    """Validated source units preserving the recorded input-count semantics."""

    language: str
    units: tuple[NormalizationInputUnit, ...]


def prepare_normalization(evidence: RawTranscriptEvidence) -> NormalizationPlan:
    """Validate Raw evidence and build its auditable input units."""
    if not isinstance(evidence.source, SubtitleSource):
        raise NormalizationValidationError("Transcript source is invalid")
    language = evidence.language.strip()
    if not language:
        raise NormalizationValidationError("Transcript language must not be empty")
    cues = _validated_cues(evidence.cues)
    cues_by_id = {cue.id: cue for cue in cues}
    word_mode = evidence.source is SubtitleSource.STT and bool(evidence.words)
    if word_mode:
        source_units = _build_word_units(evidence.words, cues_by_id)
    else:
        source_units = _build_cue_token_units(cues)
    if not source_units:
        raise NormalizationValidationError("Transcript evidence contains no usable units")
    return NormalizationPlan(
        language=language,
        units=tuple(
            NormalizationInputUnit(unit.temporary_id, unit.text)
            for unit in source_units
        ),
    )


def _validated_cues(
    cues: tuple[PersistedRawCueData, ...],
) -> tuple[PersistedRawCueData, ...]:
    if not cues:
        raise NormalizationValidationError("Transcript evidence contains no cues")
    ordered = tuple(sorted(cues, key=lambda cue: cue.sequence_index))
    if len({cue.id for cue in ordered}) != len(ordered):
        raise NormalizationValidationError("Raw cue IDs must be unique")
    if len({cue.sequence_index for cue in ordered}) != len(ordered):
        raise NormalizationValidationError("Raw cue sequence indexes must be unique")
    for cue in ordered:
        if (
            not cue.id
            or cue.sequence_index < 0
            or not math.isfinite(cue.start_seconds)
            or not math.isfinite(cue.end_seconds)
            or cue.start_seconds < 0
            or cue.end_seconds < cue.start_seconds
        ):
            raise NormalizationValidationError("Raw cue evidence is invalid")
    return ordered


def _build_word_units(
    words: tuple[PersistedRawWordData, ...],
    cues_by_id: dict[str, PersistedRawCueData],
) -> tuple[_SourceUnit, ...]:
    ordered = tuple(sorted(words, key=lambda word: word.sequence_index))
    if len({word.id for word in ordered}) != len(ordered):
        raise NormalizationValidationError("Raw word IDs must be unique")
    if len({word.sequence_index for word in ordered}) != len(ordered):
        raise NormalizationValidationError("Raw word sequence indexes must be unique")
    units = []
    for index, word in enumerate(ordered, start=1):
        if not isinstance(word.text, str):
            raise NormalizationValidationError("Raw word evidence is invalid")
        text = " ".join(word.text.split())
        if not text or word.cue_id not in cues_by_id:
            raise NormalizationValidationError("Raw word evidence is invalid")
        _validate_optional_time(word.start_seconds, "Raw word start")
        _validate_optional_time(word.end_seconds, "Raw word end")
        if (
            word.start_seconds is not None
            and word.end_seconds is not None
            and word.end_seconds < word.start_seconds
        ):
            raise NormalizationValidationError("Raw word end precedes its start")
        units.append(_SourceUnit(
            temporary_id=_temporary_id(index),
            text=text,
        ))
    return tuple(units)


def _validate_optional_time(value: float | None, label: str) -> None:
    if value is not None and (not math.isfinite(value) or value < 0):
        raise NormalizationValidationError(f"{label} is invalid")


def _build_cue_token_units(
    cues: tuple[PersistedRawCueData, ...],
) -> tuple[_SourceUnit, ...]:
    prepared: list[_CaptionSpan] = []
    index = 0
    while index < len(cues):
        cue = cues[index]
        tokens = _cue_tokens(cue)
        if not tokens:
            index += 1
            continue
        if index + 1 < len(cues):
            following = cues[index + 1]
            following_tokens = _cue_tokens(following)
            duration = cue.end_seconds - cue.start_seconds
            gap = following.start_seconds - cue.end_seconds
            if (
                following_tokens
                and duration <= AUTO_ROLLING_CUE_MAX_SECONDS
                and 0 <= gap <= AUTO_ROLLING_GAP_SECONDS
                and _strict_prefix(tokens, following_tokens)
            ):
                prepared.append(_CaptionSpan(
                    start_seconds=cue.start_seconds,
                    end_seconds=max(cue.end_seconds, following.end_seconds),
                    tokens=[*tokens, *following_tokens[len(tokens):]],
                    auto_rolling_source_start=following.start_seconds,
                    auto_rolling_source_end=following.end_seconds,
                ))
                index += 2
                continue
        prepared.append(_CaptionSpan(cue.start_seconds, cue.end_seconds, tokens))
        index += 1

    spans: list[_CaptionSpan] = []
    for incoming in prepared:
        if spans and _merge_auto_rolling_tokens(spans, incoming):
            continue
        if spans and _is_rolling_expansion_tokens(spans[-1], incoming):
            current = spans[-1]
            current.tokens.extend(incoming.tokens[len(current.tokens):])
            current.end_seconds = max(current.end_seconds, incoming.end_seconds)
        elif spans and _should_merge_fragment_tokens(spans[-1], incoming):
            spans[-1].tokens.extend(incoming.tokens)
            spans[-1].end_seconds = max(spans[-1].end_seconds, incoming.end_seconds)
        else:
            spans.append(incoming)

    flattened = [token for span in spans for token in span.tokens]
    return tuple(
        _SourceUnit(_temporary_id(index), token.text)
        for index, token in enumerate(flattened, start=1)
    )


def _cue_tokens(cue: PersistedRawCueData) -> list[_SourceUnit]:
    if not isinstance(cue.text, str):
        raise NormalizationValidationError("Raw cue text is invalid")
    text = clean_vtt_text(cue.text)
    return [
        _SourceUnit("", token) for token in text.split()
    ]


def _strict_prefix(current: list[_SourceUnit], incoming: list[_SourceUnit]) -> bool:
    return (
        len(incoming) > len(current)
        and [_fold(unit.text) for unit in incoming[:len(current)]]
        == [_fold(unit.text) for unit in current]
    )


def _merge_auto_rolling_tokens(
    spans: list[_CaptionSpan], incoming: _CaptionSpan
) -> bool:
    current = spans[-1]
    if not current.is_auto_rolling or not incoming.is_auto_rolling:
        return False
    gap = incoming.start_seconds - current.end_seconds
    if not -AUTO_ROLLING_GAP_SECONDS <= gap <= AUTO_ROLLING_GAP_SECONDS:
        return False
    overlap = _suffix_prefix_overlap(current.tokens, incoming.tokens)
    if overlap == 0:
        return False
    novel = incoming.tokens[overlap:]
    if not novel:
        current.end_seconds = max(current.end_seconds, incoming.end_seconds)
        return True
    novel_text = " ".join(token.text for token in novel)
    if (
        END_PUNCTUATION.search(current.text)
        or len(current.text) + 1 + len(novel_text) > MAX_SEGMENT_LENGTH
    ):
        spans.append(_CaptionSpan(
            start_seconds=(
                incoming.auto_rolling_source_start
                if incoming.auto_rolling_source_start is not None
                else incoming.start_seconds
            ),
            end_seconds=(
                incoming.auto_rolling_source_end
                if incoming.auto_rolling_source_end is not None
                else incoming.end_seconds
            ),
            tokens=list(novel),
            auto_rolling_source_start=incoming.auto_rolling_source_start,
            auto_rolling_source_end=incoming.auto_rolling_source_end,
        ))
    else:
        current.tokens.extend(novel)
        current.end_seconds = max(current.end_seconds, incoming.end_seconds)
    return True


def _suffix_prefix_overlap(
    current: list[_SourceUnit], incoming: list[_SourceUnit]
) -> int:
    current_words = [_fold(unit.text) for unit in current]
    incoming_words = [_fold(unit.text) for unit in incoming]
    for size in range(min(len(current_words), len(incoming_words)), 0, -1):
        if current_words[-size:] == incoming_words[:size]:
            return size
    return 0


def _is_rolling_expansion_tokens(current: _CaptionSpan, incoming: _CaptionSpan) -> bool:
    return incoming.start_seconds < current.end_seconds and _strict_prefix(
        current.tokens, incoming.tokens
    )


def _should_merge_fragment_tokens(current: _CaptionSpan, incoming: _CaptionSpan) -> bool:
    gap = incoming.start_seconds - current.end_seconds
    return (
        0 <= gap <= MAX_FRAGMENT_GAP_SECONDS
        and len(current.text) <= MAX_FRAGMENT_LENGTH
        and len(current.text) + 1 + len(incoming.text) <= MAX_SEGMENT_LENGTH
        and _fold(current.text) != _fold(incoming.text)
        and END_PUNCTUATION.search(current.text) is None
    )


def _temporary_id(index: int) -> str:
    if index > 999999:
        raise NormalizationValidationError("Transcript exceeds temporary ID capacity")
    return f"u{index:06d}"


def _fold(text: str) -> str:
    return text.casefold()
