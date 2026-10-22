"""Local deterministic normalization and generation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.transcript.normalization_core import (
    NormalizedSegmentData,
    RawTranscriptEvidence,
    prepare_normalization,
)
from app.services.transcript.normalizer import TranscriptNormalizer


@dataclass(frozen=True, slots=True)
class NormalizationRunData:
    method: Literal['deterministic']
    normalization_version: int
    input_unit_count: int


@dataclass(frozen=True, slots=True)
class NormalizationOutcome:
    segments: tuple[NormalizedSegmentData, ...]
    run: NormalizationRunData


class TranscriptNormalizationService:
    """Generate initial reading subtitles locally, with immutable audit evidence."""

    def __init__(self) -> None:
        self.deterministic_normalizer = TranscriptNormalizer()

    async def normalize(self, evidence: RawTranscriptEvidence) -> NormalizationOutcome:
        plan = prepare_normalization(evidence)
        deterministic = self.deterministic_normalizer.normalize(list(evidence.cues))
        segments = tuple(NormalizedSegmentData(
            sequence_index=segment.sequence_index,
            start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds,
            text=segment.text,
            source_ref_type='cue',
            source_refs=tuple(segment.source_refs['cue_ids']),
            normalization_version=2,
        ) for segment in deterministic)
        return NormalizationOutcome(
            segments=segments,
            run=NormalizationRunData(
                method='deterministic',
                normalization_version=2,
                input_unit_count=len(plan.units),
            ),
        )
